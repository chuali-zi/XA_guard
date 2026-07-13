# Agent Identity + Undo 正式接入验证

日期：2026-07-12

结论：正式代码接入完成，配置默认关闭；身份、加密 effect、职责分离、六关补偿和业务 cancel 的受影响范围回归通过。

## 验证结果

- `pytest` 受影响范围：68 passed。
- 全仓：673 collected，672 passed、1 skipped；skip 原因为本机缺少 `xa-guard/sandbox:latest`。
- pytest 默认范围外的 OAR Auto-RedTeam 与 Identity/Undo 实验：33 passed。
- Ruff（新增/修改的正式源码与新增测试）：PASS。
- `git diff --check`：PASS；仅报告工作树既有文件的 CRLF/LF 转换提示，无 whitespace error。
- `python -m compileall -q src/xa_guard demo/targets/business_api_target.py`：PASS。
- `configs/xa-guard.identity-undo.yaml` 解析：identity enabled、resilience enabled、1 个 issuer。

覆盖项：JWT/JWKS 有效验签、坏签名、错误 audience、超长 TTL、请求体身份冲突；原始 token 不进入安全 claims；EffectStore 数据库不含恢复 ID/敏感输入明文；Undo 幂等、自批拒绝、补偿关联；真实业务适配器固定 cancel endpoint；既有业务 downstream、Streamable HTTP、pending ledger、Gate6 与 Governance 回归。

## 全量回归说明

早期三次短外层超时没有形成结果；将上限放宽后完整运行到 100%。首轮全仓发现既有 ChainStore 在 Windows 四进程并发写下第 32 条断链。没有修改测试：实现改为跨进程锁内读取权威末行 hash，不再把 size/mtime 缓存作为正确性判据；Windows tail reader 使用 READ/WRITE/DELETE 共享句柄，避免阻塞审计归档。最终实现完整 Merkle/归档 12 passed，并发压力额外 10/10 轮通过，500 条本机基准约 1151 records/s；修复后全仓 672 passed、1 environment skip。

## 未执行的外部验收

没有真实 IdP/JWKS/KMS、真实政企业务 API 或多节点数据库环境，因此未宣称生产部署验收。生产 profile 使用占位 issuer/audience/JWKS path，部署时必须替换。
