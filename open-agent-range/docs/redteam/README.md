# Open Agent Range 红队使用手册索引

本目录给红队和学生使用，不改变 `PRD.md` 的北极星，也不把攻击写进内核。文档中的 payload 都是合成样例，只用于本地靶场复现。

## 文档

- [REDTEAM-AGENT-TECHNICAL-MANUAL.md](REDTEAM-AGENT-TECHNICAL-MANUAL.md)：详细技术手册，给红队选手和自动化 agent 使用。覆盖概念、命令、payload、finding、A/B、live xaguard、OpenCode、证据解读和常见坑。
- [STUDENT-QUICKSTART.md](STUDENT-QUICKSTART.md)：学生快速上手版，用最少命令跑通一次“裸奔泄漏 / 防护拦截 / 证据回放”。

## 2026-07-09 实测入口

```powershell
cd D:\race\XA_guard\open-agent-range
python -m kernel.workbench worlds
python -m kernel.workbench surfaces --world scenarios/dctg/office-channels.json
python -m kernel.demo --scenario scenarios/dctg/office-channels.json --inject scenarios/injections/office-multi-combo.json --ab
python -m kernel.range_cli workbench serve --world scenarios/dctg/full-day.json --out-dir .runtime\workbench --no-server --json
```

注意：列场景/开放面使用 `python -m kernel.workbench ...`；产品级控制台生成使用 `python -m kernel.range_cli workbench serve ...`。