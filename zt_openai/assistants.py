import json
from dataclasses import dataclass, field
from typing import Any, Callable

from zt_langgraph import ControlPlaneClient
from zt_langgraph.types import ActionDecision

from zt_openai.types import ToolHandler, ToolOutput


ActionMapper = Callable[[str, dict[str, Any], Any], str]


def default_action_mapper(function_name: str, _arguments: dict[str, Any], _tool_call: Any) -> str:
    return f"openai.assistants.function.{function_name}"


class ToolRegistry:
    """Local function registry for Assistant tool calls."""

    def __init__(self) -> None:
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, name: str, handler: ToolHandler | None = None):
        if not name:
            raise ValueError("tool name is required")

        def decorator(fn: ToolHandler) -> ToolHandler:
            self._handlers[name] = fn
            return fn

        if handler is None:
            return decorator
        return decorator(handler)

    def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        handler = self._handlers.get(name)
        if handler is None:
            raise KeyError(f"tool is not registered: {name}")
        return handler(arguments)


@dataclass
class ZeroTrustAssistantsWrapper:
    """Policy-gated adapter for OpenAI Assistants API function tool calls.

    The wrapper only executes registered local tools after the zt-infra-v2
    control plane returns an allow decision for the mapped action.
    """

    openai_client: Any
    control_plane: Any = field(default_factory=ControlPlaneClient)
    actor: str = "openai-assistant"
    tools: ToolRegistry = field(default_factory=ToolRegistry)
    action_mapper: ActionMapper = default_action_mapper

    def collect_tool_outputs(self, run: Any) -> list[ToolOutput]:
        if self._get(run, "status") != "requires_action":
            raise ValueError("run does not require action")
        if self._get(run, "required_action.type") != "submit_tool_outputs":
            raise ValueError("run required_action is not submit_tool_outputs")

        outputs: list[ToolOutput] = []
        for tool_call in self._get(run, "required_action.submit_tool_outputs.tool_calls", default=[]):
            outputs.append(self._handle_tool_call(tool_call))
        return outputs

    def submit_tool_outputs(self, thread_id: str, run: Any, *, stream: bool = False) -> Any:
        run_id = self._get(run, "id")
        if not run_id:
            raise ValueError("run id is required")

        return self.openai_client.beta.threads.runs.submit_tool_outputs(
            thread_id=thread_id,
            run_id=run_id,
            tool_outputs=self.collect_tool_outputs(run),
            stream=stream,
        )

    def _handle_tool_call(self, tool_call: Any) -> ToolOutput:
        tool_call_id = self._get(tool_call, "id")
        function_name = self._get(tool_call, "function.name")
        raw_arguments = self._get(tool_call, "function.arguments", default="{}")

        if self._get(tool_call, "type") != "function":
            return self._tool_output(
                tool_call_id,
                self._deny_without_execution("unsupported tool call type", action="openai.assistants.tool.unsupported"),
            )
        if not function_name:
            return self._tool_output(
                tool_call_id,
                self._deny_without_execution(
                    "function name is required",
                    action="openai.assistants.function.unknown",
                ),
            )

        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError:
            return self._tool_output(
                tool_call_id,
                self._deny_without_execution(
                    "function arguments are not valid JSON",
                    action=f"openai.assistants.function.{function_name or 'unknown'}",
                ),
            )
        if not isinstance(arguments, dict):
            return self._tool_output(
                tool_call_id,
                self._deny_without_execution(
                    "function arguments must decode to a JSON object",
                    action=f"openai.assistants.function.{function_name or 'unknown'}",
                ),
            )

        action = self.action_mapper(function_name, arguments, tool_call)
        decision: ActionDecision = self.control_plane.decide(self.actor, action)
        if decision["decision"] != "allow":
            return self._tool_output(tool_call_id, {"ok": False, "zero_trust": decision, "result": None})

        try:
            result = self.tools.execute(function_name, arguments)
        except KeyError as error:
            return self._tool_output(
                tool_call_id,
                {
                    "ok": False,
                    "zero_trust": self._local_deny(str(error), action),
                    "result": None,
                },
            )
        return self._tool_output(tool_call_id, {"ok": True, "zero_trust": decision, "result": result})

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
    def _tool_output(tool_call_id: str, payload: dict[str, Any]) -> ToolOutput:
        if not tool_call_id:
            raise ValueError("tool call id is required")
        return {"tool_call_id": tool_call_id, "output": json.dumps(payload, sort_keys=True)}

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
