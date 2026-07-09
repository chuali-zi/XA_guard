#!/bin/sh
# poll-status.sh <host> [--quiet]
# Run from Git Bash on the Windows workstation (manually or via the scheduled
# task in register-task.md). Pulls the remote runner's health.json + ALERTS
# tail over ssh, renders a one-screen summary, appends a snapshot to
# D:/xa-evidence/remote/<host>/status-history.jsonl, and pops a msg.exe
# notification + console bell when NEW WARN/CRITICAL alerts appeared since the
# last poll (cursor kept in .alert-cursor). Exit codes: 0 ok, 1 new alerts,
# 2 host unreachable (ssh key auth must already be set up).
set -eu

HOST=${1:-}
[ -n "$HOST" ] || { echo "usage: poll-status.sh <host> [--quiet]" >&2; exit 1; }
QUIET=${2:-}

ROOT=${XA_EVIDENCE_ROOT:-D:/xa-evidence}
DEST="$ROOT/remote/$HOST"
mkdir -p "$DEST"
CURSOR_FILE="$DEST/.alert-cursor"
SNAPSHOT="$DEST/status-snapshot.json"

if ! ssh -o ConnectTimeout=15 -o BatchMode=yes "$HOST" '
    set -e
    RUN=$(cat ~/xa-runner/current-run 2>/dev/null || true)
    if [ -z "$RUN" ]; then echo "NO_ACTIVE_RUN"; exit 0; fi
    SUP=~/xa-evidence/runs/$RUN/artifacts/supervisor
    echo "RUN_ID=$RUN"
    echo "===HEALTH==="
    cat "$SUP/health.json" 2>/dev/null || echo "{}"
    echo "===ALERTS==="
    wc -l < "$SUP/ALERTS.jsonl" 2>/dev/null || echo 0
    tail -n 200 "$SUP/ALERTS.jsonl" 2>/dev/null || true
' > "$DEST/.poll-raw" 2>"$DEST/.poll-err"; then
    echo "UNREACHABLE: $HOST ($(date))" | tee -a "$DEST/status-history.jsonl" >&2
    exit 2
fi

if grep -q '^NO_ACTIVE_RUN$' "$DEST/.poll-raw"; then
    echo "no active run on $HOST (not initialized yet, or already sealed)"
    exit 0
fi

PY=python
command -v python >/dev/null 2>&1 || PY=python3

XA_POLL_HOST="$HOST" XA_POLL_CURSOR="$CURSOR_FILE" XA_POLL_QUIET="$QUIET" \
XA_POLL_HISTORY="$DEST/status-history.jsonl" XA_POLL_SNAPSHOT="$SNAPSHOT" \
"$PY" - "$DEST/.poll-raw" <<'PYEOF'
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

raw = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace").splitlines()
run_id = raw[0].split("=", 1)[1]
health_lines, alert_lines, section = [], [], ""
for line in raw[1:]:
    if line == "===HEALTH===":
        section = "health"
    elif line == "===ALERTS===":
        section = "alerts"
    elif section == "health":
        health_lines.append(line)
    else:
        alert_lines.append(line)

health = json.loads("\n".join(health_lines) or "{}")
total_alerts = int(alert_lines[0]) if alert_lines and alert_lines[0].strip().isdigit() else 0
alerts = []
for line in alert_lines[1:]:
    line = line.strip()
    if line:
        try:
            alerts.append(json.loads(line))
        except json.JSONDecodeError:
            pass

jobs = health.get("jobs", {}).get("by_status", {})
ledger = health.get("ledger", {})
print(f"run:    {run_id}")
print(f"phase:  {health.get('phase')}  halted={health.get('halted')}  heartbeat={health.get('ts_utc')}")
print(f"note:   {health.get('note')}")
print(f"jobs:   {jobs}")
print(f"spend:  total=${ledger.get('total_usd')}  buckets={ledger.get('buckets_usd')}")

cursor_path = Path(os.environ["XA_POLL_CURSOR"])
seen = int(cursor_path.read_text()) if cursor_path.is_file() else 0
new = max(0, total_alerts - seen)
cursor_path.write_text(str(total_alerts), encoding="utf-8")
fresh = alerts[-new:] if new else []
bad = [a for a in fresh if a.get("level") in ("WARN", "CRITICAL")]
if fresh:
    print(f"--- {len(fresh)} new alert(s) ---")
    for alert in fresh:
        print(f"  [{alert.get('level')}] {alert.get('ts_utc')} {alert.get('code')}: {alert.get('message')}")

snapshot = {
    "ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "host": os.environ["XA_POLL_HOST"],
    "run_id": run_id,
    "phase": health.get("phase"),
    "halted": health.get("halted"),
    "heartbeat": health.get("ts_utc"),
    "spend_total_usd": ledger.get("total_usd"),
    "jobs": jobs,
    "new_alerts": len(fresh),
}
Path(os.environ["XA_POLL_SNAPSHOT"]).write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
with open(os.environ["XA_POLL_HISTORY"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps(snapshot) + "\n")

if bad and os.environ.get("XA_POLL_QUIET") != "--quiet":
    summary = "; ".join(f"{a.get('level')} {a.get('code')}" for a in bad[:4])
    os.system(f'msg.exe "%USERNAME%" "XA runner {os.environ["XA_POLL_HOST"]}: {summary}" 2>nul')
    sys.stdout.write("\a")
sys.exit(1 if bad else 0)
PYEOF
