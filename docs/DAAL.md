# Decentralized Attestation Service

DAAL/DAS anchors Zero Trust authorization decisions to an append-only decentralized ledger.

This is intentionally a trust-anchor MVP, not a cryptocurrency subsystem.

The CTO-facing message is mathematical attestation: the ledger stores action hashes or batch roots so a later reviewer can detect whether the local signed audit record was edited after the fact. It does not store raw agent chat, prompts, tool arguments, secrets, customer records, or policy files.

## Architecture

```text
request -> ZT-Infra policy decision -> local signed audit chain
                                      -> async attestAction() sidecar queue
                                      -> batch Merkle root or single action hash
                                      -> CDP Server Wallet transaction
                                      -> optional thirdweb Engine contract write
                                      -> DAALog smart contract
                                      -> Alchemy receipt verification
                                      -> local system-of-record cross reference
```

The primary authorization path does not wait for blockchain confirmation. `ActionAuditor` writes the local signed audit record and calls `attestAction(...)`, which queues the DAAL submission asynchronously.

## Current Provider Model

The MVP provider stack is:

- **thirdweb**: contract deployment and dashboard management. Engine remains optional if you create/register a thirdweb backend wallet.
- **Coinbase Developer Platform (CDP)**: default runtime server wallet identity/signing. Key material stays in Coinbase-managed infrastructure and is not committed to Git or stored in application source.
- **Alchemy**: Base RPC, transaction receipt verification, reconciliation, and provider observability.
- **Base Sepolia first**: default testnet for the 90-day MVP. Base mainnet is supported by configuration once costs, verification, and operations are ready.

The provider roles are intentionally replaceable. DAAL is an EVM contract and the system stores `agentId`, `actionHash`, and `txHash`; Alchemy can be replaced with another RPC provider, thirdweb with another deployment pipeline, and CDP with another managed or KMS-backed signer without changing the control-plane policy contract.

Use your own CDP and thirdweb wallet values:

```bash
CDP_EVM_ACCOUNT_ADDRESS=<YOUR_CDP_EVM_ACCOUNT_ADDRESS>
THIRDWEB_BACKEND_WALLET_ADDRESS=<YOUR_THIRDWEB_ENGINE_WALLET_ADDRESS>
```

use `DAAL_PROVIDER_MODE=cdp` unless the backend wallet is explicitly registered as a thirdweb Engine backend wallet. Matching the two variables does not give thirdweb signing authority over a CDP Server Wallet.

Check the effective plan before deploying:

```bash
DAAL_ENABLED=true \
DAAL_PROVIDER_MODE=cdp \
DAAL_NETWORK=base-sepolia \
CDP_EVM_ACCOUNT_ADDRESS=<YOUR_CDP_EVM_ACCOUNT_ADDRESS> \
THIRDWEB_BACKEND_WALLET_ADDRESS=<YOUR_THIRDWEB_ENGINE_WALLET_ADDRESS> \
node scripts/check-das-config.mjs
```

The management claim should be phrased precisely:

> Local signed audit records remain the immediate system of record. DAS asynchronously anchors each action hash or batch Merkle root to Base so later tampering can be detected by recomputing the local hash and comparing it to on-chain evidence.

## Verified State

Keep current contract addresses, sender addresses, transaction hashes, and explorer links in private release evidence or a reviewed public release note. Do not place live wallet linkage evidence in README-style operator documentation by default.

Use this non-secret environment shape for local or AWS smoke tests:

```bash
export DAAL_ENABLED=true
export DAAL_PROVIDER_MODE=cdp
export DAAL_NETWORK=base-sepolia
export DAAL_CONTRACT_ADDRESS=<YOUR_DAAL_CONTRACT_ADDRESS>
export DAAL_BATCH_SIZE=10
export CDP_EVM_ACCOUNT_ADDRESS=<YOUR_CDP_EVM_ACCOUNT_ADDRESS>
```

