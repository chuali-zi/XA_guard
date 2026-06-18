# docker 模块工作日志

---

## 2026-06-17 09:30 Codex 主 agent
- `docker-compose.yml` 默认包含 `sandbox-image` 构建，不再依赖手动 profile；`xa-guard` 服务声明依赖 sandbox 镜像服务。
- `xa-guard.Dockerfile` 安装 Docker CLI，用于容器内通过挂载的 Docker socket 执行 Gate5 `docker run`。
- `sandbox.Dockerfile` 内置 `src/`、`demo/` 和项目依赖，配合 `configs/xa-guard.docker.yaml` 的 `workspace_mount: false`，避免 Docker-outside-of-Docker 场景下路径错绑。
- `docker compose config` 已通过；实际 `docker compose build sandbox-image` 因本机 Docker daemon 未启动未能验证。
