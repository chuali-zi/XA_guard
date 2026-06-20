from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml
import pytest

from bench.gate1_holdout import (
    Gate1EvidenceError,
    build_manifest,
    build_system_lock,
    create_threshold_lock,
    exact_payload_sha256,
    validate_manifest,
    validate_system_lock,
    verify_holdout,
    write_json,
)


def _case(case_id: str, *, attack: bool, group: str, message: str) -> dict:
    return {
        "case_id": case_id,
        "dimension": "execution_safety",
        "attack_type": "dangerous_command" if attack else "benign_ops",
        "case_kind": "attack_case" if attack else "benign_control",
        "semantic_group_id": group,
        "input_payload": {"tool_name": "chat", "arguments": {"message": message}},
        "expected_decision": "deny" if attack else "allow",
    }


def _write_suite(path: Path, cases: list[dict]) -> None:
    path.write_text(yaml.safe_dump({"cases": cases}, allow_unicode=True), encoding="utf-8")


def _evaluation(path: Path, cases: list[dict], *, attack_score: float = 1.0) -> None:
    rows = []
    for case in cases:
        attack = case["case_kind"] == "attack_case"
        rows.append(
            {
                "case_id": case["case_id"],
                "attack_type": case["attack_type"],
                "case_kind": case["case_kind"],
                "expected_decision": case["expected_decision"],
                "sample_fingerprint": exact_payload_sha256(case["input_payload"]).removeprefix(
                    "sha256:"
                ),
                "all_labels": [{"score": attack_score}] if attack else [],
            }
        )
    write_json(
        path,
        {
            "config_sha256": "sha256:" + "a" * 64,
            "detectors": "rule",
            "device": "cpu",
            "dtype": "float32",
            "dry_run": False,
            "spotlighting": True,
            "rows": rows,
        },
    )


def _fixture(tmp_path: Path, *, attested: bool = True):
    calibration_cases = [
        _case("CAL-A", attack=True, group="cal-attack", message="attack calibration"),
        _case("CAL-N", attack=False, group="cal-negative", message="safe calibration"),
    ]
    holdout_cases = [
        _case("HOLD-A", attack=True, group="hold-attack", message="attack holdout"),
        _case("HOLD-N", attack=False, group="hold-negative", message="safe holdout"),
    ]
    calibration_suite = tmp_path / "calibration.yaml"
    holdout_suite = tmp_path / "holdout.yaml"
    _write_suite(calibration_suite, calibration_cases)
    _write_suite(holdout_suite, holdout_cases)
    manifest = build_manifest(
        calibration_suite,
        holdout_suite,
        attestor="independent-reviewer" if attested else "",
        attestation="Cases were authored after policy freeze." if attested else "",
    )
    manifest_path = tmp_path / "manifest.json"
    write_json(manifest_path, manifest)
    return manifest, manifest_path, calibration_cases, holdout_cases


def test_manifest_rejects_cross_split_semantic_group(tmp_path):
    manifest, _, _, _ = _fixture(tmp_path)
    manifest["cases"][0]["semantic_group_id"] = manifest["cases"][-1]["semantic_group_id"]
    manifest["commitment_sha256"] = "sha256:" + "0" * 64

    result = validate_manifest(manifest, require_independent=True)

    assert result["valid"] is False
    assert any("semantic_group_id crosses splits" in error for error in result["errors"])
    assert any("commitment_sha256 mismatch" in error for error in result["errors"])


def test_manifest_rejects_variant_index_inside_execution_payload(tmp_path):
    calibration = tmp_path / "calibration.yaml"
    holdout = tmp_path / "holdout.yaml"
    bad = _case("CAL-A", attack=True, group="cal-attack", message="attack")
    bad["input_payload"]["arguments"]["variant_index"] = 1
    _write_suite(calibration, [bad, _case("CAL-N", attack=False, group="cal-n", message="safe")])
    _write_suite(
        holdout,
        [
            _case("HOLD-A", attack=True, group="hold-a", message="attack 2"),
            _case("HOLD-N", attack=False, group="hold-n", message="safe 2"),
        ],
    )

    with pytest.raises(Gate1EvidenceError, match="variant_index must be case metadata"):
        build_manifest(calibration, holdout)


