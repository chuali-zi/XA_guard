# Tool x Gate coverage matrix

Policy view: **layered-merged**

- Default Gate2/Gate3/Gate4 view: `LayeredPolicySource` baseline + accepted overlay merge
- Legacy explicit file mode: pass `--gate2`, `--gate3`, or `--gate4`
- Bench: `bench/cases/csab-gov-mini-seed.yaml`

## Summary

- Total distinct tools: **48**
- Gate2 registered tools: **48**
- Gate3 trigger tools: **44**
- Gate4 registered tools: **48**
- Bench tool names: **24**
- Gate3 triggers missing Gate2 registration: **0**
- Gate3 triggers missing Gate4 registration: **0**
- Gate2/Gate4 risk mismatches: **0**
- Bench-only tools: **0**
- Gate3 trigger tools without bench case: **23**
- Invalid risk values: **0**
- Invalid taint values: **0**

Gate3 trigger tools without bench case: admin_action, append_file, approve_label, call_model, content_generation, crawl_url, cross_domain_call, export_database, fine_tune_model, ingest_labeled_data, ingest_training_data, jailbreak, log_cleanup, payment_action, prompt_leak, recommend_content, red_operation, shell, start_annotation, switch_model, tool_call_with_external_input, train_model, update_user_role

## Matrix

