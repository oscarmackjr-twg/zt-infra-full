import crypto from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { Contract, Interface, JsonRpcProvider, NonceManager, Wallet } from "ethers";

export const DAAL_ABI = [
  "function logAction(string agentId, bytes32 actionHash, string metadata) returns (uint256)",
  "function logBatch(string agentId, bytes32 merkleRoot, string metadata) returns (uint256)",
  "event ActionLogged(uint256 indexed recordId, string indexed agentId, bytes32 indexed actionHash, uint256 timestamp, string metadata)",
];

const NETWORKS = {
  "polygon-amoy": {
    chainId: 80002,
    cdpNetwork: "polygon-amoy",
    alchemyPath: "polygon-amoy",
    explorerBaseUrl: "https://amoy.polygonscan.com/tx",
  },
  "base-sepolia": {
    chainId: 84532,
    cdpNetwork: "base-sepolia",
    alchemyPath: "base-sepolia",
    thirdwebChain: "84532",
    explorerBaseUrl: "https://sepolia.basescan.org/tx",
  },
  "base-mainnet": {
    chainId: 8453,
    cdpNetwork: "base",
    alchemyPath: "base-mainnet",
    thirdwebChain: "8453",
    explorerBaseUrl: "https://basescan.org/tx",
  },
};

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

function sha256Hex(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

async function ensureDirFor(filePath) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
}

export function actionHash(actionDetails) {
  return `0x${sha256Hex(stableJson(actionDetails))}`;
}

export function attestAction({ logger, agentId, actionDetails, actionHash: hash, metadata } = {}) {
  if (!logger) {
    return {
      status: "disabled",
      attestation_status: "pending",
      actionHash: hash || actionHash(actionDetails || {}),
      blockchain_tx_hash: "",
    };
  }
  return logger.enqueueAction(agentId, actionDetails, { actionHash: hash, metadata });
}

export function validateDASConfig(env = process.env) {
  const mode = env.DAAL_PROVIDER_MODE || "cdp";
  const network = env.DAAL_NETWORK || "base-sepolia";
  const errors = [];
  const warnings = [];

  try {
    daalNetwork(network);
  } catch (error) {
    errors.push(error.message);
  }

  if (env.DAAL_ENABLED === "true" && !env.DAAL_CONTRACT_ADDRESS) {
    errors.push("DAAL_CONTRACT_ADDRESS is required when DAAL_ENABLED=true");
  }

  if (mode === "cdp") {
    for (const key of ["CDP_API_KEY_ID", "CDP_API_KEY_SECRET", "CDP_WALLET_SECRET", "CDP_EVM_ACCOUNT_ADDRESS"]) {
      if (!env[key]) {
        errors.push(`${key} is required for DAAL_PROVIDER_MODE=cdp`);
      }
    }
    if (env.THIRDWEB_BACKEND_WALLET_ADDRESS && env.THIRDWEB_BACKEND_WALLET_ADDRESS !== env.CDP_EVM_ACCOUNT_ADDRESS) {
      warnings.push("THIRDWEB_BACKEND_WALLET_ADDRESS is ignored in cdp mode unless thirdweb Engine is used");
    }
  } else if (mode === "thirdweb-engine") {
    for (const key of ["THIRDWEB_ENGINE_URL", "THIRDWEB_ENGINE_ACCESS_TOKEN", "THIRDWEB_BACKEND_WALLET_ADDRESS"]) {
      if (!env[key]) {
        errors.push(`${key} is required for DAAL_PROVIDER_MODE=thirdweb-engine`);
      }
    }
    if (env.THIRDWEB_BACKEND_WALLET_ADDRESS === env.CDP_EVM_ACCOUNT_ADDRESS) {
      warnings.push(
        "Matching CDP_EVM_ACCOUNT_ADDRESS and THIRDWEB_BACKEND_WALLET_ADDRESS is not enough; the address must be registered as a thirdweb Engine backend wallet",
      );
    }
  } else if (mode === "ethers") {
    if (!env.DAAL_PRIVATE_KEY) {
      errors.push("DAAL_PRIVATE_KEY is required for DAAL_PROVIDER_MODE=ethers");
    }
    if (!env.DAAL_RPC_URL && !env.ALCHEMY_API_KEY) {
      errors.push("DAAL_RPC_URL or ALCHEMY_API_KEY is required for DAAL_PROVIDER_MODE=ethers");
    }
  } else {
    errors.push(`unsupported DAAL provider mode: ${mode}`);
  }

  if (!env.DAAL_RPC_URL && !env.ALCHEMY_API_KEY) {
    warnings.push("Alchemy verification is disabled until ALCHEMY_API_KEY or DAAL_RPC_URL is configured");
  }

  return { ok: errors.length === 0, mode, network, errors, warnings };
}

