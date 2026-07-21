CREATE INDEX IF NOT EXISTS xa_effect_events_tenant_seq_tail
  ON xa_effect_events(tenant_id, seq DESC)
  INCLUDE (record_hash);

CREATE INDEX IF NOT EXISTS xa_gate6_events_tenant_seq_tail
  ON xa_gate6_events(tenant_id, seq DESC)
  INCLUDE (record_hash);
