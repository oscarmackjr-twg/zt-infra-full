# Project Scope

ZT-Infra is the agent action adapter-contract layer.

It is not intended to replace the core primitives already emerging in the market:

| Layer | Best-fit primitives | ZT-Infra role |
| --- | --- | --- |
| Identity | SPIFFE/SPIRE, NANDA-style cross-organization agent identity | Consume identity and bind it to `actor`. |
| Policy / governance | CSA Agentic Trust Framework, OPA, Cedar | Wrap the decision in an agent-shaped request/response contract. |
| Execution containment | nono for local/CLI agents; gVisor, Firecracker, Kata, browser sandboxes for other runtimes | Handoff approved work to a broker and capture evidence. |
| Observability | SIEM, OpenTelemetry, eBPF/runtime telemetry, CloudWatch | Emit a consistent audit envelope. |

## Narrow Claim

ZT-Infra defines:

- `POST /actions` request shape;
- allow/deny response shape;
- fail-closed SDK behavior;
- signed audit envelope;
- broker handoff semantics;
- conformance tests across LangGraph, OpenAI wrappers, MCP, A2A, and custom adapters.

It should be possible to swap the policy engine, identity provider, execution sandbox, or audit sink without changing the adapter contract.

## nono Position

nono is the flagship local execution-containment pairing.

```text
ZT-Infra: should this action run?
nono: what will the kernel permit if it does run?
```

nono uses Linux Landlock and macOS Seatbelt to apply kernel-enforced allow-lists to the sandboxed process and its children. ZT-Infra does not compete with that; it decides and records the action before handing approved work to the broker.

## Contributor White Space

The useful work is at the integration boundary:

- LangGraph decorators that wrap tool calls automatically;
- MCP middleware before tool dispatch;
- A2A peer attestation hooks;
- OPA and Cedar policy templates for common agent ABAC patterns;
- SPIFFE/SPIRE actor binding;
- adapter conformance tests.

## Preferred One-Liner

```text
An open adapter contract and audit envelope for agent action authorization, designed to plug into your existing identity, policy engine, and sandbox.
```
