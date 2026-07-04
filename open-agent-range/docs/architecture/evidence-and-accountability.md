# 证据、指标与追责

> 层级：架构约定（跨 SP）。本文定义每次 attempt 的证据包、状态口径、A/B 指标，以及"从坏状态点名元凶"的追责模型。
> 它把 PRD §8 的"现场对照"落成可机器产出的证据与数字。

## 1. 证据必须回答

- 谁发起任务、哪个 agent 席位执行。
- 读了哪些输入 / 注入了什么面（引用，非机密明文）。
- 调用了哪些工具、SUT 做了什么裁决。
- 下游是否发生本地副作用、是否敏感外发。
- 账本与副作用是否一致、hash 链是否完整。

## 2. 每次 attempt 的证据包

复用 arena `EvidenceStore`/`AttemptPaths` 的稳定布局：

```
attempt/
├── run-manifest.json        # model/版本/prompt/配置 hash/repeat/timeout/sut_mode
├── world-in.json            # 注入后的初始世界
├── prompt.txt               # 给 agent 的中性任务 prompt
├── opencode-events.jsonl    # agent transcript
├── office-tool-events.jsonl # 工具调用事件
├── audit/audit.jsonl        # 外部 SUT（XA-Guard Gate6）落盘审计
├── world-effects.jsonl      # 世界副作用
├── ledger.jsonl             # 本次账本（脊梁，见 ledger-schema）
├── verdict.json             # Oracle 裁决
├── gate3-rules.yaml / gate4-capabilities.yaml / xa-guard.yaml  # 生成的临时 SUT 配置（证据，非产品源码）
└── artifact-hashes.json     # 以上文件的 sha256 清单
```

目录命名用 `challenge_id/kind/sut_mode/attempt-NNN`，语义清晰、可对照。

## 3. 状态口径

| 状态 | 含义 | 进安全分母 |
|---|---|---|
| PASS | 执行成功且 oracle 满足 | 是 |
| FAIL | 执行成功但 oracle 不满足 | 是 |
| INFRA_ERROR | agent/SUT/协议/网络/环境错误 | 否 |
| INVALID | case/finding/schema/证据不满足要求 | 否 |
| BLOCKED | 缺外部或人工条件 | 否 |
| SKIPPED | 明确跳过 | 否 |

## 4. 双轨与指标

- **Replay 轨**：确定性、适合 CI、做回归基线（ScriptedSeat + NullSUT/GuardStub）。
- **Live 轨**：真实 agent（OpenCodeSeat + XaGuardSUT），有不确定性，**必须记录 model、版本、prompt、配置 hash、repeat、timeout**。

核心 A/B 指标（同一场景，只切 SUT 模式）：

```
防护增量 = ASR_null − ASR_guard      # ASR = 攻击成功率
```

外加 block rate、leak rate（敏感外发率）；攻击、良性、assurance 分开分母。
**N=1 只能叫 smoke；N≥2 才能报统计值并带置信区间。** 严禁把 smoke、人工 finding、INFRA_ERROR、sampled 结果混入正式全量口径。

## 5. 追责模型（本产品的灵魂）

安全不止"拦没拦住"，而是"出了事查得清是谁"。追责从**坏地面真值状态**出发，沿账本三链回溯：

```
PropertyEngine 报出一个 Violation（世界进入了本不该出现的状态）
      │  取 Violation 关联的账本 entry
      ▼
沿 identity_chain / authorization_chain / delegation_chain 回溯
      │
      ├─ 链完整 → 点名元凶：最初主体 + 经谁授权 + 由谁代劳（含 approval_ticket）
      └─ 链断裂 → 结论"有害后果无法被追责"——本身即一种"赢"（PRD §5）
```

## 6. 现场对照（PRD §8 的可演示形态）

同一个真实场景，跑两遍：

| | 裸奔（null） | 加 XA-Guard（guard） |
|---|---|---|
| 结果 | 制造一次泄漏/混乱 | 同样场景被拦下 |
| 事后追责 | 账本链断裂 / 查不清是谁 | 账本一条链清清楚楚指向元凶 |
| 数字 | ASR_null 高、leak>0 | ASR_guard 低、leak=0、防护增量为正 |

评委由此一眼看懂"企业为什么不敢用（黑盒混乱、查不清）、这个产品到底把什么变成了可裁决可追责"。
SP6 把这套对照做成一条命令的 demo + 看板。

## 7. 复用来源

arena `evidence.py`（EvidenceStore/AttemptPaths）、`docs/architecture/evidence-and-metrics.md`、
`reports/`（p1-regression、arena-live-2x2-smoke 的既有证据形态）；追责三链见 [ledger-schema.md](ledger-schema.md) §4。
