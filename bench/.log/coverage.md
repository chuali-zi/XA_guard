# CSAB-Gov-mini coverage report

Total cases: **290**
Distinct fingerprints: **290**  

## By dimension
- compliance: 50
- content_safety: 60
- data_safety: 50
- execution_safety: 60
- interpretability: 20
- supply_chain: 25
- traceability: 25

## By case_kind
- assurance_check: 21
- attack_case: 193
- benign_control: 76

## By expected_decision
- allow: 73
- deny: 118
- require_approval: 77
- warn: 22

## By dimension × attack_type
### compliance
- assessment_evidence_missing: 5
- backup_policy_change: 5
- benign_compliant: 8
- cii_external_transfer: 5
- encryption_downgrade: 4
- extension_profile_missing: 5
- key_role_change: 5
- log_retention_below_6m: 8
- model_governance: 5

### content_safety
- aigc_label_missing: 8
- benign_non_refusal: 20
- forbidden_generation: 8
- jailbreak_or_prompt_leak: 12
- minor_protection: 6
- repeated_illegal_input: 6

### data_safety
- benign_data_query: 8
- benign_notification: 6
- cross_domain_internal: 6
- pii_leak: 7
- secret_exfil: 8
- training_data_governance: 15

### execution_safety
- benign_green_tool: 10
- benign_red_tool: 12
- dangerous_command: 15
- indirect_injection: 10
- privilege_escalation: 8
- restart_requires_approval: 5

### interpretability
- benign_explainable: 5
- risk_explanation: 15

### supply_chain
- benign_pinned_plugin: 6
- benign_plugin: 1
- code_capability_scan: 6
- covert_network: 1
- dependency_typosquat: 1
- malicious_plugin: 1
- remote_artifact_review: 5
- unknown_package_review: 4

### traceability
- audit_decision_coverage: 8
- audit_hash_chain: 6
- audit_required_red_tool: 7
- retention_audit_denied: 4

## Standards cited
- AI 生成合成内容标识办法: 11 citations
- GB/T 22239-2019: 137 citations
- GB/T 45654-2025: 148 citations
- TC260-003: 48 citations
- 中华人民共和国网络安全法: 12 citations

