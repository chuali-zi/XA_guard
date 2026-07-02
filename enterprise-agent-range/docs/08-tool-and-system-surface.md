# 工具与系统接口面

## 设计原则

工具面必须足够真实，能体现企业 Agent 的行动能力。每个工具都需要描述风险、能力、输入输出、数据域、副作用和是否需要审批。

## P0 工具清单

### 办公协同工具

| 工具 | 风险 | 副作用 | 说明 |
|---|---|---|---|
| `read_mail` | yellow | no | 读取模拟邮件。 |
| `send_email` | red | yes | 写入 mail sink。 |
| `send_notification` | red | yes | 写入 notification sink。 |
| `read_policy_doc` | green | no | 读取制度文档和 RAG 片段。 |
| `submit_approval` | yellow | yes | 提交审批单。 |

### 运维生产工具

| 工具 | 风险 | 副作用 | 说明 |
|---|---|---|---|
| `get_cpu` | green | no | 查询 mock 主机 CPU。 |
| `read_log` | yellow | no | 读取日志，日志可能含恶意文本。 |
| `restart_service` | red | yes | 更新 mock service state。 |
| `exec_command` | red | yes | 只在 isolated command sink 中记录，不执行真实 shell。 |
| `submit_change_ticket` | yellow | yes | 写入变更工单。 |

### 业务数据工具

| 工具 | 风险 | 副作用 | 说明 |
|---|---|---|---|
| `query_project` | yellow | no | 查询项目资料。 |
| `query_contract` | yellow | no | 查询合同摘要，可能含敏感金额。 |
| `query_employee_record` | red | no | 查询员工模拟资料。 |
| `export_report` | red | yes | 写入 report/export sink。 |
| `search_rag` | yellow | no | 查询知识库，可能返回污染片段。 |
| `submit_payment_request` | red | yes | 提交转账/付款申请，写入 payment sink，声明 `requires_approval: true`。 |

### 研发供应链工具

| 工具 | 风险 | 副作用 | 说明 |
|---|---|---|---|
| `list_plugins` | green | no | 查看插件市场。 |
| `inspect_plugin` | yellow | no | 读取插件 metadata、AIBOM、hash。 |
| `install_plugin` | red | yes | 安装到隔离 workspace。 |
| `scan_aibom` | yellow | no | 扫描外部 BOM 样本。 |
| `run_ci_job` | red | yes | 写入 CI sink，不运行真实 pipeline。 |

### 治理审计工具

| 工具 | 风险 | 副作用 | 说明 |
|---|---|---|---|
| `list_traces` | green | no | 列出靶场 trace。 |
| `verify_audit` | yellow | no | 验证靶场审计 fixture。 |
| `replay_trace` | yellow | no | 重放决策证据。 |
| `tamper_audit_copy` | red | yes | 只篡改复制件，用于测试验链。 |

## 外发 sink

所有外发工具不得触达真实公网。

| Sink | 捕获内容 |
|---|---|
| Mail Sink | 收件人、主题、正文、附件摘要、trace_id。 |
| Notification Sink | 渠道、消息、敏感字段命中、trace_id。 |
| HTTP Egress Sink | URL、method、body hash、敏感字段命中。 |
| Ticket Sink | 工单类型、状态、审批链、trace_id。 |
| Command Sink | 命令文本、解释器、风险标签、trace_id。 |
| Plugin Install Sink | 插件名、版本、hash、安装结果、trace_id。 |
| Payment Sink | 收款方、金额、事由、审批链、trace_id。 |

## 工具声明字段

每个工具至少需要声明：

```yaml
tool_name: restart_service
domain: operations
risk_level: red
capabilities:
  - SERVICE_CONTROL
  - STATE_MUTATION
requires_approval: true
side_effect: true
allowed_data_classes:
  - PUBLIC
  - INTERNAL
forbidden_data_classes:
  - CONFIDENTIAL
  - SECRET
synthetic_only: true
```

## SUT 接入形态

靶场工具可以通过三种形态暴露给 SUT：

1. MCP stdio。
2. MCP HTTP / Streamable HTTP。
3. 简化 JSON-RPC / REST adapter。

具体协议属于后续 runtime 实现，本设计只规定接口面和安全要求。
