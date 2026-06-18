# External Benchmark Adapters

XA-Guard currently provides an adapter skeleton for AgentDojo and InjecAgent exports.
It does not clone upstream repositories, download datasets, run official benchmark
environments, run models, or produce official comparable scores.

The adapters only normalize user-provided JSON/JSONL/CSV exports into an auditable
XA-Guard JSONL schema. Every normalized record sets `official_claim` to `false` and
includes limitations such as `adapter_only`, `not_official_reproduction`,
`input_user_provided`, and `no_large_dependency_download`.

## Commands

```bash
python -m bench.external.cli normalize \
  --benchmark agentdojo \
  --input bench/external/fixtures/agentdojo_smoke.jsonl \
  --output bench/.log/external/agentdojo-normalized.jsonl

python -m bench.external.cli validate \
  --input bench/.log/external/agentdojo-normalized.jsonl

python -m bench.external.cli smoke-metrics \
  --input bench/.log/external/agentdojo-normalized.jsonl

python -m bench.external.cli archive \
  --benchmark agentdojo \
  --input bench/external/fixtures/agentdojo_smoke.jsonl \
  --out-dir bench/.log/external/agentdojo-archive

python -m bench.external.cli archive \
  --benchmark agentdojo \
  --input bench/external/fixtures/agentdojo_smoke.jsonl \
  --out-dir bench/.log/external/agentdojo-projection-archive \
  --run-projection \
  --config configs/xa-guard.yaml
```

`smoke-metrics` reports adapter health only: record counts, validation counts, and
`attack_success_rate_if_labeled`. It is not AgentDojo ASR, InjecAgent ASR, or any
official benchmark result.

## Evidence Archive

`archive` creates a small evidence bundle for a user-provided export without
claiming an official score:

- `normalized.jsonl` - normalized XA-Guard records.
- `validation.json` - validation summary.
- `smoke-metrics.json` - adapter health metrics only.
- `report.json` - auditable summary with coverage, limitation counts, and hashes.
- `manifest.json` - benchmark name, adapter/schema versions, input hash,
  normalized hash, schema hash, validation counts, and `official_claim=false`.
- `README.md` - human-readable limitation statement for the archive directory.
- `xa-guard-projection/results.json` - optional local XA-Guard projection
  decisions when `--run-projection` is used.
- `xa-guard-projection/summary.json` - optional projection summary using
  `xa_guard_projection_*` field names only.
- `xa-guard-projection/audit/audit.jsonl` - isolated audit log for projection
  runs.
- `xa-guard-projection/audit-verify.json` - audit hash-chain verification
  summary with record count, first/last record hash, and audit file hash.

Recommended long-lived evidence layout:

```text
evidence/external-benchmarks/
  agentdojo/
    manifest.json
    normalized.jsonl
    validation.json
    smoke-metrics.json
    report.json
    README.md
  injecagent/
    ...
```

The archive is suitable as supporting traceability evidence. It is not a
replacement for running the official AgentDojo / InjecAgent environments.

`--run-projection` is also supporting evidence only. It maps each normalized
record's `xa_guard_projection.input_payload` into the local XA-Guard pipeline
with a mock executor, writes an isolated audit log, and reports local decisions.
It does not update external `observed` labels, does not change smoke metrics, and
must not be reported as AgentDojo ASR, InjecAgent ASR, utility, leaderboard
score, or any official reproduction.
