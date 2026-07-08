"""Gate6Audit 单元测试 — 14 字段 / 链式 / fallback / 禁用。"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from xa_guard.audit.merkle import ChainStore, canonical_json
from xa_guard.audit.archive import verify_audit_signatures
from xa_guard.audit.sm_crypto import generate_sm2_keypair, sm2_verify, write_sm2_keyfile
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
    ctx.session_history = [{"model": "qwen-max"}]
    ctx.tool_result = tool_result if tool_result is not None else {"cpu": "30%"}
    ctx.append(
        GateResult(
            gate_name="gate1_input",
            decision=Decision.WARN,
            risks=["x"],
            rule_hits=["POLICY-1", "POLICY-2"],
            note="suspicious",
        )
    )
    return ctx


def _fake_external_signer(tmp_path: Path) -> list[str]:
    script = tmp_path / "fake_external_signer.py"
    script.write_text(
        """
import hashlib
import hmac
import json
import sys

request = json.loads(sys.stdin.read())
secret = b"fake-provider-secret"
payload = bytes.fromhex(request["payload_hex"])
expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
if request["operation"] == "sign":
    print(json.dumps({
        "signature": expected,
        "key_id": request["key_id"],
        "algorithm": request["algorithm"],
        "provider": request.get("provider", "fake-provider"),
    }))
elif request["operation"] == "verify":
    print(json.dumps({
        "valid": hmac.compare_digest(expected, request.get("signature", "")),
        "key_id": request["key_id"],
        "algorithm": request["algorithm"],
        "provider": request.get("provider", "fake-provider"),
    }))
else:
    raise SystemExit(2)
""".lstrip(),
        encoding="utf-8",
    )
    return [sys.executable, str(script)]


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



def test_gate6_faithfulness_detects_inconsistent_final_decision(tmp_path: Path):
    gate = Gate6Audit(
        GateConfig(enabled=True, options={"audit_dir": str(tmp_path), "hash_algo": "sha256"})
    )
    ctx = _make_ctx()
    ctx.final_decision = Decision.ALLOW
    ctx.final_reason = ""

    result = gate(ctx, GateStage.OUTBOUND)
    record = json.loads(Path(result.metadata["audit_path"]).read_text(encoding="utf-8"))
    assessment = result.metadata["faithfulness"]
    assert 0.0 <= assessment["score"] < 1.0
    assert assessment["algorithm"] == "xa-guard-decision-faithfulness/v1"
    assert assessment["evidence"]["expected_decision"] == "warn"
    assert assessment["evidence"]["components"]["decision_consistent"] is False
    assert record["gen_ai.decision.faithfulness_score"] == assessment["score"]
    assert record["gen_ai.decision.faithfulness.algorithm"] == assessment["algorithm"]



def test_gate6_chain_links_three_records(tmp_path: Path):
    g = Gate6Audit(GateConfig(enabled=True, options={"audit_dir": str(tmp_path), "hash_algo": "sha256"}))
    hashes = []
    for i in range(3):
        ctx = _make_ctx({"i": i})
        r = g(ctx, GateStage.OUTBOUND)
        hashes.append(r.metadata["record_hash"])

    p = Path(r.metadata["audit_path"])
    lines = p.read_text(encoding="utf-8").splitlines()
    recs = [json.loads(line) for line in lines]

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
    payload = canonical_json({key: value for key, value in rec.items() if key != "signature"})
    assert sm2_verify(payload, rec["signature"], "", prefer_gm=False)


def test_gate6_signed_concurrent_writers_preserve_every_record(tmp_path: Path):
    options = {
        "audit_dir": str(tmp_path),
        "hash_algo": "sha256",
        "enable_sm2_signature": True,
        "sm2_key_path": "",
    }
    gates = [Gate6Audit(GateConfig(enabled=True, options=options)) for _ in range(4)]

    def write(index: int) -> None:
        ctx = _make_ctx({"index": index})
        ctx.arguments = {"host": f"web-{index}"}
        gates[index % len(gates)](ctx, GateStage.OUTBOUND)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(write, range(40)))

    path = tmp_path / "audit.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 40
    assert len({record["trace_id"] for record in records}) == 40
    assert ChainStore(path).verify() == (True, None)
    for record in records:
        signature = record.pop("signature")
        assert sm2_verify(canonical_json(record), signature, "", prefer_gm=False)


def test_gate6_strict_sm2_records_algorithm_key_id_and_verifies(tmp_path: Path):
    private_hex, public_hex = generate_sm2_keypair()
    key_path = tmp_path / "sm2.key"
    write_sm2_keyfile(key_path, private_hex, public_hex)
    gate = Gate6Audit(
        GateConfig(
            enabled=True,
            options={
                "audit_dir": str(tmp_path),
                "hash_algo": "sm3",
                "signature_mode": "sm2",
                "sm2_key_path": str(key_path),
            },
        )
    )

    result = gate(_make_ctx(), GateStage.OUTBOUND)
    record = json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8"))
    assert result.metadata["signature"] == record["signature"]
    assert record["signature_algorithm"] == "SM2-SM3"
    assert len(record["signature_key_id"]) == 16
    verified = verify_audit_signatures(
        tmp_path / "audit.jsonl",
        mode="sm2",
        key_path=str(key_path),
    )
    assert verified["ok"] is True
    assert verified["record_count"] == 1


def test_gate6_strict_sm2_missing_key_fails_before_write(tmp_path: Path):
    gate = Gate6Audit(
        GateConfig(
            enabled=True,
            options={
                "audit_dir": str(tmp_path),
                "hash_algo": "sm3",
                "signature_mode": "sm2",
                "sm2_key_path": str(tmp_path / "missing.key"),
            },
        )
    )

    try:
        gate(_make_ctx(), GateStage.OUTBOUND)
    except ValueError as exc:
        assert "SM2" in str(exc)
    else:
        raise AssertionError("strict SM2 mode must reject a missing key")
    assert not (tmp_path / "audit.jsonl").exists()


def test_gate6_external_signature_mode_roundtrip_and_tamper_reject(tmp_path: Path):
    command = _fake_external_signer(tmp_path)
    gate = Gate6Audit(
        GateConfig(
            enabled=True,
            options={
                "audit_dir": str(tmp_path),
                "hash_algo": "sm3",
                "signature_mode": "external",
                "external_sign_command": command,
                "external_key_id": "fake-hsm-key-1",
                "external_algorithm": "EXTERNAL-HSM-SM2-SM3",
                "external_provider": "fake-provider",
            },
        )
    )

    result = gate(_make_ctx(), GateStage.OUTBOUND)
    record = json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8"))
    assert result.metadata["signature"] == record["signature"]
    assert record["signature_algorithm"] == "EXTERNAL-HSM-SM2-SM3"
    assert record["signature_key_id"] == "fake-hsm-key-1"
    assert record["signature_provider"] == "fake-provider"

    verified = verify_audit_signatures(
        tmp_path / "audit.jsonl",
        mode="external",
        external_verify_command=command,
        external_key_id="fake-hsm-key-1",
        external_algorithm="EXTERNAL-HSM-SM2-SM3",
        external_provider="fake-provider",
    )
    assert verified["ok"] is True

    record["signature"] = "0" * 64
    (tmp_path / "audit.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    tampered = verify_audit_signatures(
        tmp_path / "audit.jsonl",
        mode="external",
        external_verify_command=command,
        external_key_id="fake-hsm-key-1",
        external_algorithm="EXTERNAL-HSM-SM2-SM3",
        external_provider="fake-provider",
    )
    assert tampered["ok"] is False


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
