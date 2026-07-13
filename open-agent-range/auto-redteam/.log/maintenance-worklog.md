# 2026-07-12 Auto-RedTeam 持续运行维护

- 新增跨平台前台 supervisor `maintain.py`：监控进程与状态进度，异常退出指数退避恢复，重启频率熔断，正常完成不误重启。
- 增加原子状态、持久 stop/resume、单实例锁、陈旧锁回收、日志轮转和离线单测；未合并 `feat/cursor-auto-redteam` 的 Conductor 源码，当前 main 需先整合该实现才能真实运行。
