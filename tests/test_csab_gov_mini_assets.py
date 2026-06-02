"""Guardrails for bench/cases/csab-gov-mini-seed.yaml.

These tests make the 290-case YAML maintainable as it grows:
  - Each case carries `case_kind` + `source_documents` so an auditor can
    trace citations back to GB/T 22239-2019 / GB/T 45654-2025 / TC260-003.
  - Enrichment is idempotent — re-running the generator script does not
    silently mutate the on-disk YAML.
  - The validator script returns zero errors and zero warnings.
  - Metadata totals match the actual case list.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "bench" / "cases" / "csab-gov-mini-seed.yaml"
ENRICH = ROOT / "scripts" / "enrich_csab_gov_mini.py"
VALIDATE = ROOT / "scripts" / "validate_csab_gov_mini.py"


def _load_suite() -> dict:
    return yaml.safe_load(SUITE.read_text(encoding="utf-8")) or {}


def test_every_case_has_case_kind_and_sources():
    suite = _load_suite()
    cases = suite["cases"]
    assert len(cases) == 290, f"expected 290 cases, found {len(cases)}"

    allowed_kinds = {"attack_case", "benign_control", "assurance_check", "exploratory_finding"}
    for case in cases:
        cid = case.get("case_id", "?")
        assert case.get("case_kind") in allowed_kinds, f"{cid}: bad case_kind"
        docs = case.get("source_documents") or []
        assert docs, f"{cid}: missing source_documents"
        for doc in docs:
            assert doc.get("standard"), f"{cid}: source_documents entry missing `standard`"


def test_case_kind_matches_attack_type_prefix():
    for case in _load_suite()["cases"]:
        cid = case["case_id"]
        atype = case["attack_type"]
        if atype.startswith("benign_"):
            assert case["case_kind"] == "benign_control", f"{cid}: benign_* should map to benign_control"


def test_fingerprints_are_unique():
    cases = _load_suite()["cases"]
    fingerprints = [c.get("fingerprint") for c in cases]
    assert all(fingerprints), "every case must carry a fingerprint"
    assert len(set(fingerprints)) == len(fingerprints), \
        "duplicate fingerprints — run scripts/enrich_csab_gov_mini.py to decollide"


def test_case_ids_are_unique():
    ids = [c["case_id"] for c in _load_suite()["cases"]]
    assert len(set(ids)) == len(ids), "duplicate case_id"


def test_metadata_totals_match():
    suite = _load_suite()
    meta = suite["metadata"]
    cases = suite["cases"]
    assert meta["total"] == len(cases)

    from collections import Counter
    actual = Counter(c["dimension"] for c in cases)
    for dim, expected in meta["dimensions"].items():
        assert actual[dim] == expected, f"dimension count mismatch for {dim}"


def test_enrichment_is_idempotent():
    """Running enrich --check must succeed on a freshly enriched YAML."""
    result = subprocess.run(
        [sys.executable, str(ENRICH), "--check"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"enrich --check failed: {result.stdout}\n{result.stderr}"


def test_validator_passes_strict():
    """Validator must return zero errors AND zero warnings (--strict)."""
    result = subprocess.run(
        [sys.executable, str(VALIDATE), "--strict"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"validator --strict failed:\n{result.stdout}\n{result.stderr}"
