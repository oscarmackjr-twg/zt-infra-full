#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTRACT_FILE="${ROOT_DIR}/contracts/DAALog.sol"

: "${THIRDWEB_SECRET_KEY:?THIRDWEB_SECRET_KEY is required. Create a thirdweb project secret and export it first.}"

if [ ! -f "${CONTRACT_FILE}" ]; then
  echo "missing contract: ${CONTRACT_FILE}" >&2
  exit 1
fi

echo "Deploying DAALog with thirdweb..."
echo "Contract: ${CONTRACT_FILE}"
echo "Select Base Sepolia for the MVP. Use Base mainnet only after explorer verification and gas policy are ready."

npx thirdweb deploy \
  --contract \
  --path "${ROOT_DIR}/contracts" \
  --file "DAALog.sol" \
  --contract-name "DAALog" \
  -k "${THIRDWEB_SECRET_KEY}"
