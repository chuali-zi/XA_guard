# audit 模块工作日志

## 2026-07-15 SM2 strict signer 稳定性
- strict signer 增加有限自验重试，拒绝 gmssl 偶发不可自验签名；verifier 将第三方点运算异常按无效签名 fail-closed。

---

## 2026-06-17 09:30 Codex 主 agent
- 新增 `tsa.py` 本地文件 TSA anchor 原型：锚定 audit 文件 SHA-256、字节数、记录数、首尾 `record_hash`，并用 `anchors/index.jsonl` 串联多次 anchor。
- 决策：anchor 是不可变 sidecar，不回写已落盘 audit JSONL；明确不是外部可信 TSA。
- 测试：`tests/unit/test_audit_tsa.py` 覆盖创建、验锚、篡改拒绝、旧 anchor 失效和 index 串联。

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
