"""演示前端：审计回放时间线（演示视频素材）。

子 agent 实施职责：
- 单页 HTML（不要复杂 React 构建链）
- 读 logs/audit/audit.jsonl，渲染时间线
- 每条 trace 一行：tool / decision / latency / rule_hits / 签名状态
- 支持点开展开 14 字段 + 哈希链验证状态
- 可选：WebSocket 推送实时事件（demo 用文件轮询足够）

入口：frontend/index.html（双击即可在浏览器看）
"""
