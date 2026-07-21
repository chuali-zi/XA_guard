CREATE OR REPLACE FUNCTION xa_lock_and_read_chain_tail(
  p_chain text,
  p_tenant_id text
) RETURNS text
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
  tail_hash text;
BEGIN
  IF p_chain = 'effect' THEN
    PERFORM pg_advisory_xact_lock(hashtext('effect-chain:' || p_tenant_id));
    SELECT record_hash INTO tail_hash
      FROM xa_effect_events
     WHERE tenant_id = p_tenant_id
     ORDER BY seq DESC
     LIMIT 1;
  ELSIF p_chain = 'gate6' THEN
    PERFORM pg_advisory_xact_lock(hashtext('gate6-chain:' || p_tenant_id));
    SELECT record_hash INTO tail_hash
      FROM xa_gate6_events
     WHERE tenant_id = p_tenant_id
     ORDER BY seq DESC
     LIMIT 1;
  ELSE
    RAISE EXCEPTION 'unsupported XA-Guard chain: %', p_chain;
  END IF;

  RETURN COALESCE(tail_hash, '');
END;
$$;
