# Interoperability Demo

This demo proves the product thesis:

> One zero-trust control plane can govern agent actions across frameworks and protocols.

The same denial scenario is exercised through four integration surfaces:

1. LangGraph agent blocked.
2. OpenAI Responses agent blocked.
3. MCP tool call blocked.
4. A2A external agent task rejected.
5. All four produce the same signed audit record format.

## Demo Flow

| Surface | Attempt | Expected outcome |
| --- | --- | --- |
| LangGraph | Agent state requests `aws.ec2.terminate_instances` | Graph routes to `deny`; guarded action node is skipped |
| OpenAI Responses | Function call requests `delete_instance` | Wrapper returns `function_call_output`; local tool is not executed |
| MCP | `tools/call` invokes `github.create_pull_request` | Gateway returns `isError: true`; real MCP server is not called |
| A2A | External agent sends write request to GitHub agent | Proxy returns `TASK_STATE_REJECTED`; downstream A2A agent is not called |

## Common Signed Audit Format

Every blocked interface exposes this canonical envelope:

```json
{
  "ok": false,
  "actor": "demo-agent",
  "action": "mcp.github.create_pull_request",
  "resource": "octo/repo",
  "decision": "deny",
  "reason": "blocked by zero-trust policy",
  "audit": {
    "timestamp": "2026-04-30T00:00:00Z",
    "previous_hash": "0000000000000000000000000000000000000000000000000000000000000000",
    "current_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "kms_signature": {
      "algorithm": "ECDSA_SHA_256",
      "key_id": "arn:aws:kms:us-east-2:<AWS_ACCOUNT_ID>:key/demo",
      "signature": "base64-signature"
    }
  }
}
```

## Verification

Run:

```bash
make PYTHON=.venv/bin/python static
```

The core contract is tested in:

```text
tests/test_interoperability_demo_contract.py
```

The test proves:

- denied actions do not execute;
- downstream protocol servers are not called;
- A2A denial is represented as a rejected task;
- all four denial records share the exact same top-level, audit, and signature keys.

## Investor Talk Track

This is the product moment:

> An agent can arrive through LangGraph, OpenAI, MCP, or A2A. The same control plane blocks unauthorized action before execution and emits the same signed evidence envelope.

That moves the demo from a single-agent sandbox into an interoperability control layer for autonomous systems.
