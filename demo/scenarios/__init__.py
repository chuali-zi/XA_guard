"""3 大演示场景 — 对应产品架构 §8.1 视频脚本：

scenario_01_indirect_injection.py   read_log → 注入 → rm -rf → 关卡 1+3 拦截
scenario_02_data_exfil.py           read 机密 → send_email → 关卡 4 拦截
scenario_03_hitl_approval.py        red 操作 → 弹窗 / stdout → 审批后执行

每个脚本独立可跑：python -m demo.scenarios.scenario_01_indirect_injection
不需要真 LLM；直接构造 GateContext 跑 pipeline 演示决策。
"""
