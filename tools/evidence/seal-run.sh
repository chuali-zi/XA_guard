#!/bin/sh
# seal-run.sh <run-id> --result PASS|LIMIT|BLOCKED|INFRA_ERROR [--end-utc T]
# EVIDENCE-LAYOUT-SPEC.md §3: recompute artifact-hashes.json, finalize meta.json,
# build the deterministic tarball under sealed/, write its .sha256, append a line
# to HOST-INDEX.jsonl, and print the provenance manifest record (spec §4) on
# stdout for the operator to commit into
# docs/acceptance/remote-evidence/provenance-manifest.jsonl + PROVENANCE.md.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/common.sh"

RUN_ID=${1:-}
[ -n "$RUN_ID" ] || die "usage: seal-run.sh <run-id> --result <R> [--end-utc T]"
shift

RESULT=""
END_UTC=$(utc_iso)
while [ $# -gt 0 ]; do
    case "$1" in
        --result) RESULT=$2; shift 2 ;;
        --end-utc) END_UTC=$2; shift 2 ;;
        *) die "unknown argument: $1" ;;
    esac
done
case "$RESULT" in
    PASS|LIMIT|BLOCKED|INFRA_ERROR) ;;
    *) die "--result must be PASS|LIMIT|BLOCKED|INFRA_ERROR" ;;
esac

require_gnu_tar
PY=$(find_python)
ROOT=$(evidence_root)
RUN_DIR="$ROOT/runs/$RUN_ID"
[ -d "$RUN_DIR" ] || die "no such run: $RUN_DIR"
TARBALL="$ROOT/sealed/$RUN_ID.tar.gz"
[ ! -e "$TARBALL" ] || die "already sealed: $TARBALL (sealed runs are immutable; re-run under a new run-id)"
mkdir -p "$ROOT/sealed"

# result must match the first line of RESULTS.md (spec §2.3).
FIRST_LINE=$(head -n1 "$RUN_DIR/RESULTS.md" | tr -d '\r')
case "$FIRST_LINE" in
    "$RESULT"|"$RESULT "*) ;;
    *) die "RESULTS.md first line is '$FIRST_LINE' but --result is '$RESULT'; finalize RESULTS.md first" ;;
esac

# Finalize meta.json, then recompute artifact-hashes.json over everything except itself.
XA_SEAL_RESULT="$RESULT" XA_SEAL_END="$END_UTC" \
"$PY" - "$RUN_DIR" <<'PYEOF'
import hashlib, json, os, sys
from pathlib import Path

run_dir = Path(sys.argv[1])
meta_path = run_dir / "meta.json"
meta = json.loads(meta_path.read_text(encoding="utf-8"))
meta["time"]["end_utc"] = os.environ["XA_SEAL_END"]
meta["result"] = os.environ["XA_SEAL_RESULT"]
meta["notes"] = meta.get("notes", "").replace(
    "in progress; result/end_utc are finalized by seal-run.sh", ""
).strip()
meta_path.write_text(
    json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
)

files = {}
for path in sorted(run_dir.rglob("*")):
    if not path.is_file() or path.name == "artifact-hashes.json":
        continue
    rel = path.relative_to(run_dir).as_posix()
    files[rel] = {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }
# generated_utc mirrors end_utc so re-sealing identical content is byte-reproducible.
hashes = {
    "generated_utc": os.environ["XA_SEAL_END"],
    "algorithm": "SHA-256",
    "evidence_dir": str(run_dir.as_posix()),
    "files": files,
}
(run_dir / "artifact-hashes.json").write_text(
    json.dumps(hashes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
)
PYEOF

# Deterministic tarball (spec §3): sorted names, fixed ownership, mtime = end_utc,
# gzip -n so the archive is byte-reproducible.
tar --sort=name --owner=0 --group=0 --numeric-owner --mtime="$END_UTC" \
    -cf - -C "$ROOT/runs" "$RUN_ID" | gzip -n > "$TARBALL"
TARBALL_SHA=$(sha256_file "$TARBALL")
printf '%s  %s\n' "$TARBALL_SHA" "$RUN_ID.tar.gz" > "$TARBALL.sha256"

MANIFEST_LINE=$(XA_SEAL_SHA="$TARBALL_SHA" "$PY" - "$RUN_DIR" <<'PYEOF'
import json, os, sys
from pathlib import Path

run_dir = Path(sys.argv[1])
meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
paths = [p for p in run_dir.rglob("*") if p.is_file()]
record = {
    "run_id": meta["run_id"],
    "host": meta["host"]["shorthost"],
    "target": meta["target"],
    "end_utc": meta["time"]["end_utc"],
    "tarball_sha256": os.environ["XA_SEAL_SHA"],
    "file_count": len(paths),
    "total_bytes": sum(p.stat().st_size for p in paths),
    "result": meta["result"],
}
print(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
PYEOF
)

printf '%s\n' "$MANIFEST_LINE" >> "$ROOT/HOST-INDEX.jsonl"

info "sealed $TARBALL"
info "sha256 $TARBALL_SHA"
info "append the line below to docs/acceptance/remote-evidence/provenance-manifest.jsonl"
info "and PROVENANCE.md, then commit+push (git is the trust anchor, spec §4):"
printf '%s\n' "$MANIFEST_LINE"
