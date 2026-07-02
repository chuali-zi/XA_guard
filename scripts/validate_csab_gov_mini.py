"""Validate bench/cases/csab-gov-mini-seed.yaml as a trustworthy evaluation asset.

Checks:
  - Required fields per case (case_kind, source_documents, severity, …).
  - Enum / regex validity (case_id, expected_decision, dimension, …).
  - Unique case_id and unique fingerprint (no silent duplicates).
  - case_kind ↔ attack_type consistency (benign_* ↔ benign_control etc.).
  - policy_refs whitelist drawn from policies/baseline/gate3_rules.yaml.
  - Coverage report by dimension / case_kind / attack_type / source.
  - Metadata.total matches len(cases) and dimension counts.

Exit code is non-zero on any structural failure.  Coverage gaps surface as
warnings (printed but not blocking) so the asset can grow incrementally.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUITE = ROOT / "bench" / "cases" / "csab-gov-mini-seed.yaml"
DEFAULT_POLICIES = ROOT / "policies" / "baseline" / "gate3_rules.yaml"
DEFAULT_REPORT = ROOT / "bench" / ".log" / "coverage.md"

DIMENSIONS = {
    "execution_safety",
    "data_safety",
    "content_safety",
    "supply_chain",
    "compliance",
    "interpretability",
    "traceability",
}
DECISIONS = {"allow", "warn", "deny", "require_approval"}
SEVERITIES = {"low", "medium", "high", "critical"}
CASE_KINDS = {"attack_case", "benign_control", "assurance_check", "exploratory_finding"}
CASE_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]*-[0-9]{3,4}$")

# Refs we accept even when not present in policies/baseline/gate3_rules.yaml.
# Drawn from the official standards bench cases cite directly (clause-level
# refs that map to inline sub-rules rather than top-level rule IDs).
EXTRA_ALLOWED_POLICY_REFS = {
    "TC260-003-7.2",
    "TC260-003-9.4",
    "GBT-22239-8.1.3.1",
    "GBT-22239-8.1.4.2",
    "GBT-22239-8.1.4.4",
    "GBT-22239-8.1.4.5",
    "GBT-45654-A.1.1",
    "GBT-45654-A.2.3",
    "GBT-45654-A.3.2",
    "GBT-45654-A.4.1",
}


def _load_policy_refs(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    refs = {r.get("id") for r in data.get("rules", []) if r.get("id")}
    refs.update(EXTRA_ALLOWED_POLICY_REFS)
    return refs


class Validator:
    def __init__(self, suite: dict[str, Any], allowed_policy_refs: set[str]):
        self.suite = suite
        self.cases: list[dict[str, Any]] = list(suite.get("cases", []) or [])
        self.allowed_policy_refs = allowed_policy_refs
        self.errors: list[str] = []
        self.warnings: list[str] = []

    # ------------------------------------------------------------------
    # structural checks
    def _check_case(self, idx: int, case: dict[str, Any]) -> None:
        cid = case.get("case_id", f"#{idx}")
        required = [
            "case_id", "dimension", "attack_type", "case_kind",
            "input_payload", "expected_decision", "severity",
            "source_documents", "note",
        ]
        for field in required:
            if field not in case:
                self.errors.append(f"{cid}: missing required field `{field}`")

        if "case_id" in case and not CASE_ID_RE.match(str(case["case_id"])):
            self.errors.append(f"{cid}: case_id must match {CASE_ID_RE.pattern}")

        if case.get("dimension") not in DIMENSIONS:
            self.errors.append(f"{cid}: dimension `{case.get('dimension')}` not allowed")

        if case.get("expected_decision") not in DECISIONS:
            self.errors.append(
                f"{cid}: expected_decision `{case.get('expected_decision')}` not in {sorted(DECISIONS)}"
            )

        if case.get("severity") not in SEVERITIES:
            self.errors.append(f"{cid}: severity `{case.get('severity')}` not allowed")

        ck = case.get("case_kind")
        if ck not in CASE_KINDS:
            self.errors.append(f"{cid}: case_kind `{ck}` not allowed")

        atype = case.get("attack_type", "")
        if ck == "benign_control" and not atype.startswith("benign_"):
            self.errors.append(
                f"{cid}: case_kind=benign_control but attack_type=`{atype}` does not start with benign_"
            )
        if ck == "attack_case" and atype.startswith("benign_"):
            self.errors.append(
                f"{cid}: case_kind=attack_case but attack_type starts with benign_ — pick benign_control"
            )

        docs = case.get("source_documents") or []
        if not isinstance(docs, list) or not docs:
            self.errors.append(f"{cid}: source_documents must be a non-empty list")
        else:
            for doc in docs:
                if not isinstance(doc, dict) or not doc.get("standard"):
                    self.errors.append(f"{cid}: source_documents entry missing `standard`")

        for ref in case.get("policy_refs", []) or []:
            if ref not in self.allowed_policy_refs:
                self.warnings.append(
                    f"{cid}: policy_ref `{ref}` not present in policies/baseline/gate3_rules.yaml — "
                    "either add the rule or move the ref into EXTRA_ALLOWED_POLICY_REFS."
                )

        payload = case.get("input_payload", {})
        if not isinstance(payload, dict) or not payload.get("tool_name"):
            self.errors.append(f"{cid}: input_payload.tool_name is required")

    def _check_uniqueness(self) -> None:
        by_id: dict[str, int] = defaultdict(int)
        by_fp: dict[str, list[str]] = defaultdict(list)
        for case in self.cases:
            cid = case.get("case_id")
            if cid:
                by_id[cid] += 1
            fp = case.get("fingerprint")
            if fp:
                by_fp[fp].append(cid or "<unknown>")

        for cid, n in by_id.items():
            if n > 1:
                self.errors.append(f"duplicate case_id `{cid}` appears {n} times")

        # Fingerprint clashes mean the YAML pays the storage cost of 290 cases
        # while exercising fewer distinct payloads.  Surfaced as warnings so the
        # asset stays usable; --strict turns them into hard errors.
        for fp, ids in by_fp.items():
            if len(ids) > 1:
                self.warnings.append(
                    f"duplicate fingerprint `{fp}` shared by {ids} — payload effectively repeats."
                )

    def _check_metadata(self) -> None:
        meta = self.suite.get("metadata", {}) or {}
        if meta.get("total") != len(self.cases):
            self.errors.append(
                f"metadata.total={meta.get('total')} but len(cases)={len(self.cases)}"
            )

        declared = meta.get("dimensions", {}) or {}
        actual = Counter(c.get("dimension", "") for c in self.cases)
        for dim, expected in declared.items():
            if actual.get(dim, 0) != expected:
                self.errors.append(
                    f"metadata.dimensions[{dim}]={expected} but actual={actual.get(dim, 0)}"
                )

    # ------------------------------------------------------------------
    def run(self) -> tuple[list[str], list[str]]:
        for idx, case in enumerate(self.cases):
            self._check_case(idx, case)
        self._check_uniqueness()
        self._check_metadata()
        return self.errors, self.warnings


def coverage_report(suite: dict[str, Any]) -> str:
    cases = suite.get("cases", []) or []
    lines: list[str] = []
    lines.append("# CSAB-Gov-mini coverage report")
    lines.append("")
    lines.append(f"Total cases: **{len(cases)}**")
    distinct_fps = {c.get("fingerprint") for c in cases if c.get("fingerprint")}
    lines.append(f"Distinct fingerprints: **{len(distinct_fps)}**  ")
    dup_count = len(cases) - len(distinct_fps)
    if dup_count:
        lines.append(
            f"_({dup_count} case(s) share a fingerprint with another — see `--strict` to fail on this.)_"
        )
    lines.append("")

    lines.append("## By dimension")
    by_dim = Counter(c.get("dimension", "?") for c in cases)
    for dim in sorted(by_dim):
        lines.append(f"- {dim}: {by_dim[dim]}")
    lines.append("")

    lines.append("## By case_kind")
    by_kind = Counter(c.get("case_kind", "?") for c in cases)
    for kind in sorted(by_kind):
        lines.append(f"- {kind}: {by_kind[kind]}")
    lines.append("")

    lines.append("## By expected_decision")
    by_dec = Counter(c.get("expected_decision", "?") for c in cases)
    for dec in sorted(by_dec):
        lines.append(f"- {dec}: {by_dec[dec]}")
    lines.append("")

    lines.append("## By dimension × attack_type")
    matrix: dict[str, Counter] = defaultdict(Counter)
    for c in cases:
        matrix[c.get("dimension", "?")][c.get("attack_type", "?")] += 1
    for dim in sorted(matrix):
        lines.append(f"### {dim}")
        for at in sorted(matrix[dim]):
            lines.append(f"- {at}: {matrix[dim][at]}")
        lines.append("")

    lines.append("## Standards cited")
    standards = Counter()
    for c in cases:
        for doc in c.get("source_documents", []) or []:
            standards[doc.get("standard", "?")] += 1
    for std in sorted(standards):
        lines.append(f"- {std}: {standards[std]} citations")
    lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--policies", type=Path, default=DEFAULT_POLICIES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT,
                        help="Markdown coverage report destination.")
    parser.add_argument("--strict", action="store_true",
                        help="Treat warnings as errors.")
    parser.add_argument("--json", action="store_true",
                        help="Emit machine-readable JSON summary on stdout.")
    args = parser.parse_args()

    if not args.suite.exists():
        print(f"[validate] suite not found: {args.suite}", file=sys.stderr)
        return 2

    suite = yaml.safe_load(args.suite.read_text(encoding="utf-8")) or {}
    allowed = _load_policy_refs(args.policies)
    validator = Validator(suite, allowed)
    errors, warnings = validator.run()

    report = coverage_report(suite)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")

    summary = {
        "suite": str(args.suite),
        "cases": len(suite.get("cases", []) or []),
        "errors": errors,
        "warnings": warnings,
        "coverage_report": str(args.report),
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        for err in errors:
            print(f"[ERROR] {err}")
        for warn in warnings:
            print(f"[warn]  {warn}")
        print(f"[validate] cases={summary['cases']} errors={len(errors)} warnings={len(warnings)}")
        print(f"[validate] coverage report -> {args.report}")

    if errors:
        return 1
    if args.strict and warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
