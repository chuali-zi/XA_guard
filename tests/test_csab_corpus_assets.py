"""Tests for the auditable GB/T 45654 corpus contract."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from bench.corpus import (
    NORMALIZATION_VERSION,
    SCHEMA_VERSION,
    canonical_payload,
    file_sha256,
    manifest_commitment,
    payload_sha256,
    validate_corpus,
)

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "bench" / "cases" / "csab-gov-v1-candidate"


def test_payload_normalization_is_stable_and_drops_non_semantic_fields():
    left = {
        "arguments": {"text": "Cafe\u0301\r\nline", "variant_index": 1},
        "tool_name": "answer_question",
        "case_id": "LEFT",
    }
    right = {
        "tool_name": "answer_question",
        "arguments": {"text": "Caf\u00e9\nline", "variant_index": 99},
        "note": "not executable",
    }
    assert canonical_payload(left) == canonical_payload(right)
    assert payload_sha256(left) == payload_sha256(right)


def test_candidate_asset_is_hash_bound_and_has_500_unique_non_refusals():
    result = validate_corpus(CORPUS, profile="candidate")
    assert result.valid, result.errors
    assert result.counts["cohorts"] == {"non_refusal": 500}
    assert result.counts["normalized_payloads_unique"] == 500
    assert result.counts["semantic_groups"] == 500
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["normalization_version"] == NORMALIZATION_VERSION
    assert manifest["commitment_sha256"] == manifest_commitment(manifest)
    assert manifest["sources"][0]["license_id"] == "MIT"
    assert manifest["sources"][0]["version"] == "5be00913f99e24965378b557f1f0ecb7443caba3"


def test_candidate_is_not_misrepresented_as_formal_corpus():
    result = validate_corpus(CORPUS, profile="formal")
    assert not result.valid
    assert "formal profile requires at least 500 refusal cases" in result.errors
    assert "formal profile requires a hash-bound independent evaluator attestation" in result.errors
    assert "formal profile requires exactly 17 refusal taxonomy categories" in result.errors


def test_artifact_tampering_is_detected(tmp_path: Path):
    target = tmp_path / "corpus"
    shutil.copytree(CORPUS, target)
    artifact = target / "non-refusal.jsonl"
    artifact.write_text(artifact.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
    result = validate_corpus(target, profile="candidate")
    assert not result.valid
    assert any("sha256 mismatch" in error for error in result.errors)


def test_duplicate_normalized_payload_is_detected_even_with_new_case_id(tmp_path: Path):
    target = tmp_path / "corpus"
    shutil.copytree(CORPUS, target)
    artifact = target / "non-refusal.jsonl"
    lines = artifact.read_text(encoding="utf-8").splitlines()
    duplicate = json.loads(lines[0])
    duplicate["case_id"] = "CSQA-NR-DUPLICATE"
    duplicate["semantic_group_id"] = "manually-renamed-group"
    lines.append(json.dumps(duplicate, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    artifact.write_text("\n".join(lines) + "\n", encoding="utf-8")

    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][0]["case_count"] += 1
    manifest["artifacts"][0]["sha256"] = file_sha256(artifact)
    manifest["commitment_sha256"] = manifest_commitment(manifest)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = validate_corpus(target, profile="candidate")
    assert not result.valid
    assert any("duplicate normalized payload" in error for error in result.errors)


def test_manifest_and_license_tampering_are_detected(tmp_path: Path):
    target = tmp_path / "corpus"
    shutil.copytree(CORPUS, target)
    license_path = target / "THIRD_PARTY_LICENSE.ChineseSafetyQA.txt"
    license_path.write_text("changed", encoding="utf-8")
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["claim_scope"] = "overstated"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    result = validate_corpus(target, profile="candidate")
    assert not result.valid
    assert "manifest commitment_sha256 mismatch" in result.errors
    assert any("license_sha256 mismatch" in error for error in result.errors)

