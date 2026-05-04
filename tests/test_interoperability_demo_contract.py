import json

from zt_a2a import A2APolicyProxy
from zt_langgraph import create_guarded_action_node, create_policy_decision_node, route_by_decision
from zt_mcp import MCPZeroTrustGateway
from zt_openai import ToolRegistry, ZeroTrustResponsesWrapper


def signed_denial(actor, action, resource):
    return {
        "ok": False,
        "actor": actor,
        "action": action,
        "resource": resource,
        "decision": "deny",
        "reason": "blocked by zero-trust policy",
        "audit": {
            "timestamp": "2026-04-30T00:00:00Z",
            "previous_hash": "0" * 64,
            "current_hash": "a" * 64,
            "kms_signature": {
                "algorithm": "ECDSA_SHA_256",
                "key_id": "arn:aws:kms:us-east-2:<AWS_ACCOUNT_ID>:key/demo",
                "signature": "base64-signature",
            },
        },
    }


class DenyControlPlane:
    def __init__(self):
        self.requests = []

    def decide(self, actor, action, resource=None):
        resource = resource or "demo-resource"
        self.requests.append({"actor": actor, "action": action, "resource": resource})
        return signed_denial(actor, action, resource)


class RecordingDownstream:
    def __init__(self):
        self.calls = []

    def __call__(self, message):
        self.calls.append(message)
        return {"jsonrpc": "2.0", "id": message.get("id"), "result": {"ok": True}}


def assert_signed_audit_record(record):
    assert set(record) >= {"actor", "action", "resource", "decision", "reason", "audit"}
    assert record["decision"] == "deny"
    assert record["actor"]
    assert record["action"]
    assert record["resource"]
    audit = record["audit"]
    assert set(audit) == {"timestamp", "previous_hash", "current_hash", "kms_signature"}
    assert len(audit["previous_hash"]) == 64
    assert len(audit["current_hash"]) == 64
    assert audit["kms_signature"]["algorithm"] == "ECDSA_SHA_256"
    assert audit["kms_signature"]["key_id"].startswith("arn:aws:kms:")
    assert audit["kms_signature"]["signature"]


def test_langgraph_agent_blocked_and_signed_audit_contract():
    control_plane = DenyControlPlane()
    policy_gate = create_policy_decision_node(control_plane)
    executed = False

    def dangerous_action(_state):
        nonlocal executed
        executed = True
        return {"execution_result": "should-not-run"}

    guard = create_guarded_action_node(dangerous_action)
    state = {"actor": "langgraph-agent", "action": "aws.ec2.terminate_instances"}

    decision_update = policy_gate(state)
    route = route_by_decision(decision_update)
    guard_update = guard(decision_update)

    assert route == "deny"
    assert executed is False
    assert guard_update == {"execution_skipped": True}
    assert_signed_audit_record(decision_update["control_plane_decision"])


def test_openai_responses_agent_blocked_and_signed_audit_contract():
    control_plane = DenyControlPlane()
    registry = ToolRegistry()
    executed = False

    def delete_instance(_arguments):
        nonlocal executed
        executed = True
        return {"deleted": True}

    registry.register("delete_instance", delete_instance)
    wrapper = ZeroTrustResponsesWrapper(
        openai_client=object(),
        control_plane=control_plane,
        actor="openai-responses-agent",
        tools=registry,
        action_mapper=lambda _name, args, _call: ("aws.ec2.terminate_instances", args["instance_id"]),
    )
    response = {
        "id": "resp-demo",
        "model": "gpt-5",
        "output": [
            {
                "type": "function_call",
                "call_id": "call-demo",
                "name": "delete_instance",
                "arguments": json.dumps({"instance_id": "i-danger"}),
            }
        ],
    }

    outputs = wrapper.collect_function_call_outputs(response)
    body = json.loads(outputs[0]["output"])

    assert executed is False
    assert outputs[0]["type"] == "function_call_output"
    assert body["ok"] is False
    assert_signed_audit_record(body["zero_trust"])


