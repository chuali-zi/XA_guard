# 仓库状态：XA-Guard / XA-202620

> 快照日期：**2026-07-21**（America/Los_Angeles）
> 当前统一口径：**CORE-IMPLEMENTED / KIND-HA-PASS / PERFORMANCE-PASS / RELEASE-NOT-FROZEN**
> 比赛交付口径：[docs/acceptance/DELIVERY-v2.md](docs/acceptance/DELIVERY-v2.md)
> 本文件只描述当前状态；工作历史见 [log.md](log.md)。

## 总体结论

Gate1–6、OAR 主评测、MCP 代理、OIDC + 动态 assignment、PostgreSQL Effect、可审批 Undo、Worker 补偿、Console/BFF 和本地 kind HA 主路径均已实现。Identity + Undo 的功能、故障、链完整性、恢复时延与正式并发性能目前均通过 Reference 验证；性能硬缺口已从状态中关闭。

当前仍不冻结发布。Reference all fault、证据重封存、独立验签和 final release manifest 尚未按最新性能候选重跑，因此状态不是最终冻结发布。

## 2026-07-21 当前验证基线

- 全仓 pytest：**782 collected / 777 passed / 5 skipped / 0 failed**，耗时 291.9s。4 个 skip 为本机缺 Helm，1 个为 Windows directory-symlink capability。
- 本轮并发/链尾/intent-first/审计/性能相关定向回归：**27 passed**。
- Reference core fault suite：**7/7 passed**，场景净耗时 231.016s；覆盖身份拒绝、伪造 header、assignment 立即撤销、跨租户隔离、PostgreSQL 中断、prepared-effect 恢复、并发双审批单任务。
- fault suite 后 SQL 全链检查：Effect chain gaps 0、Gate6 chain gaps 0、Effect tail mismatches 0、Gate6 tail mismatches 0。
- Reference Compose 已由当前候选源码完整重建；PostgreSQL、Keycloak、business-api、xa-guard、worker、Console 均运行，schema 为 **v8**，故障钩子开启，Server-Timing 关闭。
- 当前库约有 99,556 条 Effect event、98,701 条 Gate6 event；完整长期压测库未做清空或以空库制造通过。
- 产品文件与本轮新增测试 Ruff 通过；未修改测试阈值或既有断言来制造通过。
- 当前全局 Python 仍有 letta-evals 0.13.0 要求 anyio==4.10.0、实际 anyio 4.14.1 的环境冲突；项目依赖文件未为此改写。

## 并发性能状态

### 最终实现

- prepared/completed Effect 使用同租户单 worker 微批；final 优先，仅空闲边界聚合 2ms。
- prepared Effect + pre-approval Gate6、final Effect + final Gate6 各自保持原子 CTE、双链固定顺序锁和 CAS。
- 当同一调度周期同时存在 final 与 prepared 批次时，两条 CTE 复用同一连接、双链锁和事务，保持 final→prepared 顺序但只提交一次。
- asyncpg JSON/JSONB 编码改为语义等价的紧凑 UTF-8，减少大型合同快照和 Gate6 记录的传输及 PostgreSQL JSON 解析量。
- 可选脱敏计时进一步区分 prepared/final 的批次 SQL、事务其余部分和混合事务总耗时；生产默认关闭。
- 原有批量 UNNEST、实时授权 SQL、xa_chain_tails、Gate6 LZ4/EXTENDED、intent-first、响应前审计持久化语义均保留。

### 正式结果

最终候选已经连续完成两组独立的正式 3×500。每轮均为 10 并发、30 warmup、500 paired writes、5000 次 bootstrap，incremental p95 与单侧 95% bootstrap upper 均要求 ≤50ms。

- 注入候选验证：
  - seed 20260735：p95/upper **39.049/40.249ms**
  - seed 20365464：p95/upper **38.899/40.065ms**
  - seed 20470193：p95/upper **42.827/45.149ms**
  - Undo 10/10，通过范围约 **0.22–0.97s**
- 完整重建镜像、默认配置、独立 seed 复验：
  - seed 20260741：p95/upper **45.109/46.984ms**
  - seed 20365470：p95/upper **42.141/43.120ms**
  - seed 20470199：p95/upper **43.934/45.528ms**
  - Undo 10/10，通过范围约 **0.45–0.94s**

紧凑 JSON 单独候选的重建复验曾只有 2/3 通过；加入混合批次单事务后，两组连续正式验收均通过。因此当前口径为 PERFORMANCE-PASS，而不是用单轮或单 seed 推断达标。

## 当前能力状态

| 能力面 | 状态 | 当前事实与边界 |
|---|---|---|
| Gate1–6、Gate6 审计、OAR B1–B5 | DONE | canonical OAR A/B、ledger replay 与 audit 对齐已有证据 |
| MCP 代理主形态 | LIVE-PASS | 真实 MCP JSON-RPC 9 场景、Gate6 审计链和 Console 三账号闭环已有证据 |
| OIDC 与动态 assignment | REFERENCE-PASS | 身份拒绝、伪造、撤销、跨租户通过；授权每请求实时查库 |
| PostgreSQL EffectStore | REFERENCE-PASS / PERFORMANCE-PASS | schema v8、intent-first、CAS 双链尾、批处理、混合单事务和正式 3×500 通过 |
| Undo / Worker | REFERENCE-PASS | core fault 与 20 次正式性能流程通过；至少一次 + 下游幂等，不宣称绝对 exactly-once |
| Console/BFF | BUILT / MANUAL-QA-PASS | Alice 建票/请求 Undo、Dora 批准、Admin 只读闭环通过 |
| Reference Compose | RUNNING / CORE-FAULT-PASS / PERFORMANCE-PASS | 当前候选完整重建；本轮 core 7/7；历史 all suite 11/11，long/keys 尚未按最终候选重跑 |
| Helm / kind HA profile | PASS-HISTORICAL | 本地三节点升级、接管、网络策略和回滚已有 PASS；本机当前缺 Helm，未重跑 |
| Evidence（Identity + Undo） | SEALED-HISTORICAL / NEEDS-RESEAL | 历史包独立验签通过；最终性能候选尚未重封存 |
| D2 release freeze | PARTIAL / NOT-FROZEN | 用户明确要求暂不冻结；final manifest 尚未生成 |

## 距离赛题目标的剩余事项

1. 按最终性能候选重跑 Reference all fault（core/long/keys），再采集并独立验签新证据包。
2. 在具备 Helm 的隔离环境重跑 kind/发布验证，并隔离全局 letta-evals/anyio 冲突。
3. 用户允许冻结后再执行 clean freeze、生成 final release manifest；当前不得提前冻结。
4. D1 PDF / D3 视频继续按负责人要求暂缓；D4 已完成。

## 声明边界

- kind PASS 只证明本机三节点 profile，不外推为生产多地域 HA。
- 本轮 core fault PASS 不替代最终候选尚未重跑的 long/keys。
- 注入候选的性能结果仅作交叉验证；最终性能结论同时有源码哈希一致的完整重建镜像结果支撑。
- .runtime/reference/、.runtime/kind-ha/、.runtime/evidence/ 含运行时数据或敏感材料且被 gitignore，不得提交。
- 本轮没有新增第三方依赖；紧凑 JSON、ContextVar 和事务复用均使用 Python/asyncpg/PostgreSQL 现有合法能力。
