# 仓库状态：XA-Guard / XA-202620

> 快照日期：**2026-07-21**（America/Los_Angeles）
> 当前统一口径：**ENGINEERING-FROZEN / RELEASE-VERIFIED / SUBMISSION-MANUAL-PENDING**
> 比赛交付口径：[docs/acceptance/DELIVERY-v2.md](docs/acceptance/DELIVERY-v2.md)
> 工作历史见 [log.md](log.md)。

## 总体结论

产品功能已停止扩展并完成本地工程冻结。Gate1–6、OAR 主评测、MCP 代理、OIDC + 动态 assignment、PostgreSQL Effect、独立审批 Undo、Worker 补偿、Console/BFF 与本地 kind HA 主路径均已实现。最终候选的 Reference 全故障 11/11、kind HA 全阶段、正式 10 并发性能和 unified release verifier 均已通过。

D1 技术方案已生成 14 页 PDF 并完成渲染抽检；D2 最终 evidence、统一发布复验、本地冻结提交和 clean release manifest 已完成；D3 逐镜录制指南与字幕模板已完成，最终视频仍需负责人手工录制。剩余事项均为人工录制、远端发布与正式提交，不再是工程实现缺口。

## 当前交付成熟度

| 交付面 | 状态 | 当前事实与边界 |
|---|---|---|
| 核心功能与四方向覆盖 | DONE | 六关、MCP、AIBOM、OAR、Identity + Undo、Console 和审计均有实现与证据 |
| B6/B7 Identity + Undo | DONE | 最终候选 all fault 11/11、kind HA 和正式性能通过；不外推为生产 IAM/多地域 HA |
| D1 技术方案 | DONE | `output/pdf/XA-Guard-XA-202620-technical-report.pdf`，14 页，仓库安全封面 |
| D2 代码与发布 | DONE-LOCAL / RELEASE-VERIFIED | 最终 evidence、统一复验、本地冻结提交与 clean manifest 完成；未 tag、未 push |
| D3 演示视频 | MANUAL-PENDING | 录制指南和 SRT 模板完成；MP4 尚未录制 |
| D4 报名表 | DONE-MANUAL | 负责人已确认审核/盖章完成；隐私材料在仓库外 |
| 文档一致性 | CONVERGED | README、Delivery v2、TODO、架构和交付文档已统一到最终性能口径 |

## 2026-07-21 最终候选验证基线

- Reference clean-volume 全故障 suite：**11/11 PASS**。最终报告：`.runtime/evidence/reference-faults-all-final-rerun-20260721.json`。
- 同一最终候选的 core 恢复复跑：**7/7 PASS**。首次 all 尝试在 PostgreSQL 恢复后的首个 Keycloak 登录出现一次瞬态 400；保留失败报告，随后 core 和完整 all 独立复跑均通过，未修改产品或测试掩盖。
- 本地三节点 kind profile：安装旧版、升级当前版、migration 重跑、API Pod 删除、Effect prepared 接管、Worker lease 接管、NetworkPolicy 正负探针和 Helm rollback **全阶段 PASS**。报告：`.runtime/evidence/kind-ha-final-pass-20260721.json`。
- 完整重建镜像正式性能三轮：incremental p95 **45.109/42.141/43.934ms**；单侧 95% bootstrap upper **46.984/43.120/45.528ms**；均满足 ≤50ms。Undo **10/10**，约 **0.45–0.94s**。
- 隔离发布 Python 环境：项目依赖安装完成，`pip check` PASS。全局 Python 的 `letta-evals`/`anyio` 冲突属于宿主环境，不通过改写项目依赖规避。
- Console 使用 `npm ci` 恢复依赖；audit 为 **0 vulnerabilities**。
- unified verifier：**782 collected / 781 passed / 1 allowed capability skip / 0 failure / 0 error**；隔离 `pip check`、产品 Ruff、L3 static 11/11、Compose config、Console 5/5 + build 和最终 evidence 验签全部 PASS。
- 本轮未修改任何测试代码、既有断言或性能阈值。

## 关键能力边界

| 能力面 | 状态 | 声明边界 |
|---|---|---|
| Gate1–6、Gate6 审计、OAR B1–B5 | DONE | OAR 是自建红队靶场，不冒充官方 benchmark |
| OIDC 与动态 assignment | REFERENCE-PASS | 每请求实时授权；生产仍需组织 IdP、TLS 与密钥治理 |
| PostgreSQL EffectStore | REFERENCE/PERFORMANCE-PASS | intent-first、双链 CAS、批处理与混合单事务均保留 |
| Undo / Worker | REFERENCE-PASS | 至少一次调度 + 下游幂等，不宣称绝对 exactly-once |
| Console/BFF | BUILT / MANUAL-QA-PASS | 三账号职责分离闭环已由负责人手测 |
| Helm / kind | LOCAL-PROFILE-PASS | 只证明本机三节点 profile，不是生产多地域 HA |
| Evidence | SEALED / VERIFIED | 最终候选 14 artifacts、102 Effect、59 Gate6；SM2-with-SM3 key id `87ca0b5c56dc9313` 独立验签通过 |

## 剩余事项

1. 负责人按 D3 指南录制、剪辑并复核不超过 10 分钟的视频。
2. 人工确认 D2 远端仓库链接、D4 隐私附件、网盘权限和邮件内容；需要时再执行 push/tag，本轮未做。
3. 按提交清单核对 D1–D4，并在 2026-09-15 截止前提交。

## 声明边界

- `.runtime/reference/`、`.runtime/kind-ha/`、`.runtime/evidence/` 含运行数据或敏感材料且不进入 Git。
- D1/D3 仓库内容不含学校、个人信息、密码、token 或私钥。
- 本轮没有新增产品运行依赖；PDF 生成使用已有本机构建工具，产品依赖清单未改。
- 产品不再新增功能；只有最终验证暴露真实缺陷时才回到修复流程。
