import fs from "node:fs";

const DEFAULT_POLICY = {
  defaultDecision: "deny",
  allow: [],
  deny: [
    {
      action: "aws.ec2.terminate_instances",
      reason: "Agents may not terminate EC2 instances in the Dark Factory MVP.",
    },
  ],
};

function matches(pattern, action) {
  if (pattern === action) {
    return true;
  }
  if (pattern.endsWith("*")) {
    return action.startsWith(pattern.slice(0, -1));
  }
  return false;
}

export function loadPolicy(path = process.env.ACTION_POLICY_FILE || "/etc/zt-provisioner/actions-policy.json") {
  if (!path || !fs.existsSync(path)) {
    return DEFAULT_POLICY;
  }
  return JSON.parse(fs.readFileSync(path, "utf8"));
}

export function evaluateAction(policy, request) {
  const actor = String(request?.actor || "").trim();
  const action = String(request?.action || "").trim();

  if (!actor) {
    return { decision: "deny", reason: "actor is required" };
  }
  if (!action) {
    return { decision: "deny", reason: "action is required" };
  }

  const explicitDeny = (policy.deny || []).find((rule) => matches(rule.action, action));
  if (explicitDeny) {
    return { decision: "deny", reason: explicitDeny.reason || "action is explicitly denied" };
  }

  const explicitAllow = (policy.allow || []).find((rule) => matches(rule.action, action));
  if (explicitAllow) {
    return { decision: "allow", reason: explicitAllow.reason || "action is explicitly allowed" };
  }

  return {
    decision: policy.defaultDecision === "allow" ? "allow" : "deny",
    reason:
      policy.defaultDecision === "allow"
        ? "action allowed by default policy"
        : "action is not in the allow list",
  };
}
