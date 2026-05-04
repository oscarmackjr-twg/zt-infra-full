import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";

import {
  actionHash,
  alchemyRpcUrl,
  AlchemyReceiptVerifier,
  attestAction,
  CDPDAALContract,
  daalNetwork,
  dasRuntimePlan,
  DAALogger,
  FileAttestationStore,
  merkleRootHex,
  ThirdwebEngineDAALContract,
  validateDASConfig,
  verifyAttestationIntegrity,
} from "../src/daal.js";
import { ActionAuditor } from "../src/audit.js";

function tmpPath(name) {
  return path.join(os.tmpdir(), `zt-infra-v2-${process.pid}-${Date.now()}-${name}`);
}

class FakeContract {
  constructor() {
    this.calls = [];
  }

  async logAction(agentId, hash, metadata) {
    this.calls.push({ method: "logAction", agentId, hash, metadata });
    return { hash: `0xsingle${this.calls.length}`, wait: async () => ({ status: 1 }) };
  }

  async logBatch(agentId, hash, metadata) {
    this.calls.push({ method: "logBatch", agentId, hash, metadata });
    return { hash: `0xbatch${this.calls.length}`, wait: async () => ({ status: 1 }) };
  }
}

test("actionHash is stable bytes32 hex for object key order", () => {
  const first = actionHash({ b: 2, a: 1 });
  const second = actionHash({ a: 1, b: 2 });

  assert.equal(first, second);
  assert.match(first, /^0x[a-f0-9]{64}$/);
});

test("Alchemy network configuration builds official testnet RPC URLs", () => {
  assert.equal(daalNetwork("polygon-amoy").chainId, 80002);
  assert.equal(daalNetwork("base-sepolia").chainId, 84532);
  assert.equal(daalNetwork("base-mainnet").chainId, 8453);
  assert.equal(daalNetwork("base-sepolia").thirdwebChain, "84532");
  assert.equal(
    alchemyRpcUrl({ network: "polygon-amoy", apiKey: "demo-key" }),
    "https://polygon-amoy.g.alchemy.com/v2/demo-key",
  );
  assert.equal(
    alchemyRpcUrl({ network: "base-sepolia", apiKey: "demo-key" }),
    "https://base-sepolia.g.alchemy.com/v2/demo-key",
  );
  assert.equal(
    alchemyRpcUrl({ network: "base-mainnet", apiKey: "demo-key" }),
    "https://base-mainnet.g.alchemy.com/v2/demo-key",
  );
});

test("Alchemy receipt verifier confirms mined transactions target DAAL contract", async () => {
  const calls = [];
  const verifier = new AlchemyReceiptVerifier({
    rpcUrl: "https://base-sepolia.g.alchemy.com/v2/demo",
    contractAddress: "0x000000000000000000000000000000000000dEaD",
    fetchImpl: async (url, request) => {
      calls.push({ url, request: JSON.parse(request.body) });
      return {
        ok: true,
        async json() {
          return {
            jsonrpc: "2.0",
            id: 1,
            result: {
              transactionHash: "0x" + "1".repeat(64),
              status: "0x1",
              blockNumber: "0x123",
              from: "0x000000000000000000000000000000000000bEEF",
              to: "0x000000000000000000000000000000000000dEaD",
            },
          };
        },
      };
    },
  });

  const result = await verifier.verifyTransaction("0x" + "1".repeat(64));

  assert.equal(result.ok, true);
  assert.equal(result.status, "verified");
  assert.equal(result.contractMatches, true);
  assert.equal(calls[0].url, "https://base-sepolia.g.alchemy.com/v2/demo");
  assert.equal(calls[0].request.method, "eth_getTransactionReceipt");
});

test("Alchemy receipt verifier flags contract mismatch and pending receipts", async () => {
  const verifier = new AlchemyReceiptVerifier({
    rpcUrl: "https://base-sepolia.g.alchemy.com/v2/demo",
    contractAddress: "0x000000000000000000000000000000000000dEaD",
    fetchImpl: async () => ({
      ok: true,
      async json() {
        return {
          result: {
            transactionHash: "0x" + "2".repeat(64),
            status: "0x1",
            to: "0x0000000000000000000000000000000000000001",
          },
        };
      },
    }),
  });
  const mismatch = await verifier.verifyTransaction("0x" + "2".repeat(64));
  assert.equal(mismatch.ok, false);
  assert.equal(mismatch.contractMatches, false);

  const pendingVerifier = new AlchemyReceiptVerifier({
    rpcUrl: "https://base-sepolia.g.alchemy.com/v2/demo",
    fetchImpl: async () => ({ ok: true, async json() { return { result: null }; } }),
  });
  const pending = await pendingVerifier.verifyTransaction("0x" + "3".repeat(64));
  assert.equal(pending.ok, false);
  assert.equal(pending.status, "pending");
});

