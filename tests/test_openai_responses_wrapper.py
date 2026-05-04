import json

import pytest

from zt_openai import ToolRegistry, ZeroTrustResponsesWrapper, default_response_action_mapper


def decision_payload(decision="deny", action="openai.responses.function.delete_instance"):
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


def responses_function_call(name="delete_instance", arguments=None):
    return {
        "id": "resp_123",
        "model": "gpt-5",
        "output": [
            {"id": "rs_123", "type": "reasoning", "summary": []},
            {
                "id": "fc_123",
                "type": "function_call",
                "call_id": "call_123",
                "name": name,
                "arguments": json.dumps(arguments or {"instance_id": "i-danger"}),
            },
        ],
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
        self.created = None
        self.responses = self

    def create(self, **kwargs):
        self.created = kwargs
        return {"id": "resp_next", **kwargs}


def decode_output(output_item):
    return json.loads(output_item["output"])


def test_default_response_action_mapper_namespaces_function_calls():
    assert default_response_action_mapper("delete_instance", {}, {}) == "openai.responses.function.delete_instance"


def test_denied_function_call_is_not_executed():
    registry = ToolRegistry()
    called = False

    def delete_instance(_arguments):
        nonlocal called
        called = True
        return {"terminated": True}

    registry.register("delete_instance", delete_instance)
    wrapper = ZeroTrustResponsesWrapper(
        openai_client=FakeOpenAIClient(),
        control_plane=FakeControlPlane("deny"),
        actor="demo-agent",
        tools=registry,
    )

    outputs = wrapper.collect_function_call_outputs(responses_function_call())

    assert called is False
    assert outputs[0]["type"] == "function_call_output"
    assert outputs[0]["call_id"] == "call_123"
    body = decode_output(outputs[0])
    assert body["ok"] is False
    assert body["zero_trust"]["decision"] == "deny"
    assert body["zero_trust"]["audit"]["kms_signature"]["algorithm"] == "ECDSA_SHA_256"


def test_allowed_function_call_executes_registered_handler():
    registry = ToolRegistry()
    registry.register("lookup_instance", lambda arguments: {"id": arguments["instance_id"], "state": "running"})
    wrapper = ZeroTrustResponsesWrapper(
        openai_client=FakeOpenAIClient(),
        control_plane=FakeControlPlane("allow"),
        actor="demo-agent",
        tools=registry,
    )

    outputs = wrapper.collect_function_call_outputs(responses_function_call("lookup_instance"))

    body = decode_output(outputs[0])
    assert body["ok"] is True
    assert body["result"] == {"id": "i-danger", "state": "running"}
    assert body["zero_trust"]["decision"] == "allow"


def test_unregistered_function_fails_closed_after_policy_allow():
    wrapper = ZeroTrustResponsesWrapper(
        openai_client=FakeOpenAIClient(),
        control_plane=FakeControlPlane("allow"),
        actor="demo-agent",
    )

    outputs = wrapper.collect_function_call_outputs(responses_function_call("unknown_tool"))

    body = decode_output(outputs[0])
    assert body["ok"] is False
    assert body["zero_trust"]["decision"] == "deny"
    assert "not registered" in body["zero_trust"]["reason"]


def test_build_follow_up_input_preserves_response_output_items():
    registry = ToolRegistry()
    registry.register("lookup_instance", lambda _arguments: {"state": "running"})
    wrapper = ZeroTrustResponsesWrapper(
        openai_client=FakeOpenAIClient(),
        control_plane=FakeControlPlane("allow"),
        actor="demo-agent",
        tools=registry,
    )

    follow_up_input = wrapper.build_follow_up_input(responses_function_call("lookup_instance"))

    assert follow_up_input[0]["type"] == "reasoning"
    assert follow_up_input[1]["type"] == "function_call"
    assert follow_up_input[2]["type"] == "function_call_output"
    assert follow_up_input[2]["call_id"] == "call_123"


def test_continue_response_calls_responses_create_shape():
    client = FakeOpenAIClient()
    registry = ToolRegistry()
    registry.register("lookup_instance", lambda _arguments: {"state": "running"})
    wrapper = ZeroTrustResponsesWrapper(
        openai_client=client,
        control_plane=FakeControlPlane("allow"),
        actor="demo-agent",
        tools=registry,
    )

    result = wrapper.continue_response(responses_function_call("lookup_instance"), instructions="stay brief")

    assert result["id"] == "resp_next"
    assert client.created["model"] == "gpt-5"
    assert client.created["instructions"] == "stay brief"
    assert client.created["input"][-1]["type"] == "function_call_output"


def test_missing_call_id_raises_because_api_requires_it():
    run = responses_function_call()
    del run["output"][1]["call_id"]
    wrapper = ZeroTrustResponsesWrapper(openai_client=FakeOpenAIClient(), control_plane=FakeControlPlane())

    with pytest.raises(ValueError, match="call_id is required"):
        wrapper.collect_function_call_outputs(run)
