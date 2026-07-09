# remote-runner —— R2/R3 budget60 远程无人值守运行系统

在一台远程 Linux 服务器（Proxmox VM，校园网）上无人值守跑完 R2/R3 官方抽样验收
（`subscription_budget60_v1`，$60 硬顶），证据严格按
`docs/acceptance/remote-evidence/EVIDENCE-LAYOUT-SPEC.md` 落盘并传回本机。

核心原则：**监督层只包裹、不修改** `scripts/run_r2_r3_acceptance.py`。

## 架构

```
Windows 本机                            Linux VM (Proxmox, 校园网)
─────────────                           ──────────────────────────
windows/push-repo.sh   ── bundle ──▶    bootstrap.sh (部署引导, 幂等)
windows/poll-status.sh ◀── ssh ───      systemd: xa-runner.service ─▶ supervisor.py
tools/evidence/collect.sh ◀ rsync ─              xa-watchdog.timer ─▶ watchdog.sh
                                        证据: ~/xa-evidence/runs/<run-id>/  (规范七件套)
                                             orchestrator 输出 = <run>/artifacts/orchestrator/
```

- **supervisor.py**：守护进程。每个付费批次前先过时钟门控（chrony 同步，掉电重启后
  RTC 漂移不放行）和网络门控（provider 连续 2 次可达才放行——断网时等待，
  不让 orchestrator 空转烧掉 `max_job_resume_attempts` 打成 FAILED_TERMINAL）。
  按退出码状态机推进，见下。
- **watchdog.sh**（每 2min）：服务死了 / 心跳超 5min → 自动拉起 + CRITICAL 告警；
  另查磁盘、时钟漂移。`runnerctl pause` 会写 `~/xa-runner/paused` 阻止误拉。
- **报警**：全部先原子追加到 `<run>/artifacts/supervisor/ALERTS.jsonl`
  （O_APPEND+fsync，断网断电不丢，随 run 封存成为证据），Windows 侧轮询弹窗。

## phase 状态机

```
READY ─approve calibration→ CALIBRATION ─批次循环至 no pending→ CALIB_DONE
CALIB_DONE ─approve freeze→ FREEZE(budget-freeze) ─FROZEN─ approve main→ MAIN
MAIN ─批次循环→ MAIN_DONE →(自动) AGGREGATE →(自动) VERIFY → AWAIT_SEAL ─人工 seal→ 结束
任意批次: exit2→halt(budget_exhausted)  exit3→halt(execution_lock_failed)
          exit4→QUOTA_WAIT 每30min轮询(quota拒绝不计费)  exit1→冷却+批次降为2
熔断(halt): 30min内新增FAILED_TERMINAL≥2 / 濒危infra_error≥6 / 连续2批失败率≥50% / 连续3次异常退出
```

三处人工门都是花钱节点：`runnerctl approve calibration|freeze|main`。
halt 后修好原因执行 `runnerctl revive`。

## 部署流程（服务器，一次性）

```sh
# 0) Windows 侧推 bundle（服务器连不上 GitHub 时）：
#    tools/remote-runner/windows/push-repo.sh <host> --agentdojo <本地agentdojo克隆> --injecagent <本地injecagent克隆>
#    第一次没有仓库时：先 scp bundle 上去，git clone ~/xa-runner/bundles/xa_guard.bundle ~/xa-runner/XA_guard
sudo sh ~/xa-runner/XA_guard/tools/remote-runner/bootstrap.sh system
sh      ~/xa-runner/XA_guard/tools/remote-runner/bootstrap.sh all      # repo+python+opencode+verify
# 手动一步：订阅登录（只需一次）
XDG_CONFIG_HOME=~/xa-runner/oc-config XDG_DATA_HOME=~/xa-runner/oc-data opencode auth login
sudo sh ~/xa-runner/XA_guard/tools/remote-runner/bootstrap.sh units
sh      ~/xa-runner/XA_guard/tools/remote-runner/bootstrap.sh verify   # 必须全绿
```

## 运行流程

```sh
alias runnerctl='sh ~/xa-runner/XA_guard/tools/remote-runner/runnerctl.sh'
runnerctl init                    # 建证据 run + 冻结 local config + budget-plan（免费）
runnerctl resume                  # 启动守护（此时 READY，等门）
runnerctl approve calibration     # ← 第一次真花钱（$6 校准桶封顶）
runnerctl status                  # 随时看
# 校准跑完(CALIB_DONE) → 人工审 ledger + 校准 job 结果，然后：
runnerctl approve freeze
# FROZEN → 人工审 artifacts/orchestrator/sample-manifest.json，然后：
runnerctl approve main
# ... MAIN 跑数天，断电断网自动恢复 ...
# AWAIT_SEAL → 人工写 RESULTS.md 结论（首行=最终 result），然后：
runnerctl seal --result PASS      # 或 LIMIT/BLOCKED/INFRA_ERROR
```

