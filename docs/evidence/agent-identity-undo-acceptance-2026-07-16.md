# Identity + Undo acceptance evidence · 2026-07-16

The sibling directory with the same stem is the sealed, redacted acceptance
bundle for the Reference and local Kind HA profiles. This overview deliberately
stays outside that directory so the signed artifact set remains immutable. The
private SM2 key remains under gitignored `.runtime/`.

## Result

| Area | Result | Evidence |
|---|---|---|
| Reference fault injection | **PASS 11/11** | `acceptance/reference-faults-all-clean.json` |
| Worker kill takeover | **PASS** | 2 distinct workers, one effective cancel, 102.719s |
| Retry schedule | **PASS** | 5.057/30.141/120.454s observations, one effective cancel |
| KEK rotation | **PASS** | wrong-key fail closed + admin recovery; v1→v2 rewrapped 7 records |
| Kind HA profile | **PASS** | N-1 install, upgrade, migration rerun, Pod takeover, NetworkPolicy, rollback |
| Undo latency | **PASS 10/10** | 46.935–916.320ms against a 30s limit |
| 10-concurrency write overhead | **FAIL** | incremental p95 352.548/486.272/248.346ms against a 50ms limit |
| Bundle integrity | **PASS** | 14 artifacts, 46 Effect records, 25 Gate6 records |

The bundle is evidence-complete but **not a REFERENCE-READY pass**: the signed
manifest deliberately includes the failed performance report.

## Verification

```powershell
$env:TEMP='D:\tmp'
$env:TMP='D:\tmp'
python scripts\verify_identity_undo_evidence.py `
  --bundle docs\evidence\agent-identity-undo-acceptance-2026-07-16 `
  --expected-key-id 87ca0b5c56dc9313
```

Expected summary:

```json
{"artifact_count":14,"effect_records":46,"gate6_records":25,"ok":true,"signature_algorithm":"SM2-with-SM3","signature_key_id":"87ca0b5c56dc9313"}
```

The SHA-256 of `artifact-manifest.json` is
`f6c1cc156f6593448c008f58a0f79f4e51d6817a6b160647cdaacb0ce4455c7c`.

## Boundaries

- Compensation is at-least-once with downstream idempotency, not absolute
  exactly-once.
- Kind used reference Compose OIDC/PostgreSQL/key-provider dependencies and
  proves only this local profile, not production HA.
- Interactive Alice/Dora/Admin browser validation is a separate manual item.
- Sealing proves integrity, chains, cross-links, and signature; it does not
  turn a failed performance assertion into a pass.
