import json
from urllib.error import HTTPError

import pytest

from zt_langgraph import (
    ControlPlaneClient,
    ControlPlaneError,
    create_guarded_action_node,
    create_policy_decision_node,
    route_by_decision,
)


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body

    def close(self):
        return None


def decision_payload(decision="deny"):
    return {
        "ok": decision == "allow",
        "actor": "demo-agent",
        "action": "aws.ec2.terminate_instances",
        "decision": decision,
        "reason": "test reason",
        "audit": {
            "timestamp": "2026-04-30T00:00:00Z",
            "previous_hash": "0" * 64,
            "current_hash": "a" * 64,
            "kms_signature": {"algorithm": "ECDSA_SHA_256", "key_id": "test", "signature": "sig"},
        },
    }


def test_client_posts_action_and_accepts_deny_http_403():
    captured = {}

    def transport(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        body = json.dumps(decision_payload("deny")).encode("utf-8")
        raise HTTPError(request.full_url, 403, "Forbidden", {}, FakeResponse(body))

    client = ControlPlaneClient("http://control-plane.local", timeout_seconds=2, transport=transport)

    decision = client.decide("demo-agent", "aws.ec2.terminate_instances")

    assert captured == {
        "url": "http://control-plane.local/actions",
        "timeout": 2,
        "body": {"actor": "demo-agent", "action": "aws.ec2.terminate_instances"},
    }
    assert decision["decision"] == "deny"
    assert decision["audit"]["kms_signature"]["algorithm"] == "ECDSA_SHA_256"


def test_client_rejects_invalid_decision_payload():
    def transport(_request, _timeout):
        return FakeResponse(b'{"decision":"maybe"}')

    client = ControlPlaneClient(transport=transport)

    with pytest.raises(ControlPlaneError):
        client.decide("demo-agent", "bad.action")


def test_policy_decision_node_writes_partial_state_update():
    class FakeClient:
        def decide(self, actor, action):
            assert actor == "demo-agent"
            assert action == "aws.ec2.terminate_instances"
            return decision_payload("deny")

    node = create_policy_decision_node(FakeClient())

    update = node({"actor": "demo-agent", "action": "aws.ec2.terminate_instances"})

    assert update["control_plane_decision"]["decision"] == "deny"


def test_route_by_decision_returns_allow_or_deny():
    assert route_by_decision({"control_plane_decision": decision_payload("deny")}) == "deny"
    assert route_by_decision({"control_plane_decision": decision_payload("allow")}) == "allow"


def test_guarded_action_node_skips_denied_action():
    called = False

    def action_node(_state):
        nonlocal called
        called = True
        return {"execution_result": "ran"}

    node = create_guarded_action_node(action_node)

    update = node({"control_plane_decision": decision_payload("deny")})

    assert called is False
    assert update == {"execution_skipped": True}


def test_guarded_action_node_runs_allowed_action():
    node = create_guarded_action_node(lambda _state: {"execution_result": "ran"})

    update = node({"control_plane_decision": decision_payload("allow")})

    assert update == {"execution_result": "ran", "execution_skipped": False}
