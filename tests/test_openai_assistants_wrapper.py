import json

import pytest

from zt_openai import ToolRegistry, ZeroTrustAssistantsWrapper, default_action_mapper


def decision_payload(decision="deny", action="openai.assistants.function.delete_instance"):
    return {
        "ok": decision == "allow",
        "actor": "demo-agent",
        "action": action,
        "decision": decision,
        "reason": "policy decision",
        "audit": {
            "timestamp": "2026-04-30T00:00:00Z",
            "previous_hash": "0" * 64,
            "current_hash": "a" * 64,
            "kms_signature": {"algorithm": "ECDSA_SHA_256", "key_id": "test", "signature": "sig"},
        },
    }


def assistant_run(function_name="delete_instance", arguments=None):
    return {
        "id": "run_123",
        "status": "requires_action",
        "required_action": {
            "type": "submit_tool_outputs",
            "submit_tool_outputs": {
                "tool_calls": [
                    {
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": function_name,
                            "arguments": json.dumps(arguments or {"instance_id": "i-danger"}),
                        },
                    }
                ]
            },
        },
    }


class FakeControlPlane:
    def __init__(self, decision="deny"):
        self.decision = decision
        self.requests = []

    def decide(self, actor, action):
        self.requests.append({"actor": actor, "action": action})
        return decision_payload(self.decision, action)


class FakeOpenAIClient:
    def __init__(self):
        self.submitted = None
        self.beta = self
        self.threads = self
        self.runs = self

    def submit_tool_outputs(self, **kwargs):
        self.submitted = kwargs
        return {"status": "queued", **kwargs}


def decode_output(outputs):
    return json.loads(outputs[0]["output"])


def test_default_action_mapper_namespaces_assistant_functions():
    assert default_action_mapper("delete_instance", {}, {}) == "openai.assistants.function.delete_instance"


def test_denied_tool_call_is_not_executed():
    registry = ToolRegistry()
    called = False

    def delete_instance(_arguments):
        nonlocal called
        called = True
        return {"terminated": True}

    registry.register("delete_instance", delete_instance)
    wrapper = ZeroTrustAssistantsWrapper(
        openai_client=FakeOpenAIClient(),
        control_plane=FakeControlPlane("deny"),
        actor="demo-agent",
        tools=registry,
    )

    outputs = wrapper.collect_tool_outputs(assistant_run())

    body = decode_output(outputs)
    assert called is False
    assert body["ok"] is False
    assert body["zero_trust"]["decision"] == "deny"
    assert body["zero_trust"]["audit"]["kms_signature"]["algorithm"] == "ECDSA_SHA_256"


def test_allowed_tool_call_executes_registered_handler():
    registry = ToolRegistry()
    registry.register("lookup_instance", lambda arguments: {"id": arguments["instance_id"], "state": "running"})
    wrapper = ZeroTrustAssistantsWrapper(
        openai_client=FakeOpenAIClient(),
        control_plane=FakeControlPlane("allow"),
        actor="demo-agent",
        tools=registry,
    )

    outputs = wrapper.collect_tool_outputs(assistant_run("lookup_instance"))

    body = decode_output(outputs)
    assert body["ok"] is True
    assert body["result"] == {"id": "i-danger", "state": "running"}
    assert body["zero_trust"]["decision"] == "allow"


def test_unregistered_tool_fails_closed_after_policy_allow():
    wrapper = ZeroTrustAssistantsWrapper(
        openai_client=FakeOpenAIClient(),
        control_plane=FakeControlPlane("allow"),
        actor="demo-agent",
    )

    outputs = wrapper.collect_tool_outputs(assistant_run("unknown_tool"))

    body = decode_output(outputs)
    assert body["ok"] is False
    assert body["zero_trust"]["decision"] == "deny"
    assert "not registered" in body["zero_trust"]["reason"]


def test_missing_function_name_fails_closed_before_policy_request():
    control_plane = FakeControlPlane("allow")
    run = assistant_run()
    del run["required_action"]["submit_tool_outputs"]["tool_calls"][0]["function"]["name"]
    wrapper = ZeroTrustAssistantsWrapper(
        openai_client=FakeOpenAIClient(),
        control_plane=control_plane,
        actor="demo-agent",
    )

    outputs = wrapper.collect_tool_outputs(run)

    body = decode_output(outputs)
    assert control_plane.requests == []
    assert body["zero_trust"]["decision"] == "deny"
    assert body["zero_trust"]["reason"] == "function name is required"


def test_submit_tool_outputs_calls_assistants_runs_endpoint_shape():
    client = FakeOpenAIClient()
    registry = ToolRegistry()
    registry.register("lookup_instance", lambda _arguments: {"state": "running"})
    wrapper = ZeroTrustAssistantsWrapper(
        openai_client=client,
        control_plane=FakeControlPlane("allow"),
        actor="demo-agent",
        tools=registry,
    )

    result = wrapper.submit_tool_outputs("thread_123", assistant_run("lookup_instance"))

    assert result["status"] == "queued"
    assert client.submitted["thread_id"] == "thread_123"
    assert client.submitted["run_id"] == "run_123"
    assert client.submitted["stream"] is False
    assert decode_output(client.submitted["tool_outputs"])["ok"] is True


def test_wrapper_rejects_run_without_required_action():
    wrapper = ZeroTrustAssistantsWrapper(openai_client=FakeOpenAIClient(), control_plane=FakeControlPlane())

    with pytest.raises(ValueError, match="does not require action"):
        wrapper.collect_tool_outputs({"id": "run_123", "status": "completed"})
