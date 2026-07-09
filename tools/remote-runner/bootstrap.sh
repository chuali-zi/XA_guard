#!/bin/sh
# bootstrap.sh - idempotent deployment of the R2/R3 remote runner on a fresh
# Debian/Ubuntu VM. Every subcommand can be re-run safely.
#
#   sudo sh bootstrap.sh system     # apt packages, chrony, qemu-guest-agent
#   sh bootstrap.sh repo            # clone/refresh XA_guard + both upstreams
#   sh bootstrap.sh python          # venv + pip install -e ".[bench]" + agentdojo
#   sh bootstrap.sh opencode        # opencode CLI + dedicated XDG dirs (then: auth login)
#   sudo sh bootstrap.sh units      # install + enable systemd units (boot autostart)
#   sh bootstrap.sh verify          # read-only readiness report; all green => runnerctl init
#   sh bootstrap.sh all             # user-level steps: repo python opencode verify
#                                   # (run `sudo sh bootstrap.sh system` first and
#                                   #  `sudo sh bootstrap.sh units` after)
#
# Offline-first: if ~/xa-runner/bundles/<name>.bundle exists (pushed from the
# Windows side by tools/remote-runner/windows/push-repo.sh) the clone uses the
# bundle instead of the network - the campus network often cannot reach GitHub.
#
# Overridable via environment:
#   XA_RUNNER_HOME (~/xa-runner)  XA_RUNUSER (current user)
#   XA_REPO_URL / XA_AGENTDOJO_URL / XA_INJECAGENT_URL  (network fallbacks)
#   XA_AGENTDOJO_REF (v1.2.2)
set -eu

RUNNER_HOME=${XA_RUNNER_HOME:-"$HOME/xa-runner"}
EVIDENCE_ROOT=${XA_EVIDENCE_ROOT:-"$HOME/xa-evidence"}
RUNUSER=${XA_RUNUSER:-$(whoami)}
REPO_URL=${XA_REPO_URL:-"https://github.com/chuali-zi/agent_safety.git"}
AGENTDOJO_URL=${XA_AGENTDOJO_URL:-"https://github.com/ethz-spylab/agentdojo.git"}
AGENTDOJO_REF=${XA_AGENTDOJO_REF:-"v1.2.2"}
INJECAGENT_URL=${XA_INJECAGENT_URL:-"https://github.com/uiuc-kang-lab/InjecAgent.git"}
UNIT_DIR=/etc/systemd/system

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
step() { printf '\n== %s\n' "$*"; }

clone_or_refresh() { # clone_or_refresh <dest> <bundle-name> <url> [ref]
    dest=$1; bundle="$RUNNER_HOME/bundles/$2"; url=$3; ref=${4:-}
    if [ -d "$dest/.git" ]; then
        echo "already cloned: $dest"
    elif [ -f "$bundle" ]; then
        echo "cloning from bundle: $bundle"
        git clone "$bundle" "$dest"
    else
        echo "cloning from network: $url"
        git clone "$url" "$dest"
    fi
    if [ -n "$ref" ]; then
        git -C "$dest" fetch --tags origin 2>/dev/null || true
        git -C "$dest" checkout --quiet "$ref"
    fi
    git -C "$dest" log -1 --format='  %H %s'
}

do_system() {
    [ "$(id -u)" = 0 ] || die "run 'system' with sudo"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y git python3 python3-venv python3-pip curl rsync chrony jq unzip qemu-guest-agent
    systemctl enable --now chrony
    systemctl enable --now qemu-guest-agent || echo "qemu-guest-agent needs the Proxmox VM option enabled; see README checklist"
    timedatectl set-ntp true || true
}

do_repo() {
    mkdir -p "$RUNNER_HOME/bundles"
    clone_or_refresh "$RUNNER_HOME/XA_guard" xa_guard.bundle "$REPO_URL"
    clone_or_refresh "$RUNNER_HOME/agentdojo-upstream" agentdojo.bundle "$AGENTDOJO_URL" "$AGENTDOJO_REF"
    clone_or_refresh "$RUNNER_HOME/injecagent-upstream" injecagent.bundle "$INJECAGENT_URL"
    if [ ! -f "$RUNNER_HOME/runner.json" ]; then
        sed "s/\"shorthost\": \"lin01\"/\"shorthost\": \"$(hostname -s | tr 'A-Z' 'a-z')\"/" \
            "$RUNNER_HOME/XA_guard/tools/remote-runner/runner-config.example.json" > "$RUNNER_HOME/runner.json"
        echo "wrote $RUNNER_HOME/runner.json - review it (gate URLs, operator)"
    fi
}

do_python() {
    [ -d "$RUNNER_HOME/venv" ] || python3 -m venv "$RUNNER_HOME/venv"
    "$RUNNER_HOME/venv/bin/pip" install --upgrade pip
    "$RUNNER_HOME/venv/bin/pip" install -e "$RUNNER_HOME/XA_guard[bench]"
    # budget-plan imports agentdojo.task_suite at planning time.
    "$RUNNER_HOME/venv/bin/pip" install -e "$RUNNER_HOME/agentdojo-upstream"
}

