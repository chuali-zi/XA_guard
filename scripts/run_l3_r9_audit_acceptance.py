"""Run L3 R9 audit, SM2/SM3, TSA, and optional HSM/TSA acceptance evidence.

Local SM3/SM2/TSA evidence is fully verified. Third-party TSA and HSM/KMS are
checked only when operator-provided environment variables are present:

  XA_GUARD_EXTERNAL_TSA_URL
  XA_GUARD_EXTERNAL_SIGN_CMD
  XA_GUARD_EXTERNAL_VERIFY_CMD
  XA_GUARD_EXTERNAL_KEY_ID

Without those variables the report marks the external items BLOCKED. Use
--require-external to make missing third-party provider evidence a non-zero
acceptance failure.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from xa_guard.audit.archive import verify_audit_jsonl, verify_audit_signatures
from xa_guard.audit.sm_crypto import generate_sm2_keypair, write_sm2_keyfile
from xa_guard.audit.tsa import create_file_anchor, verify_file_anchor
from xa_guard.audit.tsa_client import verify_timestamp_token
from xa_guard.config import GateConfig
from xa_guard.gates.base import GateStage
from xa_guard.gates.gate6_audit import Gate6Audit
from xa_guard.types import Decision, GateContext, GateResult, TaintLabel


def _sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _hash_manifest(out_dir: Path) -> None:
    artifacts = []
    for path in sorted(out_dir.rglob("*")):
        if path.is_file() and path.name != "artifact-hashes.json":
            artifacts.append({"path": str(path.relative_to(out_dir)), "bytes": path.stat().st_size, "sha256": _sha256(path)})
    (out_dir / "artifact-hashes.json").write_text(
        json.dumps({"schema_version": "xa-artifact-hashes/v1", "artifacts": artifacts}, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _sm2_key(path: Path) -> Path:
    private_hex, public_hex = generate_sm2_keypair()
    write_sm2_keyfile(path, private_hex, public_hex)
    return path


def _ctx(index: int, *, inconsistent: bool = False) -> GateContext:
    ctx = GateContext(
        tool_name="audit_acceptance_tool",
        arguments={"case": index},
        user_role="ops",
        session_history=[{"model": "acceptance-offline"}],
    )
    ctx.taint = TaintLabel.INTERNAL
    ctx.tool_result = {"ok": True, "case": index}
    if inconsistent:
        ctx.append(
            GateResult(
                gate_name="gate3_policy",
                decision=Decision.WARN,
                risks=["acceptance warning"],
                rule_hits=["R9-FAITHFULNESS-WARN"],
                note="warned",
            )
        )
        ctx.final_decision = Decision.ALLOW
        ctx.final_reason = ""
    else:
        ctx.append(
            GateResult(
                gate_name="gate3_policy",
                decision=Decision.ALLOW,
                rule_hits=["R9-ALLOW"],
            )
        )
    return ctx


def _write_sm2_audit(out_dir: Path, key_path: Path) -> Path:
    audit_dir = out_dir / "audit-sm2"
    gate = Gate6Audit(
        GateConfig(
            enabled=True,
            options={
                "audit_dir": str(audit_dir),
                "hash_algo": "sm3",
                "signature_mode": "sm2",
                "sm2_key_path": str(key_path),
            },
        )
    )
    gate(_ctx(1), GateStage.OUTBOUND)
    gate(_ctx(2), GateStage.OUTBOUND)
    gate(_ctx(3, inconsistent=True), GateStage.OUTBOUND)
    return audit_dir / "audit.jsonl"


def _tamper_checks(audit_path: Path, anchor_path: Path, token_path: Path, key_path: Path, out_dir: Path) -> dict[str, Any]:
    tampered_audit = out_dir / "tampered-audit.jsonl"
    shutil.copyfile(audit_path, tampered_audit)
    records = [json.loads(line) for line in tampered_audit.read_text(encoding="utf-8").splitlines() if line.strip()]
    records[0]["gen_ai.tool.name"] = "tampered"
    tampered_audit.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n", encoding="utf-8")

    tampered_signature = out_dir / "tampered-signature.jsonl"
    shutil.copyfile(audit_path, tampered_signature)
    records = [json.loads(line) for line in tampered_signature.read_text(encoding="utf-8").splitlines() if line.strip()]
    records[0]["signature"] = "0" * 128
    tampered_signature.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )

    tampered_anchor = out_dir / "tampered-anchor.json"
    anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
    anchor["anchor_hash"] = "0" * len(str(anchor["anchor_hash"]))
    tampered_anchor.write_text(json.dumps(anchor, ensure_ascii=False, indent=2), encoding="utf-8")

    checks: dict[str, Any] = {
        "audit_tamper_rejected": not verify_audit_jsonl(tampered_audit, algo="sm3")["ok"],
        "signature_tamper_rejected": not verify_audit_signatures(
            tampered_signature,
            mode="sm2",
            key_path=str(key_path),
        )["ok"],
        "tsa_token_wrong_anchor_rejected": not verify_timestamp_token(
            token_path,
            tsa_pub_path=str(key_path),
            anchor_hash="f" * 64,
            prefer_gm=True,
        ),
    }
    try:
        verify_file_anchor(audit_path, tampered_anchor, algo="sm3", verify_index=True)
    except Exception:
        checks["anchor_tamper_rejected"] = True
    else:
        checks["anchor_tamper_rejected"] = False
    return checks


def _external_hsm_check(out_dir: Path) -> dict[str, Any]:
    sign_cmd = os.getenv("XA_GUARD_EXTERNAL_SIGN_CMD", "").strip()
    verify_cmd = os.getenv("XA_GUARD_EXTERNAL_VERIFY_CMD", "").strip()
    key_id = os.getenv("XA_GUARD_EXTERNAL_KEY_ID", "").strip()
    provider = os.getenv("XA_GUARD_EXTERNAL_PROVIDER", "operator-external-provider").strip()
    algorithm = os.getenv("XA_GUARD_EXTERNAL_ALGORITHM", "EXTERNAL-HSM-SM2-SM3").strip()
    if not sign_cmd or not verify_cmd or not key_id:
        return {
            "status": "blocked",
            "reason": "XA_GUARD_EXTERNAL_SIGN_CMD, XA_GUARD_EXTERNAL_VERIFY_CMD, and XA_GUARD_EXTERNAL_KEY_ID are required",
        }

    audit_dir = out_dir / "audit-external"
    try:
        gate = Gate6Audit(
            GateConfig(
                enabled=True,
                options={
                    "audit_dir": str(audit_dir),
                    "hash_algo": "sm3",
                    "signature_mode": "external",
                    "external_sign_command": sign_cmd,
                    "external_key_id": key_id,
                    "external_algorithm": algorithm,
                    "external_provider": provider,
                },
            )
        )
        gate(_ctx(9), GateStage.OUTBOUND)
        result = verify_audit_signatures(
            audit_dir / "audit.jsonl",
            mode="external",
            external_verify_command=verify_cmd,
            external_key_id=key_id,
            external_algorithm=algorithm,
            external_provider=provider,
        )
    except Exception as exc:
        return {"status": "fail", "error": f"{type(exc).__name__}: {exc}"}
    return {"status": "pass" if result["ok"] else "fail", "verify": result}


def run(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    key_path = _sm2_key(out_dir / "sm2-audit.key")
    tsa_key_path = _sm2_key(out_dir / "sm2-tsa.key")
    audit_path = _write_sm2_audit(out_dir, key_path)

    chain = verify_audit_jsonl(audit_path, algo="sm3")
    signatures = verify_audit_signatures(audit_path, mode="sm2", key_path=str(key_path))

    token_path = out_dir / "audit.tsa.token.json"
    external_tsa_url = os.getenv("XA_GUARD_EXTERNAL_TSA_URL", "").strip() or None
    anchor = create_file_anchor(
        audit_path,
        anchor_path=out_dir / "audit.anchor.json",
        index_path=out_dir / "anchor-index.jsonl",
        algo="sm3",
        tsa_key_path=str(tsa_key_path),
        tsa_token_path=token_path,
        external_tsa_url=external_tsa_url,
    )
    anchor_verified = False
    token_verified = False
    anchor_error = ""
    try:
        verify_file_anchor(audit_path, anchor.anchor_path, algo="sm3", verify_index=True)
        anchor_verified = True
        token_verified = verify_timestamp_token(
            token_path,
            tsa_pub_path=str(tsa_key_path),
            anchor_hash=anchor.manifest["anchor_hash"],
            prefer_gm=True,
        )
    except Exception as exc:
        anchor_error = f"{type(exc).__name__}: {exc}"

    records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    faithfulness_scores = [record.get("gen_ai.decision.faithfulness_score") for record in records]
    tamper = _tamper_checks(audit_path, anchor.anchor_path, token_path, tsa_key_path, out_dir)

    token = json.loads(token_path.read_text(encoding="utf-8"))
    external_tsa = token.get("external_tsa") if external_tsa_url else None
    external_tsa_status = (
        "pass"
        if isinstance(external_tsa, dict) and external_tsa.get("status") == "pass"
        else "fail"
        if external_tsa_url
        else "blocked"
    )
    external_hsm = _external_hsm_check(out_dir)

    local_expectations = {
        "sm3_chain_ok": chain["ok"],
        "sm2_signatures_ok": signatures["ok"],
        "anchor_verified": anchor_verified,
        "sm2_tsa_token_verified": token_verified,
        "faithfulness_has_non_fixed_score": any(isinstance(score, (int, float)) and score < 1.0 for score in faithfulness_scores),
        **tamper,
    }
    local_pass = all(local_expectations.values())
    external_complete = external_tsa_status == "pass" and external_hsm.get("status") == "pass"
    status = "pass" if local_pass and external_complete else "limit" if local_pass else "fail"
    if args.require_external and not external_complete and local_pass:
        status = "fail"

    report: dict[str, Any] = {
        "schema_version": "xa-l3-r9-audit-acceptance/v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "local_evidence": {
            "audit_path": str(audit_path),
            "chain": chain,
            "signatures": signatures,
            "anchor_path": str(anchor.anchor_path),
            "anchor_verified": anchor_verified,
            "anchor_error": anchor_error,
            "tsa_token_path": str(token_path),
            "tsa_token_verified": token_verified,
            "faithfulness_scores": faithfulness_scores,
            "tamper_checks": tamper,
        },
        "external_tsa": {
            "status": external_tsa_status,
            "url_configured": bool(external_tsa_url),
            "result": external_tsa,
        },
        "external_hsm": external_hsm,
        "boundary": {
            "third_party_tsa_and_hsm_required_for_final_r9_pass": True,
            "local_tsa_and_software_sm2_key_claim": "demo_ci_only",
        },
        "expectations": local_expectations,
    }
    report_path = out_dir / "r9-audit-acceptance-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    _hash_manifest(out_dir)
    print(json.dumps({"status": status, "report": str(report_path)}, ensure_ascii=False, indent=2))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--require-external", action="store_true")
    args = parser.parse_args()
    report = run(args)
    return 0 if report["status"] in {"pass", "limit"} and not args.require_external else 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