def test_mcp_tool_call_blocked_and_signed_audit_contract():
    control_plane = DenyControlPlane()
    downstream = RecordingDownstream()
    gateway = MCPZeroTrustGateway(
        downstream=downstream,
        control_plane=control_plane,
        actor="claude-desktop",
        server_name="github",
    )

    result = gateway.handle_message(
        {
            "jsonrpc": "2.0",
            "id": "mcp-demo",
            "method": "tools/call",
            "params": {
                "name": "create_pull_request",
                "arguments": {"owner": "octo", "repo": "repo", "title": "demo"},
            },
        }
    )
    body = json.loads(result["result"]["content"][0]["text"])

    assert downstream.calls == []
    assert result["result"]["isError"] is True
    assert result["result"]["structuredContent"] == body
    assert_signed_audit_record(body)


def test_a2a_external_agent_task_rejected_and_signed_audit_contract():
    control_plane = DenyControlPlane()
    downstream = RecordingDownstream()
    proxy = A2APolicyProxy(
        downstream=downstream,
        control_plane=control_plane,
        remote_agent="github_agent",
    )

    result = proxy.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": "a2a-demo",
            "method": "SendMessage",
            "params": {
                "message": {
                    "role": "ROLE_USER",
                    "messageId": "message-demo",
                    "contextId": "context-demo",
                    "metadata": {"actor": "external-agent", "resource": "octo/repo"},
                    "parts": [{"text": "Create a pull request"}],
                }
            },
        }
    )
    task = result["result"]["task"]
    record = task["metadata"]["zero_trust"]

    assert downstream.calls == []
    assert task["status"]["state"] == "TASK_STATE_REJECTED"
    assert "Denied by zero-trust policy" in task["status"]["message"]["parts"][0]["text"]
    assert_signed_audit_record(record)


def test_all_demo_interfaces_share_signed_audit_record_format():
    records = []

    control_plane = DenyControlPlane()
    records.append(
        create_policy_decision_node(control_plane)(
            {"actor": "langgraph-agent", "action": "aws.ec2.terminate_instances"}
        )["control_plane_decision"]
    )

    responses = ZeroTrustResponsesWrapper(
        openai_client=object(),
        control_plane=DenyControlPlane(),
        actor="openai-responses-agent",
        action_mapper=lambda _name, args, _call: ("aws.ec2.terminate_instances", args["instance_id"]),
    )
    records.append(
        json.loads(
            responses.collect_function_call_outputs(
                {
                    "id": "resp-demo",
                    "model": "gpt-5",
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call-demo",
                            "name": "delete_instance",
                            "arguments": json.dumps({"instance_id": "i-danger"}),
                        }
                    ],
                }
            )[0]["output"]
        )["zero_trust"]
    )

    mcp = MCPZeroTrustGateway(
        downstream=RecordingDownstream(),
        control_plane=DenyControlPlane(),
        actor="claude-desktop",
        server_name="github",
    )
    records.append(
        json.loads(
            mcp.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": "mcp-demo",
                    "method": "tools/call",
                    "params": {
                        "name": "create_pull_request",
                        "arguments": {"owner": "octo", "repo": "repo"},
                    },
                }
            )["result"]["content"][0]["text"]
        )
    )

    a2a = A2APolicyProxy(
        downstream=RecordingDownstream(),
        control_plane=DenyControlPlane(),
        remote_agent="github_agent",
    )
    records.append(
        a2a.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": "a2a-demo",
                "method": "SendMessage",
                "params": {
                    "message": {
                        "role": "ROLE_USER",
                        "messageId": "message-demo",
                        "metadata": {"actor": "external-agent", "resource": "octo/repo"},
                        "parts": [{"text": "Create a pull request"}],
                    }
                },
            }
        )["result"]["task"]["metadata"]["zero_trust"]
    )

    canonical_keys = None
    audit_keys = None
    signature_keys = None
    for record in records:
        assert_signed_audit_record(record)
        canonical_keys = canonical_keys or set(record)
        audit_keys = audit_keys or set(record["audit"])
        signature_keys = signature_keys or set(record["audit"]["kms_signature"])
        assert set(record) == canonical_keys
        assert set(record["audit"]) == audit_keys
        assert set(record["audit"]["kms_signature"]) == signature_keys
