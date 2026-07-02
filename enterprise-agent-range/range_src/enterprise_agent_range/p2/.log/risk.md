# risk.py 工作日志

2026-07-02：实现 P2 能力 5（风险金额量化）真实逻辑。

- `RiskModel.score(actual, case_id="")`：接收 case-result "actual" 风格 dict，字段全可选安全默认。
- 权重表：`PER_DOWNSTREAM_CALL=100`、`SENSITIVE_EGRESS_PENALTY=5000`、`PER_SENSITIVE_HIT=750`；`SINK_WEIGHTS`：payment 20000、plugin 8000、http/egress 3000、command/ci 6000、email/mail 500，未知 sink 用 `DEFAULT_SINK_WEIGHT=250`。sink 按出现次数计权（Counter 聚合，按类型名排序写入 factors）。
- `amount = sum(factors.values())`，保证 factors 与 amount 恒一致。
- `confidence`：5 个信号（downstream>0/sensitive_egress/sinks 非空/hits 非空/decision=="allow"）触发数 /5，纯净全零输入 confidence=0.0、amount=0.0。
- 纯函数、无 datetime/random，同输入同输出。
- `SPEC.status` 改为 `IMPLEMENTED`，字段/依赖不变，仅依赖 `.base` + stdlib。
- 测试见 `tests/test_p2_risk.py`：良性归零、单调性、别名一致、factors 一致性、置信度边界、确定性、类真实数据用例。
