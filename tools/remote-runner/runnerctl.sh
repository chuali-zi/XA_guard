#!/bin/sh
# runnerctl.sh - operator CLI for the R2/R3 budget60 remote runner.
#
#   runnerctl init                 create the evidence run + budget-plan
#   runnerctl status               render health.json + recent alerts
#   runnerctl approve <gate>       arm calibration | freeze | main
#   runnerctl pause                systemctl stop xa-runner
#   runnerctl resume               systemctl start xa-runner
#   runnerctl revive               clear a breaker/budget halt and restart
#   runnerctl seal --result <R>    stop, re-verify, then seal the run
#   runnerctl logs                 follow the supervisor journal
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RUNNER_HOME=${XA_RUNNER_HOME:-"$HOME/xa-runner"}
EVIDENCE_ROOT=${XA_EVIDENCE_ROOT:-"$HOME/xa-evidence"}
PYTHON=${XA_RUNNER_PYTHON:-"$RUNNER_HOME/venv/bin/python"}
[ -x "$PYTHON" ] || PYTHON=$(command -v python3 || command -v python)
SUPERVISOR="$SCRIPT_DIR/supervisor.py"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

current_run() {
    [ -f "$RUNNER_HOME/current-run" ] || die "no current run; run 'runnerctl init' first"
    cat "$RUNNER_HOME/current-run"
}

CMD=${1:-}
[ -n "$CMD" ] || { grep '^#   runnerctl' "$0" | sed 's/^#   //'; exit 1; }
shift || true

case "$CMD" in
    init)
        "$PYTHON" "$SUPERVISOR" init "$@"
        ;;
    status)
        "$PYTHON" "$SUPERVISOR" status
        if command -v systemctl >/dev/null 2>&1; then
            printf 'service: %s\n' "$(systemctl is-active xa-runner 2>/dev/null || echo unavailable)"
        fi
        ;;
    approve)
        [ $# -ge 1 ] || die "usage: runnerctl approve calibration|freeze|main"
        "$PYTHON" "$SUPERVISOR" approve "$1"
        ;;
    pause)
        touch "$RUNNER_HOME/paused"   # tells the watchdog not to auto-restart
        sudo systemctl stop xa-runner
        echo "paused (systemd service stopped); 'runnerctl resume' to continue"
        ;;
    resume)
        rm -f "$RUNNER_HOME/paused"
        sudo systemctl start xa-runner
        echo "resumed"
        ;;
    revive)
        "$PYTHON" "$SUPERVISOR" revive
        if command -v systemctl >/dev/null 2>&1; then
            sudo systemctl restart xa-runner
            echo "service restarted"
        fi
        ;;
    seal)
        RESULT=""
        while [ $# -gt 0 ]; do
            case "$1" in
                --result) RESULT=$2; shift 2 ;;
                *) die "unknown argument: $1" ;;
            esac
        done
        [ -n "$RESULT" ] || die "usage: runnerctl seal --result PASS|LIMIT|BLOCKED|INFRA_ERROR"
        RUN_ID=$(current_run)
        RUN_DIR="$EVIDENCE_ROOT/runs/$RUN_ID"
        touch "$RUNNER_HOME/paused"   # keep the watchdog from restarting mid-seal
        if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet xa-runner; then
            echo "stopping xa-runner before sealing..."
            sudo systemctl stop xa-runner
        fi
        CONFIG="$RUN_DIR/artifacts/config/acceptance.local.json"
        echo "re-running budget-verify before sealing..."
        "$PYTHON" "$RUNNER_HOME/XA_guard/scripts/run_r2_r3_acceptance.py" budget-verify --config "$CONFIG" \
            || die "budget-verify failed; fix the evidence before sealing"
        FIRST_LINE=$(head -n1 "$RUN_DIR/RESULTS.md" | tr -d '\r')
        case "$FIRST_LINE" in
            "$RESULT"|"$RESULT "*) ;;
            *) die "RESULTS.md first line is '$FIRST_LINE'; write the final conclusion (first line = $RESULT) before sealing" ;;
        esac
        sh "$SCRIPT_DIR/../evidence/seal-run.sh" "$RUN_ID" --result "$RESULT"
        # Archive the run pointer: nothing may write into runs/<run-id>/ after
        # sealing, or the live copy diverges from the sealed tarball hashes.
        printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$RUN_ID" >> "$RUNNER_HOME/sealed-runs.log"
        rm -f "$RUNNER_HOME/current-run"
        echo
        echo "next: collect from Windows (tools/evidence/collect.sh <host> --sealed),"
        echo "then commit the printed manifest line into docs/acceptance/remote-evidence/."
        ;;
    logs)
        journalctl -u xa-runner -f
        ;;
    *)
        die "unknown command: $CMD"
        ;;
esac
