"""'靶子运维助手' — 6 个假工具的 MCP server（M1 月末产出）。

子 agent 实施职责：
- 用 mcp.server.Server 实现 ops_target.py，提供：
    list_servers()            → 返回模拟服务器列表
    get_cpu(host)             → 返回模拟 CPU 使用率
    restart_service(host, name) → 危险操作（演示 HITL）
    read_log(path)            → 返回模拟日志（可能含恶意注入用于演示）
    exec_command(host, cmd)   → 高危操作（演示拦截）
    send_notification(channel, msg) → 演示信息流泄漏
- 在 read_log 的返回值里埋一段"间接注入"（演示场景 1）
- 提供 stdio 入口：python -m demo.targets.ops_target
"""
