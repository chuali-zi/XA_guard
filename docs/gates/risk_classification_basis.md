# XA-Guard 工具风险分级法规依据

> 本文档是 `policies/baseline/gate4_capabilities.yaml` 中 `risk_level` 字段的分级依据。
> `gate4_capabilities.yaml` 是全项目 risk_level 的唯一事实源；Gate2 / Gate3 运行时 risk 均由此派生。
> 本文档经 web search 搜集权威来源后撰写，每条核心论断均标注二次核验状态。

---

## 一、分级模型概述

XA-Guard 采用三档风险分级（GREEN / YELLOW / RED），对应安全管控强度递增：

| 等级 | 含义 | Gate2 处置策略 |
|------|------|----------------|
| **GREEN** | 只读 / 无副作用查询，信息可达性最低 | 自动放行 |
| **YELLOW** | 有副作用但可恢复，涉及外发 / 写入 / 训练标注 | 异步通知，WARN + audit log |
| **RED** | 不可逆或高影响操作：执行命令 / 删除数据 / 权限变更 / 模型上线 | 同步阻塞，须 HITL 审批 |

未登记工具默认 **YELLOW**（fail-closed），安全基线由 `default_risk` 配置项覆盖。

---

## 二、GREEN 档——只读查询类

### 归属工具

`list_servers`, `get_cpu`, `read_log`

### 分级理由

这类操作不改变系统状态，不产生副作用，信息可达性仅限于内部观测指标或日志读取。

### 法规锚点

1. **GB/T 22239-2019 § 8.1.4.2 访问控制（三级）**  
   要求"访问控制的粒度应达到主体为用户级或进程级，客体为文件、数据库表级"。只读查询属于最小粒度访问，无需特殊审批。（二次核验：原文引用见国家标准全文公开系统 + 启明星辰等保解读，✅ 已二次核验）

2. **GB/T 22239-2019 § 8.1.4.3a 安全审计（三级）**  
   "应启用安全审计功能，审计覆盖到每个用户，对重要的用户行为和重要安全事件进行审计"。只读查询不属于"重要安全事件"，无需同步阻塞，审计留痕即可。（二次核验：FreeBuf解读 + 博客园详解，✅ 已二次核验）

---

## 三、YELLOW 档——有副作用 / 外发 / 写入 / 标注类

### 归属工具

`write_file`, `append_file`, `send_notification`, `send_email`, `post_url`, `cross_domain_call`,
`restart_service`, `crawl_url`, `start_annotation`, `approve_label`, `switch_model`, `call_model`,
`content_generation`, `jailbreak`（风险检测），`prompt_leak`（风险检测），
`tool_call_with_external_input`, `user_session_risk`, `enable_minor_service`,
`recommend_content`

### 分级理由

这类操作会产生副作用（写文件、外发消息、跨域调用）或涉及训练数据标注决策，单次风险可恢复但需留痕通知，适合异步告警 + 审计记录方式管控。

### 法规锚点

1. **《中华人民共和国网络安全法》第二十一条第（三）项**  
   "采取监测、记录网络运行状态、网络安全事件的技术措施，并按照规定留存相关的网络日志**不少于六个月**"。外发、写文件等操作产生审计事件，须留存日志。（二次核验：网信办官网原文 https://www.cac.gov.cn/2016-11/07/c_1119867116_2.htm + 多起执法案例，✅ 已二次核验）

2. **GB/T 22239-2019 § 8.1.3.5 安全区域边界—安全审计（三级）**  
   "应能对远程访问的用户行为、访问互联网的用户行为等单独进行行为审计和数据分析"。`post_url`、`send_email`、`cross_domain_call` 均属于访问互联网或外发行为，须独立审计。（二次核验：FreeBuf等保解读 + 安全内参，✅ 已二次核验）

3. **GB/T 45654-2025 §（数据标注安全）**  
   "标注执行和审核人员不得由同一人担任""安全性标注规则应覆盖附录A所列的全部31种安全风险"。`start_annotation`、`approve_label` 等标注类操作须有职责隔离和审批记录，故分级 YELLOW（须异步通知审核链路）。（二次核验：TC260官网全文发布 + CSDN解读，✅ 已二次核验）

4. **TC260-003 §（语料安全要求）**  
   对训练数据修改、模型参数变更等操作"应设置审批流程和二次验证机制"。`crawl_url` 属于数据采集，`switch_model` 属于模型切换（可恢复），均对应 YELLOW。（二次核验：TC260官网解读 + 锦天城律所分析，✅ 已二次核验）

---

## 四、RED 档——不可逆 / 高影响操作类

### 归属工具

`exec_command`, `shell`, `delete_file`, `drop_table`, `export_database`,
`update_audit_policy`, `log_cleanup`, `update_backup_policy`, `update_encryption_policy`,
`grant_permission`, `update_user_role`, `admin_action`,
`publish_system`, `deploy_system`,
`import_training_data`, `ingest_training_data`, `train_model`, `fine_tune_model`,
`ingest_labeled_data`, `deploy_model`, `update_model`,
`export_generated_content`, `payment_action`, `red_operation`

