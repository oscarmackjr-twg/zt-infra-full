import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from zt_langgraph import ControlPlaneClient, ControlPlaneError


AgentActorResolver = Callable[[Any], str]
AgentActionMapper = Callable[[str, dict[str, Any], Any], tuple[str, str]]


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


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
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


def default_agents_action_mapper(tool_name: str, arguments: dict[str, Any], data: Any) -> tuple[str, str]:
    namespace = _get(data, "context.tool_namespace", default="") or ""
    prefix = f"openai.agents.tool.{_safe_segment(namespace)}" if namespace else "openai.agents.tool"
    return f"{prefix}.{_safe_segment(tool_name)}", extract_resource(arguments)


def default_actor_resolver(data: Any) -> str:
    return (
        _get(data, "agent.name")
        or _get(data, "context.agent.name")
        or _get(data, "context.run_config.workflow_name")
        or "openai-agent"
    )


@dataclass
class LocalToolGuardrailFunctionOutput:
    output_info: Any
    behavior: dict[str, Any] = field(default_factory=lambda: {"type": "allow"})

    @classmethod
    def allow(cls, output_info: Any = None):
        return cls(output_info=output_info, behavior={"type": "allow"})

    @classmethod
    def reject_content(cls, message: str, output_info: Any = None):
        return cls(output_info=output_info, behavior={"type": "reject_content", "message": message})

    @classmethod
    def raise_exception(cls, output_info: Any = None):
        return cls(output_info=output_info, behavior={"type": "raise_exception"})


@dataclass
class LocalToolInputGuardrail:
    guardrail_function: Callable[[Any], Any]
    name: str

    def get_name(self) -> str:
        return self.name

    async def run(self, data: Any) -> Any:
        result = self.guardrail_function(data)
        if hasattr(result, "__await__"):
            return await result
        return result


@dataclass
class AgentsSDKGuardrailPlugin:
    """OpenAI Agents SDK tool-guardrail adapter for the zt-infra-v2 control plane."""

    control_plane: Any = field(default_factory=ControlPlaneClient)
    actor: str | None = None
    actor_resolver: AgentActorResolver = default_actor_resolver
    action_mapper: AgentActionMapper = default_agents_action_mapper
    deny_behavior: str = "reject_content"
    guardrail_name: str = "zt_policy_tool_guardrail"

    def create_tool_input_guardrail(self) -> Any:
        async def guardrail(data: Any) -> Any:
            return self.evaluate_tool_input(data)

        sdk = self._load_agents_sdk()
        if sdk:
            return sdk["tool_input_guardrail"](name=self.guardrail_name)(guardrail)
        return LocalToolInputGuardrail(guardrail_function=guardrail, name=self.guardrail_name)

    def function_tool_options(self) -> dict[str, list[Any]]:
        return {"tool_input_guardrails": [self.create_tool_input_guardrail()]}

    def evaluate_tool_input(self, data: Any) -> Any:
        tool_name = _get(data, "context.tool_name", default="")
        raw_arguments = _get(data, "context.tool_arguments", default="{}")

        if not tool_name:
            return self._deny(
                self._local_decision("openai.agents.tool.unknown", "", "tool name is required"),
                "tool name is required",
            )

        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError:
            action = f"openai.agents.tool.{_safe_segment(tool_name)}"
            return self._deny(
                self._local_decision(action, "", "tool arguments are not valid JSON"),
                "tool arguments are not valid JSON",
            )
        if not isinstance(arguments, dict):
            action = f"openai.agents.tool.{_safe_segment(tool_name)}"
            return self._deny(
                self._local_decision(action, "", "tool arguments must decode to a JSON object"),
                "tool arguments must decode to a JSON object",
            )

        action, resource = self.action_mapper(tool_name, arguments, data)
        actor = self.actor or self.actor_resolver(data)
        try:
            decision = self.control_plane.decide(actor, action, resource=resource)
        except ControlPlaneError as error:
            decision = self._local_decision(action, resource, f"control plane unavailable: {error}", actor=actor)

        if decision["decision"] == "allow":
            return self._allow(decision)
        return self._deny(decision, decision["reason"])

    def _allow(self, decision: dict[str, Any]) -> Any:
        output = self._output_class()
        return output.allow(output_info={"zero_trust": decision})

    def _deny(self, decision: dict[str, Any], message: str) -> Any:
        output = self._output_class()
        output_info = {"zero_trust": decision}
        if self.deny_behavior == "raise_exception":
            return output.raise_exception(output_info=output_info)
        return output.reject_content(message, output_info=output_info)

    def _local_decision(self, action: str, resource: str, reason: str, actor: str | None = None) -> dict[str, Any]:
        return {
            "ok": False,
            "actor": actor or self.actor or "openai-agent",
            "action": action,
            "resource": resource,
            "decision": "deny",
            "reason": reason,
            "audit": {"local_guardrail_only": True},
        }

    @staticmethod
    def _load_agents_sdk() -> dict[str, Any] | None:
        try:
            from agents import ToolGuardrailFunctionOutput, tool_input_guardrail
        except ImportError:
            return None
        return {
            "ToolGuardrailFunctionOutput": ToolGuardrailFunctionOutput,
            "tool_input_guardrail": tool_input_guardrail,
        }

    def _output_class(self) -> Any:
        sdk = self._load_agents_sdk()
        if sdk:
            return sdk["ToolGuardrailFunctionOutput"]
        return LocalToolGuardrailFunctionOutput
