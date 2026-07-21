-- Gate6 records sit just above PostgreSQL's TOAST threshold.  LZ4 keeps the
-- full replayable JSONB payload while reducing compression CPU on each of the
-- two durable audit writes in the protected request path.
ALTER TABLE xa_gate6_events
  ALTER COLUMN record SET STORAGE EXTENDED;

ALTER TABLE xa_gate6_events
  ALTER COLUMN record SET COMPRESSION lz4;
