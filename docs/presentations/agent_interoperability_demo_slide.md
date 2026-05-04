# Slide: One Policy Layer Across Agent Ecosystems

## Headline

Every agent action is intercepted before execution, regardless of framework.

## Demo Proof

1. LangGraph agent blocked.
2. OpenAI Responses agent blocked.
3. MCP tool call blocked.
4. A2A external agent task rejected.
5. All four produce the same signed audit record format.

## Visual

```text
LangGraph ┐
OpenAI    ├─> POST /actions ─> deny/reject ─> signed audit evidence
MCP       │
A2A      ┘
```

## Callout

Same envelope everywhere:

```json
{
  "actor": "...",
  "action": "...",
  "resource": "...",
  "decision": "deny",
  "audit": {
    "previous_hash": "...",
    "current_hash": "...",
    "kms_signature": {"algorithm": "ECDSA_SHA_256"}
  }
}
```

## Speaker Note

The wow moment is not that one agent was denied. It is that four different agent ecosystems hit the same policy plane, skip execution, and emit the same audit evidence shape. Unit tests use fake KMS signatures; live private infrastructure signs with AWS KMS when configured.
