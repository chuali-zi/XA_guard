# Open Agent Range 状态

更新时间：2026-07-04

## 当前状态

仓库处在 SP0 walking skeleton 已跑通阶段，已从只有 PRD/docs 的空架子推进到一个可运行 spike：

- `PRD.md` 已冻结，仍是唯一北极星。
- `docs/README.md` 保留文档分层和“不写题”约束。
- `docs/specs/SP0-walking-skeleton-design.md` 描述当前 spike 的目标、边界、模型和验收。
- `spike.py` 已实现最小世界：场景数据、正常业务流、hash-chain 账本、工具表面、属性判据、scripted Seat、OpenCode Seat adapter。
- **完整设计已固化进文档（2026-07-04）**：`docs/architecture/` 6 篇（system-overview / kernel-architecture / ledger-schema / decoupling-contract / injection-surface-model / evidence-and-accountability）、`docs/reference/` 5 篇（数字城市科技集团世界 + 完整一天时间线 + 攻击面 + 数据分级 + 拓展路线）、`docs/specs/` SP1–SP6，`docs/README.md` 已补 reference 分层与全量索引。这一轮**只固化设计、未写 runtime 代码**。

本次复查结论：它符合 **SP0 walking skeleton** 的预期，但还不符合 PRD 中“真实政企一天沙盘”的完整预期。当前复杂度仍是单 seat、少量背景事件和一个属性判据，适合证明闭环，不适合直接交给红队自由渗透。通往完整预期的路径已由上述文档钉死（SP1 内核 → SP2 DCTG 一天数据化 → SP3 注入面 → SP4 工作台 → SP5 追责 → SP6 演示）。

## 已验证能力

- `python spike.py` 已通过：离线跑完一个正常业务日，并断言账本无敏感数据外发违规。
- `python spike.py --probe-violation` 已通过：人为追加一个坏账本事实后，判据能从账本识别敏感数据外发。
- `python spike.py --agent opencode --model deepseek/deepseek-v4-flash` 已通过：OpenCode/DeepSeek 产出 JSON action plan，世界通过同一工具表面执行并落账，最终零违规。
- `python -c "import ast, pathlib; ast.parse(pathlib.Path('spike.py').read_text(encoding='utf-8')); print('syntax ok')"` 已通过：`spike.py` 语法检查通过且不产生 `.pyc`。
- 2026-07-04 本次复查重跑了离线 `python spike.py`、`python spike.py --probe-violation` 和 AST 语法检查，均通过；未重跑 OpenCode live 调用。

## 与 PRD 的距离

已经证明的部分：

- 世界可以作为数据驱动的模拟环境运行。
- 判据可以是账本上的属性，而不是攻击脚本。
- Seat/agent 可以作为适配层接入，不需要污染内核判据。

尚未完成的关键部分：

- 还没有正式 SP1 内核包结构、场景 schema、持久化账本或 property engine 插件化。
- OpenCode Seat 目前是一轮严格 JSON action plan，不是完整多轮 tool loop。
- 还没有 XA-Guard/SUT in-the-loop。
- 还没有通用注入面、红队工作台、多 agent 追责或演示看板。
- 账本 hash chain 仍是内存 spike，不是正式不可篡改存储。
- “一天”还不是世界级仿真：没有业务时钟、排班、队列、审批状态、跨部门依赖、失败重试、并发事件或可持续变化的组织/数据状态。
- “自由红队”还没有入口：当前 prompt 明确要求安全计划，攻击只靠 `--probe-violation` 人工追加坏事实，尚未开放邮件、文档、插件、MCP、员工、供应链等多注入面。
- “追责”仍是账本字段雏形：没有身份链、授权链、委托链、证据包、报告或反事实对照。

## 下一步

1. 作者审阅本轮固化的架构/一天/SP 文档；如需改北极星须显式走评审。
2. 进 SP1 内核实现：按 `docs/specs/SP1-kernel-design.md` 的"移植 vs 新写"清单，从 arena 移植 surface/seat/sut/policy_overlay/oracle/evidence，从 spike 移植并扩展 ledger，新写 property engine 与 scenario schema。
3. SP2 把 `spike.py` 内联场景外置为 DCTG fixtures（先竖切 Office + 业务数据），并接第二个域证明"加域=加数据、不改内核"。
4. 把 OpenCode Seat 从一轮 action plan 扩展为多轮 tool loop，再接入 SUT/XA-Guard 裁决点（真实 live 需显式授权）。
