# xa-aibom CLI Validate/Admit Matrix

Run date: 2026-07-07 local workspace.

Source BOM: `docs/acceptance/r8-aibom-external/evidence/l3-r8-aibom-20260707T105519Z/aibom.cdxgen.json`

Source BOM SHA-256: `6a43e3a3b8637f7cc05c328a9261311825e4ba08ec119faf1ec0699dea1db100`

Temporary work dir: `C:/Users/chual/AppData/Local/Temp/opencode/r8-aibom-cli-20260707T060622`

Negative input construction:

- Schema-valid tampered BOM: appended `{"name":"r8:tamper","value":"schema-valid"}` to `metadata.properties` while keeping the original expected SHA-256.
- Missing-field BOM: removed top-level `bomFormat` from the external BOM.
- High-risk artifact: zipped a plugin containing `main.py` with `import subprocess` and `subprocess.Popen(['id'])`.

## Results

| Case | Command shape | Expected exit | Actual exit | Result |
|---|---|---:|---:|---|
| `validate_external_bom_ok` | `python -m xa_guard.aibom.cli validate <external-bom> --expected-sha256 <bom-sha>` | 0 | 0 | `valid=true`, `hash_valid=true`, `spec_version=1.6`, `validator=jsonschema` |
| `validate_schema_valid_tamper_hash_fail` | `validate <schema-valid-tampered-bom> --expected-sha256 <original-bom-sha>` | 2 | 2 | Schema still valid, but SHA-256 mismatch caught. Actual tampered SHA-256: `e251c99f34ce5fc2b116af9cda9007c20a9748a15bf1ffbab3a4eab9aeecdac5` |
| `validate_missing_required_field_fail` | `validate <bom-without-bomFormat>` | 2 | 2 | Schema rejected missing required `bomFormat` |
| `validate_original_wrong_hash_fail` | `validate <external-bom> --expected-sha256 000...000` | 2 | 2 | Original BOM content valid, but expected hash mismatch caught |
| `admit_artifact_ok` | `admit <python-ai-plugin.zip> --expected-sha256 <artifact-sha>` | 0 | 0 | `decision=allow`, `grade=B`, `schema_valid=true`; artifact SHA-256 `c808a4c6408f668b94dc69a95fb05ffa8fd213aa91668ffed75000a81938f166` |
| `admit_artifact_wrong_hash_deny` | `admit <python-ai-plugin.zip> --expected-sha256 000...000` | 2 | 2 | `decision=deny`, `grade=F`, reason includes `artifact sha256 mismatch` |
| `admit_high_risk_artifact_deny` | `admit <dangerous-plugin.zip> --expected-sha256 <artifact-sha>` | 2 | 2 | `decision=deny`, `grade=D`, reason includes `process_exec detected via shell/subprocess API`; artifact SHA-256 `6745ce5d9bcce969acd3f76a1e44854e5ea439ddb4f8d19a326a4f34a92f2a44` |

## Implementation Fixes Found By This Run

- `xa-aibom validate` only performed schema validation before this run. It now reports actual BOM SHA-256 and supports `--expected-sha256`, failing closed on hash mismatch.
- `xa-aibom admit <local-artifact> --expected-sha256 ...` did not route local artifacts through hash-verifying artifact scan before this run. It now uses `scan_artifact` when an expected hash is provided, so mismatched local archives deny with exit code 2.
- Artifact expected SHA-256 comparison now normalizes uppercase input to lowercase, matching the validate path.

## Verification

- `python -m pytest tests/unit/test_aibom_cli.py tests/unit/test_aibom_gateway.py tests/unit/test_aibom_scanner.py tests/unit/test_aibom_external_generator.py tests/unit/test_aibom_schema_validator.py -q` passed.
- `python -m ruff check src/xa_guard/aibom/cli.py src/xa_guard/aibom/gateway.py src/xa_guard/aibom/scanner.py tests/unit/test_aibom_cli.py` passed.
- `python -m pytest tests/unit/test_aibom_cli.py tests/unit/test_aibom_gateway.py tests/unit/test_aibom_scanner.py tests/unit/test_aibom_external_generator.py tests/unit/test_aibom_schema_validator.py tests/unit/test_aibom_signing.py tests/unit/test_aibom_offline_fetch.py tests/unit/test_aibom_intel.py tests/unit/test_aibom_drift_monitor.py tests/test_aibom_bench_supply_chain.py -q` passed.
