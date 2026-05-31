# docs 模块工作日志

## 2026-05-28

任务：撰写《关卡1 输入检测模型接入与微调要求》需求规格说明书。

读取了 base.py、types.py、gate1_input.py、dangerous_patterns.yaml、status.md、configs/xa-guard.yaml 及 detectors/__init__.py，完整理解现有接口后撰写文档。

文档路径：`docs/gate1-模型接入与微调要求.md`，共 8 章：目标定位、接入接口规格（含 ModelBackend 四方法精确签名、DetectionLabel 字段规范、最小骨架代码）、类目映射要求（含 Qwen3Guard 推断映射表）、微调数据要求（JSONL schema + 政企特化 + 样本规模建议）、微调方法建议（LoRA/QLoRA + 许可合规）、评测验收标准（量化门槛表）、分阶段交付路线（5 阶段）、风险与回退（fail-open 机制 + 降级路径）。全文约 300 行 Markdown。
