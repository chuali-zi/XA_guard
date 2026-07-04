# SP6 演示与看板设计 — 现场对照

> 状态：设计草案，待作者审后进实现。依赖 SP1–SP5。
> 落地 PRD §8"成功长什么样"与 [../architecture/evidence-and-accountability.md](../architecture/evidence-and-accountability.md) §6。

## 目标

把整套能力收敛成一条命令的**现场对照 demo** + 一个看板，让评委一眼看懂"企业为什么不敢用、XA-Guard 到底解决了什么"，
并提供可信的 live 统计（非 smoke）。

## 边界

- 不做真实外发/凭据/公网目标。
- N=1 只标 smoke；正式统计须 N≥2 且带置信区间；smoke/人工/INFRA_ERROR 不混入全量口径。

## 模型

- **一条命令 demo**：同一真实场景跑两遍——
  - null：裸奔 agent 制造一次泄漏/混乱，事后账本链断裂、查不清是谁。
  - guard（XA-Guard）：同场景被拦下，账本一条链清清楚楚指向元凶。
- **看板**：并排展示两侧的 verdict、副作用、追责链，以及数字（ASR_null−ASR_guard、block rate、leak rate）。
- **live 统计层**：`repeat N` 聚合 attempt 表，攻击/良性/assurance 分开分母，输出 JSON/Markdown/HTML + artifact 索引 + hash。

## 判据

demo 两侧对照成立：null 侧"泄漏 + 不可追责"，guard 侧"拦截 + 一条清晰追责链"；数字方向正确（防护增量为正、leak 从 >0 到 0）。

## 验收

```
range demo --scenario <s>            # 一条命令跑出 null vs guard 对照 + 看板
range report --run <r>               # N≥2 的统计报告（ASR_null/ASR_guard/CI/artifact 索引）
```

预期：评委观看 demo 即理解产品价值；报告口径干净（不混 smoke/人工/INFRA_ERROR）。

## 后续

- 看板从 CLI/静态 HTML 演进到交互式 Web（与 SP4 Web 工作台合流）。
- 更多域/更多攻击类目进入常态对照与统计。
