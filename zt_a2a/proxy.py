import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from zt_langgraph import ControlPlaneClient, ControlPlaneError


DownstreamTransport = Callable[[dict[str, Any]], dict[str, Any] | list[dict[str, Any]] | None]
A2AActionMapper = Callable[[str, dict[str, Any], str], tuple[str, str]]


class A2AProxyError(RuntimeError):
    """Raised when the A2A proxy cannot safely process a protocol message."""


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
    return cleaned.strip("._-") or "unknown"


def _snake_method(method: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", method).lower()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def extract_message_text(message: dict[str, Any]) -> str:
    text_parts: list[str] = []
    for part in message.get("parts", []) or []:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            text_parts.append(part["text"])
    return "\n".join(text_parts)


def extract_resource(params: dict[str, Any]) -> str:
    message = params.get("message") if isinstance(params.get("message"), dict) else {}
    metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    for key in ("resource", "target", "taskId", "contextId"):
        value = metadata.get(key) or message.get(key) or params.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return extract_message_text(message)[:120]


def default_a2a_action_mapper(remote_agent: str, params: dict[str, Any], method: str) -> tuple[str, str]:
    return f"a2a.{_safe_segment(remote_agent)}.{_snake_method(method)}", extract_resource(params)


@dataclass
class A2APolicyProxy:
    """Policy-enforcing proxy for A2A JSON-RPC requests."""

    downstream: DownstreamTransport
    control_plane: Any = field(default_factory=ControlPlaneClient)
    actor: str | None = None
    remote_agent: str = "remote-agent"
    action_mapper: A2AActionMapper = default_a2a_action_mapper
    protected_methods: frozenset[str] = frozenset({"SendMessage", "SendStreamingMessage", "CancelTask"})
    denial_state: str = "TASK_STATE_REJECTED"

    def handle_jsonrpc(self, request: dict[str, Any]) -> dict[str, Any] | list[dict[str, Any]] | None:
        self._validate_jsonrpc_request(request)
        method = request["method"]

        if method not in self.protected_methods:
            return self.downstream(request)

        request_id = request.get("id")
        params = request.get("params")
        if not isinstance(params, dict):
            return self._error(request_id, -32602, "Invalid parameters")

        action, resource = self.action_mapper(self.remote_agent, params, method)
        actor = self.actor or self._actor_from_params(params)
        try:
            decision = self.control_plane.decide(actor, action, resource=resource)
        except ControlPlaneError as error:
            decision = self._local_deny(actor, action, resource, f"control plane unavailable: {error}")

        if decision["decision"] != "allow":
            return self._denied_response(request_id, params, decision, streaming=method == "SendStreamingMessage")

        return self.downstream(request)

    def _validate_jsonrpc_request(self, request: dict[str, Any]) -> None:
        if not isinstance(request, dict):
            raise A2AProxyError("A2A JSON-RPC request must be an object")
        if request.get("jsonrpc") != "2.0":
            raise A2AProxyError("A2A JSON-RPC request must use jsonrpc 2.0")
        if not isinstance(request.get("method"), str):
            raise A2AProxyError("A2A JSON-RPC request method must be a string")
        if request.get("id") is None:
            raise A2AProxyError("A2A JSON-RPC request id is required")

    def _actor_from_params(self, params: dict[str, Any]) -> str:
        message = params.get("message") if isinstance(params.get("message"), dict) else {}
        metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        for key in ("actor", "client", "agent"):
            value = metadata.get(key) or params.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "a2a-client"

    def _local_deny(self, actor: str, action: str, resource: str, reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "actor": actor,
            "action": action,
            "resource": resource,
            "decision": "deny",
            "reason": reason,
            "audit": {"local_proxy_only": True},
        }

    def _denied_response(
        self,
        request_id: Any,
        params: dict[str, Any],
        decision: dict[str, Any],
        *,
        streaming: bool,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        task = self._denied_task(params, decision)
        response = {"jsonrpc": "2.0", "id": request_id, "result": {"task": task}}
        if streaming:
            return [response]
        return response

    def _denied_task(self, params: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
        message = params.get("message") if isinstance(params.get("message"), dict) else {}
        metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        task_id = message.get("taskId") or params.get("taskId") or f"zt-denied-{uuid.uuid4()}"
        context_id = message.get("contextId") or params.get("contextId")

        task: dict[str, Any] = {
            "id": task_id,
            "status": {
                "state": self.denial_state,
                "timestamp": _now(),
                "message": {
                    "role": "ROLE_AGENT",
                    "parts": [{"text": f"Denied by zero-trust policy: {decision['reason']}"}],
                    "messageId": f"zt-policy-{uuid.uuid4()}",
                    "metadata": {"zero_trust": decision},
                },
            },
            "metadata": {
                **({"originalMessageId": message.get("messageId")} if message.get("messageId") else {}),
                **({"resource": decision.get("resource")} if decision.get("resource") else {}),
                "zero_trust": decision,
            },
        }
        if context_id:
            task["contextId"] = context_id
        if metadata:
            task["history"] = [message]
        return task

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