| Tool | Gate2 risk | Gate3 rules | Gate4 risk | Gate4 capabilities | Taint in/out | Bench cases | Bench decisions | Status |
|---|---|---:|---|---|---|---:|---|---|
| admin_action | red | 3 | red | AUTHZ_ADMIN, POLICY_ADMIN | INTERNAL / INTERNAL | 0 | - | NO_BENCH_CASE |
| append_file | yellow | 1 | yellow | FS_WRITE | INTERNAL / INTERNAL | 0 | - | NO_BENCH_CASE |
| approve_label | yellow | 1 | yellow | DATA_INGEST | CONFIDENTIAL / INTERNAL | 0 | - | NO_BENCH_CASE |
| call_model | yellow | 1 | yellow | MODEL_CALL, NETWORK_EXTERNAL | INTERNAL / INTERNAL | 0 | - | NO_BENCH_CASE |
| content_generation | yellow | 2 | yellow | CONTENT_PUBLISH | INTERNAL / INTERNAL | 0 | - | NO_BENCH_CASE |
| crawl_url | yellow | 1 | yellow | NETWORK_EXTERNAL, DATA_INGEST | PUBLIC / INTERNAL | 0 | - | NO_BENCH_CASE |
| cross_domain_call | yellow | 2 | yellow | NETWORK_EXTERNAL | PUBLIC / PUBLIC | 0 | - | NO_BENCH_CASE |
| delete_file | red | 6 | red | FS_WRITE | INTERNAL / PUBLIC | 2 | deny | OK |
| deploy_model | red | 2 | red | MODEL_DEPLOY | INTERNAL / INTERNAL | 3 | require_approval | OK |
| deploy_system | red | 2 | red | NETWORK_INTERNAL, MODEL_DEPLOY | INTERNAL / INTERNAL | 5 | require_approval | OK |
| drop_table | red | 3 | red | NETWORK_INTERNAL, EXEC | INTERNAL / INTERNAL | 3 | deny, require_approval | OK |
| echo | green | 0 | green | - | CONFIDENTIAL / PUBLIC | 0 | - | OK |
| enable_minor_service | yellow | 1 | yellow | CONTENT_PUBLISH | INTERNAL / INTERNAL | 6 | require_approval | OK |
| exec_command | red | 7 | red | EXEC, FS_WRITE | INTERNAL / INTERNAL | 40 | deny, require_approval | OK |
| export_database | red | 1 | red | NETWORK_INTERNAL, FS_READ, DATA_EXPORT | INTERNAL / CONFIDENTIAL | 0 | - | NO_BENCH_CASE |
| export_generated_content | red | 1 | red | NETWORK_EXTERNAL, CONTENT_PUBLISH | PUBLIC / PUBLIC | 11 | deny | OK |
| fine_tune_model | red | 4 | red | MODEL_TRAINING, DATA_INGEST | CONFIDENTIAL / INTERNAL | 0 | - | NO_BENCH_CASE |
| get_cpu | green | 0 | green | NETWORK_INTERNAL | PUBLIC / INTERNAL | 10 | allow | NO_GATE3_RULE |
| grant_permission | red | 1 | red | AUTHZ_ADMIN | INTERNAL / INTERNAL | 8 | require_approval | OK |
| import_training_data | red | 5 | red | FS_READ, DATA_INGEST | CONFIDENTIAL / CONFIDENTIAL | 15 | deny, require_approval | OK |
| ingest_labeled_data | red | 1 | red | DATA_INGEST | CONFIDENTIAL / CONFIDENTIAL | 0 | - | NO_BENCH_CASE |
| ingest_training_data | red | 5 | red | FS_READ, DATA_INGEST | CONFIDENTIAL / CONFIDENTIAL | 0 | - | NO_BENCH_CASE |
| install_plugin | red | 1 | red | NETWORK_EXTERNAL, DATA_INGEST, FS_WRITE, EXEC | PUBLIC / INTERNAL | 25 | allow, deny, warn | OK |
| jailbreak | yellow | 1 | yellow | - | PUBLIC / PUBLIC | 0 | - | NO_BENCH_CASE |
| list_servers | green | 0 | green | NETWORK_INTERNAL, FS_READ | PUBLIC / INTERNAL | 28 | allow | NO_GATE3_RULE |
| log_cleanup | red | 2 | red | AUDIT_ADMIN, FS_WRITE | INTERNAL / PUBLIC | 0 | - | NO_BENCH_CASE |
| payment_action | red | 1 | red | NETWORK_EXTERNAL, PAYMENT | PUBLIC / PUBLIC | 0 | - | NO_BENCH_CASE |
| post_url | yellow | 4 | yellow | NETWORK_EXTERNAL | PUBLIC / PUBLIC | 14 | require_approval | OK |
| prompt_leak | yellow | 1 | yellow | - | PUBLIC / PUBLIC | 0 | - | NO_BENCH_CASE |
| publish_system | red | 2 | red | NETWORK_INTERNAL, MODEL_DEPLOY | INTERNAL / INTERNAL | 5 | require_approval | OK |
| read_log | green | 0 | green | FS_READ | INTERNAL / INTERNAL | 45 | allow, deny | NO_GATE3_RULE |
| recommend_content | yellow | 1 | yellow | CONTENT_PUBLISH | INTERNAL / PUBLIC | 0 | - | NO_BENCH_CASE |
| red_operation | red | 1 | red | EXEC | INTERNAL / INTERNAL | 0 | - | NO_BENCH_CASE |
| restart_service | yellow | 3 | yellow | NETWORK_INTERNAL, EXEC | INTERNAL / INTERNAL | 7 | deny, require_approval | OK |
| send_email | yellow | 4 | yellow | NETWORK_EXTERNAL, NOTIFY | INTERNAL / PUBLIC | 12 | deny | OK |
| send_notification | yellow | 2 | yellow | NETWORK_EXTERNAL, NOTIFY | INTERNAL / PUBLIC | 14 | deny, warn | OK |
| shell | red | 2 | red | EXEC, FS_WRITE | INTERNAL / INTERNAL | 0 | - | NO_BENCH_CASE |
| start_annotation | yellow | 1 | yellow | DATA_INGEST | CONFIDENTIAL / INTERNAL | 0 | - | NO_BENCH_CASE |
| switch_model | yellow | 1 | yellow | MODEL_DEPLOY | INTERNAL / INTERNAL | 0 | - | NO_BENCH_CASE |
| tool_call_with_external_input | yellow | 1 | yellow | - | INTERNAL / INTERNAL | 0 | - | NO_BENCH_CASE |
| train_model | red | 3 | red | MODEL_TRAINING, DATA_INGEST | CONFIDENTIAL / INTERNAL | 0 | - | NO_BENCH_CASE |
| update_audit_policy | red | 1 | red | AUDIT_ADMIN, POLICY_ADMIN | INTERNAL / INTERNAL | 12 | deny | OK |
| update_backup_policy | red | 1 | red | POLICY_ADMIN | INTERNAL / INTERNAL | 5 | require_approval | OK |
| update_encryption_policy | red | 1 | red | POLICY_ADMIN | INTERNAL / INTERNAL | 4 | deny | OK |
| update_model | red | 1 | red | MODEL_DEPLOY, MODEL_TRAINING | INTERNAL / INTERNAL | 2 | require_approval | OK |
| update_user_role | red | 1 | red | AUTHZ_ADMIN | INTERNAL / INTERNAL | 0 | - | NO_BENCH_CASE |
| user_session_risk | yellow | 1 | yellow | - | INTERNAL / INTERNAL | 6 | require_approval | OK |
| write_file | yellow | 2 | yellow | FS_WRITE | INTERNAL / INTERNAL | 8 | deny | OK |

## Gate3 trigger detail

