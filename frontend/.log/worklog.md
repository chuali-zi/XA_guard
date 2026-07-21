# frontend 模块工作日志

---

## 2026-07-19 Claude(Opus4.8) 修复 timeline.js 决策字段名缺陷
- 缺陷：inferDecision 只读 `rec.decision`/`gen_ai.decision`，未读服务端真实字段 `gen_ai.decision.final`，导致真实审计文件的 deny/require_approval 被静默错显为「允许」、拒绝计数=0（示例数据用旧字段名故未暴露）。
- 修复：inferDecision 增加 `gen_ai.decision.final` 读取，向后兼容旧 `decision`/`gen_ai.decision`。
- 验证：MCP 真实验收产出的 11 条审计（logs/mcp-acceptance）经浏览器实测正确渲染 5 deny + 待审批 + 允许、哈希链完整。证据见 docs/evidence/mcp-live-acceptance-2026-07-19/。

## 2026-05-25 agent-F 完成演示前端初版
- 创建 index.html：banner + 左侧文件选择 + 统计条 + 时间线主区，纯 HTML5，无构建链
- 创建 timeline.js：fetch ReadableStream 逐行解析 JSONL；File API 拖拽/选择；verifyChain() 比对 hash_prev
- 创建 style.css：白底蓝灰政企风，decision badge 四色（绿/黄/红/橙），卡片折叠展开，移动端适配
- 创建 sample_audit.jsonl：5 条样例（含 1 条 DENY、1 条 REQUIRE_APPROVAL、1 条故意断链记录）
- 双击 index.html 即可在浏览器看到示例时间线；注：本地 file:// 协议下 fetch 受限，需点"加载示例数据"触发 loadFromURL 或拖拽文件

---

## 2026-05-24 23:55 主助手
- 单页 HTML 设计，不要 React 构建链
- 数据源：logs/audit/audit.jsonl
- TODO（agent-F）：时间线 + 14 字段展开 + 哈希链状态徽章
