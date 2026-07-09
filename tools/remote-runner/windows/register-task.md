# Windows 侧监控计划任务

前置：ssh key 免密已配好（`ssh <host>` 不需要密码），`<host>` 建议是 `~/.ssh/config` 里的别名。

每 10 分钟轮询一次（管理员 PowerShell / cmd）：

```bat
schtasks /Create /SC MINUTE /MO 10 /TN "XA-R2R3-Poll" ^
  /TR "\"C:\Program Files\Git\bin\bash.exe\" -lc '/d/race/XA_guard/tools/remote-runner/windows/poll-status.sh <host>'"
```

- 新出现 WARN/CRITICAL 告警时会 `msg.exe` 弹窗 + 响铃；快照追加到 `D:/xa-evidence/remote/<host>/status-history.jsonl`。
- 手动看一眼当前状态：Git Bash 里直接跑 `tools/remote-runner/windows/poll-status.sh <host>`。
- 删除任务：`schtasks /Delete /TN "XA-R2R3-Poll" /F`。
- 证据采集（与轮询独立，跑完或想看中间产物时手动执行）：
  - 迭代期：`tools/evidence/collect.sh <host> --live`
  - 封存后：`tools/evidence/collect.sh <host> --sealed`（自动对 git 已提交 manifest 校验）
