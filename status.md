# 仓库状态：XA-Guard / XA-202620

> 快照日期：**2026-07-20**（America/Los_Angeles）
> 当前统一口径：**CORE-IMPLEMENTED / KIND-HA-PASS / PERFORMANCE-IMPROVED-NOT-STABLE / RELEASE-NOT-FROZEN**
> 比赛交付口径：[docs/acceptance/DELIVERY-v2.md](docs/acceptance/DELIVERY-v2.md)
> 本文件只描述当前状态；工作历史见 [log.md](log.md)。

## 总体结论

Gate1–6、OAR 主评测、MCP 代理、OIDC + 动态 assignment、PostgreSQL Effect、可审批 Undo、Worker 补偿、Console/BFF 和本地 kind HA 主路径均已实现。Identity + Undo 的功能、故障、链完整性和恢复时延在 Reference 环境通过；并发写路径相较本轮起点显著改善，但正式 3×500 的 p95 与 bootstrap 上界仍不能连续稳定满足 ≤50ms，因此当前仍不标记 REFERENCE-READY。

本轮没有冻结发布。代码将整理提交，但不生成 final release manifest、不重封存证据、不宣称生产 HA。

## 2026-07-20 当前验证基线

- 全仓 pytest：**778 collected / 773 passed / 5 skipped / 0 failed**。4 个 skip 为本机缺 Helm，1 个为 Windows directory-symlink capability。
- 本轮并发/链尾/授权/intent-first/Undo 相关回归：**25 passed**。
- Reference core fault suite：**7/7 passed**，包含身份拒绝、伪造 header、assignment 立即撤销、跨租户隔离、PostgreSQL 中断、prepared-effect 恢复、并发双审批单任务。
- 故障套件后 SQL 全链检查：Effect gaps 0、Gate6 gaps 0、Effect tail mismatches 0、Gate6 tail mismatches 0。
- Reference Compose：PostgreSQL、Keycloak、business-api、xa-guard、worker 均在运行；API/Worker 使用最终候选源码；schema 为 **v8**；故障钩子开启，Server-Timing 关闭。
- 产品相关 Ruff 与本轮新增测试 Ruff 通过。全仓 Ruff 仍有 **19 个既有测试代码样式告警**，主要是未使用 import 和测试变量名；未修改测试来消除这些告警。
- 当前全局 Python 环境仍有 letta-evals 0.13.0 要求 anyio==4.10.0、实际 anyio 4.14.1 的环境冲突；项目依赖文件未为此做不安全改写。

## 并发性能状态

### 已完成的优化

- 将 prepared/completed Effect 的同租户写入统一成单 worker 微批，消除任务碎片化。
- prepared Effect + pre-approval Gate6 在一个事务内写入；final Effect + final Gate6 在一个事务内写入，保持 intent-first 和响应前持久化。
- 新增 xa_chain_tails 双链尾表和固定顺序 FOR UPDATE + CAS；跨实例缓存冲突只重试一次。
- Worker、Undo、独立 Effect/Gate6 旧写入路径与链尾表在同一事务推进，避免 API/Worker 交错后断链。
- prepared/final 使用统一按租户调度器；final 优先；仅空闲边界聚合 2ms，已有 backlog 立即处理。
- Effect completion 使用批量 UNNEST UPDATE；Gate6 CTE 改为有序列数组 unnest，去掉外层 Gate6 JSON 数组拆解。
- assignment 授权匹配下推到 PostgreSQL 单行实时查询，不做 TTL 缓存，撤销语义保持即时。
- schema v8 为完整 Gate6 JSONB 启用 PostgreSQL 内置 LZ4，保留 EXTENDED 存储、完整证据字段和可重放性。
- 性能脚本增加可选、脱敏的 Server-Timing 诊断；Docker Compose 瞬时查询失败只在 Undo 有界轮询内重试，持续失败仍会超时失败。

### 当前数据

