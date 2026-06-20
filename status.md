# 仓库状态：XA-Guard / XA-202620

> 快照日期：2026-06-20（Asia/Shanghai）
> 本文件仅描述当前仓库状态、验收边界与剩余差距，不记录工作历史。
> 2026-06-20 已运行 verifier 单测（5 passed）、统一静态校验（11 sections PASS）及三组轻量 pytest（29 + 63 + 28 passed）。未运行全仓测试，也未执行真实 LLM、Docker、gVisor、OPA 或 Trae 验收。

## 总体结论

仓库已达到 **L3 static-only implementation 可验**：`scripts/verify_l3_static.py` 覆盖 11 个 section（corpus、faithfulness、langchain、gvisor、opa、trae、aibom、deployment、crypto、benchmarks、docs）。静态校验只能证明资产存在、关键配置可解析及实现入口具备，不能替代真实环境、独立评测或最终交付验收。

当前不能宣称“L3 最终验收通过”或“赛题最终达标”。主要差距已从静态实现转为正式独立复核、真实产品/运行时验证、完整外部评测和最终证据包。

## 当前实现快照

| 验收面 | 当前状态 | 边界 |
|---|---|---|
| L3 static-only | 11 个 section 已实现，统一静态校验已 11 sections PASS；verifier 单测 5 passed，三组轻量 pytest 分别 29、63、28 passed | 未跑全仓；静态 PASS 不等于运行时或最终验收 PASS |
| 双 500 语料 | implementation profile 已有 500 refusal + 500 non-refusal，共 1000 条，1000 个归一化 payload 唯一 | formal 所需 hash-bound 独立 attestation、逐条 taxonomy 与 semantic group 独立复核未完成，不能作为正式双 500 成绩 |
| Decision faithfulness | `xa-guard-decision-faithfulness/v1` 已实现基于最终决策、逐 Gate 决策/规则命中、原因和下游动作一致性的评分，已非固定 `1.0` | 真实 agent trace 的独立重算与一致性验收未完成 |
| LangChain / LangGraph | wrapper、callback/observer、HITL resume、node/tool 等适配已实现 | 固定真实版本及真实 agent/transport 端到端验收未完成 |
| Trae | 配置模板、接入文档和 allow/deny/taint/pending 四案例静态资产已实现 | 真实 Trae 的工具发现、调用、HITL、日志、截图/录像未验收 |
| gVisor | `runsc`、禁网、只读根、非 root、capability 与资源限制等静态部署资产已实现 | 真实 Linux/runsc 隔离、故障恢复和性能未验收 |
| OPA | Rego/bundle、strict profile、exporter 与 fail-closed 配置资产已实现 | 真实 OPA 固定镜像、Python/OPA 100% parity、异常与漂移负测未验收 |
| AIBOM | 内部扫描、评级、签名、漂移及离线 preflight 准入已实现；CycloneDX 1.6 外部产物导入/校验静态资产已实现 | 合法外部生成器真实产物和 marketplace/IDE 安装链未验收 |
| 审计与国密 | SM3 链、SM2-with-SM3、local TSA 路径、签验与篡改检测入口已实现 | local TSA 不等于第三方 TSA，软件密钥不等于 HSM；TSA/HSM 生产验收未完成 |
| 外部 benchmark / holdout | runner、协议和局部 smoke/证据入口已存在 | AgentDojo/InjecAgent 完整正式矩阵、独立 holdout、固定模型/scorer 和独立结论未验收 |

## 历史性能证据

以下均为仓库内 **2026-06-18 历史证据**，不是本轮实测，也不能外推为真实 Trae、gVisor、OPA、远程模型或生产环境性能：

- 进程内六 Gate：500 请求、并发 10，P50 `20.305 ms`、P95 `168.273 ms`、`53.486 QPS`、峰值 RSS `62.996 MB`，证据记录为目标通过。
- 单进程 Streamable HTTP：10 sessions、500 请求，调用 P50 `98.03 ms`、P95 `153.117 ms`、`92.981 QPS`、峰值 RSS `103.836 MB`，证据记录为通过；仅 allow workload、单 worker、无 TLS/外部代理。
- 20-session 结果未形成满足 P95 门槛的可接受正式证据，仍需重测与验收。

## 未完成的正式验收

1. 双 500 formal 独立复核，以及独立 Gate1 holdout 数据、阈值锁定和 Recall/FPR 正式结论。
2. 真实 Trae 四案例与完整可复核证据。
3. 真实 Linux/gVisor 隔离、故障和性能验证。
4. 真实 OPA 的 100% parity、fail-closed、镜像 provenance/license 和漂移验证。
5. AgentDojo/InjecAgent 等外部 benchmark 的完整正式矩阵、baseline/defended 对比及官方 scorer 证据。
6. 合法外部 AIBOM 生成器、真实 CycloneDX 1.6 产物和真实安装链验证。
7. 第三方 TSA、正式 HSM/合法 SDK、密钥托管、故障负测及 faithfulness 独立重放。
8. 最终 PDF、视频、表单、截图、原始证据、artifact hash manifest 与外部存证/签名的收束和验收。

## 距离赛题目标

核心安全链路、L3 静态资产和验证入口已基本具备；但正式独立语料、真实 Trae/gVisor/OPA、外部 benchmark、独立 holdout、TSA/HSM 和最终交付物均未验收。在这些项目形成可复核证据并满足 `docs/L3-test-and-acceptance.md` 前，仓库状态保持：**L3 static-only implementation 可验，L3 最终验收未完成**。
