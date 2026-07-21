CREATE TABLE IF NOT EXISTS xa_chain_tails (
  chain text NOT NULL CHECK (chain IN ('effect', 'gate6')),
  tenant_id text NOT NULL,
  tail_hash text NOT NULL DEFAULT '',
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (chain, tenant_id)
);

INSERT INTO xa_chain_tails(chain, tenant_id, tail_hash)
SELECT 'effect', tenant_id, record_hash
FROM (
  SELECT DISTINCT ON (tenant_id) tenant_id, record_hash
  FROM xa_effect_events
  ORDER BY tenant_id, seq DESC
) AS tails
ON CONFLICT (chain, tenant_id) DO UPDATE
SET tail_hash=EXCLUDED.tail_hash, updated_at=now();

INSERT INTO xa_chain_tails(chain, tenant_id, tail_hash)
SELECT 'gate6', tenant_id, record_hash
FROM (
  SELECT DISTINCT ON (tenant_id) tenant_id, record_hash
  FROM xa_gate6_events
  ORDER BY tenant_id, seq DESC
) AS tails
ON CONFLICT (chain, tenant_id) DO UPDATE
SET tail_hash=EXCLUDED.tail_hash, updated_at=now();
