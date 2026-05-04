import express from "express";
import os from "node:os";

import { ActionAuditor } from "./audit.js";
import { evaluateAction, loadPolicy } from "./policy.js";

const port = Number(process.env.PORT || 3000);
const host = process.env.HOST || "127.0.0.1";

export function createApp(options = {}) {
  const app = express();
  const policy = options.policy || loadPolicy(options.policyPath);
  const auditor = options.auditor || new ActionAuditor(options.audit);

  app.use(express.json({ limit: "16kb" }));

  app.get("/health", (_req, res) => {
    res.json({ ok: true, service: "zt-provisioner", host: os.hostname(), ts: new Date().toISOString() });
  });

  app.get("/api/status", (_req, res) => {
    res.json({ ok: true, zeroTrust: { publicIngress: false, tailscaleExpected: true, ssmFallback: true } });
  });

  app.post("/actions", async (req, res, next) => {
    try {
      const actor = String(req.body?.actor || "").trim();
      const action = String(req.body?.action || "").trim();
      const resource = String(req.body?.resource || "").trim();
      const result = evaluateAction(policy, { actor, action });
      const audit = await auditor.record({ actor, action, resource, decision: result.decision, reason: result.reason });

      res.status(result.decision === "allow" ? 200 : 403).json({
        ok: result.decision === "allow",
        actor,
        action,
        resource,
        decision: result.decision,
        reason: result.reason,
        audit: {
          timestamp: audit.timestamp,
          previous_hash: audit.previous_hash,
          current_hash: audit.current_hash,
          kms_signature: audit.kms_signature,
          daal: audit.daal,
        },
      });
    } catch (error) {
      next(error);
    }
  });

  return app;
}

export function startServer() {
  return createApp().listen(port, host, () => {
    console.log(`zt-provisioner listening on http://${host}:${port}`);
  });
}

if (import.meta.url === `file://${process.argv[1]}`) {
  startServer();
}
