# tools/remote-runner 工作日志

## 2026-07-10
修复 Windows 未把 Git Bash 加入 PATH 时 supervisor 硬编码 `sh` 导致离线测试失败的问题：优先 PATH，回退 Git for Windows 路径；`tests/remote_runner` 13 passed。新增根 `requires.txt` 供组员安装开发验证依赖；未改远程 Linux 运行语义。

## 2026-07-09
新建远程无人值守运行系统：supervisor.py（时钟/网络门控→budget-resume 批次状态机，
exit 0/1/2/3/4 分类，三处人工花钱门，FAILED_TERMINAL/infra 濒危/连续坏批熔断，
心跳与 ALERTS 原子落盘断电不丢）；runnerctl 操作员 CLI（含 revive 复活与 seal 收尾，
seal 后归档 current-run 防止污染已封存 run）；watchdog（2min 拉活+心跳过期检测，
paused 标志防误拉）；systemd 三单元（开机自启）；bootstrap 幂等部署（bundle 离线优先，
verify 全绿才许 init）；Windows 侧 push-repo/poll-status。离线单测 12 例全过
（tests/remote_runner，假 orchestrator 剧本驱动）。未做：服务器实机冒烟、真实付费校准。

补：本机真实 orchestrator 端到端冒烟通过（init 真实 budget-plan 32 jobs + approve +
budget-resume --dry-run 批次，run 目录/commands/console/health 全对）；冒烟抓到并修复
子进程缺 PYTHONPATH 导致 `bench` 不可导入的 bug；离线单测增至 13 例（含 dry-run 透传）。
