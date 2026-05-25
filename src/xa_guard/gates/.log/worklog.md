# gates 模块工作日志

每个子 agent 完工时追加一条。覆盖关卡 1-6 各自的决策、偏差、TODO。

---

## 2026-05-25 子 agent G56A (gate5_sandbox + gate6_audit)
- Gate5Sandbox：按 ctx.risk_level / 前置 gate2 metadata 路由 native/docker/docker_gvisor；RED 但 runtime!=runsc 自动降级 docker；cfg.enabled=false 统一 native + note="docker disabled in demo"
- 偏差：base.__call__ 的 disabled 短路会返回空 metadata，与 spec 要求 enabled=false 必须 metadata["sandbox_mode"]="native" 冲突 → Gate5 覆盖 __call__（保留 stage 检查 + 异常捕获 + latency 计时，不走 disabled 短路）
- Gate6Audit：构造时建 audit_dir + 实例化 ChainStore；evaluate 渲染 14 字段 AuditRecord → to_otel_dict → ChainStore.append 落 JSONL；hash_algo=sha256/sm3 双轨；enable_sm2_signature=true 时 _patch_last_signature 把 signature 写回最后一行
- 决策：approval_token 从 gate2 metadata 取；request_model 从 ctx.session_history 含 model 字段的第一个 dict 取
- 测试：test_gate5.py 5 用例 / test_gate6_audit.py 6 用例 / test_merkle.py 5 用例；端到端 verify_audit.py 3 条记录 exit 0；全套 87 测试通过

## 2026-05-25 agent-G3 (gate3_policy)
- gate3_policy.py 完整实现：__init__ 加载 YAML + 编译每条 predicate（一次性，evaluate 不重编译）
- 聚合优先级 DENY > REQUIRE_APPROVAL > WARN > ALLOW；空 triggers 视为匹配所有工具
- backend=python 走 compile_predicate；backend=rego 直接 NotImplementedError（M3 接 OPA）
- predicate 内部异常吞掉视为未命中，避免单条规则崩整个 gate
- metadata 输出 policy_count / policy_hit_count / policy_severity_max / backend
- 配套 pipeline.py 加 _sync_ctx_from_result：每关后把 result.metadata.risk_level/taint 同步回 ctx（gate3 predicate 依赖 ctx.risk_level）；修正 enterprise-l3.yaml 中 8.1.3.1 / 8.1.4.2 两条规则的 triggers 与 predicate 不一致；tests/unit/test_gate3.py 25 个用例通过

## 2026-05-25 agent-G1 (gate1_input)
- 改了 gate1_input.py：从 YAML 加载 dangerous_patterns → 拼接 tool_name+arguments+session_history 文本做大小写无关匹配 → 按 _DENY_CATEGORIES 决策 DENY/WARN/ALLOW → 写 detected_patterns + source_risk_score 到 metadata
- 关键决策：路径解析用 Path(__file__) 向上四层定位项目根，避免 cwd 依赖；session_history 支持 content 为字符串或 list[dict] 两种格式；warn_source 仅在无 deny 命中时生效，保证 deny 优先
- 已知问题：patterns_file 路径解析假设 gate1_input.py 位于 src/xa_guard/gates/，层级硬编码；M2 PromptGuard 推理未实现（按设计留 stub）

## 2026-05-25 G4 (gate4_taint)
- 实现 Gate4Taint：INBOUND 推断污点（input_sources merge + arguments/session_history 敏感关键字扫描）→ can_flow_to 检查；OUTBOUND merge output_taint → CONFIDENTIAL+EXTERNAL/NOTIFY 阻断
- 加载 policies/tool_capabilities.yaml；未登记工具默认 input_max=CONFIDENTIAL（宽松通行）
- 敏感正则覆盖：密码/密钥/access_key/secret_key/AKIA.../ghp_.../身份证
- strict_mode 保留接口（当前无 WARN 输出路径，分支备扩展）
- 新建 tests/unit/test_gate4.py，9 个用例全部通过（PYTHONPATH=src）

## 2026-05-25 G2 (gate2_plan)
- 实现 Gate2Plan.evaluate: 从 tool_risks.yaml 加载风险映射，GREEN→ALLOW，YELLOW→WARN+notify_async，RED→_request_approval
- elicitation_fallback 三路：stdout(REQUIRE_APPROVAL+stderr打印)、deny(DENY)、async_notify(WARN+notify_async)
- risk_level 写入 GateResult.metadata["risk_level"]，不 mutate ctx；downstream gate3/4/5 自读 metadata
- approval_token 签发留 TODO，真正 MCP elicitation 由 proxy/upstream.py 负责（事实源 F-3.4：国产 IDE 未声明，必须 fallback）
- 12 个单元测试全部通过（tests/unit/test_gate2.py）

## 2026-05-24 23:55 主助手
- 6 关卡 stub 建立；Gate 抽象基类约定 evaluate(ctx, stage) -> GateResult
- 关卡 1/2/3/5 supported_stages=(INBOUND,)；关卡 4 双向；关卡 6 仅 OUTBOUND
- 决策：关卡内异常不应崩 pipeline → base.__call__ 捕获并返回 WARN
- TODO（子 agent）：填充 evaluate；不要 mutate ctx，由 pipeline.append 统一处理
