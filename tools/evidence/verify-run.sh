#!/bin/sh
# verify-run.sh <run-id> [--tarball] [--manifest PATH]
# EVIDENCE-LAYOUT-SPEC.md §6: recompute and compare artifact-hashes.json for
# runs/<run-id>/ (reports mismatched, missing and unlisted files). With
# --tarball, also check sealed/<run-id>.tar.gz against the committed
# provenance manifest (git is the trust anchor; the .sha256 next to the
# tarball is never used as the source of truth, spec §4).
# Exit codes: 0 ok, 1 mismatch, 2 tarball untracked in manifest.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/common.sh"

RUN_ID=${1:-}
[ -n "$RUN_ID" ] || die "usage: verify-run.sh <run-id> [--tarball] [--manifest PATH]"
shift

CHECK_TARBALL=0
MANIFEST="$SCRIPT_DIR/../../docs/acceptance/remote-evidence/provenance-manifest.jsonl"
while [ $# -gt 0 ]; do
    case "$1" in
        --tarball) CHECK_TARBALL=1; shift ;;
        --manifest) MANIFEST=$2; shift 2 ;;
        *) die "unknown argument: $1" ;;
    esac
done

PY=$(find_python)
ROOT=$(evidence_root)
RUN_DIR="$ROOT/runs/$RUN_ID"
STATUS=0

if [ -d "$RUN_DIR" ]; then
    "$PY" - "$RUN_DIR" <<'PYEOF' || STATUS=1
import hashlib, json, sys
from pathlib import Path

run_dir = Path(sys.argv[1])
listed = json.loads((run_dir / "artifact-hashes.json").read_text(encoding="utf-8"))["files"]
problems = []
actual = {
    p.relative_to(run_dir).as_posix(): p
    for p in run_dir.rglob("*")
    if p.is_file() and p.name != "artifact-hashes.json"
}
for rel, entry in listed.items():
    path = actual.pop(rel, None)
    if path is None:
        problems.append(f"MISSING   {rel}")
        continue
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        problems.append(f"MISMATCH  {rel}")
    elif len(data) != entry["bytes"]:
        problems.append(f"SIZE      {rel}")
for rel in sorted(actual):
    problems.append(f"UNLISTED  {rel}")
for problem in problems:
    print(problem, file=sys.stderr)
print(f"artifact-hashes: {len(listed)} listed, {len(problems)} problem(s)")
sys.exit(1 if problems else 0)
PYEOF
else
    info "runs/$RUN_ID not present locally; skipping artifact-hashes check"
fi

if [ "$CHECK_TARBALL" = 1 ]; then
    TARBALL=""
    for candidate in "$ROOT/sealed/$RUN_ID.tar.gz" "$ROOT"/remote/*/sealed/"$RUN_ID.tar.gz"; do
        [ -f "$candidate" ] && TARBALL=$candidate && break
    done
    [ -n "$TARBALL" ] || die "sealed tarball not found for $RUN_ID under $ROOT"
    [ -f "$MANIFEST" ] || die "committed manifest not found: $MANIFEST"
    ACTUAL=$(sha256_file "$TARBALL")
    EXPECTED=$(XA_RUN_ID="$RUN_ID" "$PY" - "$MANIFEST" <<'PYEOF'
import json, os, sys
run_id = os.environ["XA_RUN_ID"]
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    record = json.loads(line)
    if record.get("run_id") == run_id:
        print(record["tarball_sha256"])
        break
PYEOF
)
    if [ -z "$EXPECTED" ]; then
        info "UNTRACKED: $RUN_ID has no committed manifest record"
        exit 2
    elif [ "$ACTUAL" = "$EXPECTED" ]; then
        echo "tarball: OK ($ACTUAL)"
    else
        info "tarball: MISMATCH actual=$ACTUAL manifest=$EXPECTED"
        exit 1
    fi
fi

exit "$STATUS"
