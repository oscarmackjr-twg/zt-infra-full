import crypto from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import {
  CloudWatchLogsClient,
  CreateLogStreamCommand,
  PutLogEventsCommand,
  ResourceAlreadyExistsException,
} from "@aws-sdk/client-cloudwatch-logs";
import { KMSClient, SignCommand } from "@aws-sdk/client-kms";
import { attestAction, createDAALoggerFromEnv } from "./daal.js";

const ZERO_HASH = "0".repeat(64);

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function stableJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map(stableJson).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

async function ensureDirFor(filePath) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
}

export class ActionAuditor {
  constructor(options = {}) {
    this.region = options.region || process.env.AWS_REGION || "us-east-2";
    this.stateFile =
      options.stateFile || process.env.AUDIT_STATE_FILE || "/var/lib/zt-provisioner/audit-chain.jsonl";
    this.kmsKeyId = options.kmsKeyId || process.env.AUDIT_KMS_KEY_ID || "";
    this.logGroupName = options.logGroupName || process.env.AUDIT_LOG_GROUP_NAME || "";
    this.logStreamName =
      options.logStreamName || process.env.AUDIT_LOG_STREAM_NAME || `${os.hostname()}-actions`;
    this.signer = options.signer || null;
    this.logSink = options.logSink || null;
    this.kms = options.kms || new KMSClient({ region: this.region });
    this.logs = options.logs || new CloudWatchLogsClient({ region: this.region });
    this.daal = options.daal === undefined ? createDAALoggerFromEnv() : options.daal;
    this.logStreamReady = false;
  }

  async previousHash() {
    try {
      const content = await fs.readFile(this.stateFile, "utf8");
      const lines = content.trim().split("\n").filter(Boolean);
      if (lines.length === 0) {
        return ZERO_HASH;
      }
      return JSON.parse(lines[lines.length - 1]).current_hash || ZERO_HASH;
    } catch (error) {
      if (error.code === "ENOENT") {
        return ZERO_HASH;
      }
      throw error;
    }
  }

  async signHash(currentHash) {
    if (this.signer) {
      return this.signer(currentHash);
    }
    if (!this.kmsKeyId) {
      return { algorithm: "none", key_id: "", signature: "" };
    }

    const response = await this.kms.send(
      new SignCommand({
        KeyId: this.kmsKeyId,
        Message: Buffer.from(currentHash, "hex"),
        MessageType: "DIGEST",
        SigningAlgorithm: "ECDSA_SHA_256",
      }),
    );

    return {
      algorithm: response.SigningAlgorithm,
      key_id: this.kmsKeyId,
      signature: Buffer.from(response.Signature).toString("base64"),
    };
  }

  async publish(record) {
    if (this.logSink) {
      await this.logSink(record);
      return;
    }
    if (!this.logGroupName) {
      return;
    }

    if (!this.logStreamReady) {
      try {
        await this.logs.send(
          new CreateLogStreamCommand({
            logGroupName: this.logGroupName,
            logStreamName: this.logStreamName,
          }),
        );
      } catch (error) {
        const alreadyExists =
          error instanceof ResourceAlreadyExistsException || error.name === "ResourceAlreadyExistsException";
        if (!alreadyExists) {
          throw error;
        }
      }
      this.logStreamReady = true;
    }

    await this.logs.send(
      new PutLogEventsCommand({
        logGroupName: this.logGroupName,
        logStreamName: this.logStreamName,
        logEvents: [{ timestamp: Date.now(), message: JSON.stringify(record) }],
      }),
    );
  }

  async record({ actor, action, resource = "", decision, reason }) {
    const timestamp = new Date().toISOString();
    const previous_hash = await this.previousHash();
    const unsigned = { actor, action, resource, decision, reason, timestamp, previous_hash };
    const current_hash = sha256(stableJson(unsigned));
    const kms_signature = await this.signHash(current_hash);
    const daal = attestAction({
      logger: this.daal,
      agentId: actor,
      actionDetails: { ...unsigned, current_hash, kms_signature },
      actionHash: `0x${current_hash}`,
    });
    const record = { ...unsigned, current_hash, kms_signature, daal };

    await ensureDirFor(this.stateFile);
    await fs.appendFile(this.stateFile, `${JSON.stringify(record)}\n`, { mode: 0o600 });
    await this.publish(record);
    return record;
  }
}
