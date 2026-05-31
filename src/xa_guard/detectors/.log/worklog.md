# 工作日志

## 2026-05-28 — 实现通用模型调用壳子

**创建文件：**
1. `backends/__init__.py` — 后端注册表（`register_backend` 装饰器 + `get_backend` 工厂），内置 stub，占位 qwen3guard/shieldlm/promptguard/llamaguard。
2. `backends/stub.py` — `StubBackend`：默认 `ready=False`，保证 ModelDetector fail-open 跳过；`ready=True` 时用 `keyword_labels` 子串匹配辅助单测。
3. `model_detector.py` — `ModelDetector(Detector)`：包一个 `ModelBackend`，实现惰性加载、threshold 过滤、category_map 归一、origin 补填、全异常捕获。

**StubBackend 默认行为：** `is_ready()=False`，`load()` 是 no-op（_loaded=True），`classify()` 永不抛异常。未配置 `ready=True` 时 ModelDetector 在 load 后仍 not ready，直接返回 `available=False`，pipeline 继续。

**占位后端接入方式：** `load()` 抛 `NotImplementedError` 并附接入步骤（安装 transformers/torch、下载对应权重、实现推理逻辑），`is_ready()` 永远 `False`。接入真实模型只需替换实现类，调用方零改动。

**自测：** 4 项均通过（stub is_ready False；keyword 命中；ModelDetector fail-open；占位后端 load 抛 NotImplementedError）。

---

## 2026-05-28 — RuleDetector + Fusion + Spotlighting + Gate1Input v2 编排（主 agent）

**新增文件：**
1. `rule_detector.py` — 旧版规则逻辑封装为 Detector。YAML 加载 patterns，扫描 tool+history 产出 DetectionLabel，保留 origin 和降级元数据。
2. `fusion.py` — 多检测器融合：DENY 优先 / WARN 次之 / ALLOW 兜底；available=False fail-open 忽略；RAG/assistant 来源降级。
3. `spotlighting.py` — 非 user 来源文本加 `<untrusted_source>` 标记，基于 MS Spotlighting 思路。
4. `gate1_input.py` 完全重写 — 从 config options 解析 detectors 列表，按 spec 实例化 RuleDetector/ModelDetector，运行后 fusion 判决。默认自动使用单个 rule 检测器（等价旧版语义）。

**质量：** 13 个旧有 gate1 测试全通过（1 个 risks 断言从 pattern_match:→deny:/warn:）。新增 35 个 detectors 测试（RuleDetector×7/ModelDetector×6/Fusion×8/Spotlighting×3/Gate1InputV2×11），全部通过。全量 150+ 测试 pytest -q 全绿无回归。config yaml gate1 段更新为 detectors 列表格式。

**关键行为：** ModelBackend stub 默认 ready=False → ModelDetector fail-open，不阻塞 pipeline。后续接入 Qwen3Guard 只在 config 改 backend 名，Gate1 零改动。
