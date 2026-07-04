# SP4 红队工作台设计 — CLI 优先

> 状态：设计草案，待作者审后进实现。依赖 SP1–SP3。
> 上手路径见 `enterprise-agent-range/docs/redteam/operator-guide.md`（复用其工作流）。

## 目标

让红队成员**不读内核源码**也能完成闭环：看靶场地图 → 选注入面 → 投毒 → 跑 guard/null A/B → 读证据 → 提交 finding → 审核后固化为 regression。红队只攻关，不维护 runtime。

## 边界

- CLI 优先，Web UI 后置。
- Finding 是草稿（可失败、可不完整）；正式 case 须过审并满足固化规则。
- 触发真实 agent/模型调用（run-ab）前必须显式授权。

## 模型

CLI 子命令组（沿用 arena 已实现形态，迁到 open-agent-range 内核）：

```
range worlds                      # 看可用 world
range surfaces --world <w>        # 看工具面 + 敞开的注入面
range challenges --suite <s>      # 看 suite 里的 challenge
range init-finding --world <w> --target <scheme:locator> --task-prompt <中性任务> --payload-... 
range run-ab --finding <f> --sut-mode both --repeat N   # guard/null A/B（需授权）
range show <attempt-dir> --json   # 读证据摘要
range promote --finding <f> --out <challenge.json>      # 审核后固化
```

- **Finding schema**（复用 arena `findings.py`）：`finding_id / world / target / payload_ref / task_prompt / expected_risk / notes`。
- **Finding → Challenge** 转换 + promotion（只有过审的才进 `challenges/`）。
- **证据阅读**：transcript / tool-events / audit / world-effects / ledger / verdict（见 evidence-and-accountability）。

## 判据

红队用上面命令跑完整闭环，全程零内核代码改动；finding 固化后可作 regression 复现。

## 验收

```
range worlds / surfaces / challenges / init-finding / show / promote 全部可离线跑通（不触发真实模型）。
run-ab 提供 dry-run/plan 输出，降低误触真实调用风险；真实 A/B 需显式授权。
一条红队 finding 从 init → run-ab(授权) → show → promote 全链路复现。
```

## 后续

- attempt/report → 自动 regression promotion（当前是 Finding→Challenge，未做从 live 结果反向固化）。
- Web 工作台（后置）：可视化地图 + 证据浏览。
