# open-agent-range 工作日志

## 2026-07-04 完整架构 + SP 规划 + 一天蓝图（文档固化）
- 决策锁定（用户确认）：open-agent-range 为唯一 go-forward 家，SP1 内核吸收并泛化 `enterprise-agent-range/arena` 已验证模式 + spike 的 ledger 脊梁，丢弃 p0/p1/p2 遗留，enterprise-agent-range 降级为参考；本轮**只出文档**；一天锚定"数字城市科技集团"，蓝图写全 6 域。
- 产出 17 篇：`docs/architecture/` 6（system-overview/kernel-architecture/ledger-schema/decoupling-contract/injection-surface-model/evidence-and-accountability）；`docs/reference/` 5（enterprise-world/a-day-in-the-life/attack-surface/data-classification/expansion-roadmap）；`docs/specs/` SP1–SP6；并更新 `docs/README.md`（补 reference 分层 + 全量索引）。
- 守铁律：文档不写题/攻击/机密/payload；一天只写正常业务流 + 敞开注入面。
- 下一步：作者审文档；进 SP1 内核实现（移植 vs 新写清单见 SP1 spec）。

## 2026-07-04 SP0 适配性复查
- 对照 PRD/spec/status/spike.py 检查“真实一天沙盘”目标；离线重跑 `python spike.py`、`--probe-violation`、AST 语法检查均通过，未重跑 OpenCode live。结论：SP0 闭环合格，但复杂度不足，仍缺多流程世界、开放注入面、SUT、持久化账本和追责报告层。

## 2026-07-03 立项
- 决策：不重构旧 `enterprise-agent-range`（降级为静态题库/回归基线），在根目录新建 `open-agent-range/` 做**开放红队靶场平台**。
- 定调：内核通用 + 场景当数据；不脚本化攻击、不固化内核、开放一切注入面、真实优先；红队"赢"= 世界进入本不该出现的地面真值坏状态，判据从不可篡改账本读出。作者硬约束：纯模拟政企一天、不写题、红队任意角度自由渗透。
- 产出：`PRD.md`（薄，突出自由，作者审核后**已冻结**）。

## 2026-07-03 docs 规范
- 立 `docs/README.md`：文档三原则(薄/分层/不写题) + 分层职责表 + 命名约定(`SP<N>-<topic>-design.md`)。
- PRD 状态置为冻结。
- 下一步：进 SP1 内核世界模型——实体建模，首个决策=身份/Agent 建模。
