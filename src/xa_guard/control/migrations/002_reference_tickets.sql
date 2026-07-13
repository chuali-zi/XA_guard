CREATE TABLE IF NOT EXISTS xa_reference_tickets (
  ticket_id text PRIMARY KEY,
  tenant_id text NOT NULL,
  title text NOT NULL,
  description text NOT NULL,
  priority text NOT NULL,
  state text NOT NULL CHECK (state IN ('open', 'cancelled')),
  create_effect_id text NOT NULL UNIQUE,
  create_fingerprint text NOT NULL,
  cancel_idempotency_key text,
  correlation_id text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  cancelled_at timestamptz
);
CREATE INDEX IF NOT EXISTS xa_reference_tickets_tenant ON xa_reference_tickets(tenant_id, created_at DESC);