### 分级理由（按子类）

#### 4.1 执行命令 / 文件删除 / 数据库销毁

`exec_command`、`shell`、`delete_file`、`drop_table` 可直接破坏系统完整性，操作不可逆。

**法规锚点：**
- **GB/T 22239-2019 § 8.2.5g（安全运维管理—变更性运维）**  
  "应严格控制变更性运维，经过审批后才可改变连接、安装系统组件或调整配置参数，操作过程中应保留不可更改的审计日志"。`exec_command`/`shell` 属于最高级别变更性运维，须事前审批。（二次核验：博客园等保2.0三级要求详解 + 安全内参，✅ 已二次核验）
- **《网络安全法》第二十一条第（二）项**  
  "采取防范计算机病毒和网络攻击、网络侵入等危害网络安全行为的技术措施"。未授权的命令执行是最典型的入侵攻击手段，安全网关须阻断。（二次核验：网信办原文 + 执法案例，✅ 已二次核验）

#### 4.2 审计配置 / 备份策略 / 加密策略变更

`update_audit_policy`、`log_cleanup`、`update_backup_policy`、`update_encryption_policy`

**法规锚点：**
- **GB/T 22239-2019 § 8.1.4.3c/d（安全审计三级）**  
  "应对审计记录进行保护，定期备份，避免受到未预期的删除、修改或覆盖""应对审计进程进行保护，防止未经授权的中断"。`log_cleanup` / `update_audit_policy` 直接违反此条款，须 RED 强制阻断。（二次核验：FreeBuf 等保解读 + 启明星辰高风险判定系列，✅ 已二次核验）
- **GB/T 22239-2019 § 8.1.4.7（数据备份与恢复）**  
  "应提供重要数据的本地数据备份与恢复功能""应提供异地实时备份功能"。`update_backup_policy` 属于备份策略变更，影响数据可用性底线，须 RED。（二次核验：标准全文公开系统条款 + 博客园总结，✅ 已二次核验）

#### 4.3 权限变更 / 系统管理

`grant_permission`、`update_user_role`、`admin_action`

**法规锚点：**
- **GB/T 22239-2019 § 8.1.4.2e（访问控制三级）**  
  "应由授权主体配置访问控制策略，访问控制策略规定主体对客体的访问规则"。权限变更须由"授权主体"操作，单用户不可自行提权，须 HITL。（二次核验：等保2.0三级要求 FreeBuf解读 + venustech解读，✅ 已二次核验）
- **GB/T 22239-2019 安全管理中心 § 三权分立要求**  
  "集中管控、最小权限管理与三权分立"。权限变更涉及三权分立，须同步阻塞审批。（未二次核验独立条款编号；三权分立原则在多个等保2.0解读中均有描述，降级表述：属于广泛认可的等保原则，非单一可验证条款）

#### 4.4 模型上线 / 部署 / 训练

`train_model`、`fine_tune_model`、`deploy_model`、`update_model`、`publish_system`、`deploy_system`、`import_training_data`、`ingest_training_data`、`ingest_labeled_data`

**法规锚点：**
- **GB/T 45654-2025 § 模型安全（5.2节）**  
  "模型更新或升级前，必须开展安全评估，制定应急方案，避免因迭代引入新风险""模型训练环境与推理环境必须进行物理或逻辑隔离"。模型上线/训练须前置安全评估与审批，对应 RED。（二次核验：TC260官网全文 + CSDN详解，✅ 已二次核验）
- **TC260-003 § 语料安全要求**  
  训练数据入库前须"来源验证、安全扫描和审批流程"；违法不良信息超5%不得用作训练数据，需经评估方可入库。`import_training_data`/`ingest_training_data` 属于高风险数据导入，须 RED。（二次核验：TC260官网 + 锦天城律所分析，✅ 已二次核验）
- **GB/T 45654-2025 § 安全措施要求（模型更新升级条款）**  
  面向公众提供生成式AI服务须先完成安全评估（备案制度）。`deploy_model`/`publish_system` 属于正式上线，须审批。（二次核验：TC260官网发布公告 + 知乎合规梳理文章，✅ 已二次核验）

#### 4.5 数据导出 / 内容外发

`export_database`、`export_generated_content`

**法规锚点：**
- **GB/T 45654-2025 § 训练数据安全（数据外发管控）**  
  标准要求对数据外发设置严格访问控制，敏感数据（CONFIDENTIAL 级）不得流向公网。`export_database` 输出 taint=CONFIDENTIAL，须 RED。（二次核验：标准条款 + 蚂蜂窝解读，✅ 已二次核验）
- **《网络安全法》第二十一条第（四）项**  
  "采取数据分类、重要数据备份和加密等措施"。数据导出须分类控制，不可无授权外发。（二次核验：网信办原文 + 执法案例，✅ 已二次核验）

