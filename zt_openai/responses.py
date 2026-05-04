import json
from dataclasses import dataclass, field
from typing import Any, Callable

from zt_langgraph import ControlPlaneClient
from zt_langgraph.types import ActionDecision

from zt_openai.assistants import ToolRegistry


ResponseActionMapper = Callable[[str, dict[str, Any], Any], str]


def default_response_action_mapper(function_name: str, _arguments: dict[str, Any], _function_call: Any) -> str:
    return f"openai.responses.function.{function_name}"


@dataclass
class ZeroTrustResponsesWrapper:
    """Policy-gated adapter for OpenAI Responses API function calls."""

    openai_client: Any
    control_plane: Any = field(default_factory=ControlPlaneClient)
    actor: str = "openai-response-agent"
    tools: ToolRegistry = field(default_factory=ToolRegistry)
    action_mapper: ResponseActionMapper = default_response_action_mapper

    def collect_function_call_outputs(self, response: Any) -> list[dict[str, Any]]:
        outputs: list[dict[str, Any]] = []
        for item in self._get(response, "output", default=[]):
            if self._get(item, "type") == "function_call":
                outputs.append(self._handle_function_call(item))
        return outputs

    def build_follow_up_input(self, response: Any) -> list[Any]:
        response_output = list(self._get(response, "output", default=[]))
        return [*response_output, *self.collect_function_call_outputs(response)]

    def continue_response(self, response: Any, *, model: str | None = None, **kwargs: Any) -> Any:
        selected_model = model or self._get(response, "model")
        if not selected_model:
            raise ValueError("model is required to continue a Responses API function-call turn")
        return self.openai_client.responses.create(
            model=selected_model,
            input=self.build_follow_up_input(response),
            **kwargs,
        )

    def _handle_function_call(self, function_call: Any) -> dict[str, Any]:
        call_id = self._get(function_call, "call_id")
        function_name = self._get(function_call, "name")
        raw_arguments = self._get(function_call, "arguments", default="{}")

        if not call_id:
            raise ValueError("function call_id is required")
        if not function_name:
            return self._function_call_output(
                call_id,
                self._deny_without_execution(
                    "function name is required",
                    action="openai.responses.function.unknown",
                ),
            )

        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError:
            return self._function_call_output(
                call_id,
                self._deny_without_execution(
                    "function arguments are not valid JSON",
                    action=f"openai.responses.function.{function_name}",
                ),
            )
        if not isinstance(arguments, dict):
            return self._function_call_output(
                call_id,
                self._deny_without_execution(
                    "function arguments must decode to a JSON object",
                    action=f"openai.responses.function.{function_name}",
                ),
            )

        action = self.action_mapper(function_name, arguments, function_call)
        decision: ActionDecision = self.control_plane.decide(self.actor, action)
        if decision["decision"] != "allow":
            return self._function_call_output(call_id, {"ok": False, "zero_trust": decision, "result": None})

        try:
            result = self.tools.execute(function_name, arguments)
        except KeyError as error:
            return self._function_call_output(
                call_id,
                {
                    "ok": False,
                    "zero_trust": self._local_deny(str(error), action),
                    "result": None,
                },
            )
        return self._function_call_output(call_id, {"ok": True, "zero_trust": decision, "result": result})

    def _deny_without_execution(self, reason: str, *, action: str) -> dict[str, Any]:
        return {"ok": False, "zero_trust": self._local_deny(reason, action), "result": None}

    def _local_deny(self, reason: str, action: str) -> dict[str, Any]:
        return {
            "ok": False,
            "actor": self.actor,
            "action": action,
            "decision": "deny",
            "reason": reason,
            "audit": {"local_wrapper_only": True},
        }

    @staticmethod
    def _function_call_output(call_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "function_call_output",
            "call_id": call_id,
            "output": json.dumps(payload, sort_keys=True),
        }

    @staticmethod
    def _get(value: Any, path: str, default: Any = None) -> Any:
        current = value
        for part in path.split("."):
            if isinstance(current, dict):
                current = current.get(part, default)
            else:
                current = getattr(current, part, default)
            if current is default:
                return default
        return current
