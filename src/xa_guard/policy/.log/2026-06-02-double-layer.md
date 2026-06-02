# 双层策略层落地（2026-06-02）

落地范围：Gate2 / Gate3 / Gate4 三家共享 `LayeredPolicySource` 单例。

新增模块：
- `layered.py` — baseline + overlay 加载、单调性合并、bundle_sha
- `monotonicity.py` — 4 类红线（rule.id 覆盖、tool_risks 弱化、input_max_taint 放宽、敏感词重复）
- `predicate_safe.py` — overlay 走 AST 白名单（evalidate 优先；缺失时内置 walker）
- `hot_reload.py` — watchfiles 监听 overlay/，失败 fail-safe 保留旧 snapshot

策略文件改造：
- `policies/baseline_manifest.yaml` — 注册 baseline 4 类资源
- `policies/sensitive_patterns.yaml` — 从 Gate4 硬编码正则提取
- `policies/overlay/_template/*` — 企业接入示例

兼容性：
- 现有 yaml 路径全部保留，未做 rule.id 重命名；290 条 bench / 30 条 Gate3 单测零改动
- gate2/3/4 引入 `prefer_layered` 开关；default false → 老测试走单文件路径
- `configs/xa-guard.yaml` 默认 `prefer_layered: true`（生产）

回归验证：
- pytest 204/204 绿（旧 183 + 新 21）
- bench 290/100% pass_rate；7 维度均 100%
- audit chain 7031 records 0 errors；新字段 `gen_ai.policy.bundle_sha` 已落盘
