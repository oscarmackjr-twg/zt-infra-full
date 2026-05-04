import json

import pytest

from zt_langgraph import ControlPlaneError
from zt_mcp import MCPGatewayError, MCPZeroTrustGateway, default_mcp_action_mapper, extract_resource


def decision_payload(decision="deny", action="mcp.github.create_pull_request", resource="octo/repo"):
    return {
        "ok": decision == "allow",
        "actor": "claude-desktop",
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


def tool_call(name="create_pull_request", arguments=None):
    return {
        "jsonrpc": "2.0",
        "id": "call-1",
        "method": "tools/call",
        "params": {
            "name": name,
            "arguments": arguments or {"owner": "octo", "repo": "repo", "title": "demo"},
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
        self.messages = []

    def __call__(self, message):
        self.messages.append(message)
        return {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "result": {"content": [{"type": "text", "text": "created"}], "isError": False},
        }


def denied_payload(response):
    return json.loads(response["result"]["content"][0]["text"])


def test_default_mapper_namespaces_mcp_tool_and_extracts_resource():
    action, resource = default_mcp_action_mapper("github", "create_pull_request", {"owner": "octo", "repo": "repo"})

    assert action == "mcp.github.create_pull_request"
    assert resource == "octo/repo"
    assert extract_resource({"repository": "org/project"}) == "org/project"


def test_denied_tool_call_is_not_forwarded_and_returns_mcp_tool_error_result():
    downstream = FakeDownstream()
    control_plane = FakeControlPlane("deny")
    gateway = MCPZeroTrustGateway(
        downstream=downstream,
        control_plane=control_plane,
        actor="claude-desktop",
        server_name="github",
    )

    response = gateway.handle_message(tool_call())

    assert downstream.messages == []
    assert control_plane.requests == [
        {
            "actor": "claude-desktop",
            "action": "mcp.github.create_pull_request",
            "resource": "octo/repo",
        }
    ]
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "call-1"
    assert response["result"]["isError"] is True
    body = denied_payload(response)
    assert body["decision"] == "deny"
    assert body["resource"] == "octo/repo"
    assert body["audit"]["kms_signature"]["algorithm"] == "ECDSA_SHA_256"


def test_allowed_tool_call_is_forwarded_to_downstream_mcp_server():
    downstream = FakeDownstream()
    gateway = MCPZeroTrustGateway(
        downstream=downstream,
        control_plane=FakeControlPlane("allow"),
        actor="cursor",
        server_name="github",
    )

    response = gateway.handle_message(tool_call())

    assert len(downstream.messages) == 1
    assert response["result"]["isError"] is False
    assert response["result"]["content"][0]["text"] == "created"


def test_non_tool_call_messages_are_forwarded_without_policy_check():
    downstream = FakeDownstream()
    control_plane = FakeControlPlane("deny")
    gateway = MCPZeroTrustGateway(downstream=downstream, control_plane=control_plane)

    response = gateway.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    assert control_plane.requests == []
    assert downstream.messages == [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}]
    assert response["id"] == 1


def test_malformed_tool_call_returns_json_rpc_invalid_params():
    gateway = MCPZeroTrustGateway(downstream=FakeDownstream(), control_plane=FakeControlPlane())

    response = gateway.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {}})

    assert response == {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {"code": -32602, "message": "tools/call params.name is required"},
    }


def test_control_plane_failure_fails_closed_without_forwarding():
    downstream = FakeDownstream()
    gateway = MCPZeroTrustGateway(
        downstream=downstream,
        control_plane=FakeControlPlane(fail=True),
        actor="claude-desktop",
        server_name="github",
    )

    response = gateway.handle_message(tool_call())

    assert downstream.messages == []
    body = denied_payload(response)
    assert body["decision"] == "deny"
    assert body["audit"] == {"local_gateway_only": True}
    assert "control plane unavailable" in body["reason"]


def test_invalid_json_rpc_message_raises_gateway_error():
    gateway = MCPZeroTrustGateway(downstream=FakeDownstream(), control_plane=FakeControlPlane())

    with pytest.raises(MCPGatewayError):
        gateway.handle_message({"jsonrpc": "1.0", "id": 1, "method": "tools/list"})
