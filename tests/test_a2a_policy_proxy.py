import pytest

from zt_a2a import A2APolicyProxy, A2AProxyError, default_a2a_action_mapper, extract_message_text, extract_resource
from zt_langgraph import ControlPlaneError


def decision_payload(decision="deny", action="a2a.github_agent.send_message", resource="octo/repo"):
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


def send_message_request(method="SendMessage"):
    return {
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": method,
        "params": {
            "message": {
                "role": "ROLE_USER",
                "messageId": "msg-1",
                "contextId": "ctx-1",
                "metadata": {"actor": "demo-agent", "resource": "octo/repo"},
                "parts": [{"text": "Create a GitHub pull request"}],
            },
            "configuration": {"acceptedOutputModes": ["text/plain"]},
        },
    }


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


class FakeDownstream:
    def __init__(self):
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {"message": {"role": "ROLE_AGENT", "messageId": "msg-ok", "parts": [{"text": "ok"}]}},
        }


def denied_task(response):
    return response["result"]["task"]


def test_default_mapper_and_resource_extraction():
    params = send_message_request()["params"]
    action, resource = default_a2a_action_mapper("github-agent", params, "SendMessage")

    assert action == "a2a.github-agent.send_message"
    assert resource == "octo/repo"
    assert extract_message_text(params["message"]) == "Create a GitHub pull request"
    assert extract_resource({"message": {"parts": [{"text": "fallback text"}]}}) == "fallback text"


def test_denied_send_message_returns_rejected_a2a_task_without_forwarding():
    downstream = FakeDownstream()
    control_plane = FakeControlPlane("deny")
    proxy = A2APolicyProxy(downstream=downstream, control_plane=control_plane, remote_agent="github_agent")

    response = proxy.handle_jsonrpc(send_message_request())

    assert downstream.requests == []
    assert control_plane.requests == [
        {"actor": "demo-agent", "action": "a2a.github_agent.send_message", "resource": "octo/repo"}
    ]
    task = denied_task(response)
    assert task["status"]["state"] == "TASK_STATE_REJECTED"
    assert task["contextId"] == "ctx-1"
    assert task["metadata"]["zero_trust"]["decision"] == "deny"
    assert task["metadata"]["zero_trust"]["audit"]["kms_signature"]["algorithm"] == "ECDSA_SHA_256"
    assert "Denied by zero-trust policy" in task["status"]["message"]["parts"][0]["text"]


def test_allowed_send_message_is_forwarded():
    downstream = FakeDownstream()
    proxy = A2APolicyProxy(
        downstream=downstream,
        control_plane=FakeControlPlane("allow"),
        remote_agent="github_agent",
    )

    response = proxy.handle_jsonrpc(send_message_request())

    assert len(downstream.requests) == 1
    assert response["result"]["message"]["parts"][0]["text"] == "ok"


def test_streaming_denial_returns_single_stream_event_response():
    proxy = A2APolicyProxy(
        downstream=FakeDownstream(),
        control_plane=FakeControlPlane("deny"),
        remote_agent="github_agent",
    )

    response = proxy.handle_jsonrpc(send_message_request("SendStreamingMessage"))

    assert isinstance(response, list)
    assert response[0]["jsonrpc"] == "2.0"
    assert denied_task(response[0])["status"]["state"] == "TASK_STATE_REJECTED"


def test_cancel_task_is_policy_checked_with_task_resource():
    control_plane = FakeControlPlane("deny")
    proxy = A2APolicyProxy(downstream=FakeDownstream(), control_plane=control_plane, remote_agent="worker")

    response = proxy.handle_jsonrpc(
        {"jsonrpc": "2.0", "id": "req-2", "method": "CancelTask", "params": {"taskId": "task-123"}}
    )

    assert control_plane.requests == [{"actor": "a2a-client", "action": "a2a.worker.cancel_task", "resource": "task-123"}]
    assert denied_task(response)["id"] == "task-123"


def test_control_plane_failure_fails_closed():
    proxy = A2APolicyProxy(
        downstream=FakeDownstream(),
        control_plane=FakeControlPlane(fail=True),
        actor="fixed-agent",
        remote_agent="github_agent",
    )

    response = proxy.handle_jsonrpc(send_message_request())

    decision = denied_task(response)["metadata"]["zero_trust"]
    assert decision["actor"] == "fixed-agent"
    assert decision["audit"] == {"local_proxy_only": True}
    assert "control plane unavailable" in decision["reason"]


def test_non_protected_method_forwards_without_policy_check():
    downstream = FakeDownstream()
    control_plane = FakeControlPlane("deny")
    proxy = A2APolicyProxy(downstream=downstream, control_plane=control_plane)
    request = {"jsonrpc": "2.0", "id": "req-3", "method": "GetTask", "params": {"id": "task-1"}}

    response = proxy.handle_jsonrpc(request)

    assert control_plane.requests == []
    assert downstream.requests == [request]
    assert response["result"]["message"]["parts"][0]["text"] == "ok"


def test_invalid_request_and_params_fail_safely():
    proxy = A2APolicyProxy(downstream=FakeDownstream(), control_plane=FakeControlPlane())

    with pytest.raises(A2AProxyError):
        proxy.handle_jsonrpc({"jsonrpc": "1.0", "id": "bad", "method": "SendMessage"})

    response = proxy.handle_jsonrpc({"jsonrpc": "2.0", "id": "bad", "method": "SendMessage", "params": []})
    assert response == {"jsonrpc": "2.0", "id": "bad", "error": {"code": -32602, "message": "Invalid parameters"}}