- admin_action: GBT-22239-8.1.3.1, GBT-22239-DUTY-SEPARATION, GBT-22239-KEY-ROLE
- append_file: GBT-45654-A.2.3
- approve_label: GBT-45654-LABEL-DUTY-SEPARATION
- call_model: GBT-45654-MODEL-FILING
- content_generation: GBT-45654-A.2.3, TC260-003-REPEATED-ILLEGAL-INPUT
- crawl_url: GBT-45654-DATA-ROBOTS
- cross_domain_call: GBT-22239-8.1.4.2, GBT-22239-CII-EXTERNAL
- delete_file: GBT-22239-8.1.3.1, GBT-22239-8.1.4.4, GBT-22239-AUDIT-DELETE, GBT-22239-BACKUP-DISABLE, GBT-22239-DUTY-SEPARATION, TC260-003-9.4
- deploy_model: GBT-45654-MODEL-FILING, GBT-45654-MODEL-UPDATE-ASSESS
- deploy_system: GBT-22239-ASSESSMENT-EVIDENCE, GBT-22239-EXT-PROFILE
- drop_table: GBT-22239-8.1.3.1, GBT-22239-8.1.4.4, TC260-003-9.4
- enable_minor_service: GBT-45654-MINOR-PROTECTION
- exec_command: GBT-22239-8.1.3.1, GBT-22239-8.1.4.4, GBT-22239-8.1.4.5, GBT-22239-AUDIT-DELETE, GBT-22239-BACKUP-DISABLE, GBT-22239-DUTY-SEPARATION, TC260-003-9.4
- export_database: GBT-22239-DATA-ENCRYPTION
- export_generated_content: AIGC-LABEL-REQUIRED
- fine_tune_model: GBT-45654-DATA-AUTH, GBT-45654-DATA-PII-CONSENT, GBT-45654-DATA-SPI-CONSENT, GBT-45654-MODEL-UPDATE-ASSESS
- grant_permission: GBT-22239-KEY-ROLE
- import_training_data: GBT-45654-DATA-AUTH, GBT-45654-DATA-COMMERCIAL-PROOF, GBT-45654-DATA-PII-CONSENT, GBT-45654-DATA-ROBOTS, GBT-45654-DATA-SPI-CONSENT
- ingest_labeled_data: GBT-45654-LABEL-DUTY-SEPARATION
- ingest_training_data: GBT-45654-DATA-AUTH, GBT-45654-DATA-COMMERCIAL-PROOF, GBT-45654-DATA-PII-CONSENT, GBT-45654-DATA-ROBOTS, GBT-45654-DATA-SPI-CONSENT
- install_plugin: AIBOM-INSTALL-PLUGIN-SUPPLY-CHAIN
- jailbreak: GBT-45654-A.3.2
- log_cleanup: CSL-LOG-RETENTION-6M, GBT-22239-AUDIT-DELETE
- payment_action: GBT-45654-MINOR-PROTECTION
- post_url: AIGC-LABEL-REQUIRED, GBT-22239-8.1.4.2, GBT-22239-CII-EXTERNAL, GBT-45654-A.1.1
- prompt_leak: GBT-45654-A.4.1
- publish_system: GBT-22239-ASSESSMENT-EVIDENCE, GBT-22239-EXT-PROFILE
- recommend_content: GBT-45654-MINOR-PROTECTION
- red_operation: TC260-003-9.4
- restart_service: GBT-22239-8.1.3.1, GBT-22239-8.1.4.4, GBT-22239-DUTY-SEPARATION
- send_email: AIGC-LABEL-REQUIRED, GBT-22239-8.1.4.2, GBT-22239-CII-EXTERNAL, GBT-45654-A.1.1
- send_notification: GBT-22239-8.1.4.2, GBT-45654-A.1.1
- shell: GBT-22239-8.1.4.4, TC260-003-9.4
- start_annotation: GBT-45654-LABEL-DUTY-SEPARATION
- switch_model: GBT-45654-MODEL-FILING
- tool_call_with_external_input: TC260-003-7.2
- train_model: GBT-45654-DATA-AUTH, GBT-45654-DATA-PII-CONSENT, GBT-45654-DATA-SPI-CONSENT
- update_audit_policy: CSL-LOG-RETENTION-6M
- update_backup_policy: GBT-22239-BACKUP-DISABLE
- update_encryption_policy: GBT-22239-DATA-ENCRYPTION
- update_model: GBT-45654-MODEL-UPDATE-ASSESS
- update_user_role: GBT-22239-KEY-ROLE
- user_session_risk: TC260-003-REPEATED-ILLEGAL-INPUT
- write_file: GBT-22239-DATA-ENCRYPTION, GBT-45654-A.2.3
