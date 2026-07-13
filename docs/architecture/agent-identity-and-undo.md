# 智能体身份与 Undo 正式接入

状态：已进入 `src/xa_guard` 正式运行路径，默认关闭；生产配置显式启用后失败关闭。

## 安全边界

身份不是客户端自报的 `user_role`。HTTP 模式只接受 Bearer JWT，经精确 issuer 白名单、JWKS 签名、算法白名单、audience、`exp/iat`、最大 TTL 和 `xa.invoke` scope 校验后，绑定以下链路：

`human sub -> act.sub(agent) -> tenant -> tools -> data_domains -> permissions`

请求中的 `_xa_guard` 仍作为业务上下文载体，但其中 human、agent、tenant、tool、data domain 必须与已验签声明一致。冲突在下游执行前返回 403。stdio 模式使用进程级短期令牌，来自 `identity.stdio_token_env`；必需令牌缺失或验签失败时拒绝启动。

原始 Bearer、JWT `jti` 和恢复材料不会写入 GateContext 或审计。审计只保留 issuer、kid、scope、`jti` 摘要及 `identity_verified`。

## Undo 不是数据库回滚

Undo 是受控补偿事务：只有在 `tool_effects.yaml` 中声明了副作用合同的成功调用才生成 effect。合同显式给出副作用等级、可逆性、从结果提取的恢复字段、补偿工具及参数映射。

恢复字段以 AES-256-GCM 存入 SQLite，AAD 绑定 effect、tenant 和原工具；主库不保存明文。每个状态变化写前向哈希事件。当前状态机为：

`available -> undo_pending -> compensating -> compensated | compensation_failed`

请求人需 `undo.request`，审批人需 `undo.approve`；同一身份不能自批。幂等键防止重复请求，SQLite `BEGIN IMMEDIATE` 保证同一 effect 只被一个审批者取得。补偿调用重新进入治理预检和六关管线；它不是绕过安全检查的管理员后门。

## 生产配置

入口配置见 `configs/xa-guard.identity-undo.yaml`。上线前必须：

1. 将 issuer、audience 和 `jwks_file` 换成组织身份系统的真实值；JWKS 文件只放公钥并由配置管理系统更新。
2. 注入 `XA_GUARD_RECOVERY_KEY`，值为 32 字节随机密钥的 Base64 或十六进制表示。不要写入 YAML、`.env` 或镜像。
3. 为令牌签发 human、`act.sub`、tenant、tools、data domains、permissions，TTL 不超过 300 秒。
4. 在治理注册表中分别授予业务执行者和 Undo 审批者权限；不要给同一个自然人同时授予请求与审批职责。
5. 为每个新增写工具定义并评审副作用合同；未声明的工具不会伪装成可撤销。

生成恢复密钥示例：

```powershell
python -c "import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"
$env:XA_GUARD_RECOVERY_KEY='<secret-manager-injected-value>'
python -m xa_guard.server --config configs/xa-guard.identity-undo.yaml
```

控制工具为 `xa_guard_list_effects`、`xa_guard_request_undo`、`xa_guard_approve_undo`。它们也必须出现在 JWT 的 tools claim 中，且请求仍需携带与 JWT 一致的 `_xa_guard` envelope。

## 已知边界

- 当前是单库 SQLite 事务协调，适合单实例或共享单写节点；多地域主动—主动部署需换成具备条件写的数据库。
- 补偿能否恢复业务语义由下游 API 保证；不可逆动作必须声明为不可逆，不能制作虚假的 Undo。
- 目前实现 AES-GCM 单 key_id 校验，换钥前需设计旧密钥只读解密窗口和数据重包裹流程。
- JWKS URI 由 PyJWT 支持，但生产建议配合出站网络控制、TLS 信任与缓存刷新监控。

依赖合规：PyJWT 使用 MIT License；`cryptography` 使用 Apache-2.0/BSD 双许可证，均与本项目 Apache-2.0 分发兼容。两者进入项目直接依赖/AIBOM 扫描范围。
