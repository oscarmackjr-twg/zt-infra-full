import assert from "node:assert/strict";
import { test } from "node:test";

import { createApp } from "../src/server.js";
import { evaluateAction } from "../src/policy.js";

function invokeRoute(path) {
  const app = createApp({ auditor: { record: async () => ({}) } });
  const layer = app._router.stack.find((candidate) => candidate.route?.path === path);
  assert.ok(layer, `route ${path} exists`);

  let payload;
  layer.route.stack[0].handle({}, {
    json(body) {
      payload = body;
    },
  });
  return payload;
}

async function invokePostAction(app, body) {
  const layer = app._router.stack.find((candidate) => candidate.route?.path === "/actions");
  assert.ok(layer, "route /actions exists");
  const handler = layer.route.stack.find((candidate) => candidate.method === "post").handle;

  let status = 200;
  let payload;
  await handler(
    { body },
    {
      status(code) {
        status = code;
        return this;
      },
      json(responseBody) {
        payload = responseBody;
      },
    },
    (error) => {
      if (error) {
        throw error;
      }
    },
  );
  return { status, body: payload };
}

test("health endpoint reports local provisioner status", async () => {
  const body = invokeRoute("/health");

  assert.equal(body.ok, true);
  assert.equal(body.service, "zt-provisioner");
  assert.match(body.ts, /^\d{4}-\d{2}-\d{2}T/);
});

test("status endpoint reports zero trust expectations", async () => {
  const body = invokeRoute("/api/status");

  assert.deepEqual(body.zeroTrust, {
    publicIngress: false,
    tailscaleExpected: true,
    ssmFallback: true,
  });
});

test("policy denies unauthorized AWS action with reason", () => {
  const result = evaluateAction(
    {
      defaultDecision: "deny",
      allow: [],
      deny: [{ action: "aws.ec2.terminate_instances", reason: "termination blocked" }],
    },
    { actor: "demo-agent", action: "aws.ec2.terminate_instances" },
  );

  assert.deepEqual(result, { decision: "deny", reason: "termination blocked" });
});

test("actions endpoint blocks and audits unauthorized action", async () => {
  const auditRecords = [];
  const app = createApp({
    policy: {
      defaultDecision: "deny",
      allow: [{ action: "zt.status.read", reason: "read allowed" }],
      deny: [{ action: "aws.ec2.terminate_instances", reason: "termination blocked" }],
    },
    auditor: {
      async record(record) {
        auditRecords.push(record);
        return {
          ...record,
          timestamp: "2026-04-30T00:00:00.000Z",
          previous_hash: "0".repeat(64),
          current_hash: "a".repeat(64),
        kms_signature: {
          algorithm: "ECDSA_SHA_256",
          key_id: "test-key",
          signature: "test-signature",
        },
        daal: {
          status: "queued",
          actionHash: "0x" + "a".repeat(64),
        },
      };
      },
    },
  });

  const response = await invokePostAction(app, {
    actor: "demo-agent",
    action: "aws.ec2.terminate_instances",
    resource: "i-danger",
  });

  assert.equal(response.status, 403);
  assert.equal(response.body.ok, false);
  assert.equal(response.body.decision, "deny");
  assert.equal(response.body.resource, "i-danger");
  assert.equal(response.body.reason, "termination blocked");
  assert.equal(response.body.audit.kms_signature.algorithm, "ECDSA_SHA_256");
  assert.equal(response.body.audit.daal.status, "queued");
  assert.deepEqual(auditRecords, [
    {
      actor: "demo-agent",
      action: "aws.ec2.terminate_instances",
      resource: "i-danger",
      decision: "deny",
      reason: "termination blocked",
    },
  ]);
});

test("actions endpoint allows only explicit read-only action", async () => {
  const app = createApp({
    policy: {
      defaultDecision: "deny",
      allow: [{ action: "zt.status.read", reason: "read allowed" }],
      deny: [],
    },
    auditor: {
      async record(record) {
        return {
          ...record,
          timestamp: "2026-04-30T00:00:00.000Z",
          previous_hash: "0".repeat(64),
          current_hash: "b".repeat(64),
          kms_signature: { algorithm: "ECDSA_SHA_256", key_id: "test-key", signature: "test-signature" },
        };
      },
    },
  });

  const allowed = await invokePostAction(app, { actor: "demo-agent", action: "zt.status.read" });
  const unknown = await invokePostAction(app, { actor: "demo-agent", action: "aws.s3.delete_bucket" });

  assert.equal(allowed.status, 200);
  assert.equal(allowed.body.decision, "allow");
  assert.equal(unknown.status, 403);
  assert.equal(unknown.body.reason, "action is not in the allow list");
});
