# Demo Narrative

This document captures demo framing for internal rehearsals and release planning. Keep the repository README focused on engineering usage.

## Core Moment

The strongest demo is an agent attempting a dangerous action and being denied before execution:

```json
{
  "actor": "demo-agent",
  "action": "aws.ec2.terminate_instances"
}
```

Expected response shape:

```json
{
  "decision": "deny",
  "reason": "policy denied this action",
  "audit": {
    "previous_hash": "...",
    "current_hash": "...",
    "kms_signature": {
      "algorithm": "ECDSA_SHA_256",
      "signature": "..."
    }
  }
}
```

The line to say:

> The agent never got to execute. The denial was signed, hash-chained to the previous event, and shipped as audit evidence.

## Where Nono Fits

Nono is an execution-containment layer, not the control plane.

Safe wording:

> ZT-Infra answers "should this action run?" and hands approved work to a broker. Nono can enforce "what can the process do?" at the kernel boundary for local or CLI agents.

Avoid claiming that the AWS MVP depends on nono unless the demo is specifically showing the nono broker.
