# A2A Policy Proxy

The A2A Policy Proxy enforces zt-infra-v2 policy at the Agent2Agent protocol boundary.

```text
external agent -> A2A client -> Zero Trust A2A Policy Proxy -> /actions -> A2A remote agent
```

## Protocol Scope

The proxy currently targets the A2A JSON-RPC binding:

- `SendMessage`
- `SendStreamingMessage`
- `CancelTask`

Other methods such as `GetTask`, `ListTasks`, and `SubscribeToTask` are forwarded by default because they are read/monitoring operations.

## Policy Mapping

By default:

```text
remote_agent = github_agent
method       = SendMessage
action       = a2a.github_agent.send_message
resource     = message.metadata.resource | message.taskId | message.contextId | message text
```

Actor resolution checks:

```text
message.metadata.actor -> params.actor -> "a2a-client"
```

Pass a custom `action_mapper` if a production integration needs skill-specific or tenant-specific policy strings.

## Denial Semantics

Denied protected operations are not forwarded. The proxy returns an A2A task result with:

```json
{
  "status": {
    "state": "TASK_STATE_REJECTED",
    "message": {
      "role": "ROLE_AGENT",
      "parts": [
        {
          "text": "Denied by zero-trust policy: action is not in the allow list"
        }
      ]
    }
  },
  "metadata": {
    "zero_trust": {
      "actor": "demo-agent",
      "action": "a2a.github_agent.send_message",
      "resource": "octo/repo",
      "decision": "deny",
      "reason": "action is not in the allow list",
      "audit": {
        "previous_hash": "...",
        "current_hash": "...",
        "kms_signature": {
          "algorithm": "ECDSA_SHA_256",
          "key_id": "...",
          "signature": "..."
        }
      }
    }
  }
}
```

`TASK_STATE_REJECTED` is used because the A2A specification defines it as the terminal state for a task the agent has decided not to perform. `denial_state` can be set to `TASK_STATE_AUTH_REQUIRED` when a policy decision should drive an authorization flow instead.

For `SendStreamingMessage`, the proxy returns a single stream-event-shaped JSON-RPC response containing the rejected task. A real HTTP/SSE adapter can serialize this as one `data:` event and close the stream.

## Minimal Usage

```python
from zt_a2a import A2APolicyProxy


def downstream_a2a(request):
    return real_a2a_client.send_jsonrpc(request)


proxy = A2APolicyProxy(
    downstream=downstream_a2a,
    remote_agent="github_agent",
)

response = proxy.handle_jsonrpc({
    "jsonrpc": "2.0",
    "id": "req-1",
    "method": "SendMessage",
    "params": {
        "message": {
            "role": "ROLE_USER",
            "messageId": "msg-1",
            "metadata": {
                "actor": "demo-agent",
                "resource": "octo/repo"
            },
            "parts": [{"text": "Create a pull request"}]
        }
    }
})
```

## Security Properties

- Protected A2A operations are policy-checked before reaching the remote agent.
- Denied operations return protocol-native task rejection instead of leaking through to downstream agents.
- Control-plane outages fail closed with `audit.local_proxy_only = true`.
- Signed control-plane responses preserve actor, action, resource, decision, reason, previous hash, current hash, and KMS signature.
- Invalid protected request params return JSON-RPC `-32602`.