test("thirdweb Engine adapter queues contract write with sponsored gas header", async () => {
  const requests = [];
  const contract = new ThirdwebEngineDAALContract({
    contractAddress: "0x000000000000000000000000000000000000dEaD",
    network: "base-sepolia",
    engineUrl: "https://engine.example",
    accessToken: "engine-token",
    backendWalletAddress: "0x000000000000000000000000000000000000bEEF",
    transactionMode: "sponsored",
    fetchImpl: async (url, request) => {
      requests.push({ url, request });
      return {
        ok: true,
        async json() {
          return { result: { queueId: "queue-1", transactionHash: "0xthirdweb" } };
        },
      };
    },
  });

  const tx = await contract.logAction("agent-1", actionHash({ n: 1 }), "ipfs://metadata");

  assert.equal(tx.hash, "0xthirdweb");
  assert.equal(tx.queueId, "queue-1");
  assert.equal(
    requests[0].url,
    "https://engine.example/contract/84532/0x000000000000000000000000000000000000dEaD/write",
  );
  assert.equal(requests[0].request.headers.Authorization, "Bearer engine-token");
  assert.equal(requests[0].request.headers["x-backend-wallet-address"], "0x000000000000000000000000000000000000bEEF");
  assert.equal(requests[0].request.headers["x-transaction-mode"], "sponsored");
  assert.deepEqual(JSON.parse(requests[0].request.body), {
    functionName: "logAction",
    args: ["agent-1", actionHash({ n: 1 }), "ipfs://metadata"],
  });
});

test("DAS config defaults to CDP direct mode for the current CDP wallet setup", () => {
  const env = {
    DAAL_ENABLED: "true",
    DAAL_PROVIDER_MODE: "cdp",
    DAAL_NETWORK: "base-sepolia",
    DAAL_CONTRACT_ADDRESS: "0x000000000000000000000000000000000000dEaD",
    CDP_API_KEY_ID: "key-id",
    CDP_API_KEY_SECRET: "secret",
    CDP_WALLET_SECRET: "wallet-secret",
    CDP_EVM_ACCOUNT_ADDRESS: "0x1111111111111111111111111111111111111111",
    THIRDWEB_BACKEND_WALLET_ADDRESS: "0x1111111111111111111111111111111111111111",
    ALCHEMY_API_KEY: "alchemy",
  };

  const validation = validateDASConfig(env);
  const plan = dasRuntimePlan(env);

  assert.equal(validation.ok, true);
  assert.equal(plan.mode, "cdp");
  assert.equal(plan.writerAddress, "0x1111111111111111111111111111111111111111");
  assert.equal(plan.thirdwebRole, "contract deployment and dashboard management");
  assert.equal(plan.cdpRole, "runtime signer and transaction sender");
  assert.equal(plan.alchemyRole, "receipt verification and reconciliation");
});

test("DAS config warns when a CDP address is reused as thirdweb Engine wallet", () => {
  const validation = validateDASConfig({
    DAAL_ENABLED: "true",
    DAAL_PROVIDER_MODE: "thirdweb-engine",
    DAAL_NETWORK: "base-sepolia",
    DAAL_CONTRACT_ADDRESS: "0x000000000000000000000000000000000000dEaD",
    THIRDWEB_ENGINE_URL: "https://engine.example",
    THIRDWEB_ENGINE_ACCESS_TOKEN: "token",
    THIRDWEB_BACKEND_WALLET_ADDRESS: "0x1111111111111111111111111111111111111111",
    CDP_EVM_ACCOUNT_ADDRESS: "0x1111111111111111111111111111111111111111",
  });

  assert.equal(validation.ok, true);
  assert.ok(validation.warnings.some((warning) => warning.includes("registered as a thirdweb Engine backend wallet")));
});

test("merkleRootHex returns deterministic bytes32 root", () => {
  const root = merkleRootHex([actionHash({ n: 1 }), actionHash({ n: 2 }), actionHash({ n: 3 })]);

  assert.match(root, /^0x[a-f0-9]{64}$/);
  assert.equal(root, merkleRootHex([actionHash({ n: 1 }), actionHash({ n: 2 }), actionHash({ n: 3 })]));
});

test("logAction submits to contract and stores transaction cross reference", async () => {
  const store = new FileAttestationStore({ path: tmpPath("daal.jsonl") });
  const contract = new FakeContract();
  const logger = new DAALogger({
    contract,
    store,
    explorerBaseUrl: "https://amoy.polygonscan.com/tx",
    waitForConfirmation: true,
  });

  const result = await logger.logAction("agent-1", { action: "zt.status.read" });

  assert.equal(contract.calls.length, 1);
  assert.equal(contract.calls[0].method, "logAction");
  assert.equal(result.status, "submitted");
  assert.equal(result.txHash, "0xsingle1");
  assert.equal(result.txLink, "https://amoy.polygonscan.com/tx/0xsingle1");
  assert.equal((await store.entries())[0].txHash, "0xsingle1");
});