Secrets still need to come from AWS Secrets Manager, CI secrets, or a local gitignored environment file:

```bash
CDP_API_KEY_ID
CDP_API_KEY_SECRET
CDP_WALLET_SECRET
ALCHEMY_API_KEY
THIRDWEB_SECRET_KEY
```

Do not commit those values to this repository. The remaining production work is to add scheduled reconciliation, define alerting for stuck `pending` attestations, and prepare the Base mainnet runbook.

## Contract

The Solidity contract is:

```text
contracts/DAALog.sol
```

It stores append-only records:

```solidity
string agentId;
bytes32 actionHash;
uint256 timestamp;
string metadata;
```

It has no admin edit/delete function. A tampered local database row can be detected by recomputing the action hash and comparing it to the on-chain `actionHash`.

## Service API

The Node service interface is:

```js
import { attestAction, DAALogger } from "./src/daal.js";

const logger = new DAALogger({ contract, store });
const result = await logger.logAction("agent-1", { action: "aws.ec2.terminate_instances" });
```

For the authorization path, use the non-blocking sidecar hook:

```js
const daal = attestAction({
  logger,
  agentId: "agent-1",
  actionDetails: signedAuditRecord,
  actionHash: `0x${signedAuditRecord.current_hash}`,
});
```

`logAction(agentId, actionDetails)` returns:

```json
{
  "agentId": "agent-1",
  "actionHash": "0x...",
  "metadata": "",
  "status": "submitted",
  "attestation_status": "verified",
  "txHash": "0x...",
  "blockchain_tx_hash": "0x...",
  "queueId": "",
  "txLink": "https://amoy.polygonscan.com/tx/0x...",
  "mode": "single"
}
```

For thirdweb Engine, the immediate response may contain a `queueId` before a network transaction hash is available. In that case the local row remains `attestation_status = pending` until the queued transaction is reconciled to a Base transaction hash. In the current verified CDP direct mode, the smoke test returned a transaction hash immediately and marked the local record `verified` after receipt verification.

## Batching

`DAAL_BATCH_SIZE` defaults to `10`.

When the queue reaches the batch size, DAAL computes a Merkle root from the queued action hashes and submits one `logBatch(...)` transaction. This keeps authorization overhead low and reduces gas per action.

## Nonce Management

The production logger wraps the wallet with ethers v6 `NonceManager` by default. This prevents concurrent submissions from reusing the same nonce under load.

Set this only for debugging:

```bash
DAAL_USE_NONCE_MANAGER=false
```

## Configuration

Recommended MVP provider stack:

- CDP Server Wallet: default backend signer and transaction sender.
- thirdweb: contract deployment and optional Engine only after backend-wallet registration.
- Alchemy: Base RPC for receipt verification, reconciliation, and fallback `ethers` test mode.

```bash
DAAL_ENABLED=true
DAAL_PROVIDER_MODE=cdp
DAAL_NETWORK=base-sepolia
DAAL_CONTRACT_ADDRESS=0x...
DAAL_BATCH_SIZE=10

ALCHEMY_API_KEY=REPLACE_ME

CDP_API_KEY_ID=REPLACE_ME
CDP_API_KEY_SECRET=REPLACE_ME
CDP_WALLET_SECRET=REPLACE_ME
CDP_EVM_ACCOUNT_ADDRESS=0x...
```

Do not put CDP wallet secrets, thirdweb access tokens, or Alchemy keys in Git; load them from AWS Secrets Manager, your CI secret store, or the instance environment at deploy time.

`DAAL_PROVIDER_MODE=cdp` sends the encoded `DAALog.logAction(...)` or `DAALog.logBatch(...)` call through `cdp.evm.sendTransaction(...)`. CDP handles signing, gas estimation, and nonce sequencing for the server wallet.

## Optional thirdweb Engine Runtime

