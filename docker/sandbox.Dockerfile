# xa-guard 下游 MCP 工具进程沙箱镜像。
# 与 Gate5 路由的 docker / docker_gvisor 模式配套：只读根 FS + 无网 + 降权由
# build_docker_command 在 `docker run` 参数层施加，这里只需提供一个最小 Python 运行时。
FROM python:3.12-slim

# 非 root 运行，配合 --cap-drop ALL / --security-opt no-new-privileges。
RUN useradd --create-home --uid 10001 sandbox
USER sandbox
WORKDIR /workspace

CMD ["python", "-c", "print('xa-guard sandbox ready')"]
