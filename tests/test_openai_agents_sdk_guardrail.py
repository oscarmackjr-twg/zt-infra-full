import asyncio
from dataclasses import dataclass

from zt_langgraph import ControlPlaneError
from zt_openai import AgentsSDKGuardrailPlugin, default_agents_action_mapper


def decision_payload(decision="deny", action="openai.agents.tool.github.create_pull_request", resource="octo/repo"):
    return {
        "ok": decision == "allow",
        "actor": "demo-agent",
        "action": action,
        "resource": resource,
        "decision": decision,
        "reason": "policy decision",
        "audit": {
            "timestamp": "2026-04-30T00:00:00Z",
            "previous_hash": "0" * 64,
            "current_hash": "a" * 64,
            "kms_signature": {"algorithm": "ECDSA_SHA_256", "key_id": "test", "signature": "sig"},
        },
    }


@dataclass
class FakeAgent:
    name: str = "demo-agent"


@dataclass
class FakeContext:
    tool_name: str = "create_pull_request"
    tool_arguments: str = '{"owner":"octo","repo":"repo","title":"demo"}'
    tool_namespace: str = "github"


@dataclass
class FakeData:
    context: FakeContext
    agent: FakeAgent


class FakeControlPlane:
    def __init__(self, decision="deny", fail=False):
        self.decision = decision
        self.fail = fail
        self.requests = []

    def decide(self, actor, action, resource=None):
        self.requests.append({"actor": actor, "action": action, "resource": resource})
        if self.fail:
            raise ControlPlaneError("offline")
        return decision_payload(self.decision, action, resource or "")


def test_default_agents_action_mapper_uses_namespace_and_resource():
    action, resource = default_agents_action_mapper(
        "create_pull_request",
        {"owner": "octo", "repo": "repo"},
        FakeData(context=FakeContext(), agent=FakeAgent()),
    )

    assert action == "openai.agents.tool.github.create_pull_request"
    assert resource == "octo/repo"


def test_denied_tool_input_rejects_content_before_execution():
    control_plane = FakeControlPlane("deny")
    plugin = AgentsSDKGuardrailPlugin(control_plane=control_plane)

    output = plugin.evaluate_tool_input(FakeData(context=FakeContext(), agent=FakeAgent()))

    assert output.behavior == {"type": "reject_content", "message": "policy decision"}
    assert output.output_info["zero_trust"]["decision"] == "deny"
    assert output.output_info["zero_trust"]["audit"]["kms_signature"]["algorithm"] == "ECDSA_SHA_256"
    assert control_plane.requests == [
        {
            "actor": "demo-agent",
            "action": "openai.agents.tool.github.create_pull_request",
            "resource": "octo/repo",
        }
    ]


def test_allowed_tool_input_returns_allow_behavior():
    plugin = AgentsSDKGuardrailPlugin(control_plane=FakeControlPlane("allow"))

    output = plugin.evaluate_tool_input(FakeData(context=FakeContext(), agent=FakeAgent()))

    assert output.behavior == {"type": "allow"}
    assert output.output_info["zero_trust"]["decision"] == "allow"


def test_control_plane_failure_fails_closed():
    plugin = AgentsSDKGuardrailPlugin(control_plane=FakeControlPlane(fail=True), actor="fixed-agent")

    output = plugin.evaluate_tool_input(FakeData(context=FakeContext(), agent=FakeAgent()))

    assert output.behavior["type"] == "reject_content"
    assert output.output_info["zero_trust"]["actor"] == "fixed-agent"
    assert output.output_info["zero_trust"]["audit"] == {"local_guardrail_only": True}
    assert "control plane unavailable" in output.output_info["zero_trust"]["reason"]


def test_raise_exception_behavior_is_configurable_for_denies():
    plugin = AgentsSDKGuardrailPlugin(control_plane=FakeControlPlane("deny"), deny_behavior="raise_exception")

    output = plugin.evaluate_tool_input(FakeData(context=FakeContext(), agent=FakeAgent()))

    assert output.behavior == {"type": "raise_exception"}
    assert output.output_info["zero_trust"]["decision"] == "deny"


def test_malformed_tool_arguments_fail_closed_without_control_plane_call():
    control_plane = FakeControlPlane("allow")
    plugin = AgentsSDKGuardrailPlugin(control_plane=control_plane)
    data = FakeData(context=FakeContext(tool_arguments="{bad-json"), agent=FakeAgent())

    output = plugin.evaluate_tool_input(data)

    assert control_plane.requests == []
    assert output.behavior["type"] == "reject_content"
    assert output.output_info["zero_trust"]["decision"] == "deny"
    assert output.output_info["zero_trust"]["audit"] == {"local_guardrail_only": True}


def test_create_tool_input_guardrail_returns_runnable_guardrail_without_agents_sdk_dependency():
    plugin = AgentsSDKGuardrailPlugin(control_plane=FakeControlPlane("allow"))

    guardrail = plugin.create_tool_input_guardrail()
    output = asyncio.run(guardrail.run(FakeData(context=FakeContext(), agent=FakeAgent())))

    assert guardrail.get_name() == "zt_policy_tool_guardrail"
    assert output.behavior == {"type": "allow"}
    assert plugin.function_tool_options()["tool_input_guardrails"][0].get_name() == "zt_policy_tool_guardrail"
