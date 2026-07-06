# docs 模块工作日志

## 2026-07-05 R8 外部 AIBOM 生成器准备

任务：为后续 R8 验收准备合法外部 AIBOM/CycloneDX 生成器候选、样本目录和命令，不宣称通过。

新增 `docs/acceptance/r8-aibom-external/`：选择 `@cyclonedx/cdxgen` 作为优先候选，补候选来源/许可证/风险、最小 Python AI 插件样本、生成/哈希/XA-Guard 导入校验命令和证据清单。

同步更新 `docs/acceptance/L3-aibom-external-generator.md` 与 `docs/README.md` 指向新入口。本轮未实跑外部工具、未生成真实 BOM、未改变 R8 BLOCKED 状态。

## 2026-07-05 R4 证据收束

为 L3 R4 复跑新增 `docs/evidence/l3-r4-20260705-current/README.md` 与 `artifact-hashes.json`，同步 `status.md` 和根 `log.md`。结果：进程内 500 与 HTTP 10x500 PASS；HTTP 20x500 为容量 LIMIT。

## 2026-06-30 19:28 PDT

任务：基于赛题 PDF、现有 docs、`status.md` 和根 README，整理当前状态和下一步 TODO。

读取并核对了赛题 PDF、`docs/README.md`、`docs/planning/PRD.md`、`docs/source-of-truth/事实源.md`、`docs/acceptance/L3-test-and-acceptance.md`、`docs/acceptance/R2-R3矩阵自动验收使用说明.md`、`docs/acceptance/R2-R3完整矩阵预算分析.md`、`docs/planning/产品架构.md`、`docs/planning/项目总览.md`、Trae/AIBOM/force-ai 相关文档和根目录状态文件。

新增文档：`docs/workplan/TODO.md`。内容包括官方 D1-D4 交付物复核、当前状态分层、P0/P1/P2 待办、四个赛题方向的证据收束、L3 真实验收补证、docs 整理计划、执行顺序、不做清单和最小完成定义。

同步更新：`docs/README.md`，把 TODO、status、PRD、L3 验收和 R2/R3 使用说明列为当前核心入口；同时更新根 `status.md` 和 `log.md`。本轮没有移动既有 docs 文件，没有运行测试或模型调用，没有改变代码能力。

## 2026-05-28

任务：撰写《关卡1 输入检测模型接入与微调要求》需求规格说明书。

读取了 base.py、types.py、gate1_input.py、dangerous_patterns.yaml、status.md、configs/xa-guard.yaml 及 detectors/__init__.py，完整理解现有接口后撰写文档。

文档路径：`docs/gates/gate1-模型接入与微调要求.md`，共 8 章：目标定位、接入接口规格（含 ModelBackend 四方法精确签名、DetectionLabel 字段规范、最小骨架代码）、类目映射要求（含 Qwen3Guard 推断映射表）、微调数据要求（JSONL schema + 政企特化 + 样本规模建议）、微调方法建议（LoRA/QLoRA + 许可合规）、评测验收标准（量化门槛表）、分阶段交付路线（5 阶段）、风险与回退（fail-open 机制 + 降级路径）。全文约 300 行 Markdown。