Use thirdweb Engine only if `THIRDWEB_BACKEND_WALLET_ADDRESS` is a wallet thirdweb Engine can use. A CDP Server Wallet address is not automatically usable by Engine just because the address is copied into an environment variable.

```bash
DAAL_PROVIDER_MODE=thirdweb-engine
THIRDWEB_ENGINE_URL=https://engine.thirdweb.com
THIRDWEB_ENGINE_ACCESS_TOKEN=REPLACE_ME
THIRDWEB_BACKEND_WALLET_ADDRESS=0x...
THIRDWEB_ENGINE_CHAIN=84532
THIRDWEB_ENGINE_TRANSACTION_MODE=
```

`DAAL_PROVIDER_MODE=thirdweb-engine` sends:

```http
POST /contract/<chain>/<contract_address>/write
Authorization: Bearer <thirdweb_engine_access_token>
x-backend-wallet-address: <cdp_server_wallet_address>
```

with a body like:

```json
{
  "functionName": "logAction",
  "args": ["agent-1", "0xACTION_HASH", "ipfs://metadata"]
}
```

Set `THIRDWEB_ENGINE_TRANSACTION_MODE=sponsored` only after confirming the selected chain and backend wallet mode support thirdweb sponsored transactions. Leave it empty by default.

For fallback/local EOA testing only:

```bash
DAAL_PROVIDER_MODE=ethers
DAAL_RPC_URL=https://polygon-amoy.g.alchemy.com/v2/REPLACE_ME
DAAL_PRIVATE_KEY=REPLACE_WITH_TESTNET_KEY
DAAL_CONTRACT_ADDRESS=0x...
DAAL_EXPLORER_BASE_URL=https://amoy.polygonscan.com/tx
DAAL_METADATA_BASE_URI=https://example.invalid/audit
```

Base Sepolia is also compatible:

```bash
DAAL_NETWORK=base-sepolia
DAAL_EXPLORER_BASE_URL=https://sepolia.basescan.org/tx
```

## Contract Deployment With thirdweb

Deploy and manage the contract through thirdweb:

```bash
export THIRDWEB_SECRET_KEY=REPLACE_ME
./scripts/deploy-daal-thirdweb.sh
```

The helper runs:

```bash
npx thirdweb deploy --contract --path ./contracts --file DAALog.sol --contract-name DAALog -k "$THIRDWEB_SECRET_KEY"
```

Select Base Sepolia in the thirdweb deployment UI for the MVP. After deployment, copy the contract address into `DAAL_CONTRACT_ADDRESS`.

## Alchemy RPC

Alchemy RPC URLs are derived from `DAAL_NETWORK` and `ALCHEMY_API_KEY`:

```text
polygon-amoy -> https://polygon-amoy.g.alchemy.com/v2/<api-key>
base-sepolia -> https://base-sepolia.g.alchemy.com/v2/<api-key>
base-mainnet -> https://base-mainnet.g.alchemy.com/v2/<api-key>
```

For `DAAL_PROVIDER_MODE=thirdweb-engine` or `cdp`, Alchemy is not on the primary authorization path and is not the system signer. Use it for:

- `eth_getTransactionReceipt` reconciliation after thirdweb Engine/CDP returns a transaction hash;
- confirming the transaction succeeded and was sent to the configured `DAAL_CONTRACT_ADDRESS`;
- Base Sepolia/Base mainnet RPC reads for validation tooling;
- fallback `ethers` mode in local/test deployments.

Do not use Alchemy Gas Manager as the default MVP gas path. Alchemy Gas Manager is useful for smart-wallet/paymaster flows, but the current DAS write path is a backend contract write through thirdweb Engine with a CDP-managed backend wallet. Revisit Gas Manager only if the product moves from server-wallet contract writes to account-abstraction wallets.

The provisioner includes `AlchemyReceiptVerifier`:

```js
import { AlchemyReceiptVerifier } from "./src/daal.js";

const verifier = new AlchemyReceiptVerifier({
  network: "base-sepolia",
  contractAddress: process.env.DAAL_CONTRACT_ADDRESS,
});

const result = await verifier.verifyTransaction("0xTRANSACTION_HASH");
```

It returns `verified`, `pending`, or `failed` semantics suitable for updating `agent_logs.attestation_status`.

## CDP Server Wallet

CDP Server Wallet mode requires:

```bash
CDP_API_KEY_ID
CDP_API_KEY_SECRET
CDP_WALLET_SECRET
CDP_EVM_ACCOUNT_ADDRESS
```

The provisioner does not store or expose private keys. CDP keeps the signing key material in the Coinbase-controlled wallet system, and the provisioner submits only transaction intent:

```json
{
  "address": "0xSYSTEM_WALLET",
  "network": "base-sepolia",
  "transaction": {
    "to": "0xDAALOG_CONTRACT",
    "data": "0xENCODED_LOG_ACTION_CALL",
    "value": "0"
  }
}
```

For `DAAL_PROVIDER_MODE=thirdweb-engine`, the backend wallet must be managed or registered in thirdweb Engine. Do not assume a CDP wallet address is usable by Engine unless it has been explicitly registered there. In the current MVP path, `DAAL_PROVIDER_MODE=cdp` is the working runtime and thirdweb is used for contract deployment and management.

Coinbase's public Server Wallet material describes secure enclave / TEE custody for wallet private keys. Treat that as a vendor control to validate during procurement; ZT-Infra's local control is that raw private keys are never committed, templated into Terraform, or handled by the provisioner in CDP mode.

## Local System Of Record

The MVP uses a durable JSONL store by default:

```text
/var/lib/zt-provisioner/daal-attestations.jsonl
```

The Postgres schema for a production system-of-record is:

```text
daal/schema.sql
```

This keeps the MVP deployable without adding a managed database, while preserving the Postgres migration path required by the product spec.

The production schema includes the requested cross-reference columns:

```sql
ALTER TABLE agent_logs
ADD COLUMN blockchain_tx_hash VARCHAR(255),
ADD COLUMN attestation_status attestation_status NOT NULL DEFAULT 'pending';
```

Status semantics:

| Status | Meaning |
| --- | --- |
| `pending` | Local audit was written and attestation was queued, but no Base transaction hash has been reconciled yet. |
| `verified` | A Base transaction hash exists for the action hash or batch Merkle root. |
| `failed` | The attestation provider rejected or failed the write. Local audit evidence still exists and should be retried. |

## Tamper Test

1. Record an action and capture `actionHash` plus `txHash`.
2. Edit the local system-of-record row.
3. Recompute the hash from the edited action details using `verifyAttestationIntegrity(...)`.
4. Use Alchemy receipt verification to confirm the transaction exists and targeted the DAAL contract.
5. Compare the recomputed local hash to the contract event or block explorer record.

If the local row was altered, the recomputed hash will no longer match the on-chain `actionHash`.

## Load Test

Covered locally by:

```bash
cd provisioner
npm test
```

The test simulates 50 agents making 5 tool calls each. With `DAAL_BATCH_SIZE=10`, the 250 actions become 25 batch submissions.

A Base Sepolia single-action smoke test has passed with CDP direct mode and Alchemy receipt verification. A sustained live load test is still pending and should use funded testnet gas plus provider rate-limit monitoring before investor or customer demos.

## References

- Base Sepolia first; Base mainnet only after verification, gas policy, and runbooks are complete.
- thirdweb CLI/dashboard for contract deployment and Engine for contract writes.
- Coinbase Developer Platform Server Wallets for server-side wallet identity/signing.
- Alchemy for Base read/verify tooling and fallback RPC testing.
- ethers v6 `NonceManager` for concurrent transaction sequencing.
- OpenZeppelin guidance on avoiding unnecessary admin mutation paths; this MVP contract has no edit/delete methods.