export function dasRuntimePlan(env = process.env) {
  const validation = validateDASConfig(env);
  return {
    ...validation,
    contractAddress: env.DAAL_CONTRACT_ADDRESS || "",
    writerAddress:
      validation.mode === "thirdweb-engine"
        ? env.THIRDWEB_BACKEND_WALLET_ADDRESS || ""
        : env.CDP_EVM_ACCOUNT_ADDRESS || env.THIRDWEB_BACKEND_WALLET_ADDRESS || "",
    thirdwebRole:
      validation.mode === "thirdweb-engine"
        ? "runtime contract writes through thirdweb Engine"
        : "contract deployment and dashboard management",
    cdpRole:
      validation.mode === "cdp"
        ? "runtime signer and transaction sender"
        : "server wallet identity/reference address",
    alchemyRole: env.ALCHEMY_API_KEY || env.DAAL_RPC_URL ? "receipt verification and reconciliation" : "not configured",
  };
}

export function daalNetwork(name = process.env.DAAL_NETWORK || "polygon-amoy") {
  const network = NETWORKS[name];
  if (!network) {
    throw new Error(`unsupported DAAL network: ${name}`);
  }
  return { name, ...network };
}

export function alchemyRpcUrl({ network = process.env.DAAL_NETWORK || "polygon-amoy", apiKey = process.env.ALCHEMY_API_KEY } = {}) {
  if (!apiKey) {
    return "";
  }
  const selected = daalNetwork(network);
  return `https://${selected.alchemyPath}.g.alchemy.com/v2/${apiKey}`;
}

function normalizeAddress(value) {
  return String(value || "").toLowerCase();
}

export function merkleRootHex(hashes) {
  if (hashes.length === 0) {
    throw new Error("cannot build Merkle root for empty batch");
  }
  let layer = hashes.map((hash) => Buffer.from(hash.replace(/^0x/, ""), "hex"));
  while (layer.length > 1) {
    const next = [];
    for (let index = 0; index < layer.length; index += 2) {
      const left = layer[index];
      const right = layer[index + 1] || left;
      next.push(Buffer.from(sha256Hex(Buffer.concat([left, right])), "hex"));
    }
    layer = next;
  }
  return `0x${layer[0].toString("hex")}`;
}

export class FileAttestationStore {
  constructor(options = {}) {
    this.path =
      options.path || process.env.DAAL_SYSTEM_OF_RECORD_FILE || "/var/lib/zt-provisioner/daal-attestations.jsonl";
  }

  async append(record) {
    await ensureDirFor(this.path);
    await fs.appendFile(this.path, `${JSON.stringify(record)}\n`, { mode: 0o600 });
  }

  async entries() {
    try {
      const content = await fs.readFile(this.path, "utf8");
      return content
        .trim()
        .split("\n")
        .filter(Boolean)
        .map((line) => JSON.parse(line));
    } catch (error) {
      if (error.code === "ENOENT") {
        return [];
      }
      throw error;
    }
  }
}

