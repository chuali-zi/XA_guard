CREATE TABLE IF NOT EXISTS xa_schema_versions (
  version integer PRIMARY KEY,
  name text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS xa_assignments (
  assignment_id text PRIMARY KEY,
  tenant_id text NOT NULL,
  subject_type text NOT NULL CHECK (subject_type IN ('human', 'group')),
  subject_id text NOT NULL,
  agent_id text NOT NULL,
  tools jsonb NOT NULL,
  data_domains jsonb NOT NULL,
  valid_from timestamptz NOT NULL DEFAULT now(),
  valid_until timestamptz,
  version integer NOT NULL DEFAULT 1,
  changed_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz,
  CONSTRAINT xa_assignment_validity CHECK (valid_until IS NULL OR valid_until > valid_from)
);
CREATE UNIQUE INDEX IF NOT EXISTS xa_assignments_active_scope
  ON xa_assignments(tenant_id, subject_type, subject_id, agent_id)
  WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS xa_assignments_lookup
  ON xa_assignments(tenant_id, agent_id, subject_type, subject_id)
  WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS xa_effects (
  effect_id text PRIMARY KEY,
  tenant_id text NOT NULL,
  trace_id text NOT NULL,
  principal_sub text NOT NULL,
  principal_username text NOT NULL,
  agent_id text NOT NULL,
  data_domain text NOT NULL,
  tool_name text NOT NULL,
  args_sha256 text NOT NULL,
  contract_version text NOT NULL,
  contract_hash text NOT NULL,
  contract_snapshot jsonb NOT NULL,
  side_effect_level text NOT NULL,
  reversibility text NOT NULL,
  status text NOT NULL,
  prepared_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  undo_expires_at timestamptz NOT NULL,
  key_id text,
  wrapped_dek bytea,
  recovery_nonce bytea,
  recovery_ciphertext bytea,
  result_sha256 text NOT NULL DEFAULT '',
  downstream_reference text NOT NULL DEFAULT '',
  compensation_trace_id text NOT NULL DEFAULT '',
  retry_count integer NOT NULL DEFAULT 0,
  next_attempt_at timestamptz,
  lease_owner text,
  lease_until timestamptz,
  heartbeat_at timestamptz,
  last_error_code text NOT NULL DEFAULT '',
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS xa_effects_tenant_time ON xa_effects(tenant_id, prepared_at DESC);
CREATE INDEX IF NOT EXISTS xa_effects_worker_queue
  ON xa_effects(status, next_attempt_at, lease_until)
  WHERE status IN ('approved', 'retry_wait', 'compensating');

CREATE TABLE IF NOT EXISTS xa_undo_requests (
  request_id text PRIMARY KEY,
  effect_id text NOT NULL REFERENCES xa_effects(effect_id),
  tenant_id text NOT NULL,
  idempotency_sha256 text NOT NULL,
  requester_sub text NOT NULL,
  requester_username text NOT NULL,
  reason_sha256 text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  approver_sub text,
  approver_username text,
  decision_reason_sha256 text,
  compensation_args_sha256 text NOT NULL DEFAULT '',
  internal_authorization text,
  requested_at timestamptz NOT NULL DEFAULT now(),
  decided_at timestamptz,
  UNIQUE (tenant_id, effect_id, idempotency_sha256)
);
CREATE INDEX IF NOT EXISTS xa_undo_pending ON xa_undo_requests(tenant_id, status, requested_at);

CREATE TABLE IF NOT EXISTS xa_effect_events (
  seq bigserial PRIMARY KEY,
  tenant_id text NOT NULL,
  effect_id text NOT NULL REFERENCES xa_effects(effect_id),
  event_type text NOT NULL,
  actor_sub text NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  payload jsonb NOT NULL,
  prev_hash text NOT NULL,
  record_hash text NOT NULL
);
CREATE INDEX IF NOT EXISTS xa_effect_events_timeline ON xa_effect_events(tenant_id, effect_id, seq);

CREATE TABLE IF NOT EXISTS xa_control_events (
  seq bigserial PRIMARY KEY,
  tenant_id text NOT NULL,
  event_type text NOT NULL,
  actor_sub text NOT NULL,
  target_id text NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  payload jsonb NOT NULL,
  prev_hash text NOT NULL,
  record_hash text NOT NULL
);
CREATE INDEX IF NOT EXISTS xa_control_events_tenant ON xa_control_events(tenant_id, seq);