收尾（Windows 侧）：

```sh
tools/evidence/collect.sh <host> --sealed        # rsync + 对已提交 manifest 校验
# 把 seal 打印的 manifest 行提交进：
#   docs/acceptance/remote-evidence/provenance-manifest.jsonl（原文一行）
#   docs/acceptance/remote-evidence/PROVENANCE.md（表格一行）
# commit + push —— git 是唯一信任锚（规范 §4）
```

## 断电/断网行为

- 宿舍晚上断电：所有状态（state/health/ALERTS/job 结果）随写随落盘（原子替换或
  O_APPEND+fsync），掉电最多丢当前正在跑的一个 job 的半成品。
- 早上来电：物理机 BIOS 自动上电 → PVE onboot 拉 VM → systemd 起 chrony →
  `xa-runner` 自启 → 时钟门控等 NTP 收敛 → 网络门控等校园网保活续上 →
  `budget-resume` 幂等续跑（已完成 job 被 `_result_matches` 跳过，不重复付费）。
- 断网：网络门控退避等待（60s→300s，10min 后 WARN 落盘）；恢复后自动继续。
- 订阅额度耗尽（5h/周窗口）：exit 4 → QUOTA_WAIT，每 30min 轮询，恢复自动继续
  （quota 拒绝不计费）；>24h 未恢复升 WARN。

## Proxmox / 宿主机 checklist（人工核对，不是脚本）

- [ ] VM 开机自启：PVE 上 `qm set <vmid> --onboot 1`（或 UI: Options → Start at boot）。
- [ ] `qm set <vmid> --agent enabled=1`，VM 内 qemu-guest-agent 已由 bootstrap 装好并 enable。
- [ ] 物理机 BIOS：`AC Power Loss → Power On`（断电来电自动开机，整条链路的第一环）。
- [ ] VM 磁盘余量 ≥ 20GB（jobs 目录会长大；watchdog <2GB 会 WARN）。
- [ ] 校园网 1min 保活脚本建议做成 systemd timer（`OnUnitActiveSec=1min`，
      `Persistent=true`），确保重启后无需人工登录校园网；否则来电后网络门控会一直等。
- [ ] Windows → VM 的 ssh key 免密；`~/.ssh/config` 里给 VM 起别名（poll/collect 都用它）。
- [ ] Windows 计划任务已注册（见 `windows/register-task.md`）。

## 证据映射（与规范的对应关系）

- run-id：`l3-r2r3-budget60-<UTCstamp>-<shorthost>`。R2+R3 合并为一个 run，因为
  budget-plan / 四桶 ledger / sample-manifest / sampled-report 是两题共享的单文件，
  拆开会导致同一 ledger 进两个 sealed 包。meta.json `notes` 与 manifest 注明覆盖
  `l3-r2-agentdojo` + `l3-r3-injecagent`（sampled）。
- orchestrator `output_dir` = `<run>/artifacts/orchestrator/` → 逐 case trace、
  官方 scorer 输出、cost ledger、全部失败/invalid/timeout 样本天然进入 artifacts/
  并被 artifact-hashes.json 覆盖（L3 文档对 R2/R3 的证据要求）。
- local config 冻结在 `<run>/artifacts/config/acceptance.local.json`，其 sha256 被
  orchestrator 冻入 budget-plan —— **init 之后不得改动**（改了 = exit 3 lock fail）。
- 每条命令原文进 `commands.txt`，stdout/stderr 逐字进 `console.log`（规范 §2.4）。

## 文件清单

| 文件 | 职责 |
|---|---|
| `supervisor.py` | 守护：门控 + 状态机 + 熔断 + 心跳/告警落盘 |
| `runnerctl.sh` | 操作员 CLI：init/status/approve/pause/resume/revive/seal/logs |
| `watchdog.sh` | 拉活 + 磁盘/时钟检查（xa-watchdog.timer 每 2min） |
| `bootstrap.sh` | 幂等部署：system/repo/python/opencode/units/verify |
| `runner-config.example.json` | 全部阈值/路径参数模板 → `~/xa-runner/runner.json` |
| `systemd/*` | 单元模板（bootstrap units 替换占位符后安装） |
| `windows/push-repo.sh` | git bundle → scp（离线部署源） |
| `windows/poll-status.sh` | ssh 轮询 health/ALERTS，新告警弹窗 |
| `windows/register-task.md` | schtasks 注册说明 |
| `../evidence/*.sh` | 规范 §6 契约：new-run/seal-run/verify-run/collect |
| `../../tests/remote_runner/` | 离线单测（假 orchestrator 剧本，不花钱不联网） |