export class DAALogger {
  constructor(options = {}) {
    this.contract = options.contract || null;
    this.store = options.store || new FileAttestationStore(options.store);
    this.network = options.network || process.env.DAAL_NETWORK || "polygon-amoy";
    this.explorerBaseUrl = options.explorerBaseUrl || process.env.DAAL_EXPLORER_BASE_URL || daalNetwork(this.network).explorerBaseUrl;
    this.metadataBaseUri = options.metadataBaseUri || process.env.DAAL_METADATA_BASE_URI || "";
    this.waitForConfirmation = options.waitForConfirmation ?? false;
    this.batchSize = Number(options.batchSize || process.env.DAAL_BATCH_SIZE || 10);
    this.pending = [];
    this.inFlight = Promise.resolve();

    this.contract =
      this.contract ||
      options.contract ||
      createContractFromOptions({
        ...options,
        network: this.network,
      });
  }

  isEnabled() {
    return Boolean(this.contract);
  }

  metadataUri(actionHashValue) {
    if (!this.metadataBaseUri) {
      return "";
    }
    return `${this.metadataBaseUri.replace(/\/$/, "")}/${actionHashValue}`;
  }

  txLink(txHash) {
    if (!txHash) {
      return "";
    }
    return `${this.explorerBaseUrl.replace(/\/$/, "")}/${txHash}`;
  }

  async logAction(agentId, actionDetails, options = {}) {
    const hash = options.actionHash || actionHash(actionDetails);
    const metadata = options.metadata ?? this.metadataUri(hash);
    const submittedAt = new Date().toISOString();

    if (!this.contract) {
      const record = {
        agentId,
        actionHash: hash,
        metadata,
        status: "queued",
        attestation_status: "pending",
        txHash: "",
        blockchain_tx_hash: "",
        queueId: "",
        txLink: "",
        mode: "disabled",
        submittedAt,
      };
      await this.store.append(record);
      return record;
    }

    try {
      const tx = await this.contract.logAction(agentId, hash, metadata);
      if (this.waitForConfirmation && tx.wait) {
        await tx.wait();
      }
      const record = {
        agentId,
        actionHash: hash,
        metadata,
        status: "submitted",
        attestation_status: tx.hash ? "verified" : "pending",
        txHash: tx.hash,
        blockchain_tx_hash: tx.hash,
        queueId: tx.queueId || "",
        txLink: this.txLink(tx.hash),
        mode: "single",
        submittedAt,
      };
      await this.store.append(record);
      return record;
    } catch (error) {
      const record = {
        agentId,
        actionHash: hash,
        metadata,
        status: "failed",
        attestation_status: "failed",
        txHash: "",
        blockchain_tx_hash: "",
        queueId: "",
        txLink: "",
        mode: "single",
        error: error.message,
        submittedAt,
      };
      await this.store.append(record);
      throw error;
    }
  }

  enqueueAction(agentId, actionDetails, options = {}) {
    const hash = options.actionHash || actionHash(actionDetails);
    const metadata = options.metadata ?? this.metadataUri(hash);
    const queued = {
      agentId,
      actionDetails,
      actionHash: hash,
      metadata,
      queuedAt: new Date().toISOString(),
    };
    this.pending.push(queued);
    this.inFlight = this.inFlight.then(() => this.flushIfReady()).catch(() => undefined);
    return { status: "queued", attestation_status: "pending", actionHash: hash, metadata, blockchain_tx_hash: "" };
  }

  async flushIfReady() {
    if (this.pending.length >= this.batchSize) {
      await this.flush();
    }
  }

  async flush() {
    if (this.pending.length === 0) {
      return [];
    }
    const batch = this.pending.splice(0, this.batchSize);
    if (batch.length === 1) {
      return [await this.logAction(batch[0].agentId, batch[0].actionDetails, batch[0])];
    }
    return [await this.logBatch(batch)];
  }

