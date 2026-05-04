# Appendix: Agent Interoperability Demo Evidence

## Test Coverage

The proof is implemented in:

```text
tests/test_interoperability_demo_contract.py
```

## Required Assertions

1. LangGraph agent blocked.
   - `create_policy_decision_node` returns `decision=deny`.
   - `route_by_decision` routes to `deny`.
   - `create_guarded_action_node` sets `execution_skipped=True`.

2. OpenAI Responses agent blocked.
   - `ZeroTrustResponsesWrapper` intercepts `function_call`.
   - The local tool handler is not executed.
   - Returned item is `function_call_output` with `zero_trust` payload.

3. MCP tool call blocked.
   - `MCPZeroTrustGateway` intercepts `tools/call`.
   - Downstream MCP server is not called.
   - Result returns `isError=true` with `structuredContent`.

4. A2A external agent task rejected.
   - `A2APolicyProxy` intercepts `SendMessage`.
   - Downstream A2A agent is not called.
   - Result task state is `TASK_STATE_REJECTED`.

5. All four produce the same signed audit record format.
   - Top-level keys: `ok`, `actor`, `action`, `resource`, `decision`, `reason`, `audit`.
   - Audit keys: `timestamp`, `previous_hash`, `current_hash`, `kms_signature`; live infra may also include optional `daal`.
   - Signature keys: `algorithm`, `key_id`, `signature`.
   - Signature algorithm: `ECDSA_SHA_256`.
   - Interface metadata is adapter context today, not a mandatory signed-record field.

## Validation Command

```bash
make PYTHON=.venv/bin/python static
```

Expected result:

```text
tests/test_interoperability_demo_contract.py ... [pass]
```

## Product Claim Supported

This evidence supports the claim:

> Zero Trust V2 is a policy enforcement and cryptographic evidence layer for autonomous agents across frameworks and protocols.