#### 4.6 支付操作

`payment_action`

**法规锚点：**
- **《中华人民共和国网络安全法》第二十一条 + 金融行业支付安全实践**  
  支付操作属于不可逆的资金流转，须强制二次确认和 HITL。（**未二次核验**：无直接法条编号；金融支付行业实践普遍要求，属最佳实践而非法律强制要求，降级表述）

---

## 五、未登记工具 fail-closed 原则的法规依据

Gate2 对未在 `gate4_capabilities.yaml` 登记的工具默认 YELLOW（而非 GREEN），体现 fail-closed 原则。

**法规锚点：**
- **GB/T 22239-2019 § 8.1.4.2（访问控制—最小权限）**  
  "应采用最小授权原则，依据安全策略控制用户对有敏感标记信息资源的操作"。未登记工具身份不明，按最小权限原则应警告而非放行。（二次核验：FreeBuf解读 + venustech解读，✅ 已二次核验）
- **GB/T 45654-2025 安全措施中默认安全基线要求**  
  "规划阶段的核心目标是在模型正式部署前完成数据资产与访问权限的体系化设计，从源头规避因敏感数据失控引发的系统性风险"。未知工具属于未纳入体系的风险点，须告警。（未二次核验独立条款编号；原则性描述，降级表述）

---

## 六、参考来源

以下来源均已在本文档撰写时查阅，二次核验状态逐条标注。

| # | 标题 | URL | 标准号/条款 | 二次核验状态 |
|---|------|-----|-------------|--------------|
| 1 | GB/T 22239-2019 国家标准全文公开 | https://openstd.samr.gov.cn/bzgk/gb/newGbInfo?hcno=BAFB47E8874764186BDB7865E8344DAF | GB/T 22239-2019 | ✅ 已核验（官方页面） |
| 2 | 中华人民共和国网络安全法（网信办官网） | https://www.cac.gov.cn/2016-11/07/c_1119867116_2.htm | 网络安全法第21条 | ✅ 已核验（官方原文） |
| 3 | GB/T 45654—2025 标准全文（TC260官网） | https://www.tc260.org.cn/portal/article/1/20250630122232 | GB/T 45654-2025 | ✅ 已核验（官方发布页） |
| 4 | TC260-003《生成式人工智能服务安全基本要求》发布（TC260官网） | https://www.tc260.org.cn/front/postDetail.html?id=20240301164054 | TC260-003 | ✅ 已核验（官方页面） |
| 5 | 等保2.0基本要求框架—GB/T 22239-2019解读（启明星辰） | https://www.venustech.com.cn/new_type/dbsdjd/20200826/21477.html | GB/T 22239-2019 通用解读 | ✅ 已核验（权威厂商解读） |
| 6 | 等保2.0高风险判定系列—安全审计（启明星辰） | https://www.venustech.com.cn/new_type/dbsdjd/20200827/21454.html | GB/T 22239-2019 §8.1.4.3 | ✅ 已核验（与标准对照） |
| 7 | 等保2.0标准个人解读（四）：安全计算环境（FreeBuf） | https://www.freebuf.com/articles/es/218259.html | GB/T 22239-2019 §8.1.4.x | ✅ 已核验（与标准对照） |
| 8 | TC260-003专家解读（TC260官网） | https://www.tc260.org.cn/front/postDetail.html?id=20240319163517 | TC260-003 | ✅ 已核验（官方解读） |
| 9 | 全国网安标委发布TC260-003（锦天城律所） | https://www.allbrightlaw.com/CN/10531/51dcf1292975a1d6.aspx | TC260-003 | ✅ 已核验（独立来源） |
| 10 | 《生成式AI服务安全基本要求》发布（安全内参） | https://www.secrss.com/articles/64121 | TC260-003 | ✅ 已核验（专业媒体） |
| 11 | 案例：未按规定留存网络日志（汕尾市审计局） | https://www.shanwei.gov.cn/swssjj/gkmlpt/content/0/945/post_945994.html | 《网络安全法》第21条执法案例 | ✅ 已核验（政府网站） |
| 12 | 一文读懂生成式AI服务安全新国标（CSDN） | https://blog.csdn.net/meidaoliha/article/details/149093609 | GB/T 45654-2025 解读 | ✅ 已核验（独立于来源3） |
| 13 | 网络安全-等级保护(等保) 2-4 GB/T 22239-2019（禾木KG，博客园） | https://www.cnblogs.com/hemukg/p/18817035 | GB/T 22239-2019 条款汇总 | ✅ 已核验（独立于来源5/7） |

---

> **文档维护说明**：本文档由 XA-Guard 子 agent 于 2026-06-04 基于 web search 撰写。
> 后续如有标准版本更新（尤其 GB/T 45654-2025 正式实施后），请同步修订本文档并更新 gate4_capabilities.yaml 注释。
> 标注"未二次核验"的论断均已在文中降级表述，不作为强制合规引用依据。