  async drain() {
    await this.inFlight;
    const results = [];
    while (this.pending.length > 0) {
      results.push(...(await this.flush()));
      await this.inFlight;
    }
    return results;
  }

  async logBatch(batch) {
    const root = merkleRootHex(batch.map((item) => item.actionHash));
    const agentId = `batch:${os.hostname()}`;
    const metadata = JSON.stringify({
      count: batch.length,
      actionHashes: batch.map((item) => item.actionHash),
      queuedAt: batch.map((item) => item.queuedAt),
    });
    const submittedAt = new Date().toISOString();

    if (!this.contract) {
      const record = {
        agentId,
        actionHash: root,
        metadata,
        status: "queued",
        attestation_status: "pending",
        txHash: "",
        blockchain_tx_hash: "",
        queueId: "",
        txLink: "",
        mode: "batch-disabled",
        batchCount: batch.length,
        submittedAt,
      };
      await this.store.append(record);
      return record;
    }

    const tx = await this.contract.logBatch(agentId, root, metadata);
    if (this.waitForConfirmation && tx.wait) {
      await tx.wait();
    }
    const record = {
      agentId,
      actionHash: root,
      metadata,
      status: "submitted",
      attestation_status: tx.hash ? "verified" : "pending",
      txHash: tx.hash,
      blockchain_tx_hash: tx.hash,
      queueId: tx.queueId || "",
      txLink: this.txLink(tx.hash),
      mode: "batch",
      batchCount: batch.length,
      submittedAt,
    };
    await this.store.append(record);
    return record;
  }
}

export function createDAALoggerFromEnv() {
  if (process.env.DAAL_ENABLED !== "true") {
    return null;
  }
  const validation = validateDASConfig(process.env);
  if (!validation.ok) {
    throw new Error(`invalid DAS configuration: ${validation.errors.join("; ")}`);
  }
  return new DAALogger({
    providerMode: process.env.DAAL_PROVIDER_MODE,
    network: process.env.DAAL_NETWORK,
    rpcUrl: process.env.DAAL_RPC_URL || alchemyRpcUrl(),
    privateKey: process.env.DAAL_PRIVATE_KEY,
    contractAddress: process.env.DAAL_CONTRACT_ADDRESS,
    cdpAddress: process.env.CDP_EVM_ACCOUNT_ADDRESS,
    thirdwebEngineUrl: process.env.THIRDWEB_ENGINE_URL,
    thirdwebAccessToken: process.env.THIRDWEB_ENGINE_ACCESS_TOKEN,
    thirdwebBackendWalletAddress: process.env.THIRDWEB_BACKEND_WALLET_ADDRESS || process.env.CDP_EVM_ACCOUNT_ADDRESS,
    thirdwebChain: process.env.THIRDWEB_ENGINE_CHAIN,
    thirdwebTransactionMode: process.env.THIRDWEB_ENGINE_TRANSACTION_MODE,
    explorerBaseUrl: process.env.DAAL_EXPLORER_BASE_URL,
    metadataBaseUri: process.env.DAAL_METADATA_BASE_URI,
    batchSize: process.env.DAAL_BATCH_SIZE,
    useNonceManager: process.env.DAAL_USE_NONCE_MANAGER !== "false",
  });
}

