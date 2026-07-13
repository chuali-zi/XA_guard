ALTER TABLE xa_reference_tickets
  ADD COLUMN IF NOT EXISTS cancel_fingerprint text;
