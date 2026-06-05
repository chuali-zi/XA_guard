"""Gate6Audit 单元测试 — 14 字段 / 链式 / fallback / 禁用。"""
from __future__ import annotations

import json
from pathlib import Path

from xa_guard.audit.merkle import ChainStore
from xa_guard.config import GateConfig
from xa_guard.gates.base import GateStage
from xa_guard.gates.gate6_audit import Gate6Audit
from xa_guard.types import Decision, GateContext, GateResult, TaintLabel


REQUIRED_OTEL_KEYS = [
    "trace_id",
    "span_id",
    "timestamp",
    "gen_ai.request.model",
    "gen_ai.usage.input_tokens",
    "gen_ai.tool.name",
    "gen_ai.tool.parameters",
    "gen_ai.tool.result.hash",
    "gen_ai.user.role",
    "gen_ai.data.sensitivity_level",
    "gen_ai.policy.hit_id",
    "gen_ai.tool.approval_token",
    "gen_ai.evidence.hash_prev",
    "gen_ai.classify.risk_tag",
    "gen_ai.decision.faithfulness_score",
    "record_hash",
]


def _make_ctx(tool_result=None) -> GateContext:
    ctx = GateContext(tool_name="get_cpu", arguments={"host": "web03"}, user_role="ops")
    ctx.taint = TaintLabel.INTERNAL
    ctx.rule_hits = ["POLICY-1", "POLICY-2"]
    ctx.session_history = [{"model": "qwen-max"}]
    ctx.tool_result = tool_result if tool_result is not None else {"cpu": "30%"}
    ctx.gate_results.append(
        GateResult(gate_name="gate1_input", decision=Decision.WARN, risks=["x"], note="suspicious")
    )
    return ctx


def test_gate6_writes_14_fields(tmp_path: Path):
    g = Gate6Audit(GateConfig(enabled=True, options={"audit_dir": str(tmp_path), "hash_algo": "sha256"}))
    ctx = _make_ctx()
    r = g(ctx, GateStage.OUTBOUND)
    assert r.decision == Decision.ALLOW
    assert r.metadata["audit_completeness"] == 1.0
    assert r.metadata["record_hash"]

    p = Path(r.metadata["audit_path"])
    line = p.read_text(encoding="utf-8").strip()
    rec = json.loads(line)
    for k in REQUIRED_OTEL_KEYS:
        assert k in rec, f"missing OTel field: {k}"

    assert rec["gen_ai.tool.name"] == "get_cpu"
    assert rec["gen_ai.tool.parameters"] == {"host": "web03"}
    assert rec["gen_ai.user.role"] == "ops"
    assert rec["gen_ai.data.sensitivity_level"] == "INTERNAL"
    assert rec["gen_ai.policy.hit_id"] == ["POLICY-1", "POLICY-2"]
    assert rec["gen_ai.request.model"] == "qwen-max"
    assert "suspicious" in rec["gen_ai.classify.risk_tag"]
    assert rec["gen_ai.decision.faithfulness_score"] == 1.0


def test_gate6_chain_links_three_records(tmp_path: Path):
    g = Gate6Audit(GateConfig(enabled=True, options={"audit_dir": str(tmp_path), "hash_algo": "sha256"}))
    hashes = []
    for i in range(3):
        ctx = _make_ctx({"i": i})
        r = g(ctx, GateStage.OUTBOUND)
        hashes.append(r.metadata["record_hash"])

    p = Path(r.metadata["audit_path"])
    lines = p.read_text(encoding="utf-8").splitlines()
    recs = [json.loads(l) for l in lines]

    assert recs[0]["gen_ai.evidence.hash_prev"] == ""
    assert recs[1]["gen_ai.evidence.hash_prev"] == hashes[0]
    assert recs[2]["gen_ai.evidence.hash_prev"] == hashes[1]

    chain = ChainStore(p, algo="sha256")
    ok, _ = chain.verify()
    assert ok is True


