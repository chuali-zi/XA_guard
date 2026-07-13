# D3 演示视频脚本

> 目标：最终视频不超过 10 分钟。主线固定为“前有身份、途中六关、后有撤销、全程有证据”；OAR A/B 作为量化支撑，不抢双人闭环主镜头。

## 固定八镜头

| 时间 | 镜头 | 屏幕与旁白要点 |
|---|---|---|
| 0:00–0:50 | 1. Alice 登录 | Alice 经 Keycloak PKCE 独立登录；“我的 Agent”只显示 assignment 授权的 `general-office-agent`，展开 human→Agent→工具→数据域链。 |
| 0:50–1:50 | 2. 执行前拒绝 | 展示伪造 Agent 或越权工具请求被 401/403；业务 API 调用计数不变。旁白：身份和 assignment 在六关之前失败关闭。 |
| 1:50–3:10 | 3. 真实副作用 | Alice 委托办公 Agent 创建一张错误工单；展示 Gate1–6 trace、PostgreSQL `prepared -> available` Effect、业务状态 `open` 与 Undo 截止时间。 |
| 3:10–4:00 | 4. 自批失败 | Alice 发起 Undo，再尝试批准；返回职责分离拒绝。Alice 页面不提供角色切换，不通过前端伪装 Dora。 |
| 4:00–5:20 | 5. Dora 独立审批 | 退出 Alice，Dora 独立 Keycloak 登录；“待我审批”看到同租户 pending，查看 Effect 与理由后批准。 |
| 5:20–6:40 | 6. Worker 重新过六关 | 展示内部签名授权摘要、Worker lease/heartbeat、补偿 `business_cancel_ticket` 再次进入 Governance + Gate1–6；工单恢复为 `cancelled`。 |
| 6:40–8:10 | 7. 审计证据 | 控制台时间轨并列原动作 trace、审批身份、补偿 trace、业务前后态、assignment 版本、Gate6/Effect 两条 hash chain。补充 OAR canonical N=3：Null 3/3 泄漏、XA-Guard 3/3 拦截。 |
| 8:10–9:30 | 8. 部署与边界 | 展示 `python scripts/reference_stack.py up`、六服务健康状态、Helm 双副本架构。明确：不可逆动作只人工处置；至少一次 + 下游幂等；外部 IdP/KMS/PostgreSQL 与 kind 故障恢复仍需组织/HA 验收。 |

9:30–10:00 预留片尾、字幕和命令/hash，不新增功能镜头。

## 统一旁白

> 传统 IAM 只回答谁登录，传统审计只回答发生了什么。XA-Guard 同时绑定“谁委托了哪个 Agent”，并为 Agent 的真实副作用提供受控补偿能力——前有身份、途中六关、后有撤销、全程有证据。

可以说：Reference Compose 的 PKCE、token exchange、动态 assignment、PostgreSQL Effect、独立审批和工单补偿协议链已实际跑通。

不能说：已达到 `REFERENCE-READY` 或 `HA-READY`，除非对应验收项和 evidence manifest 已封存；不能说绝对 exactly-once、通用 Undo、第三方生产 KMS/IdP 已落地。

## 录制前清单

- [ ] 用全新 `.runtime/reference` 启动，三个账号密码只在离屏位置读取。
- [ ] 交互式浏览器完成 Alice、Dora、Admin 三账号人工验收并录制；禁止角色切换模拟。
- [ ] 身份负测证明下游执行数为 0。
- [ ] 准备一条干净 Effect，记录业务 `open -> cancelled`、原/补偿 trace 和事件链。
- [ ] 屏幕不出现 token、client secret、KEK、数据库 DSN、个人信息。
- [ ] 展示的数字、状态与 `status.md`、Delivery v2、evidence manifest 一致。
- [ ] 最终视频小于 10 分钟，生成 SHA-256 并记录使用命令。
