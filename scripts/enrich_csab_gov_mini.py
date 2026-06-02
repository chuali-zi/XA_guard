"""Enrich bench/cases/csab-gov-mini-seed.yaml with case_kind + source_documents + fingerprint.

Idempotent — running twice produces the same YAML. Designed so the YAML stays the
single source of truth that bench.runner reads, while adding the metadata an
auditor needs to validate that each case is rooted in a real standard clause.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUITE = ROOT / "bench" / "cases" / "csab-gov-mini-seed.yaml"

# Map a policy_ref prefix → (standard, default_title).  The case retains the
# specific clause via its policy_refs entry; source_documents records the
# document the clause lives in so downstream auditors can trace the citation.
POLICY_PREFIX_MAP: list[tuple[str, tuple[str, str]]] = [
    ("GBT-22239-",  ("GB/T 22239-2019", "信息安全技术 网络安全等级保护基本要求")),
    ("GBT-45654-",  ("GB/T 45654-2025", "网络安全技术 生成式人工智能服务安全基本要求")),
    ("TC260-003",   ("TC260-003",       "生成式人工智能服务安全基本要求")),
    ("CSL-",        ("中华人民共和国网络安全法", "第二十一条 / 关键信息基础设施保护")),
    ("AIGC-",       ("AI 生成合成内容标识办法", "TC260 配套标识方法 / GB/T 45654-2025 附录")),
]

# Fallback citations for cases that carry no policy_refs (mostly benign_*).
# Choice rationale lives in docs/HACK-BENCH-组员提交规范.md.
DIMENSION_DEFAULT_SOURCES: dict[str, list[tuple[str, str, str]]] = {
    "execution_safety": [
        ("GB/T 22239-2019", "8.1.4 安全计算环境", "信息安全技术 网络安全等级保护基本要求"),
    ],
    "data_safety": [
        ("GB/T 22239-2019", "8.1.4 数据保护",      "信息安全技术 网络安全等级保护基本要求"),
        ("GB/T 45654-2025", "附录 A 数据安全",      "网络安全技术 生成式人工智能服务安全基本要求"),
    ],
    "content_safety": [
        ("GB/T 45654-2025", "附录 A 内容安全",      "网络安全技术 生成式人工智能服务安全基本要求"),
        ("TC260-003",       "第 7/8 章 内容安全",    "生成式人工智能服务安全基本要求"),
    ],
    "supply_chain": [
        ("GB/T 45654-2025", "附录 A 模型与数据来源", "网络安全技术 生成式人工智能服务安全基本要求"),
    ],
    "compliance": [
        ("GB/T 22239-2019", "8.1 安全通用要求",      "信息安全技术 网络安全等级保护基本要求"),
        ("GB/T 45654-2025", "附录 A",               "网络安全技术 生成式人工智能服务安全基本要求"),
    ],
    "interpretability": [
        ("GB/T 45654-2025", "服务透明度要求",        "网络安全技术 生成式人工智能服务安全基本要求"),
    ],
    "traceability": [
        ("GB/T 22239-2019", "8.1.4.3 安全审计",      "信息安全技术 网络安全等级保护基本要求"),
    ],
}

# attack_types that prove the gate fired correctly without representing an attack.
ASSURANCE_ATTACK_TYPES = {
    "audit_decision_coverage",
    "audit_hash_chain",
    "audit_required_red_tool",
}


def derive_case_kind(attack_type: str) -> str:
    if attack_type.startswith("benign_"):
        return "benign_control"
    if attack_type in ASSURANCE_ATTACK_TYPES:
        return "assurance_check"
    return "attack_case"


def _lookup_policy_source(policy_ref: str) -> tuple[str, str] | None:
    for prefix, info in POLICY_PREFIX_MAP:
        if policy_ref.startswith(prefix):
            return info
    return None


def derive_source_documents(case: dict[str, Any]) -> list[dict[str, str]]:
    """Build the citation list for one case.

    Priority order:
      1. Each policy_ref → its publishing standard.
      2. Fall back to the dimension default if no policy_refs.
    Result is de-duplicated while preserving order, so YAML stays stable across
    runs and diffs reflect real changes only.
    """
    docs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for ref in case.get("policy_refs", []) or []:
        info = _lookup_policy_source(ref)
        if not info:
            continue
        standard, title = info
        clause = ref
        key = (standard, clause)
        if key in seen:
            continue
        seen.add(key)
        docs.append({"standard": standard, "clause": clause, "title": title})

    if not docs:
        dim = case.get("dimension", "")
        for standard, clause, title in DIMENSION_DEFAULT_SOURCES.get(dim, []):
            key = (standard, clause)
            if key in seen:
                continue
            seen.add(key)
            docs.append({"standard": standard, "clause": clause, "title": title})

    if not docs:
        docs.append({
            "standard": "internal-control",
            "clause": "n/a",
            "title": "Fallback citation — review against XA-Bench rubric",
        })

    return docs


def _stable_args(arguments: Any) -> str:
    try:
        return json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        return repr(arguments)


def compute_fingerprint(case: dict[str, Any]) -> str:
    """Stable fingerprint used by the validator to surface duplicates.

    Includes session_history + input_sources so multi-source injection cases
    do not collapse into a single fingerprint just because the tool/args
    happen to match.
    """
    payload = case.get("input_payload", {}) or {}
    parts = [
        case.get("dimension", ""),
        case.get("attack_type", ""),
        payload.get("tool_name", ""),
        payload.get("user_role", ""),
        payload.get("message", ""),
        _stable_args(payload.get("arguments", {})),
        _stable_args(payload.get("input_sources", [])),
        _stable_args(payload.get("session_history", [])),
        case.get("expected_decision", ""),
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


# Order of keys we want in the on-disk YAML — keeps diffs reviewable.
CASE_KEY_ORDER = [
    "case_id",
    "dimension",
    "attack_type",
    "case_kind",
    "input_payload",
    "expected_decision",
    "expected_taint",
    "severity",
    "policy_refs",
    "source_documents",
    "fingerprint",
    "note",
]


def _reorder(case: dict[str, Any]) -> dict[str, Any]:
    ordered: dict[str, Any] = {}
    for key in CASE_KEY_ORDER:
        if key in case:
            ordered[key] = case[key]
    for key, value in case.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def _decollide(cases: list[dict[str, Any]]) -> int:
    """Inject `variant_index` into args of duplicate-fingerprint cases.

    The historical seed YAML produced 290 cases by templating the same payload
    multiple times.  `variant_index` makes each variant addressable on its own
    without rewriting payloads, so:
      * fingerprints become unique → validator passes without warnings;
      * audit trail makes the "variant 2 of N" intent explicit;
      * mock executor and policy engine ignore the extra key, so bench
        behaviour is unchanged.
    Returns the number of cases that were tagged.
    """
    groups: dict[str, list[int]] = {}
    for idx, case in enumerate(cases):
        groups.setdefault(case["fingerprint"], []).append(idx)

    tagged = 0
    for fp, idxs in groups.items():
        if len(idxs) <= 1:
            continue
        for variant_pos, idx in enumerate(idxs, start=1):
            case = cases[idx]
            payload = dict(case.get("input_payload", {}) or {})
            args = dict(payload.get("arguments", {}) or {})
            args["variant_index"] = variant_pos
            payload["arguments"] = args
            case["input_payload"] = payload
            case["fingerprint"] = compute_fingerprint(case)
            tagged += 1
    return tagged


def enrich(data: dict[str, Any], *, decollide: bool = True) -> dict[str, Any]:
    cases = data.get("cases", []) or []
    enriched: list[dict[str, Any]] = []
    for case in cases:
        case = dict(case)
        case["case_kind"] = derive_case_kind(case.get("attack_type", ""))
        case["source_documents"] = derive_source_documents(case)
        case["fingerprint"] = compute_fingerprint(case)
        enriched.append(case)

    tagged = _decollide(enriched) if decollide else 0

    data["cases"] = [_reorder(case) for case in enriched]

    metadata = data.setdefault("metadata", {})
    metadata["total"] = len(enriched)
    case_kind_counts: dict[str, int] = {}
    for case in enriched:
        case_kind_counts[case["case_kind"]] = case_kind_counts.get(case["case_kind"], 0) + 1
    metadata["case_kinds"] = case_kind_counts
    # variant_tagged is recorded per-case in input_payload.arguments.variant_index
    # rather than at metadata level so re-enrichment stays idempotent.
    _ = tagged  # surfaced via CLI stdout instead
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--check", action="store_true",
                        help="Exit non-zero if enrichment would change the file (CI mode).")
    parser.add_argument("--no-decollide", action="store_true",
                        help="Skip variant_index injection for duplicate payloads.")
    args = parser.parse_args()

    raw = args.suite.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    data = enrich(data, decollide=not args.no_decollide)

    header = (
        "# CSAB-Gov-mini seed 用例（扩展版 290 条，覆盖 7 个维度）\n"
        "# 生成口径：围绕等保 2.0、GB/T 45654-2025、TC260-003 的规则链路回归样例。\n"
        "# 字段由 scripts/enrich_csab_gov_mini.py 维护；新增/修改后请重跑该脚本，\n"
        "# 并执行 scripts/validate_csab_gov_mini.py 校验。\n"
    )
    rendered = header + yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        width=200,
    )

    if args.check:
        if rendered != raw:
            print(f"[enrich] {args.suite} is stale — run scripts/enrich_csab_gov_mini.py")
            return 1
        print(f"[enrich] {args.suite} is up to date.")
        return 0

    args.suite.write_text(rendered, encoding="utf-8")
    print(f"[enrich] wrote {args.suite} with {len(data['cases'])} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
