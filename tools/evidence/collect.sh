#!/bin/sh
# collect.sh <host> --live|--sealed [--scp]
# EVIDENCE-LAYOUT-SPEC.md §5: pull evidence from a remote host into the local
# mirror <root>/remote/<host>/.
#   --live    incremental rsync of the whole runs/ tree (iteration phase)
#   --sealed  rsync sealed/, then verify every tarball against the COMMITTED
#             docs/acceptance/remote-evidence/provenance-manifest.jsonl
#             (git is the only trust anchor; the .sha256 next to each tarball
#             is a convenience value and never consulted, spec §4)
#   --scp     fallback when rsync is unavailable (Git Bash often lacks it):
#             full non-incremental copy via scp -r
# <host> is an ssh destination (e.g. an alias from ~/.ssh/config, or user@ip).
# Exit codes: 0 all ok, 1 at least one MISMATCH, 2 transfer failure.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/common.sh"

HOST=${1:-}
[ -n "$HOST" ] || die "usage: collect.sh <host> --live|--sealed [--scp]"
shift

MODE=""
USE_SCP=0
while [ $# -gt 0 ]; do
    case "$1" in
        --live) MODE=live; shift ;;
        --sealed) MODE=sealed; shift ;;
        --scp) USE_SCP=1; shift ;;
        *) die "unknown argument: $1" ;;
    esac
done
[ -n "$MODE" ] || die "pick one of --live | --sealed"

if [ "$USE_SCP" = 0 ] && ! command -v rsync >/dev/null 2>&1; then
    die "rsync not found. Install it (Git Bash: drop MSYS2 rsync.exe into <Git>/usr/bin) or re-run with --scp for a full non-incremental copy."
fi

PY=$(find_python)
ROOT=$(evidence_root)
DEST="$ROOT/remote/$HOST"
MANIFEST="$SCRIPT_DIR/../../docs/acceptance/remote-evidence/provenance-manifest.jsonl"

pull() { # pull <remote-subdir> <local-dir>
    mkdir -p "$2"
    if [ "$USE_SCP" = 1 ]; then
        scp -r -p "$HOST:~/xa-evidence/$1/." "$2/" || return 1
    else
        rsync -avz --partial "$HOST:~/xa-evidence/$1/" "$2/" || return 1
    fi
}

if [ "$MODE" = live ]; then
    pull runs "$DEST/runs" || { info "transfer failed"; exit 2; }
    info "live mirror updated: $DEST/runs"
    exit 0
fi

pull sealed "$DEST/sealed" || { info "transfer failed"; exit 2; }
[ -f "$MANIFEST" ] || die "committed manifest not found: $MANIFEST"

STATUS=0
FOUND=0
for tarball in "$DEST/sealed"/*.tar.gz; do
    [ -f "$tarball" ] || continue
    FOUND=1
    base=$(basename "$tarball")
    run_id=${base%.tar.gz}
    actual=$(sha256_file "$tarball")
    expected=$(XA_RUN_ID="$run_id" "$PY" - "$MANIFEST" <<'PYEOF'
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
    if [ -z "$expected" ]; then
        printf 'UNTRACKED  %s (no committed manifest record yet)\n' "$run_id"
    elif [ "$actual" = "$expected" ]; then
        printf 'OK         %s\n' "$run_id"
    else
        printf 'MISMATCH   %s actual=%s manifest=%s\n' "$run_id" "$actual" "$expected"
        STATUS=1
    fi
done
[ "$FOUND" = 1 ] || info "no sealed tarballs found on $HOST yet"
exit "$STATUS"
