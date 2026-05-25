# audit 模块工作日志

---

## 2026-05-25 子 agent G56A
- merkle.py 完整化：ChainStore 启动扫描末行恢复 _last_hash；append 写 hash_prev → 计算 record_hash → canonical JSONL 追加；verify 全量重算 + 链对齐校验，返回 (ok, first_error_line_idx)
- sm_crypto.py 完善：sm2_sign / sm2_verify 默认 HMAC-SHA256 占位（key 文件不存在用 demo 内置 key，保证 demo 可跑）；prefer_gm=True 时尝试 gmssl SM2，失败 fallback HMAC
- 决策：compute_record_hash 剔除 record_hash / signature 字段计算；canonical JSON sort_keys + ensure_ascii=False + separators=(",",":")，保证跨平台一致
- 已知限制：SM2 真签名需 PEM 私钥文件；demo 默认 HMAC-SHA256，对应 implementation-notes Q8 策略（默认 SHA-256，接口预留）
- 测试：test_merkle.py 5 用例覆盖 hash 排除自身字段 / chain append / 恢复 last_hash / 篡改检测 / canonical JSON 格式

---

## 2026-05-24 23:55 主助手
- sm_crypto.py / merkle.py / otel.py 接口骨架
- 决策（implementation-notes Q8）：默认 SHA-256，sm_crypto.sm3_hash(prefer_gm=True) 按需切换；gmssl 不可用自动 fallback
- TODO（agent-G6）：ChainStore 启动恢复 _last_hash；append / verify 完整实现
