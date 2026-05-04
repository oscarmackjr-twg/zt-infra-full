DO $$
BEGIN
  CREATE TYPE attestation_status AS ENUM ('pending', 'verified', 'failed');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS agent_logs (
  id BIGSERIAL PRIMARY KEY,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  resource TEXT NOT NULL DEFAULT '',
  decision TEXT NOT NULL CHECK (decision IN ('allow', 'deny')),
  reason TEXT NOT NULL DEFAULT '',
  action_payload JSONB NOT NULL,
  action_hash CHAR(66) NOT NULL,
  previous_hash CHAR(64) NOT NULL,
  current_hash CHAR(64) NOT NULL,
  kms_signature JSONB NOT NULL DEFAULT '{}'::jsonb,
  blockchain_tx_hash VARCHAR(255),
  attestation_status attestation_status NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE agent_logs
  ADD COLUMN IF NOT EXISTS blockchain_tx_hash VARCHAR(255),
  ADD COLUMN IF NOT EXISTS attestation_status attestation_status NOT NULL DEFAULT 'pending';

CREATE INDEX IF NOT EXISTS agent_logs_action_hash_idx
  ON agent_logs(action_hash);

CREATE TABLE IF NOT EXISTS daal_attestations (
  id BIGSERIAL PRIMARY KEY,
  agent_id TEXT NOT NULL,
  action_hash CHAR(66) NOT NULL,
  metadata TEXT NOT NULL DEFAULT '',
  tx_hash TEXT,
  blockchain_tx_hash VARCHAR(255),
  status TEXT NOT NULL CHECK (status IN ('queued', 'submitted', 'confirmed', 'failed')),
  attestation_status attestation_status NOT NULL DEFAULT 'pending',
  queue_id TEXT NOT NULL DEFAULT '',
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE daal_attestations
  ADD COLUMN IF NOT EXISTS blockchain_tx_hash VARCHAR(255),
  ADD COLUMN IF NOT EXISTS attestation_status attestation_status NOT NULL DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS queue_id TEXT NOT NULL DEFAULT '';

CREATE UNIQUE INDEX IF NOT EXISTS daal_attestations_action_hash_idx
  ON daal_attestations(action_hash);