do_opencode() {
    if ! command -v opencode >/dev/null 2>&1; then
        curl -fsSL https://opencode.ai/install | bash
        echo 'ensure ~/.opencode/bin (or the printed location) is on PATH'
    fi
    mkdir -p "$RUNNER_HOME/oc-config/opencode" "$RUNNER_HOME/oc-data"
    if [ ! -f "$RUNNER_HOME/oc-config/opencode/opencode.json" ]; then
        # Minimal deny-by-default permission config. Its tree hash is frozen
        # into the budget plan (opencode_permission_config_sha256): once
        # `runnerctl init` has run, do NOT touch this file.
        cat > "$RUNNER_HOME/oc-config/opencode/opencode.json" <<'EOF'
{
  "$schema": "https://opencode.ai/config.json",
  "permission": {
    "edit": "deny",
    "bash": "deny",
    "webfetch": "deny"
  }
}
EOF
        echo "wrote minimal opencode permission config (frozen after init)"
    fi
    echo
    echo "MANUAL STEP (once): log the subscription in with the dedicated XDG dirs:"
    echo "  XDG_CONFIG_HOME=$RUNNER_HOME/oc-config XDG_DATA_HOME=$RUNNER_HOME/oc-data opencode auth login"
}

do_units() {
    [ "$(id -u)" = 0 ] || die "run 'units' with sudo"
    src="$RUNNER_HOME/XA_guard/tools/remote-runner/systemd"
    for unit in xa-runner.service xa-watchdog.service xa-watchdog.timer xa-alert@.service; do
        sed -e "s|__RUNUSER__|$RUNUSER|g" \
            -e "s|__RUNNER_HOME__|$RUNNER_HOME|g" \
            -e "s|__EVIDENCE_ROOT__|$EVIDENCE_ROOT|g" \
            "$src/$unit" > "$UNIT_DIR/$unit"
    done
    systemctl daemon-reload
    systemctl enable xa-runner xa-watchdog.timer
    systemctl start xa-watchdog.timer
    echo "units enabled (xa-runner starts on boot; not started now - use runnerctl resume)"
}

do_verify() {
    status=0
    check() { # check <label> <command...>
        label=$1; shift
        if "$@" >/dev/null 2>&1; then
            printf 'OK    %s\n' "$label"
        else
            printf 'FAIL  %s\n' "$label"
            status=1
        fi
    }
    check "XA_guard clone"          git -C "$RUNNER_HOME/XA_guard" rev-parse HEAD
    check "XA_guard clean tree"     sh -c "[ -z \"\$(git -C '$RUNNER_HOME/XA_guard' status --porcelain)\" ]"
    check "agentdojo upstream"      sh -c "ls '$RUNNER_HOME/agentdojo-upstream/LICENSE' '$RUNNER_HOME/agentdojo-upstream/LICENCE' 2>/dev/null | grep -q ."
    check "injecagent upstream"     sh -c "ls '$RUNNER_HOME/injecagent-upstream/LICENSE' '$RUNNER_HOME/injecagent-upstream/LICENCE' 2>/dev/null | grep -q ."
    check "venv python"             "$RUNNER_HOME/venv/bin/python" --version
    check "agentdojo importable"    "$RUNNER_HOME/venv/bin/python" -c "import agentdojo"
    check "xa repo importable"      "$RUNNER_HOME/venv/bin/python" -c "import bench.external.budget"
    check "opencode CLI"            opencode --version
    check "opencode glm-5.2 model"  sh -c "XDG_CONFIG_HOME='$RUNNER_HOME/oc-config' XDG_DATA_HOME='$RUNNER_HOME/oc-data' opencode models | grep -q glm-5.2"
    check "runner.json"             sh -c "jq -e .shorthost '$RUNNER_HOME/runner.json'"
    check "chrony synchronized"     sh -c "chronyc tracking | grep -q 'Leap status *: Normal'"
    check "disk >= 5GB free"        sh -c "[ \"\$(df -Pk \"$HOME\" | awk 'NR==2 {print \$4}')\" -ge 5242880 ]"
    check "provider URL reachable"  curl -fsS --max-time 10 -o /dev/null https://opencode.ai/
    if command -v systemctl >/dev/null 2>&1; then
        check "xa-runner enabled"   sh -c "systemctl is-enabled xa-runner | grep -q enabled"
        check "watchdog timer live" systemctl is-active --quiet xa-watchdog.timer
    fi
    [ "$status" = 0 ] && echo && echo "ALL GREEN - proceed with: runnerctl init" || echo "fix FAIL items before init"
    return "$status"
}

CMD=${1:-}
case "$CMD" in
    system)   do_system ;;
    repo)     do_repo ;;
    python)   do_python ;;
    opencode) do_opencode ;;
    units)    do_units ;;
    verify)   do_verify ;;
    all)
        [ "$(id -u)" != 0 ] || die "run 'all' as the run user, not root (system/units are separate sudo steps)"
        step repo;     do_repo
        step python;   do_python
        step opencode; do_opencode
        step verify;   do_verify
        ;;
    *) die "usage: bootstrap.sh system|repo|python|opencode|units|verify|all" ;;
esac
