# Auto-RedTeam 持续运行维护

`maintain.py` 是 Conductor 外层的跨平台前台 supervisor。它只维护进程可用性，不修改攻击目标、策略、预算、scope 或 evidence 判定。

## 能力

- 监控 supervisor PID、Conductor PID 和 `.state` 最近进度时间。
- 异常退出或进度超时后指数退避重启；正常退出不重启。
- 一小时内默认最多重启 5 次，超过后进入 `halted`，避免故障循环烧钱。
- 原子写 `.state/maintainer/status.json`，轮转 `conductor.log`，单实例锁可回收陈旧 PID。
- `stop` 是持久 kill switch。服务被外部管理器再次拉起时仍保持停止，必须显式 `resume`。

## 使用

以下命令应在 `open-agent-range/auto-redteam/` 执行。真实运行前，当前分支必须包含 `conductor/conductor.py`，并准备经过审核的配置文件。

```powershell
python maintain.py resume
python maintain.py run --config conductor/my-config.yaml
```

查看机器可读健康状态：

```powershell
python maintain.py status
```

返回码：健康为 `0`，未启动/非健康为 `3`。停止：

```powershell
python maintain.py stop
```

默认 15 秒检查一次；若 `.state` 40 分钟没有任何进度文件变化，会终止并重启 Conductor。`--stale-after-s` 应大于配置中的 `run_timeout_s` 加安全余量，避免把合法长任务误杀。

## 托管建议

生产式持续运行时，让 systemd、Windows Task Scheduler 或容器编排器托管下面这个前台命令，并根据非零退出码告警：

```text
python maintain.py run --config conductor/my-config.yaml
```

外层服务管理器可以在 supervisor 崩溃时重启它，但不要自动执行 `resume`。预算耗尽、`max_runs` 达到上限等正常完成会写 `completed` 并以 0 退出；需要人工检查配置和预算后再启动下一轮。

状态文件关键字段：`state`、`healthy`、`supervisor_pid`、`child_pid`、`restart_count_window`、`last_exit_code`、`last_reason`、`progress_stale_for_s`。
