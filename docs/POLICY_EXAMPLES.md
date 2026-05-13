# Policy Examples

These examples show how to express common agent authorization decisions with
generic, non-customer-specific policy rules. They are intentionally small so
teams can adapt them to their own identity provider, policy engine, and audit
sink without copying account IDs, ARNs, hostnames, or private data.

## Deny by default

Use deny-by-default when an agent action is not explicitly covered by an allow
rule. This is the safest baseline for tool-calling agents because new tools,
new resources, or malformed requests fail closed until reviewed.

### Cedar-style example

```cedar
// Default posture: no permit policy exists for unknown actions.
// The authorizer should return deny unless another explicit permit matches.
forbid(
  principal,
  action,
  resource
) when {
  !(principal has trusted && principal.trusted)
};
```

### OPA/Rego example

```rego
package ztinfra.authz

default allow := false

deny_reason := "no matching allow rule" if {
  not allow
}
```

## Scoped allow for a low-risk read action

Use scoped allow rules for specific actor, action, and resource attributes. Keep
the scope narrow enough that the audit envelope can explain why the action was
allowed.

### Cedar-style example

```cedar
permit(
  principal,
  action == Action::"ticket.read",
  resource
) when {
  principal has role && principal.role == "support_agent" &&
  resource has classification && resource.classification == "internal" &&
  resource has environment && resource.environment == "staging"
};
```

### OPA/Rego example

```rego
package ztinfra.authz

default allow := false

allow if {
  input.actor.role == "support_agent"
  input.action == "ticket.read"
  input.resource.classification == "internal"
  input.resource.environment == "staging"
}
```

## Adapter contract mapping

A ZT-Infra adapter can send these policy inputs as the same fields used by the
`POST /actions` contract:

```json
{
  "actor": { "id": "support-review-agent", "role": "support_agent" },
  "action": "ticket.read",
  "resource": {
    "classification": "internal",
    "environment": "staging"
  }
}
```

The decision response should keep the explanation concise, for example:

```json
{
  "decision": "allow",
  "reason": "support_agent may read internal staging tickets"
}
```

## Notes for contributors

- Prefer exact action names over wildcard grants.
- Keep examples generic; do not include real account IDs, ARNs, tenants,
  customer names, or production hostnames.
- Include a denial path in tests or demos whenever adding a new allow path.
- Treat missing actor, action, resource, or environment attributes as deny.
