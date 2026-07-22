# D3 演示视频手工录制指南

> 目标：手工录制不超过 10 分钟的 16:9 视频。主线固定为“前有身份、途中六关、后有撤销、全程有证据”。
> 当前只交付录制手册和字幕模板；最终 MP4、真人旁白和视频 SHA-256 由负责人完成。

## 1. 成片标准

- 建议 9:10–9:30，至少留 30 秒余量；1440×810 或 1920×1080、30 fps、H.264 + AAC。
- 使用真实 Alice、Dora Keycloak 会话，不使用角色切换或伪造身份。
- 密码、token、client secret、KEK、DSN、私钥和个人信息不得进入画面。
- 只声明 Reference Compose、正式测试和本地 kind profile 已证明的能力。

按八个镜头分别录制，每段前后多留 2 秒静帧。准备浏览器、演示终端和离屏旁白稿；关闭通知、书签栏和密码管理器弹窗。浏览器缩放建议 90%，终端字体不小于 18 px。

## 2. 环境准备

### 2.1 固定工程状态

    git branch --show-current
    git rev-parse HEAD
    git status --short

只录 branch、commit 和干净状态，不展示远端 URL、用户名或凭据。

### 2.2 创建干净录制环境

以下 reset 会删除本机 XA-Guard Reference PostgreSQL 和审计卷，不删除 Git 文件或已提交证据：

    python scripts\verify_reference_faults.py --suite core --prepare --reset ^
      --output .runtime\evidence\d3-preflight-core.json

若收口验收已完成且不想在录制当天重跑 core：

    python scripts\reference_stack.py --no-build up

入口为 Console http://localhost:13080 和 Keycloak http://localhost:13081。凭据在 gitignored 的 .runtime/reference/credentials.json，只能离屏查看。

### 2.3 健康和闭环检查

    docker compose -f docker-compose.reference.yml ps
    python scripts\verify_reference_e2e.py

成功标准：PostgreSQL、Keycloak、business-api、xa-guard、worker、Console 均健康；PKCE、token exchange、真实写入和 Undo 闭环通过。

### 2.4 准备负测和量化结果

录制前运行，不在视频里等待：

    python scripts\verify_reference_faults.py --suite core ^
      --output .runtime\evidence\d3-core.json

视频只展示脱敏摘要：status=passed、identity_rejections_before_execution=passed、business_create_attempt_delta=0、effect_delta=0。

OAR 固定数字：Null 3/3 泄漏；XA-Guard 3/3 拦截；infra error 0；protection_delta 1.0；full-day 为 41 tool attempts、43 ledger records、0 violations；replay 7/7 PASS。

## 3. 八镜头操作

### 镜头 1：Alice 身份与委托链（0:00–0:50）

打开 Console，以 Alice 登录；在“我的 Agent”展开 human → Agent → tool → data domain；停留在 assignment version、business_submit_ticket、engineering_docs。

> XA-Guard 不接受浏览器自报 Agent 身份。Alice 通过 Keycloak PKCE 登录，BFF 再执行标准 token exchange。页面展示数据库中的实时 assignment：谁委托哪个 Agent、Agent 能用什么工具和数据域。

画面必须显示 alice、general-office-agent、1 工具、1 数据域、ACTIVE。

### 镜头 2：执行前失败关闭（0:50–1:35）

切到终端，显示 d3-core.json 的摘要；高亮 401/403、business_create_attempt_delta=0、effect_delta=0。

> 伪造签名、错误 audience、伪造主体和越权 assignment 都在业务执行前被拒绝。不只检查 HTTP 状态，还检查下游创建次数和 Effect 增量都为零。

### 镜头 3：真实副作用与 intent-first（1:35–2:55）

1. 点击“委托发起工单”。
2. 标题填写“演示：撤销错误工单”。
3. 正文填写“该工单用于 XA-Guard 比赛演示，可在补偿窗口内撤销。”
4. 点击“确认委托并执行”。
5. 展示 Effect ID、trace、AVAILABLE，再进入“操作影响”。

> XA-Guard 先在 PostgreSQL 登记 prepared intent，再以 effect_id 作为下游幂等键触达业务 API，成功后进入 available。控制数据库不可用时，下游执行数仍为零。

### 镜头 4：申请撤销与职责分离（2:55–3:50）

输入“演示错误工单，需要恢复业务状态”，点击“发起 Undo”，打开“待我审批”，停留在 NO APPROVER ROLE。

