# Enterprise Readiness Notes

This document captures the CTO-facing operating model for the DAAL/DAS integration.

## Positioning

DAAL is a mathematical attestation layer, not a crypto feature.

The business outcome is non-repudiation: after ZT-Infra makes an authorization decision, the local signed audit record can be compared against an independently anchored hash. If a privileged operator later edits the local system of record, the recomputed hash no longer matches the on-chain evidence.

Approved phrasing:

```text
ZT-Infra anchors hashes of agent authorization decisions to Base Sepolia so local audit records become independently tamper-evident.
```

Avoid:

```text
Every production audit log is blockchain verified.
```

That stronger claim requires reconciliation SLOs, alerting, delivery-rate evidence, retention policy, and Base mainnet readiness.

## Life Of A Request

```text
Tailscale / SSM access
  -> POST /actions policy decision
  -> deny stops execution, allow enters broker
  -> Docker / Nono / future cloud broker execution
  -> local hash-chained signed audit record
  -> async DAAL queue
  -> CDP Server Wallet writes action hash or batch root
  -> Base Sepolia DAALog event
  -> Alchemy receipt verification and reconciliation
```

## Data Handling Boundary

The DAAL contract receives:

- `agentId`
- `actionHash` or batch Merkle root
- timestamp
- optional metadata URI

The DAAL contract must not receive:

- raw chat messages;
- prompts;
- full tool arguments;
- secrets;
- customer records;
- full policy files;
- local execution output.

## Signer Policy

The MVP runtime uses Coinbase Developer Platform Server Wallets in `DAAL_PROVIDER_MODE=cdp`.

Operational requirements:

- private keys are not committed, copied into Terraform, or written to application source;
- CDP credential material is loaded from AWS Secrets Manager into `/etc/zt-provisioner/daal.env`;
- the provisioner submits transaction intent to CDP rather than handling a raw EOA private key;
- fallback `DAAL_PROVIDER_MODE=ethers` is for local testnet development only.

Coinbase's public Server Wallet positioning describes secure enclave / TEE custody for wallet private keys. Treat that as a vendor control to validate during procurement and vendor-risk review.

## Failure Behavior

| Failure | Expected Behavior |
| --- | --- |
| Policy engine unavailable | Fail closed; protected action does not run. |
| Broker unavailable | Decision may be `allow`, but execution fails operationally. |
| CDP unavailable | Local audit remains durable; DAAL status is `pending` or `failed`; action execution is not blocked by ledger confirmation. |
| Alchemy unavailable | Receipt verification is delayed; use another RPC provider or retry later. |
| thirdweb unavailable | Deployment or optional Engine path is delayed; CDP direct mode can continue if configured. |
| Base congestion | DAAL submission is delayed; local audit and retry queue remain the immediate evidence. |

## Vendor Portability

The product boundary is `agentId + actionHash + txHash`.

| Current Choice | Portability Path |
| --- | --- |
| Base Sepolia / Base | Any EVM chain with the DAALog contract. |
| Alchemy RPC | Another EVM RPC provider or self-hosted node. |
| thirdweb deployment tooling | Remix, Foundry, Hardhat, or native deployment pipeline. |
| CDP Server Wallet | Another managed signer, KMS-backed signer, or controlled EOA signer. |

## 10-Minute Web3 Runtime Values

Non-secret values:

```bash
DAAL_ENABLED=true
DAAL_PROVIDER_MODE=cdp
DAAL_NETWORK=base-sepolia
DAAL_CONTRACT_ADDRESS=<YOUR_DAAL_CONTRACT_ADDRESS>
CDP_EVM_ACCOUNT_ADDRESS=<YOUR_CDP_EVM_ACCOUNT_ADDRESS>
```

Secret values belong in AWS Secrets Manager:

```bash
CDP_API_KEY_ID
CDP_API_KEY_SECRET
CDP_WALLET_SECRET
ALCHEMY_API_KEY
THIRDWEB_SECRET_KEY
```

Validate configuration before deployment:

```bash
DAAL_ENABLED=true \
DAAL_PROVIDER_MODE=cdp \
DAAL_NETWORK=base-sepolia \
DAAL_CONTRACT_ADDRESS=<YOUR_DAAL_CONTRACT_ADDRESS> \
CDP_EVM_ACCOUNT_ADDRESS=<YOUR_CDP_EVM_ACCOUNT_ADDRESS> \
node scripts/check-das-config.mjs
```