export function createContractFromOptions(options = {}) {
  const providerMode = options.providerMode || process.env.DAAL_PROVIDER_MODE || "ethers";
  if (!options.contractAddress) {
    return null;
  }
  if (providerMode === "cdp") {
    return new CDPDAALContract({
      contractAddress: options.contractAddress,
      network: options.network,
      address: options.cdpAddress,
      cdpClient: options.cdpClient,
    });
  }
  if (providerMode === "thirdweb-engine") {
    return new ThirdwebEngineDAALContract({
      contractAddress: options.contractAddress,
      network: options.network,
      engineUrl: options.thirdwebEngineUrl,
      accessToken: options.thirdwebAccessToken,
      backendWalletAddress: options.thirdwebBackendWalletAddress,
      chain: options.thirdwebChain,
      transactionMode: options.thirdwebTransactionMode,
      fetchImpl: options.fetchImpl,
    });
  }
  if (providerMode === "ethers") {
    const rpcUrl = options.rpcUrl || alchemyRpcUrl({ network: options.network });
    if (!rpcUrl || !options.privateKey) {
      return null;
    }
    const provider = new JsonRpcProvider(rpcUrl);
    const wallet = new Wallet(options.privateKey, provider);
    const signer = options.useNonceManager === false ? wallet : new NonceManager(wallet);
    return new Contract(options.contractAddress, DAAL_ABI, signer);
  }
  throw new Error(`unsupported DAAL provider mode: ${providerMode}`);
}

export class CDPDAALContract {
  constructor(options = {}) {
    this.contractAddress = options.contractAddress;
    this.network = daalNetwork(options.network);
    this.address = options.address || process.env.CDP_EVM_ACCOUNT_ADDRESS || "";
    this.cdpClient = options.cdpClient || null;
    this.iface = new Interface(DAAL_ABI);
  }

  async client() {
    if (this.cdpClient) {
      return this.cdpClient;
    }
    const { CdpClient } = await import("@coinbase/cdp-sdk");
    this.cdpClient = new CdpClient();
    return this.cdpClient;
  }

  async send(functionName, args) {
    if (!this.address) {
      throw new Error("CDP_EVM_ACCOUNT_ADDRESS is required for DAAL_PROVIDER_MODE=cdp");
    }
    const cdp = await this.client();
    const data = this.iface.encodeFunctionData(functionName, args);
    const result = await cdp.evm.sendTransaction({
      address: this.address,
      network: this.network.cdpNetwork,
      transaction: {
        to: this.contractAddress,
        data,
        value: 0n,
      },
    });
    return {
      hash: result.transactionHash || result.hash,
      wait: async () => result,
    };
  }

  async logAction(agentId, actionHashValue, metadata) {
    return this.send("logAction", [agentId, actionHashValue, metadata]);
  }

  async logBatch(agentId, merkleRoot, metadata) {
    return this.send("logBatch", [agentId, merkleRoot, metadata]);
  }
}

export class ThirdwebEngineDAALContract {
  constructor(options = {}) {
    this.contractAddress = options.contractAddress;
    this.network = daalNetwork(options.network);
    this.engineUrl = String(options.engineUrl || process.env.THIRDWEB_ENGINE_URL || "").replace(/\/$/, "");
    this.accessToken = options.accessToken || process.env.THIRDWEB_ENGINE_ACCESS_TOKEN || "";
    this.backendWalletAddress = options.backendWalletAddress || process.env.THIRDWEB_BACKEND_WALLET_ADDRESS || "";
    this.chain = String(options.chain || process.env.THIRDWEB_ENGINE_CHAIN || this.network.thirdwebChain);
    this.transactionMode = options.transactionMode || process.env.THIRDWEB_ENGINE_TRANSACTION_MODE || "";
    this.fetchImpl = options.fetchImpl || globalThis.fetch;
  }

