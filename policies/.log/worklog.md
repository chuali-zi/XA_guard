# policies 模块工作日志

---

## 2026-06-04 risk_level 单一事实源收敛

**任务**：消除 gate2_tool_risks.yaml 与 gate4_capabilities.yaml 中 risk_level 的重复/漂移风险。

**结论**：两份文件工具集合完全一致（46 工具，0 差异），无需合并。

**处置方案**：保留 gate2_tool_risks.yaml 文件，但在头部加废弃注释，并从 manifest.yaml 中移除 tool_risks 资源条目，使 baseline 加载时不再读该文件。risk_level 唯一事实源收敛至 gate4_capabilities.yaml。

**layered.py 改动**：新增 `_derive_tool_risks_from_caps()` 函数，在 `_compile_layer` 中当 risks_path 为空时从 caps 自动派生 tool_risks；overlay 层独立 tool_risks.yaml 仍可用于单调性检验。

**gate2_tool_risks.yaml 处置**：保留文件（不删除）原因：测试中多处直接引用 risk_file 路径做 legacy 兼容验证；删除会触发 Gate2 legacy 路径文件不存在异常。头部标注废弃，manifest 不再引用。

**法规文档**：新建 docs/risk_classification_basis.md，经 3 轮 web search 搜集 5 个权威来源，核心论断均≥2来源交叉核验。

**测试结果**：94 passed（新增 test_unknown_tool_green_when_configured）。

## 2026-06-04 policies 目录分层重构
按"层级为主轴、关卡为命名"重组 policies/：
- 新建 baseline/ 子目录，9 个 baseline 文件迁入（git mv 保留历史）：
  manifest.yaml / gate1_input_patterns / gate2_tool_risks / gate3_rules
  （原 enterprise-l3，纠正误导命名）/ gate4_capabilities / gate4_sensitive_patterns
  / category_maps/{llamaguard,promptguard,qwen3guard}.yaml
- overlay/ 不动（租户文件名 policy.yaml 等在 layered.py 硬编码）。
- 同步更新全部路径引用：config.py / gate1-4 / rule_detector / layered / server
  / configs/xa-guard.yaml / baseline/manifest.yaml / validate_csab_gov_mini.py
  / 7 个单测。validate 脚本第 29 行 Path 拼接式漏改→被 strict 测试抓出，已补。
- 残留 "enterprise-l3" 仅逻辑标签（policy_default / @protect 默认值），非路径，未动。
全量 pytest 通过（仅 docker 用例 skip）；validator --strict errors=0 warnings=0。
