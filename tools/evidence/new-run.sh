#!/bin/sh
# new-run.sh <target> [--shorthost H] [--repo PATH] [--operator NAME]
# EVIDENCE-LAYOUT-SPEC.md §2/§6: create runs/<run-id>/ skeleton with meta.json
# initial values, environment.txt, empty commands.txt/console.log and a
# RESULTS.md placeholder. Prints the run-id (and nothing else) on stdout.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/common.sh"

TARGET=${1:-}
[ -n "$TARGET" ] || die "usage: new-run.sh <target> [--shorthost H] [--repo PATH] [--operator NAME]"
shift

case "$TARGET" in
    *[!a-z0-9-]*) die "target must be lowercase [a-z0-9-], e.g. l3-r2r3-budget60" ;;
esac

SHORTHOST=$(short_host)
REPO=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
OPERATOR=${XA_OPERATOR:-$(whoami 2>/dev/null || echo unknown)}
while [ $# -gt 0 ]; do
    case "$1" in
        --shorthost) SHORTHOST=$2; shift 2 ;;
        --repo) REPO=$2; shift 2 ;;
        --operator) OPERATOR=$2; shift 2 ;;
        *) die "unknown argument: $1" ;;
    esac
done
[ -n "$SHORTHOST" ] || die "cannot determine shorthost; pass --shorthost"

PY=$(find_python)
ROOT=$(evidence_root)
RUN_ID="${TARGET}-$(utc_stamp)-${SHORTHOST}"
RUN_DIR="$ROOT/runs/$RUN_ID"
[ ! -e "$RUN_DIR" ] || die "run directory already exists: $RUN_DIR"
mkdir -p "$RUN_DIR/artifacts" "$ROOT/sealed"

# meta.json initial values (spec §2.3); result placeholder INFRA_ERROR until sealed.
XA_META_RUN_ID="$RUN_ID" XA_META_TARGET="$TARGET" XA_META_SHORTHOST="$SHORTHOST" \
XA_META_REPO="$REPO" XA_META_OPERATOR="$OPERATOR" XA_META_START="$(utc_iso)" \
"$PY" - "$RUN_DIR/meta.json" <<'PYEOF'
import json, os, platform, socket, subprocess, sys

def git(repo, *args):
    return subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True, check=True,
        encoding="utf-8", errors="replace",
    ).stdout.strip()

repo = os.environ["XA_META_REPO"]
dirty_paths = [line for line in git(repo, "status", "--porcelain").splitlines() if line]
os_name = platform.platform()
if os.path.isfile("/etc/os-release"):
    with open("/etc/os-release", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("PRETTY_NAME="):
                os_name = line.split("=", 1)[1].strip().strip('"')
meta = {
    "run_id": os.environ["XA_META_RUN_ID"],
    "target": os.environ["XA_META_TARGET"].upper(),
    "host": {
        "shorthost": os.environ["XA_META_SHORTHOST"],
        "fqdn": socket.getfqdn(),
        "os": os_name,
        "kernel": platform.release(),
        "arch": platform.machine(),
    },
    "git": {
        "head": git(repo, "rev-parse", "HEAD"),
        "branch": git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(dirty_paths),
        "dirty_paths": [line[3:] for line in dirty_paths],
    },
    "time": {"start_utc": os.environ["XA_META_START"], "end_utc": None},
    "tool_versions": {"python": platform.python_version()},
    "operator": os.environ["XA_META_OPERATOR"],
    "result": "INFRA_ERROR",
    "notes": "in progress; result/end_utc are finalized by seal-run.sh",
}
with open(sys.argv[1], "w", encoding="utf-8", newline="\n") as handle:
    json.dump(meta, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
PYEOF

{
    echo "# environment snapshot for $RUN_ID"
    echo "captured_utc: $(utc_iso)"
    uname -a
    [ -f /etc/os-release ] && grep -E '^(PRETTY_NAME|VERSION_ID)=' /etc/os-release
    git --version
    "$PY" --version 2>&1
    command -v opencode >/dev/null 2>&1 && opencode --version 2>&1 | head -n1
    command -v chronyc >/dev/null 2>&1 && chronyc tracking 2>&1 | head -n4
    true
} > "$RUN_DIR/environment.txt"

: > "$RUN_DIR/commands.txt"
: > "$RUN_DIR/console.log"
{
    echo "INFRA_ERROR"
    echo
    echo "# $RUN_ID"
    echo
    echo "> Placeholder. Before sealing, replace the first line with the final"
    echo "> result (PASS / LIMIT / BLOCKED / INFRA_ERROR) and document metrics"
    echo "> and boundary statements. seal-run.sh refuses to seal if the first"
    echo "> line does not match --result."
} > "$RUN_DIR/RESULTS.md"

info "created $RUN_DIR"
printf '%s\n' "$RUN_ID"
