"""XA-Guard 共享数据结构。

★ 本文件是子 agent 之间的统一契约。任何关卡 / 代理 / 审计 / 评测都从这里 import。
契约改动必须在根目录 log.md 留痕；能力边界变化时同步更新 status.md。

数据模型来源：
- TaintLabel 三色 — 产品架构 §3.3 关卡 4
- RiskLevel green/yellow/red — 产品架构 §3.3 关卡 2
- Decision allow/warn/deny/require_approval — 产品架构 §3.3 关卡 3
- AuditRecord 14 字段 — 产品架构 §3.3 关卡 6（对齐 OpenTelemetry GenAI Semantic Conventions + 政企扩展）
- PolicyRule — 产品架构 §3.3 关卡 3 Rule YAML
- ToolCapability — 产品架构 §3.3 关卡 4 工具能力声明
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal


# ============================================================
# 1. 三色标签（关卡 4 信息流污点）
# ============================================================
class TaintLabel(str, Enum):
    """数据敏感性标签。值越后越严格。"""

    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"

    @property
    def _rank(self) -> int:
        return {"PUBLIC": 0, "INTERNAL": 1, "CONFIDENTIAL": 2}[self.value]

    def merge(self, other: "TaintLabel") -> "TaintLabel":
        """取最严格的标签（PUBLIC < INTERNAL < CONFIDENTIAL）。"""
        return self if self._rank >= other._rank else other

    def can_flow_to(self, capability: "TaintLabel") -> bool:
        """当前标签的数据能否流到接受标签 ≤ capability 的工具。"""
        return self._rank <= capability._rank


# ============================================================
# 2. 风险等级（关卡 2 办事大厅）
# ============================================================
class RiskLevel(str, Enum):
    GREEN = "green"     # 自动放行
    YELLOW = "yellow"   # 异步通知人审
    RED = "red"         # 同步阻塞 HITL


# ============================================================
# 3. 决策（关卡 1/2/3/4 通用输出）
# ============================================================
class Decision(str, Enum):
    ALLOW = "allow"
    WARN = "warn"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


# ============================================================
# 4. 输入来源（关卡 1 输入攻击识别 — 赛题方向 1 要求）
# ============================================================
class InputSource(str, Enum):
    USER = "user"               # 用户直接输入
    WEB = "web"                 # 网页抓取
    DOCUMENT = "document"       # 文档附件
    RAG = "rag"                 # 知识库检索结果
    MEMORY = "memory"           # 历史记忆
    TOOL_RESULT = "tool_result" # 上一个工具的输出


# ============================================================
# 5. 单关卡输出
# ============================================================
@dataclass
class GateResult:
    gate_name: str
    decision: Decision
    risks: list[str] = field(default_factory=list)      # 检测到的风险描述
    rule_hits: list[str] = field(default_factory=list)  # 命中的策略规则 id
    metadata: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0                              # 0-1
    latency_ms: float = 0.0
    note: str = ""

    @property
    def is_block(self) -> bool:
        return self.decision in (Decision.DENY, Decision.REQUIRE_APPROVAL)


# ============================================================
# 6. 工具元数据（关卡 4 用 + 关卡 5 路由用）
# ============================================================
@dataclass
class ToolCapability:
    tool_name: str
    capabilities: list[str] = field(default_factory=list)
    # 能接受的最高输入污点；CONFIDENTIAL 表示接受任意
    input_max_taint: TaintLabel = TaintLabel.CONFIDENTIAL
    # 工具输出固定的污点（写出到外部 / 公网 → PUBLIC；内部 API → INTERNAL；密钥读取 → CONFIDENTIAL）
    output_taint: TaintLabel = TaintLabel.PUBLIC
    risk_level: RiskLevel = RiskLevel.GREEN
    description: str = ""


# ============================================================
# 7. 策略规则（关卡 3）
# ============================================================
@dataclass
class PolicyRule:
    id: str                              # TC260-003-7.2 / GBT-22239-8.1.4.4 / ...
    name: str
    source: str                          # "等保 2.0 三级 8.1.4.4" / "GB/T 45654-2025 A.1.2" / ...
    triggers: list[str]                  # ["exec_command", "delete_file", "content_generation", ...]
    predicate: str                       # Python 表达式（demo）或 Rego 引用名（生产）
    enforce: Decision
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    audit: Literal["required", "optional", "none"] = "required"
    description: str = ""


# ============================================================
# 7b. 审批令牌（关卡 2 HITL → 关卡 6 审计闭环）
# ============================================================
@dataclass
class Approval:
    """人工审批的可验证凭据。

    由 xa_guard.approval.issue_approval 在人工 approve 时签发，
    pipeline.run_after_approval 执行前验签，gate6 写入审计。
    """

    approver: str                        # 审批人身份（客户端 client info / 运维账号）
    reason: str = ""                     # 审批理由
    args_hash: str = ""                  # 被审批的精确入参 sha256（防 TOCTOU 改参）
    issued_at: str = ""                  # 签发时间 ISO8601
    expires_at: str = ""                 # 过期时间 ISO8601
    token: str = ""                      # HMAC-SHA256 签名


# ============================================================
# 8. 请求上下文（穿过 6 关卡的载体）
# ============================================================
@dataclass
class GateContext:
    """6 关卡的共享上下文。pipeline 每过一关，accumulate gate_results。"""

    # 基本身份
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    span_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # 调用元数据
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    user_role: str = "user"               # user / ops / admin / ...
    session_history: list[dict] = field(default_factory=list)
    input_sources: list[InputSource] = field(default_factory=lambda: [InputSource.USER])

    # 累积属性
    taint: TaintLabel = TaintLabel.PUBLIC
    risk_level: RiskLevel = RiskLevel.GREEN
    gate_results: list[GateResult] = field(default_factory=list)
    rule_hits: list[str] = field(default_factory=list)

    # 审批凭据（REQUIRE_APPROVAL 经人工批准后挂载，run_after_approval 验签）
    approval: "Approval | None" = None

    # 终态
    final_decision: Decision = Decision.ALLOW
    final_reason: str = ""
    tool_result: Any = None
    tool_result_hash: str = ""

    def append(self, result: GateResult) -> None:
        self.gate_results.append(result)
        self.rule_hits.extend(result.rule_hits)
        if result.decision == Decision.DENY:
            self.final_decision = Decision.DENY
            self.final_reason = f"{result.gate_name}: {', '.join(result.risks) or 'denied'}"
        elif result.decision == Decision.REQUIRE_APPROVAL and self.final_decision in (Decision.ALLOW, Decision.WARN):
            self.final_decision = Decision.REQUIRE_APPROVAL
            self.final_reason = f"{result.gate_name}: approval required"
        elif result.decision == Decision.WARN and self.final_decision == Decision.ALLOW:
            self.final_decision = Decision.WARN
            self.final_reason = f"{result.gate_name}: warned"


# ============================================================
# 9. 审计记录（关卡 6，14 字段，对齐 OTel GenAI + 政企扩展）
# ============================================================
@dataclass
class AuditRecord:
    """14 字段审计 schema —— 产品架构 §3.3 关卡 6 表。

    标准字段（OTel GenAI Semantic Conventions）：
      trace_id, span_id, gen_ai.request.model, gen_ai.usage.input_tokens,
      gen_ai.tool.name, gen_ai.tool.parameters, gen_ai.tool.result.hash
    政企扩展字段：
      gen_ai.user.role, gen_ai.data.sensitivity_level, gen_ai.policy.hit_id,
      gen_ai.tool.approval_token, gen_ai.evidence.hash_prev,
      gen_ai.classify.risk_tag, gen_ai.decision.faithfulness_score
    """

    trace_id: str
    span_id: str
    timestamp: str                                                # ISO8601
    gen_ai_request_model: str = ""
    gen_ai_usage_input_tokens: int = 0
    gen_ai_tool_name: str = ""
    gen_ai_tool_parameters: dict[str, Any] = field(default_factory=dict)
    gen_ai_tool_result_hash: str = ""                             # SM3 或 SHA-256
    gen_ai_user_role: str = ""
    gen_ai_data_sensitivity_level: str = "PUBLIC"
    gen_ai_policy_hit_id: list[str] = field(default_factory=list)
    gen_ai_tool_approval_token: str | None = None
    # 审批闭环扩展：审批人 / 理由 / 过期 / 被审批入参哈希
    gen_ai_tool_approval_approver: str = ""
    gen_ai_tool_approval_reason: str = ""
    gen_ai_tool_approval_expires_at: str = ""
    gen_ai_tool_approval_args_hash: str = ""
    gen_ai_evidence_hash_prev: str = ""                           # 前一条审计记录的哈希
    gen_ai_classify_risk_tag: list[str] = field(default_factory=list)
    gen_ai_decision_faithfulness_score: float = 0.0
    gen_ai_decision_final: str = "allow"        # final pipeline decision (allow/warn/deny/require_approval)
    gen_ai_decision_final_reason: str = ""
    # 策略版本号（双层 LayeredPolicySource 的 bundle_sha）；让监管可复现事故时刻的策略快照
    gen_ai_policy_bundle_sha: str = ""
    gen_ai_tool_sandbox_mode: str = "native"
    gen_ai_tool_sandbox_enforced: bool = False
    gen_ai_tool_sandbox_image: str = ""
    gen_ai_tool_sandbox_runtime: str = ""

    # 链式签名（关卡 6）
    record_hash: str = ""                                         # 本条记录的哈希
    signature: str | None = None                                  # SM2 签名 或 demo 占位

    def to_dict(self) -> dict[str, Any]:
        """转 OTel 风格点号 key 的 JSON。"""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "timestamp": self.timestamp,
            "gen_ai.request.model": self.gen_ai_request_model,
            "gen_ai.usage.input_tokens": self.gen_ai_usage_input_tokens,
            "gen_ai.tool.name": self.gen_ai_tool_name,
            "gen_ai.tool.parameters": self.gen_ai_tool_parameters,
            "gen_ai.tool.result.hash": self.gen_ai_tool_result_hash,
            "gen_ai.user.role": self.gen_ai_user_role,
            "gen_ai.data.sensitivity_level": self.gen_ai_data_sensitivity_level,
            "gen_ai.policy.hit_id": self.gen_ai_policy_hit_id,
            "gen_ai.tool.approval_token": self.gen_ai_tool_approval_token,
            "gen_ai.tool.approval.approver": self.gen_ai_tool_approval_approver,
            "gen_ai.tool.approval.reason": self.gen_ai_tool_approval_reason,
            "gen_ai.tool.approval.expires_at": self.gen_ai_tool_approval_expires_at,
            "gen_ai.tool.approval.args_hash": self.gen_ai_tool_approval_args_hash,
            "gen_ai.evidence.hash_prev": self.gen_ai_evidence_hash_prev,
            "gen_ai.classify.risk_tag": self.gen_ai_classify_risk_tag,
            "gen_ai.decision.faithfulness_score": self.gen_ai_decision_faithfulness_score,
            "gen_ai.decision.final": self.gen_ai_decision_final,
            "gen_ai.decision.final_reason": self.gen_ai_decision_final_reason,
            "gen_ai.policy.bundle_sha": self.gen_ai_policy_bundle_sha,
            "gen_ai.tool.sandbox.mode": self.gen_ai_tool_sandbox_mode,
            "gen_ai.tool.sandbox.enforced": self.gen_ai_tool_sandbox_enforced,
            "gen_ai.tool.sandbox.image": self.gen_ai_tool_sandbox_image,
            "gen_ai.tool.sandbox.runtime": self.gen_ai_tool_sandbox_runtime,
            "record_hash": self.record_hash,
            "signature": self.signature,
        }


# ============================================================
# 10. 评测用例（XA-Bench / CSAB-Gov-mini）
# ============================================================
@dataclass
class BenchCase:
    case_id: str
    dimension: Literal[
        "data_safety",         # 数据安全（30-50）
        "content_safety",      # 内容安全（50-80）— GB/T 45654 17/31 类
        "execution_safety",    # 执行安全（50-80）
        "supply_chain",        # 供应链安全（20-30）
        "compliance",          # 合规风险（30-50）— 等保 2.0
        "interpretability",    # 可解释（10-20）
        "traceability",        # 可追溯（10-20）
    ]
    attack_type: str                          # "indirect_injection" / "jailbreak" / "data_exfil" / ...
    input_payload: dict[str, Any]             # {tool_name, arguments, session_history, ...}
    expected_decision: Decision               # allow / deny / warn / require_approval
    expected_taint: TaintLabel | None = None
    policy_refs: list[str] = field(default_factory=list)   # 对应法规条款（用于"赛题契合度"答辩）
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    note: str = ""


@dataclass
class BenchResult:
    case: BenchCase
    actual_decision: Decision
    actual_taint: TaintLabel | None
    rule_hits: list[str]
    latency_ms: float
    passed: bool                              # actual == expected
    note: str = ""
    audit_written: bool = False
    audit_complete: bool = False
    audit_completeness: float = 0.0