- 本轮起点 200-pair 诊断：增量 p95 **113.891ms**、bootstrap upper **178.923ms**。
- 200-pair 中间候选曾达到 p95/upper **43.530/45.076ms**，Undo 3/3 在 1 秒内。
- 最终候选三个正式 seed 分开跑 500 pairs 均通过：
  - seed 20260712：p95/upper **44.472/49.042ms**
  - seed 20365441：p95/upper **41.127/42.445ms**
  - seed 20470170：p95/upper **41.397/44.928ms**
- 但连续正式 3×500 仍不稳定。当前长期压测库维护后的最新正式报告为 p95 **52.598/55.185/54.988ms**、upper **54.528/58.092/56.402ms**，10 次 Undo 全部通过，批准到取消约 **0.50–0.89s**。
- 当前测试库已有约 7 万条 Effect/Gate6 事件；数据库无 deadlock、链断点或 tail mismatch。环境波动不能当作通过理由，正式性能阻塞保持未关闭。

结论：性能问题已经从数量级锁等待降到阈值附近，功能与一致性回归通过；但作品口径仍为 PERFORMANCE-IMPROVED-NOT-STABLE，B6/B7 和 D2 不得因单轮或单 seed 通过而标记完成。

## 当前能力状态

| 能力面 | 状态 | 当前事实与边界 |
|---|---|---|
| Gate1–6、Gate6 审计、OAR B1–B5 | DONE | canonical OAR A/B、ledger replay 与 audit 对齐已有证据 |
| MCP 代理主形态 | LIVE-PASS | 真实 MCP JSON-RPC 9 场景、Gate6 审计链和 Console 三账号闭环已有证据 |
| OIDC 与动态 assignment | REFERENCE-PASS | 身份拒绝、伪造、撤销、跨租户通过；授权每请求实时查库 |
| PostgreSQL EffectStore | REFERENCE-PASS / PERF-LIMIT | schema v8、intent-first、CAS 双链尾、reconciler、批处理通过；正式性能仍不稳定 |
| Undo / Worker | REFERENCE-PASS | core fault 通过；至少一次 + 下游幂等，不能宣称绝对 exactly-once |
| Console/BFF | BUILT / MANUAL-QA-PASS | Alice 建票/请求 Undo、Dora 批准、Admin 只读闭环通过 |
| Reference Compose | RUNNING / CORE-FAULT-PASS / PERF-LIMIT | 当前整栈健康；本轮 core 7/7；历史 all suite 11/11，long/keys 本轮未重跑 |
| Helm / kind HA profile | PASS-HISTORICAL | 本地三节点升级、接管、网络策略和回滚已有 PASS；本机当前缺 Helm，未重跑 |
| Evidence（Identity + Undo） | SEALED-HISTORICAL / NEEDS-RESEAL | 历史包独立验签通过；本轮性能改动未重封存 |
| D2 release freeze | PARTIAL / NOT-FROZEN | 用户明确要求暂不冻结；final manifest 和新证据封存未生成 |

## 距离赛题目标的剩余事项

1. **硬缺口**：在可复现、受控环境连续通过正式 3×500，使每轮 incremental p95 和 bootstrap upper 都 ≤50ms。
2. 性能通过后重跑 Reference all fault、正式性能、证据采集与独立验签，并重封存 Identity + Undo evidence。
3. 在具备 Helm 的环境重跑 kind/发布验证；隔离全局 letta-evals/anyio 冲突。
4. 用户允许冻结后再生成 clean commit provenance 与 final release manifest；当前不得提前冻结。
5. D1 PDF / D3 视频继续按负责人要求暂缓；D4 已完成。

## 声明边界

- kind PASS 只证明本机三节点 profile，不外推为生产多地域 HA。
- 本轮 core fault PASS 不替代未重跑的 long/keys 套件。
- 单轮、单 seed 或开发 profile 的性能通过不替代正式连续三轮。
- .runtime/reference/、.runtime/kind-ha/、.runtime/evidence/ 含运行时数据或敏感材料且被 gitignore，不得提交。
- 所有新依赖均为 PostgreSQL/Python 现有合法能力；未加入来源不明依赖。