def test_gate6_disabled_skips_writing(tmp_path: Path):
    """enabled=false → base.__call__ 短路，不应写文件。"""
    g = Gate6Audit(GateConfig(enabled=False, options={"audit_dir": str(tmp_path), "hash_algo": "sha256"}))
    ctx = _make_ctx()
    r = g(ctx, GateStage.OUTBOUND)
    assert r.decision == Decision.ALLOW
    assert r.note == "disabled"
    # audit.jsonl 不应存在或为空
    p = tmp_path / "audit.jsonl"
    assert not p.exists() or p.stat().st_size == 0


def test_gate6_sha256_fallback_on_sm3_unavailable(tmp_path: Path):
    """hash_algo=sm3 时若 gmssl 不可用，sm3_hash 内部会 fallback SHA-256。"""
    g = Gate6Audit(GateConfig(enabled=True, options={"audit_dir": str(tmp_path), "hash_algo": "sm3"}))
    ctx = _make_ctx()
    r = g(ctx, GateStage.OUTBOUND)
    assert r.metadata["record_hash"]
    # 哈希应为 hex 字符串
    int(r.metadata["record_hash"], 16)  # 不抛 ValueError 即合规
    assert r.metadata["hash_algo"] == "sm3"


def test_gate6_sm2_signature_optional(tmp_path: Path):
    g = Gate6Audit(
        GateConfig(
            enabled=True,
            options={
                "audit_dir": str(tmp_path),
                "hash_algo": "sha256",
                "enable_sm2_signature": True,
                "sm2_key_path": "",
            },
        )
    )
    ctx = _make_ctx()
    r = g(ctx, GateStage.OUTBOUND)
    assert r.metadata.get("signature")

    # 文件最后一行应含 signature 字段
    p = Path(r.metadata["audit_path"])
    rec = json.loads(p.read_text(encoding="utf-8").splitlines()[-1])
    assert rec.get("signature") == r.metadata["signature"]


def test_audit_record_carries_final_decision(tmp_path: Path):
    """AuditRecord must capture ctx.final_decision and ctx.final_reason."""
    g = Gate6Audit(GateConfig(enabled=True, options={"audit_dir": str(tmp_path), "hash_algo": "sha256"}))
    ctx = _make_ctx()
    ctx.final_decision = Decision.DENY
    ctx.final_reason = "gate3: blocked"
    g(ctx, GateStage.OUTBOUND)

    p = tmp_path / "audit.jsonl"
    rec = json.loads(p.read_text(encoding="utf-8").strip())
    assert rec["gen_ai.decision.final"] == "deny"
    assert rec["gen_ai.decision.final_reason"] == "gate3: blocked"


def test_audit_record_carries_sandbox_policy(tmp_path: Path):
    g = Gate6Audit(GateConfig(enabled=True, options={"audit_dir": str(tmp_path), "hash_algo": "sha256"}))
    ctx = _make_ctx()
    ctx.append(
        GateResult(
            gate_name="gate5_sandbox",
            decision=Decision.ALLOW,
            metadata={
                "sandbox_mode": "docker_gvisor",
                "sandbox_enforced": True,
                "docker_image": "xa-guard/sandbox:test",
                "runtime": "runsc",
            },
        )
    )

    g(ctx, GateStage.OUTBOUND)

    p = tmp_path / "audit.jsonl"
    rec = json.loads(p.read_text(encoding="utf-8").strip())
    assert rec["gen_ai.tool.sandbox.mode"] == "docker_gvisor"
    assert rec["gen_ai.tool.sandbox.enforced"] is True
    assert rec["gen_ai.tool.sandbox.image"] == "xa-guard/sandbox:test"
    assert rec["gen_ai.tool.sandbox.runtime"] == "runsc"


def test_gate6_outbound_stage_only(tmp_path: Path):
    """INBOUND 阶段不应写审计。"""
    g = Gate6Audit(GateConfig(enabled=True, options={"audit_dir": str(tmp_path), "hash_algo": "sha256"}))
    ctx = _make_ctx()
    r = g(ctx, GateStage.INBOUND)
    # base 会跳过非支持阶段
    assert "skipped" in r.note
    p = tmp_path / "audit.jsonl"
    assert not p.exists() or p.stat().st_size == 0