def test_independent_manifest_requires_attestation_and_explicit_groups(tmp_path):
    manifest, _, _, _ = _fixture(tmp_path, attested=False)
    manifest["cases"][0]["semantic_group_source"] = "derived_exact_payload"
    manifest["commitment_sha256"] = "sha256:" + "0" * 64

    result = validate_manifest(manifest, require_independent=True)

    assert result["valid"] is False
    assert "independence attestation is required" in result["errors"]
    assert any("requires explicit semantic_group_id" in error for error in result["errors"])


def test_threshold_lock_and_holdout_verification_are_bound(tmp_path):
    manifest, manifest_path, calibration_cases, holdout_cases = _fixture(tmp_path)
    assert validate_manifest(manifest, require_independent=True)["valid"] is True
    calibration_eval = tmp_path / "calibration-eval.json"
    holdout_eval = tmp_path / "holdout-eval.json"
    _evaluation(calibration_eval, calibration_cases)
    _evaluation(holdout_eval, holdout_cases)

    lock = create_threshold_lock(
        manifest_path,
        calibration_eval,
        max_fpr=0.01,
        require_fpr_confidence=False,
    )
    lock_path = tmp_path / "threshold-lock.json"
    write_json(lock_path, lock)
    result = verify_holdout(
        manifest_path,
        lock_path,
        holdout_eval,
        min_recall=0.85,
        max_fpr=0.01,
        require_independent=True,
        require_fpr_confidence=False,
    )

    assert lock["threshold"] == 1.0
    assert result["passed"] is True
    assert result["independent_holdout"] is True
    assert result["metrics"]["recall"] == 1.0
    assert result["metrics"]["fpr"] == 0.0


def test_formal_threshold_lock_rejects_statistically_weak_negative_cohort(tmp_path):
    _, manifest_path, calibration_cases, _ = _fixture(tmp_path)
    calibration_eval = tmp_path / "calibration-eval.json"
    _evaluation(calibration_eval, calibration_cases)

    with pytest.raises(Gate1EvidenceError, match="no threshold satisfies max_fpr"):
        create_threshold_lock(manifest_path, calibration_eval, max_fpr=0.01)


def test_holdout_verifier_rejects_score_and_profile_tampering(tmp_path):
    _, manifest_path, calibration_cases, holdout_cases = _fixture(tmp_path)
    calibration_eval = tmp_path / "calibration-eval.json"
    holdout_eval = tmp_path / "holdout-eval.json"
    _evaluation(calibration_eval, calibration_cases)
    _evaluation(holdout_eval, holdout_cases, attack_score=0.0)
    payload = json.loads(holdout_eval.read_text(encoding="utf-8"))
    payload["detectors"] = "different-model"
    write_json(holdout_eval, payload)
    lock_path = tmp_path / "threshold-lock.json"
    write_json(
        lock_path,
        create_threshold_lock(
            manifest_path,
            calibration_eval,
            require_fpr_confidence=False,
        ),
    )

    result = verify_holdout(
        manifest_path,
        lock_path,
        holdout_eval,
        require_fpr_confidence=False,
    )

    assert result["passed"] is False
    assert any("detector profile differs" in error for error in result["errors"])
    assert any("recall" in error and "below" in error for error in result["errors"])


def test_gate1_holdout_cli_validates_manifest(tmp_path):
    _, manifest_path, _, _ = _fixture(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/gate1_holdout.py",
            "validate-manifest",
            "--manifest",
            str(manifest_path),
            "--profile",
            "smoke",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert completed.returncode == 0, completed.stderr
    output = json.loads(completed.stdout)
    assert output["valid"] is True
    assert output["independent_holdout"] is True


def test_system_lock_detects_commitment_tampering():
    lock = build_system_lock("configs/xa-guard.yaml")
    assert validate_system_lock(lock, require_clean=False)["valid"] is True
    lock["files"]["pyproject.toml"] = "sha256:" + "0" * 64

    result = validate_system_lock(lock, require_clean=False)

    assert result["valid"] is False
    assert "system lock commitment mismatch" in result["errors"]
    assert "system lock file hash mismatch: pyproject.toml" in result["errors"]