  async send(functionName, args) {
    if (!this.engineUrl) {
      throw new Error("THIRDWEB_ENGINE_URL is required for DAAL_PROVIDER_MODE=thirdweb-engine");
    }
    if (!this.accessToken) {
      throw new Error("THIRDWEB_ENGINE_ACCESS_TOKEN is required for DAAL_PROVIDER_MODE=thirdweb-engine");
    }
    if (!this.backendWalletAddress) {
      throw new Error("THIRDWEB_BACKEND_WALLET_ADDRESS is required and must be registered in thirdweb Engine");
    }
    if (!this.fetchImpl) {
      throw new Error("fetch is required for thirdweb Engine DAAL provider");
    }

    const headers = {
      "Content-Type": "application/json",
      Authorization: `Bearer ${this.accessToken}`,
      "x-backend-wallet-address": this.backendWalletAddress,
    };
    if (this.transactionMode) {
      headers["x-transaction-mode"] = this.transactionMode;
    }

    const response = await this.fetchImpl(
      `${this.engineUrl}/contract/${this.chain}/${this.contractAddress}/write`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({ functionName, args }),
      },
    );
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body?.error?.message || body?.message || `thirdweb Engine write failed: ${response.status}`);
    }
    const result = body.result || body;
    return {
      hash: result.transactionHash || result.txHash || result.hash || "",
      queueId: result.queueId || "",
      wait: async () => result,
    };
  }

  async logAction(agentId, actionHashValue, metadata) {
    return this.send("logAction", [agentId, actionHashValue, metadata]);
  }

  async logBatch(agentId, merkleRoot, metadata) {
    return this.send("logBatch", [agentId, merkleRoot, metadata]);
  }
}

export function verifyAttestationIntegrity({ actionDetails, record } = {}) {
  if (!record?.actionHash) {
    return { ok: false, reason: "record.actionHash is required" };
  }
  const recomputed = actionHash(actionDetails || {});
  return {
    ok: recomputed.toLowerCase() === String(record.actionHash).toLowerCase(),
    actionHash: record.actionHash,
    recomputedActionHash: recomputed,
    txHash: record.blockchain_tx_hash || record.txHash || "",
    reason:
      recomputed.toLowerCase() === String(record.actionHash).toLowerCase()
        ? "local record matches anchored action hash"
        : "local record does not match anchored action hash",
  };
}

export class AlchemyReceiptVerifier {
  constructor(options = {}) {
    this.network = options.network || process.env.DAAL_NETWORK || "base-sepolia";
    this.rpcUrl = options.rpcUrl || process.env.DAAL_RPC_URL || alchemyRpcUrl({ network: this.network });
    this.contractAddress = options.contractAddress || process.env.DAAL_CONTRACT_ADDRESS || "";
    this.fetchImpl = options.fetchImpl || globalThis.fetch;
  }

  async rpc(method, params) {
    if (!this.rpcUrl) {
      throw new Error("ALCHEMY_API_KEY or DAAL_RPC_URL is required for Alchemy receipt verification");
    }
    if (!this.fetchImpl) {
      throw new Error("fetch is required for Alchemy receipt verification");
    }
    const response = await this.fetchImpl(this.rpcUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
    });
    const body = await response.json();
    if (!response.ok || body.error) {
      throw new Error(body.error?.message || `Alchemy RPC failed: ${response.status}`);
    }
    return body.result;
  }

  async verifyTransaction(txHash, { contractAddress = this.contractAddress } = {}) {
    if (!/^0x[a-fA-F0-9]{64}$/.test(String(txHash || ""))) {
      return { ok: false, status: "invalid", reason: "transaction hash must be 0x-prefixed bytes32" };
    }
    const receipt = await this.rpc("eth_getTransactionReceipt", [txHash]);
    if (!receipt) {
      return { ok: false, status: "pending", txHash, reason: "transaction receipt not found yet" };
    }
    const chainStatus = receipt.status === "0x1" || receipt.status === 1 ? "verified" : "failed";
    const expectedTo = normalizeAddress(contractAddress);
    const actualTo = normalizeAddress(receipt.to);
    const contractMatches = !expectedTo || actualTo === expectedTo;
    return {
      ok: chainStatus === "verified" && contractMatches,
      status: chainStatus,
      txHash,
      blockNumber: receipt.blockNumber,
      from: receipt.from,
      to: receipt.to,
      contractMatches,
      reason: contractMatches ? "transaction receipt verified" : "transaction was not sent to configured DAAL contract",
    };
  }
}