test("CDP contract adapter encodes contract call and sends through CDP Server Wallet", async () => {
  const sent = [];
  const contract = new CDPDAALContract({
    contractAddress: "0x000000000000000000000000000000000000dEaD",
    network: "base-sepolia",
    address: "0x000000000000000000000000000000000000bEEF",
    cdpClient: {
      evm: {
        async sendTransaction(request) {
          sent.push(request);
          return { transactionHash: "0xcdp" };
        },
      },
    },
  });

  const tx = await contract.logAction("agent-1", actionHash({ n: 1 }), "ipfs://metadata");

  assert.equal(tx.hash, "0xcdp");
  assert.equal(sent.length, 1);
  assert.equal(sent[0].address, "0x000000000000000000000000000000000000bEEF");
  assert.equal(sent[0].network, "base-sepolia");
  assert.equal(sent[0].transaction.to, "0x000000000000000000000000000000000000dEaD");
  assert.match(sent[0].transaction.data, /^0x/);
  assert.equal(sent[0].transaction.value, 0n);
});

test("enqueueAction is non-blocking and batches once threshold is reached", async () => {
  const store = new FileAttestationStore({ path: tmpPath("batch.jsonl") });
  const contract = new FakeContract();
  const logger = new DAALogger({ contract, store, batchSize: 3 });

  const queued = [
    logger.enqueueAction("agent-1", { n: 1 }),
    logger.enqueueAction("agent-2", { n: 2 }),
    logger.enqueueAction("agent-3", { n: 3 }),
  ];

  assert.deepEqual(
    queued.map((item) => item.status),
    ["queued", "queued", "queued"],
  );
  await logger.inFlight;

  assert.equal(contract.calls.length, 1);
  assert.equal(contract.calls[0].method, "logBatch");
  const entries = await store.entries();
  assert.equal(entries.length, 1);
  assert.equal(entries[0].mode, "batch");
  assert.equal(entries[0].batchCount, 3);
});

test("ActionAuditor records local audit immediately and queues DAAL asynchronously", async () => {
  const stateFile = tmpPath("audit-chain.jsonl");
  const store = new FileAttestationStore({ path: tmpPath("audit-daal.jsonl") });
  const contract = new FakeContract();
  const daal = new DAALogger({ contract, store, batchSize: 10 });
  const auditor = new ActionAuditor({
    stateFile,
    daal,
    signer: async () => ({ algorithm: "test", key_id: "key", signature: "sig" }),
  });

  const started = process.hrtime.bigint();
  const record = await auditor.record({
    actor: "agent-1",
    action: "aws.ec2.terminate_instances",
    resource: "i-danger",
    decision: "deny",
    reason: "blocked",
  });
  const elapsedMs = Number(process.hrtime.bigint() - started) / 1_000_000;

  assert.ok(elapsedMs < 10, `audit path took ${elapsedMs}ms`);
  assert.equal(record.daal.status, "queued");
  assert.equal(record.daal.actionHash, `0x${record.current_hash}`);
  assert.equal(contract.calls.length, 0);

  await daal.flush();
  assert.equal(contract.calls.length, 1);
  assert.equal((await fs.readFile(stateFile, "utf8")).trim().split("\n").length, 1);
});

test("attestAction returns pending status without blocking on blockchain confirmation", async () => {
  const store = new FileAttestationStore({ path: tmpPath("attest-action.jsonl") });
  const contract = new FakeContract();
  const logger = new DAALogger({ contract, store, batchSize: 2 });
  const queued = attestAction({
    logger,
    agentId: "agent-1",
    actionDetails: { action: "tool.call", timestamp: "2026-05-02T00:00:00.000Z" },
  });

  assert.equal(queued.status, "queued");
  assert.equal(queued.attestation_status, "pending");
  assert.equal(queued.blockchain_tx_hash, "");
  assert.equal(contract.calls.length, 0);
});

test("attestation integrity verifier detects local system-of-record tampering", () => {
  const actionDetails = { agentId: "agent-1", action: "tool.call", payload: { amount: 1 } };
  const record = { actionHash: actionHash(actionDetails), blockchain_tx_hash: "0xchain" };

  assert.equal(verifyAttestationIntegrity({ actionDetails, record }).ok, true);
  assert.equal(
    verifyAttestationIntegrity({
      actionDetails: { agentId: "agent-1", action: "tool.call", payload: { amount: 999 } },
      record,
    }).ok,
    false,
  );
});

test("50 concurrent agents with 5 calls each are queued and batched without nonce sequencing errors", async () => {
  const store = new FileAttestationStore({ path: tmpPath("load.jsonl") });
  const contract = new FakeContract();
  const logger = new DAALogger({ contract, store, batchSize: 10 });

  const agents = Array.from({ length: 50 }, (_, agentIndex) => `agent-${agentIndex}`);
  await Promise.all(
    agents.flatMap((agentId) =>
      Array.from({ length: 5 }, (_, callIndex) =>
        Promise.resolve(logger.enqueueAction(agentId, { agentId, callIndex, action: "tool.call" })),
      ),
    ),
  );

  await logger.drain();

  assert.equal(contract.calls.length, 25);
  assert.equal((await store.entries()).length, 25);
  assert.ok(contract.calls.every((call) => call.method === "logBatch"));
});
