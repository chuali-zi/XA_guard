"""关卡 6 · 黑匣子（审计溯源） — 赛题方向 4 核心。

子 agent 实施职责：
- 把 GateContext + tool_result 渲染成 AuditRecord（14 字段）
- 写 OpenTelemetry GenAI span（demo：JSONL 文件）
- 计算 record_hash（SM3 优先 / SHA-256 兜底，cfg.gate6.options.hash_algo）
- 链入 Merkle 前向链（hash_prev）
- 可选：SM2 签名（gmssl 可用时；否则 HMAC 占位）

接口契约：
- 阶段：OUTBOUND（pipeline 在出口调用）
- 输入：GateContext（含 gate_results, tool_result）
- 输出：GateResult.decision = ALLOW；metadata 含 audit_path / record_hash
- 持久化：cfg.options.audit_dir/audit.jsonl 追加一行
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from xa_guard.audit.merkle import ChainStore, canonical_json
from xa_guard.audit.otel import to_otel_dict
from xa_guard.audit.sm_crypto import sm2_sign, sm3_hash
from xa_guard.config import GateConfig
from xa_guard.gates.base import Gate, GateStage
from xa_guard.policy.layered import get_global_source
from xa_guard.types import AuditRecord, Decision, GateContext, GateResult


class Gate6Audit(Gate):
    name = "gate6_audit"
    supported_stages = (GateStage.OUTBOUND,)

    def __init__(self, cfg: GateConfig | None = None) -> None:
        super().__init__(cfg)
        audit_dir = Path(self.opt("audit_dir", "./logs/audit"))
        audit_dir.mkdir(parents=True, exist_ok=True)
        self.audit_path = audit_dir / "audit.jsonl"
        self.hash_algo: str = self.opt("hash_algo", "sha256") or "sha256"
        self.chain = ChainStore(self.audit_path, algo=self.hash_algo)
        self.enable_sig: bool = bool(self.opt("enable_sm2_signature", False))
        self.sm2_key_path: str = self.opt("sm2_key_path", "") or ""

    def evaluate(self, ctx: GateContext, stage: GateStage = GateStage.OUTBOUND) -> GateResult:
        # 1. 计算 tool_result_hash（canonical JSON）
        if ctx.tool_result is None:
            tool_result_payload = b""
        else:
            try:
                tool_result_payload = canonical_json(ctx.tool_result)
            except TypeError:
                # 工具结果非 JSON 序列化时退回 repr()
                tool_result_payload = repr(ctx.tool_result).encode("utf-8")
        result_hash = sm3_hash(tool_result_payload, prefer_gm=(self.hash_algo == "sm3"))

        # 2. 从 session_history 推断 model 字段
        request_model = ""
        for h in ctx.session_history or []:
            if isinstance(h, dict) and h.get("model"):
                request_model = str(h["model"])
                break

        # 3. risk_tag：取所有 gate_results 中有 risks 的 note
        risk_tags = [g.note for g in ctx.gate_results if g.risks and g.note]

        # 4. approval：优先取 ctx.approval（人工审批签发的可验证令牌），
        #    回退到 gate2 metadata 里的历史 approval_token。
        approval = ctx.approval
        if approval is not None:
            approval_token = approval.token or None
            approval_approver = approval.approver
            approval_reason = approval.reason
            approval_expires_at = approval.expires_at
            approval_args_hash = approval.args_hash
        else:
            approval_token = None
            approval_approver = ""
            approval_reason = ""
            approval_expires_at = ""
            approval_args_hash = ""
            for g in ctx.gate_results:
                tok = g.metadata.get("approval_token") if g.metadata else None
                if tok:
                    approval_token = str(tok)
                    break

        # 5. 双层策略 bundle_sha（若 LayeredPolicySource 已实例化）
        layered = get_global_source()
        bundle_sha = layered.bundle_sha if layered is not None else ""
        sandbox_metadata = {}
        for gate_result in reversed(ctx.gate_results):
            if gate_result.gate_name in ("gate5_sandbox", "gate5"):
                sandbox_metadata = gate_result.metadata or {}
                break

        record = AuditRecord(
            trace_id=ctx.trace_id,
            span_id=ctx.span_id,
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            gen_ai_request_model=request_model,
            gen_ai_usage_input_tokens=0,
            gen_ai_tool_name=ctx.tool_name,
            gen_ai_tool_parameters=dict(ctx.arguments or {}),
            gen_ai_tool_result_hash=result_hash,
            gen_ai_user_role=ctx.user_role,
            gen_ai_data_sensitivity_level=ctx.taint.value if ctx.taint else "PUBLIC",
            gen_ai_policy_hit_id=list(ctx.rule_hits),
            gen_ai_tool_approval_token=approval_token,
            gen_ai_tool_approval_approver=approval_approver,
            gen_ai_tool_approval_reason=approval_reason,
            gen_ai_tool_approval_expires_at=approval_expires_at,
            gen_ai_tool_approval_args_hash=approval_args_hash,
            gen_ai_evidence_hash_prev="",  # ChainStore.append 会写入
            gen_ai_classify_risk_tag=risk_tags,
            gen_ai_decision_faithfulness_score=1.0,
            gen_ai_decision_final=ctx.final_decision.value,
            gen_ai_decision_final_reason=ctx.final_reason,
            gen_ai_policy_bundle_sha=bundle_sha,
            gen_ai_tool_sandbox_mode=str(sandbox_metadata.get("sandbox_mode") or "native"),
            gen_ai_tool_sandbox_enforced=bool(sandbox_metadata.get("sandbox_enforced", False)),
            gen_ai_tool_sandbox_image=str(sandbox_metadata.get("docker_image") or ""),
            gen_ai_tool_sandbox_runtime=str(sandbox_metadata.get("runtime") or ""),
        )

        # 6. 序列化 → ChainStore 追加（落盘并计算 record_hash）
        record_dict = to_otel_dict(record)
        # 移除占位字段，让 ChainStore 重新计算
        record_dict.pop("record_hash", None)
        record_dict.pop("signature", None)
        appended = self.chain.append(record_dict)
        record_hash = appended.get("record_hash", "")

        # 7. 可选 SM2 签名（demo HMAC-SHA256 fallback）
        signature: Any = None
        if self.enable_sig:
            payload = canonical_json({k: v for k, v in appended.items() if k != "signature"})
            signature = sm2_sign(payload, self.sm2_key_path, prefer_gm=(self.hash_algo == "sm3"))
            # 把 signature 写回最后一行（追加再写一份会破坏链；这里覆盖最后一行）
            self._patch_last_signature(signature)

        return GateResult(
            gate_name=self.name,
            decision=Decision.ALLOW,
            metadata={
                "audit_path": str(self.audit_path),
                "record_hash": record_hash,
                "audit_completeness": 1.0,
                "hash_algo": self.hash_algo,
                "signature": signature,
            },
        )

    def _patch_last_signature(self, signature: str) -> None:
        """把最后一行 JSON 的 signature 字段补上。"""
        try:
            lines = self.audit_path.read_text(encoding="utf-8").splitlines()
            if not lines:
                return
            import json

            last = json.loads(lines[-1])
            last["signature"] = signature
            lines[-1] = canonical_json(last).decode("utf-8")
            self.audit_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception:
            pass
