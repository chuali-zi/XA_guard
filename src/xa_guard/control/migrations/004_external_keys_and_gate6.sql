ALTER TABLE xa_effects
  ADD COLUMN IF NOT EXISTS authorization_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS xa_gate6_events (
  seq bigserial PRIMARY KEY,
  tenant_id text NOT NULL,
  trace_id text NOT NULL,
  record jsonb NOT NULL,
  prev_hash text NOT NULL,
  record_hash text NOT NULL,
  source_instance text NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS xa_gate6_events_tenant_seq
  ON xa_gate6_events(tenant_id, seq);
CREATE INDEX IF NOT EXISTS xa_gate6_events_tenant_trace
  ON xa_gate6_events(tenant_id, trace_id, seq);
CREATE INDEX IF NOT EXISTS xa_gate6_events_tenant_hash
  ON xa_gate6_events(tenant_id, record_hash);
