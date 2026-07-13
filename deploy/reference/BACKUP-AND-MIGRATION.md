# Reference PostgreSQL backup and legacy-effect migration

This runbook covers the XA-Guard control-plane database used by the reference
environment. It does not turn the reference Compose profile into a production
backup service. Production deployments need organization-owned retention,
encryption, access control, restore drills, and off-site storage.

## Backup and restore

Create a PostgreSQL custom-format backup without placing a database password on
the command line. `XA_BACKUP_DIR` must be an access-controlled location outside
the repository worktree:

```bash
export XA_BACKUP_DIR=/secure/backup/xa-guard
mkdir -p "$XA_BACKUP_DIR"
docker compose -f docker-compose.reference.yml exec -T postgres \
  pg_dump -U xaguard -d xaguard --format=custom --no-owner --no-acl \
  > "$XA_BACKUP_DIR/xaguard.dump"
```

The dump contains effects, assignments, approval state, reference tickets, and
schema-version rows. It does **not** contain Docker secrets. Back up
`.runtime/reference/secrets/kek_keyring` separately in an approved secret store;
without all referenced KEKs, encrypted recovery material in the database cannot
be decrypted. Do not place the keyring beside the database dump in ordinary
artifact storage.

Test a restore into a separate database first:

```bash
docker compose -f docker-compose.reference.yml exec -T postgres \
  createdb -U xaguard xaguard_restore
docker compose -f docker-compose.reference.yml exec -T postgres \
  pg_restore -U xaguard -d xaguard_restore --no-owner --no-acl --exit-on-error \
  < "$XA_BACKUP_DIR/xaguard.dump"
docker compose -f docker-compose.reference.yml exec -T postgres \
  psql -U xaguard -d xaguard_restore -c \
  "SELECT version,name,applied_at FROM xa_schema_versions ORDER BY version;"
```

For an approved in-place recovery, stop database writers first, retain a
pre-restore dump, restore with `--clean --if-exists`, then run the migration job
to apply any newer numbered migrations:

```bash
docker compose -f docker-compose.reference.yml stop xa-guard worker business-api console
docker compose -f docker-compose.reference.yml exec -T postgres \
  pg_restore -U xaguard -d xaguard --clean --if-exists --no-owner --no-acl \
  --exit-on-error < "$XA_BACKUP_DIR/xaguard.dump"
docker compose -f docker-compose.reference.yml run --rm migration
docker compose -f docker-compose.reference.yml up -d business-api xa-guard worker console
```

`pg_dump` gives a transactionally consistent snapshot of the `xaguard`
database. Keycloak uses the separate `keycloak` database and needs its own dump
or a repeatable realm export if identity state must also be recovered.

## Migration lock and schema versions

Numbered SQL files live in `src/xa_guard/control/migrations/`. The migration
runner records each applied version in `xa_schema_versions` and serializes
execution with PostgreSQL advisory lock `0x58414744`. Applied migration files
must not be edited; add a new, higher-numbered migration instead.

Run and inspect migrations with:

```bash
python -m xa_guard.control.migrate
psql "$XA_GUARD_DATABASE_URL" -c \
  "SELECT version,name,applied_at FROM xa_schema_versions ORDER BY version;"
```

The SQLite importer takes the same advisory lock, so it cannot overlap a schema
migration or another importer. Its inserts use `ON CONFLICT` and deterministic
legacy event identifiers, making reruns idempotent. A colliding `effect_id` that
does not belong to a prior legacy import is counted as a conflict; legacy events
are not attached to that effect.

## SQLite effect import

First validate the source without a PostgreSQL connection:

```bash
python scripts/import_sqlite_effects.py \
  --sqlite logs/resilience/effects.sqlite3 --dry-run
```

For an externally reachable PostgreSQL service, prefer a DSN file over a command
line secret:

```bash
python scripts/import_sqlite_effects.py \
  --sqlite logs/resilience/effects.sqlite3 \
  --database-url-file /run/secrets/database_url
```

The reference database is only reachable on the Compose `data` network. Run the
tool as a one-off migration container, binding the script and legacy database
read-only:

```bash
docker compose -f docker-compose.reference.yml run --rm \
  -v "$PWD/scripts/import_sqlite_effects.py:/app/import_sqlite_effects.py:ro" \
  -v "$PWD/logs/resilience/effects.sqlite3:/import/effects.sqlite3:ro" \
  migration python /app/import_sqlite_effects.py \
  --sqlite /import/effects.sqlite3 \
  --database-url-file /run/secrets/database_url
```

The tool also accepts `XA_GUARD_DATABASE_URL` or
`XA_GUARD_DATABASE_URL_FILE`. Successful output contains counts only; it never
prints the DSN, recovery data, event contents, or effect identifiers.

### Import boundary

- The SQLite file is opened read-only. The importer selects only public effect
  metadata and public event columns.
- It never selects or decrypts the legacy `nonce`, `recovery_ciphertext`, or
  `key_id`, and it never imports legacy `undo_requests`.
- Legacy single-key ciphertext is incompatible with the PostgreSQL per-effect
  DEK/KEK envelope. Every imported effect is therefore stored with
  `status=manual_required`, `reversibility=manual_required`, no wrapped DEK, and
  `last_error_code=legacy_recovery_format_incompatible`.
- Original status, reversibility, and compensation tool name are retained only
  as non-executable legacy contract metadata. They do not make an effect
  undoable.
- Legacy SQLite did not store effect or event timestamps. Import/complete/event
  timestamps therefore represent import time, not the original action time.
- The old global event hashes are retained as provenance fields inside a new
  event payload. They are not grafted into PostgreSQL's tenant-scoped hash chain;
  imported events receive new `prev_hash` and `record_hash` values.
- Only the allowlisted public event payload fields `trace_id`, `request_id`, and
  `reason_sha256` are copied. Unexpected or malformed legacy payloads are
  counted but not copied.

After import, verify counts and the mandatory manual boundary:

```sql
SELECT status, count(*) FROM xa_effects
WHERE contract_version = 'legacy-sqlite/v1'
GROUP BY status;

SELECT count(*) AS unsafe_legacy_recovery_rows
FROM xa_effects
WHERE contract_version = 'legacy-sqlite/v1'
  AND (status <> 'manual_required'
       OR reversibility <> 'manual_required'
       OR wrapped_dek IS NOT NULL
       OR recovery_nonce IS NOT NULL
       OR recovery_ciphertext IS NOT NULL);
```

The second query must return zero.
