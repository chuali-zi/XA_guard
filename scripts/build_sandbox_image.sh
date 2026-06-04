#!/usr/bin/env bash
# 构建 Gate5 下游沙箱镜像 xa-guard/sandbox:latest。
# tests/integration/test_sandbox_runner.py 依赖此镜像；缺失时该用例会被 skip。
#
# Windows + Docker Desktop 下，docker.exe 常不在 Git-Bash 的 PATH 里，先补上：
#   export PATH="/c/Program Files/Docker/Docker/resources/bin:$PATH"
set -euo pipefail

IMAGE="${1:-xa-guard/sandbox:latest}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

docker build -f "${REPO_ROOT}/docker/sandbox.Dockerfile" -t "${IMAGE}" "${REPO_ROOT}"
echo "built ${IMAGE}"
