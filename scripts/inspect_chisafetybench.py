"""Inspect pinned CHiSafetyBench refusal files without redistributing their content."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from bench.corpus import file_sha256

UPSTREAM_COMMIT = "dd67c6f9fd82d848fe719c57ec5c91683ec6d1d8"
FILES = {
    "CHiSafetyBench/dataset/v1/risky_questions_without_dialog_history.json":
        "sha256:2cba5863275e5f2167fa9d0d46010e46f3ae862a2edb3b11a4c19ad16fc72b0a",
    "CHiSafetyBench/dataset/v1/risky_questions_with_dialog_history.json":
        "sha256:b8e87036d236ae52d9cd100a2b69c1dc40d6f844ba1680d58129a9284bec5c81",
}




def _normalized_category(label: str) -> str:
    return label.removesuffix("\u5185\u5bb9") if label.endswith("\u6b67\u89c6\u5185\u5bb9") else label


def inspect(checkout: Path) -> dict:
    for relative, expected_hash in FILES.items():
        actual_hash = file_sha256(checkout / relative)
        if actual_hash != expected_hash:
            raise ValueError(f"hash mismatch for {relative}")

    single = json.loads((checkout / next(iter(FILES))).read_text(encoding="utf-8"))
    single_rows = single[0]["infos"]
    multi_path = list(FILES)[1]
    multi_rows = json.loads((checkout / multi_path).read_text(encoding="utf-8"))
    raw_categories = {row["category"] for row in single_rows}
    raw_categories.update(row["sub_category"] for row in multi_rows)
    category_counts = Counter(_normalized_category(row["category"]) for row in single_rows)
    category_counts.update(_normalized_category(row["sub_category"]) for row in multi_rows)

    payload_digests = set()
    for row in single_rows:
        encoded = json.dumps({"question": row["question"]}, ensure_ascii=False, sort_keys=True)
        payload_digests.add(hashlib.sha256(encoded.encode("utf-8")).hexdigest())
    for row in multi_rows:
        encoded = json.dumps(
            {"input": row["input"], "history": row["history"]},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        payload_digests.add(hashlib.sha256(encoded.encode("utf-8")).hexdigest())

    applicable_licenses = [
        path.relative_to(checkout).as_posix()
        for base in (checkout, checkout / "CHiSafetyBench")
        for path in base.glob("*")
        if path.is_file() and path.name.lower().startswith(("license", "copying"))
    ]
    total = len(single_rows) + len(multi_rows)
    return {
        "schema_version": "xa-guard-external-corpus-inspection/v1",
        "source": "https://github.com/UnicomAI/UnicomBenchmark/tree/"
        f"{UPSTREAM_COMMIT}/CHiSafetyBench",
        "upstream_commit": UPSTREAM_COMMIT,
        "files": [
            {"path": relative, "sha256": digest}
            for relative, digest in FILES.items()
        ],
        "counts": {
            "single_turn": len(single_rows),
            "multi_turn": len(multi_rows),
            "total": total,
            "raw_category_labels": len(raw_categories),
            "normalized_categories": len(category_counts),
            "minimum_per_category": min(category_counts.values()),
            "maximum_per_category": max(category_counts.values()),
            "exact_payloads_unique": len(payload_digests),
        },
        "applicable_license_files": applicable_licenses,
        "license_status": "no_explicit_license_found",
        "redistribution_permitted": False,
        "formal_import_eligible": False,
        "import_performed": False,
        "official_claim": False,
        "note": (
            "Public availability is not redistribution permission. Obtain an explicit data "
            "license or author permission before importing raw questions."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = inspect(args.checkout.resolve())
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