> Alice 可以发起撤销，但不能批准自己的请求。职责分离由 IdP 身份和后端授权共同执行，前端没有角色切换按钮。

### 镜头 5：Dora 独立审批（3:50–5:00）

退出 Alice，以 Dora 独立登录；打开“待我审批”，展示申请人、目标动作、Effect 和剩余窗口；点击批准。

> Dora 通过独立 Keycloak 会话进入审批面。系统校验她与申请人不是同一 subject，并把决定持久化为可追溯事件。

### 镜头 6：Worker 补偿再次过六关（5:00–6:15）

打开“操作影响”，刷新 Effect；展示 COMPENSATED、不同的原动作 trace 和补偿 trace，以及 retry=0、无 last error。未即时更新时等 2 秒再刷新。

> 独立 Worker 持有 lease 和 heartbeat，读取加密恢复合同，以内部签名授权重新调用 business_cancel_ticket。补偿再次经过 Governance 与 Gate1 到 Gate6。语义是至少一次调度加下游幂等，不是绝对 exactly-once。

### 镜头 7：双链证据与 OAR（6:15–7:50）

打开“审计证据”，展示人员、Agent、两个 trace、业务引用、最终状态和 timeline；切到 OAR 摘要，展示 3/3 对 3/3、protection_delta=1.0、replay 7/7。

> 原动作、审批和补偿进入 Gate6 与 Effect 两条哈希链，并用 trace、Effect 和业务引用交叉关联。OAR live A/B 中，Null 三次泄漏，XA-Guard 三次阻断，七次 replay 均通过哈希、ledger 和原始审计对齐。

若页面显示 CHAIN GAP，放弃旧数据；按 reset 流程用第一条干净 Effect 重录。

### 镜头 8：部署、边界和收束（7:50–9:20）

展示 docker compose ps 六服务健康状态；展示最终 kind 证据 JSON 的七个 PASS phase；片尾显示项目名、题号 XA-202620、commit 和交付入口。

> 当前候选通过 Reference all-fault 11 个场景，以及本地三节点 kind 的安装、升级、迁移重跑、API 与 Worker 接管、网络策略和 Helm 回滚。它证明可复现原型和本地 HA profile；外部 IdP、托管 PostgreSQL、KMS/HSM、TLS、备份与容量仍需生产验收。

片尾：XA-Guard 把“谁委托哪个 Agent”与“副作用如何恢复”接到同一条安全执行和证据链上：前有身份，途中六关，后有撤销，全程有证据。

## 4. 失败恢复

| 问题 | 处理 |
|---|---|
| Keycloak 登录报错 | 等 10 秒，确认 PostgreSQL/Keycloak healthy，重开无痕窗口 |
| Alice 看不到 Agent | 重新 bootstrap/up，确认 assignment-seed 成功退出 |
| 提交失败 | 不反复点击；检查 xa-guard、business-api、PostgreSQL health |
| Dora 队列为空 | 确认 Alice 已申请 Undo、两人同租户，点击刷新 |
| 补偿持续 pending | 等待 Worker lease；检查 worker healthy；不手改数据库 |
| 证据页 CHAIN GAP | reset 后用第一条干净 Effect 重录 |
| 画面出现凭据 | 整段作废重录，不以打码作为首选 |

## 5. 合成和验收

将片段命名 01.mp4 至 08.mp4，并创建 concat.txt。合并和烧录字幕：

    ffmpeg -f concat -safe 0 -i concat.txt ^
      -vf scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,subtitles=docs/delivery/D3-video-subtitles.srt ^
      -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p ^
      -c:a aac -b:a 160k -movflags +faststart XA-Guard-XA-202620-demo.mp4

    ffprobe -v error -show_entries format=duration:stream=codec_name,width,height ^
      -of default=noprint_wrappers=1 XA-Guard-XA-202620-demo.mp4
    Get-FileHash -Algorithm SHA256 XA-Guard-XA-202620-demo.mp4

- [ ] 小于 10 分钟；Alice、Dora 是两个真实会话。
- [ ] open → cancelled、AVAILABLE → COMPENSATED 清晰可见。
- [ ] 负测证明下游执行增量为零；两个 trace 均已关联。
- [ ] OAR 数字与 D1、Delivery v2 一致。
- [ ] 无密码、token、secret、私钥、DSN、个人信息。
- [ ] 保存 MP4、SHA-256、字幕和离线备份。
