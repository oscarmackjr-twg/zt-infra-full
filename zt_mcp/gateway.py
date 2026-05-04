import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from zt_langgraph import ControlPlaneClient, ControlPlaneError


DownstreamTransport = Callable[[dict[str, Any]], dict[str, Any] | None]
MCPActionMapper = Callable[[str, str, dict[str, Any]], tuple[str, str]]


class MCPGatewayError(RuntimeError):
    """Raised when the MCP gateway cannot safely process a message."""


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned.strip("._-") or "unknown"


def extract_resource(arguments: dict[str, Any]) -> str:
    owner = arguments.get("owner") or arguments.get("org") or arguments.get("organization")
    repo = arguments.get("repo") or arguments.get("repository")
    if owner and repo:
        return f"{owner}/{repo}"
    for key in ("resource", "repository", "repo", "path", "url", "name", "id"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def default_mcp_action_mapper(server_name: str, tool_name: str, arguments: dict[str, Any]) -> tuple[str, str]:
    action = f"mcp.{_safe_segment(server_name)}.{_safe_segment(tool_name)}"
    return action, extract_resource(arguments)


@dataclass
class MCPZeroTrustGateway:
    """Policy-enforcing JSON-RPC gateway for MCP `tools/call` requests."""

    downstream: DownstreamTransport
    control_plane: Any = field(default_factory=ControlPlaneClient)
    actor: str = "mcp-agent"
    server_name: str = "unknown-server"
    action_mapper: MCPActionMapper = default_mcp_action_mapper

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        self._validate_jsonrpc_message(message)

        if message.get("method") != "tools/call":
            return self.downstream(message)

        request_id = message.get("id")
        if request_id is None:
            return None

        params = message.get("params")
        if not isinstance(params, dict):
            return self._error(request_id, -32602, "tools/call params must be an object")

        tool_name = params.get("name")
        if not isinstance(tool_name, str) or not tool_name.strip():
            return self._error(request_id, -32602, "tools/call params.name is required")

        arguments = params.get("arguments", {})
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return self._error(request_id, -32602, "tools/call params.arguments must be an object")

        action, resource = self.action_mapper(self.server_name, tool_name, arguments)
        if not action:
            return self._error(request_id, -32602, "MCP action mapper returned an empty action")

        try:
            decision = self.control_plane.decide(self.actor, action, resource=resource)
        except ControlPlaneError as error:
            decision = self._local_deny(action, resource, f"control plane unavailable: {error}")

        if decision["decision"] != "allow":
            return self._denied_tool_result(request_id, decision)

        return self.downstream(message)

    def _validate_jsonrpc_message(self, message: dict[str, Any]) -> None:
        if not isinstance(message, dict):
            raise MCPGatewayError("MCP message must be a JSON object")
        if message.get("jsonrpc") != "2.0":
            raise MCPGatewayError("MCP message must use jsonrpc 2.0")
        if "method" in message and not isinstance(message.get("method"), str):
            raise MCPGatewayError("MCP method must be a string")

    def _local_deny(self, action: str, resource: str, reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "actor": self.actor,
            "action": action,
            "resource": resource,
            "decision": "deny",
            "reason": reason,
            "audit": {"local_gateway_only": True},
        }

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    @staticmethod
    def _denied_tool_result(request_id: Any, decision: dict[str, Any]) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(decision, sort_keys=True),
                    }
                ],
                "structuredContent": decision,
                "isError": True,
            },
        }
