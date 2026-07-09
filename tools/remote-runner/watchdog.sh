#!/bin/sh
# watchdog.sh - invoked by xa-watchdog.timer every 2 minutes (and by
# xa-alert@.service with --onfailure <unit>). Revives a dead/stuck supervisor
# and appends WARN/CRITICAL lines to the run's ALERTS.jsonl. All alerts are
# written with O_APPEND single-line writes, safe alongside the supervisor.
set -eu

RUNNER_HOME=${XA_RUNNER_HOME:-"$HOME/xa-runner"}
EVIDENCE_ROOT=${XA_EVIDENCE_ROOT:-"$HOME/xa-evidence"}
STALE_SECONDS=${XA_WATCHDOG_STALE_SECONDS:-300}
MIN_DISK_KB=${XA_WATCHDOG_MIN_DISK_KB:-2097152}   # 2 GB
MAX_DRIFT_SECONDS=${XA_WATCHDOG_MAX_DRIFT:-5}

now_utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }

alerts_path() {
    [ -f "$RUNNER_HOME/current-run" ] || return 1
    run_id=$(cat "$RUNNER_HOME/current-run")
    dir="$EVIDENCE_ROOT/runs/$run_id/artifacts/supervisor"
    mkdir -p "$dir"
    printf '%s/ALERTS.jsonl\n' "$dir"
}

alert() { # alert <LEVEL> <code> <message>
    path=$(alerts_path) || { logger -t xa-watchdog "$1 $2: $3" 2>/dev/null || true; return 0; }
    printf '{"ts_utc":"%s","level":"%s","code":"%s","message":"%s","details":{"source":"watchdog"}}\n' \
        "$(now_utc)" "$1" "$2" "$3" >> "$path"
    logger -t xa-watchdog "$1 $2: $3" 2>/dev/null || true
}

if [ "${1:-}" = "--onfailure" ]; then
    alert CRITICAL service_failed "systemd reported failure of ${2:-unknown unit}"
    exit 0
fi

# 1. Service liveness: restart when inactive (unless the operator paused it on
# purpose - a paused service was stopped, i.e. "inactive" with no failure; we
# only auto-restart when a run is active and not sealed/halted-by-operator).
if command -v systemctl >/dev/null 2>&1 && [ -f "$RUNNER_HOME/current-run" ]; then
    if ! systemctl is-active --quiet xa-runner; then
        if [ ! -f "$RUNNER_HOME/paused" ]; then
            alert CRITICAL runner_dead "xa-runner inactive; watchdog restarting it"
            systemctl restart xa-runner || alert CRITICAL runner_restart_failed "systemctl restart xa-runner failed"
        fi
    else
        # 2. Heartbeat freshness: health.json must be newer than STALE_SECONDS.
        run_id=$(cat "$RUNNER_HOME/current-run")
        health="$EVIDENCE_ROOT/runs/$run_id/artifacts/supervisor/health.json"
        if [ -f "$health" ]; then
            age=$(( $(date +%s) - $(stat -c %Y "$health" 2>/dev/null || stat -f %m "$health") ))
            if [ "$age" -gt "$STALE_SECONDS" ]; then
                alert CRITICAL heartbeat_stale "health.json is ${age}s old; restarting xa-runner"
                systemctl restart xa-runner || alert CRITICAL runner_restart_failed "systemctl restart xa-runner failed"
            fi
        fi
    fi
fi

# 3. Disk space under the evidence root.
avail_kb=$(df -Pk "$EVIDENCE_ROOT" 2>/dev/null | awk 'NR==2 {print $4}')
if [ -n "${avail_kb:-}" ] && [ "$avail_kb" -lt "$MIN_DISK_KB" ]; then
    alert WARN disk_low "only ${avail_kb}KB free under $EVIDENCE_ROOT"
fi

# 4. Clock drift (power loss can leave the RTC far off until chrony catches up).
if command -v chronyc >/dev/null 2>&1; then
    drift=$(chronyc tracking 2>/dev/null | awk -F': *' '/System time/ {print $2}' | awk '{print $1}')
    if [ -n "${drift:-}" ]; then
        big=$(awk -v d="$drift" -v m="$MAX_DRIFT_SECONDS" 'BEGIN {print (d > m) ? 1 : 0}')
        [ "$big" = 1 ] && alert WARN clock_drift "system clock is ${drift}s off NTP"
    fi
fi

exit 0
