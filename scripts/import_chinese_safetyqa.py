"""Build the redistributable CSAB non-refusal candidate from Chinese SafetyQA."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from bench.corpus import (
    NORMALIZATION_VERSION,
    SCHEMA_VERSION,
    file_sha256,
    manifest_commitment,
    payload_sha256,
    write_jsonl,
)

UPSTREAM_COMMIT = "5be00913f99e24965378b557f1f0ecb7443caba3"
DATA_SHA256 = "sha256:edb401b22a0370cca603edd24c27437ea1c066360de742427202e292c06df94c"
LICENSE_SHA256 = "sha256:34d68752e1311237514a5822c1ad093e73931e157f236abffae6722fe8d3d2cb"
SOURCE_URL = "https://github.com/LivingFutureLab/ChineseSafetyQA"


def _load_rows(path: Path) -> list[tuple[int, dict]]:
    rows: list[tuple[int, dict]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            value = json.loads(line)
            if not isinstance(value, dict) or not isinstance(value.get("question"), str):
                raise ValueError(f"{path}:{line_number}: missing question")
            rows.append((line_number, value))
    return rows


def build(upstream: Path, output: Path, *, count: int) -> None:
    data_path = upstream / "data" / "chinese_safetyqa.jsonl"
    license_path = upstream / "LICENSE"
    if file_sha256(data_path) != DATA_SHA256:
        raise ValueError("Chinese SafetyQA data hash does not match the pinned official commit")
    if file_sha256(license_path) != LICENSE_SHA256:
        raise ValueError("Chinese SafetyQA license hash does not match the pinned official commit")
    source_rows = _load_rows(data_path)
    if count < 500 or count > len(source_rows):
        raise ValueError(f"count must be between 500 and {len(source_rows)}")
    questions = [row[1]["question"] for row in source_rows]
    if len(set(questions)) != len(questions):
        raise ValueError("upstream questions are not exact-unique")

    ranked = sorted(
        source_rows,
        key=lambda item: hashlib.sha256(
            f"{UPSTREAM_COMMIT}\0{item[1]['question']}".encode("utf-8")
        ).digest(),
    )[:count]
    cases = []
    for sequence, (line_number, source) in enumerate(ranked, 1):
        payload = {
            "tool_name": "answer_question",
            "arguments": {"question": source["question"]},
            "user_role": "user",
            "input_sources": ["user"],
        }
        question_digest = hashlib.sha256(source["question"].encode("utf-8")).hexdigest()
        cases.append(
            {
                "case_id": f"CSQA-NR-{sequence:04d}",
                "cohort": "non_refusal",
                "expected_refusal": False,
                "gb_category_id": None,
                "input_payload": payload,
                "normalized_payload_sha256": payload_sha256(payload),
                "semantic_group_id": f"source-question-sha256:{question_digest}",
                "semantic_group_reviewed": False,
                "split": "development",
                "source_refs": [{
                    "source_id": "chinese-safetyqa-2024",
                    "locator": f"data/chinese_safetyqa.jsonl:{line_number}",
                    "derivation": "question copied verbatim into arguments.question",
                }],
            }
        )

    output.mkdir(parents=True, exist_ok=True)
    artifact_path = output / "non-refusal.jsonl"
    write_jsonl(artifact_path, cases)
    license_name = "THIRD_PARTY_LICENSE.ChineseSafetyQA.txt"
    shutil.copyfile(license_path, output / license_name)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "corpus_id": "csab-gov-v1-candidate",
        "version": "2026-06-19",
        "taxonomy_version": "GB/T 45654-2025/A.1+A.2",
        "normalization_version": NORMALIZATION_VERSION,
        "independent_evaluator_attestation": None,
        "claim_scope": "candidate_non_refusal_corpus_only",
        "refusal_taxonomy": [],
        "sources": [{
            "source_id": "chinese-safetyqa-2024",
            "title": "Chinese SafetyQA",
            "url": SOURCE_URL,
            "version": UPSTREAM_COMMIT,
            "retrieved_at": "2026-06-19",
            "license_id": "MIT",
            "license_url": f"{SOURCE_URL}/blob/{UPSTREAM_COMMIT}/LICENSE",
            "license_file": license_name,
            "license_sha256": LICENSE_SHA256,
            "redistribution": "allowed",
            "artifact_sha256": DATA_SHA256,
        }],
        "artifacts": [{
            "cohort": "non_refusal",
            "split": "development",
            "path": artifact_path.name,
            "sha256": file_sha256(artifact_path),
            "case_count": len(cases),
        }],
        "selection": {
            "source_case_count": len(source_rows),
            "selected_case_count": len(cases),
            "method": "lowest sha256(commit + NUL + question)",
        },
    }
    manifest["commitment_sha256"] = manifest_commitment(manifest)
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path, help="Pinned ChineseSafetyQA checkout")
    parser.add_argument("--output", type=Path, default=Path("bench/cases/csab-gov-v1-candidate"))
    parser.add_argument("--count", type=int, default=500)
    args = parser.parse_args()
    build(args.upstream.resolve(), args.output.resolve(), count=args.count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

