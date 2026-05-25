# demo 模块工作日志

---

## 2026-05-25 agent-D
- 实现 demo/targets/ops_target.py：完整 MCP server，6+1 工具（含 send_email），read_log 埋间接注入 + AWS 密钥两条攻击素材
- 实现 demo/scenarios/scenario_01_indirect_injection.py：构造含 [SYSTEM_INSTRUCTION] 注入历史的 GateContext，跑 pipeline，gate1 在 stub 状态下已能识别 rm -rf 并 DENY
- 实现 demo/scenarios/scenario_02_data_exfil.py：taint=CONFIDENTIAL + send_email 外发，gate1 stub 识别 AKIA 密钥前缀 DENY
- 实现 demo/scenarios/scenario_03_hitl_approval.py：exec_command+uptime → gate2 stub 返回 REQUIRE_APPROVAL，stdout fallback 弹窗已渲染
- 决策：Windows GBK 控制台用 io.TextIOWrapper(utf-8) 包装 Console，避免 rich 中文 UnicodeEncodeError
- 更新 demo/__init__.py 顶部说明 3 场景入口与靶子启动命令

---

## 2026-05-24 23:55 主助手
- targets/ops_target.py 骨架（6 个假工具）
- scenarios/ 3 个场景占位
- 决策：read_log 的某 path 返回值必须含 [SYSTEM_INSTRUCTION] 注入字符串 → 演示场景 1
- TODO（agent-D）：实现 ops_target.py + 3 场景脚本（无 LLM 直接构造 GateContext）
