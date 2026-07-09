#!/bin/sh
# push-repo.sh <host> [--agentdojo DIR] [--injecagent DIR]
# Run from Git Bash on the Windows workstation. Creates git bundles of
# XA_guard (HEAD) and, when the local upstream clones are provided, of
# AgentDojo and InjecAgent, then scp's them to <host>:~/xa-runner/bundles/
# so bootstrap.sh repo can clone offline (the campus network often cannot
# reach GitHub from the VM).
set -eu

HOST=${1:-}
[ -n "$HOST" ] || { echo "usage: push-repo.sh <host> [--agentdojo DIR] [--injecagent DIR]" >&2; exit 1; }
shift

AGENTDOJO_DIR=""
INJECAGENT_DIR=""
while [ $# -gt 0 ]; do
    case "$1" in
        --agentdojo) AGENTDOJO_DIR=$2; shift 2 ;;
        --injecagent) INJECAGENT_DIR=$2; shift 2 ;;
        *) echo "unknown argument: $1" >&2; exit 1 ;;
    esac
done

REPO=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

echo "bundling XA_guard (HEAD of $(git -C "$REPO" rev-parse --abbrev-ref HEAD))..."
git -C "$REPO" bundle create "$STAGE/xa_guard.bundle" HEAD --branches --tags

if [ -n "$AGENTDOJO_DIR" ]; then
    echo "bundling agentdojo from $AGENTDOJO_DIR..."
    git -C "$AGENTDOJO_DIR" bundle create "$STAGE/agentdojo.bundle" --all
fi
if [ -n "$INJECAGENT_DIR" ]; then
    echo "bundling injecagent from $INJECAGENT_DIR..."
    git -C "$INJECAGENT_DIR" bundle create "$STAGE/injecagent.bundle" --all
fi

ssh "$HOST" 'mkdir -p ~/xa-runner/bundles'
scp "$STAGE"/*.bundle "$HOST:~/xa-runner/bundles/"
echo "done; on the server run: sh ~/xa-runner/XA_guard/tools/remote-runner/bootstrap.sh repo"
echo "(first push: scp the bundle, clone it manually once, then bootstrap from inside the clone)"
