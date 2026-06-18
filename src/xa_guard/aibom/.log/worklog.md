# aibom 模块工作日志

---

## 2026-06-18 — MCP install_plugin 离线准入（Codex 主 agent）
- `gateway.admit_install_request()` 新增本地目录/归档参数别名与 `expected_sha256`，本地 artifact 走真实解包/静态扫描；远程引用只在服务端离线缓存命中时扫描。
- `proxy.upstream` 在真实 MCP `tools/call install_plugin` 进入 6 关卡前注入 `aibom_gateway` 结果；D/F 或未镜像远程引用直接拒绝，A/B/C 继续服从既有策略/HITL，Gate6 记录 `AIBOM-GATEWAY`。
- E2E 验证恶意安装下游 0 次，干净本地 artifact 经 HITL 后下游 1 次并形成 `require_approval -> allow` 审计链。
- OpenCode 真实 LLM smoke 已连接 XA-Guard MCP 并实际调用 `install_plugin`；恶意源码被 AIBOM F 级阻断，Gate6 trace `e4abab76-9b3d-4556-8d08-06be6bcc77ce` 验链通过。
- 边界：不是 marketplace 下载器、IDE 商店拦截、实时漏洞 feed 或生产签名信任链。

---

## 2026-05-24 23:55 主助手
- scanner.py / rater.py 骨架
- 赛题方向 3 加分项；demo 阶段轻量实现
- TODO（agent-AIBOM）：AST 黑名单 + 评级 A-F；三段审批接口

---

## 2026-06-05 — offline_fetch.py (sub-agent)
- 新建 offline_fetch.py：OfflinePackageStore 类，严格离线 fail-closed 缓存解析。
- 支持 name+version / url / name 三种 key 查找；sha256 流式校验；原子 index 写入。
- 路径穿越防护：含 / 或 \ 的文件名直接拒绝，不做 Path.name 静默截断。
- 新建 tests/unit/test_aibom_offline_fetch.py，24 个测试全部通过（0.15 s）。
- stdlib-only，零网络库导入，无第三方依赖。

---

## 2026-06-05 — signing.py (sub-agent)
- 新建 signing.py：JSF-style sign + verify，支持 Ed25519 / SM2 / HMAC-SHA256。
- Ed25519 via cryptography 46（真实非对称路径），raw-hex .priv/.pub 文件。
- SM2 lazy import sm_crypto；gmssl 缺失时 HMAC fallback（已记录 demo 降级行为）。
- trust store 约定：`<keyId>.pub` 优先，对称场景 fallback `<keyId>.key`。
- 新建 tests/unit/test_aibom_signing.py，21 个测试全部通过（0.13 s）。

---

## 2026-06-05 — schema_validator.py (sub-agent)
- 新建 schema_validator.py：双引擎验证（jsonschema + builtin fallback）。
- 手写 schema/cyclonedx-1.6.subset.schema.json 覆盖核心字段；additionalProperties:true 顶层以允许 findings/rating 扩展键。
- Python 层独立做 bom-ref 引用完整性校验、hex 内容校验、vuln severity 校验。
- 公共接口：validate_cyclonedx(bom)->SchemaValidationResult, assert_valid(bom)->None。
- 新建 tests/unit/test_aibom_schema_validator.py，40 个测试全部通过（0.14 s）。

---

## 2026-06-05 — intel.py (sub-agent，详见 intel_worklog.md)
- 新建 intel.py + data/vulndb.json（7 包 10 CVE）+ data/reputation.json（18 包 + default）。
- ThreatIntel.lookup / scan_dependencies；PEP440 版本比较；affected vs potentially_affected。
- tests/unit/test_aibom_intel.py 26 passed。

---

## 2026-06-05 — drift_monitor.py + gateway.py + 总装 (主 agent)
- 新建 drift_monitor.py：DriftMonitor 带持久化快照 + JSONL 漂移账本；复用 exporter.compare_drift；
  严重度分级（新增危险能力/评级下调/漏洞→high，依赖/哈希变更→medium）。
- 新建 gateway.py：admit() 把"离线拉包→扫描→漏洞富化→导出→schema 校验→签名验签→漂移"串成一条流水线，
  输出 AdmissionResult（含 decision allow/warn/deny）。enrich_with_intel() 把漏洞/信誉写进 risk_indicators
  与 CycloneDX vulnerabilities。
- 新建 cli.py：xa-aibom admit/bom/validate/drift 子命令（运维入口，退出码 allow=0/warn=1/deny=2）。
- 集成改动（主 agent 自己改的共享文件）：
  * scanner.ScanReport 增 vulnerabilities 字段（向后兼容）。
  * exporter specVersion 1.5→1.6 + 输出 vulnerabilities 段。
  * rater 评级纳入 vuln_*/reputation_*/signature_invalid/schema_invalid 信号。
  * pyproject 增 aibom extra（jsonschema+cryptography）+ xa-aibom script。
  * 同步更新 test_aibom_schema_validator 中 1.5→1.6 的滞后常量断言（非业务 bug，记此备查）。
- 测试：新增 drift(6)/gateway(7)/cli(5) 全绿；全量 391 passed / 1 skipped（docker sandbox 预期跳过）。
- 端到端 smoke：urllib3==1.26.5+requests==2.31.0 命中 4 CVE、Ed25519 签名验签 True、漂移 D→F high、deny。
- 仍未做：bench supply_chain 仍走旧 rate_install_request 简化口径（接 gateway 会翻 SCM-003 基线，需重新 fingerprint，列为后续）。
