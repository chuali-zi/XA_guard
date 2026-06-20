"""Auditable corpus loading and validation for the GB/T 45654 benchmark."""
from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "xa-guard-csab-corpus/v1"
NORMALIZATION_VERSION = "xa-guard-payload-normalization/v1"
REQUIRED_REFUSAL_CATEGORY_COUNT = 17
COHORTS = {"refusal", "non_refusal"}
SPLITS = {"development", "calibration", "holdout"}
NON_SEMANTIC_KEYS = {"case_id", "fingerprint", "note", "variant_index"}


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            unicodedata.normalize("NFC", str(key)): _normalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if key not in NON_SEMANTIC_KEYS
        }
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    return value


def canonical_payload(payload: dict[str, Any]) -> bytes:
    """Return the versioned, deterministic representation used for duplicate checks."""
    normalized = _normalize(payload)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def payload_sha256(payload: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_payload(payload)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def manifest_commitment(manifest: dict[str, Any]) -> str:
    committed = dict(manifest)
    committed.pop("commitment_sha256", None)
    encoded = json.dumps(committed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: each row must be an object")
            value["_artifact"] = path.name
            value["_line"] = line_number
            rows.append(value)
    return rows


@dataclass
class CorpusValidation:
    corpus_dir: Path
    profile: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    counts: dict[str, Any] = field(default_factory=dict)

    @property
    def valid(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "xa-guard-csab-corpus-validation/v1",
            "corpus_dir": str(self.corpus_dir),
            "profile": self.profile,
            "valid": self.valid,
            "counts": self.counts,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def _required_text(row: dict[str, Any], name: str, where: str, errors: list[str]) -> str:
    value = row.get(name)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{where}: `{name}` must be a non-empty string")
        return ""
    return value


def validate_corpus(corpus_dir: str | Path, *, profile: str = "formal") -> CorpusValidation:
    """Validate a corpus directory without executing or mutating its content."""
    root = Path(corpus_dir).resolve()
    result = CorpusValidation(corpus_dir=root, profile=profile)
    if profile not in {"candidate", "formal"}:
        result.errors.append(f"unsupported profile: {profile}")
        return result

    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        result.errors.append("missing manifest.json")
        return result
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result.errors.append(f"invalid manifest.json: {exc}")
        return result
    if not isinstance(manifest, dict):
        result.errors.append("manifest.json must contain an object")
        return result

    if manifest.get("schema_version") != SCHEMA_VERSION:
        result.errors.append(f"manifest schema_version must be {SCHEMA_VERSION}")
    if manifest.get("normalization_version") != NORMALIZATION_VERSION:
        result.errors.append(f"normalization_version must be {NORMALIZATION_VERSION}")
    expected_commitment = manifest_commitment(manifest)
    if manifest.get("commitment_sha256") != expected_commitment:
        result.errors.append("manifest commitment_sha256 mismatch")
    attestation_valid = False
    attestation = manifest.get("independent_evaluator_attestation")
    if attestation is not None:
        where = "manifest.independent_evaluator_attestation"
        if not isinstance(attestation, dict):
            result.errors.append(f"{where}: must be null or an object")
        else:
            for field_name in ("evaluator", "issued_at", "statement", "path", "sha256"):
                _required_text(attestation, field_name, where, result.errors)
            relative_attestation = Path(str(attestation.get("path", "")))
            if (
                not relative_attestation.name
                or relative_attestation.is_absolute()
                or ".." in relative_attestation.parts
            ):
                result.errors.append(f"{where}: unsafe path")
            elif not (root / relative_attestation).is_file():
                result.errors.append(f"{where}: missing attestation artifact")
            elif file_sha256(root / relative_attestation) != attestation.get("sha256"):
                result.errors.append(f"{where}: sha256 mismatch")
            else:
                attestation_valid = all(
                    isinstance(attestation.get(field_name), str) and attestation[field_name].strip()
                    for field_name in ("evaluator", "issued_at", "statement")
                )

    if not manifest.get("sources"):
        result.errors.append("manifest sources must be a non-empty list")
    source_ids: set[str] = set()
    for index, source in enumerate(manifest.get("sources") or []):
        where = f"manifest.sources[{index}]"
        if not isinstance(source, dict):
            result.errors.append(f"{where}: must be an object")
            continue
        source_id = _required_text(source, "source_id", where, result.errors)
        for field_name in ("title", "url", "version", "retrieved_at", "license_id", "license_url"):
            _required_text(source, field_name, where, result.errors)
        artifact_hash = _required_text(source, "artifact_sha256", where, result.errors)
        if artifact_hash and not artifact_hash.startswith("sha256:"):
            result.errors.append(f"{where}: artifact_sha256 must use sha256:<hex>")
        if source.get("redistribution") not in {"allowed", "external_only"}:
            result.errors.append(f"{where}: redistribution must be allowed or external_only")
        if str(source.get("license_id", "")).upper() in {"", "NOASSERTION", "UNKNOWN"}:
            result.errors.append(f"{where}: an explicit license is required")
        license_file = source.get("license_file")
        license_hash = source.get("license_sha256")
        if source.get("redistribution") == "allowed":
            relative_license = Path(str(license_file or ""))
            if (
                not relative_license.name
                or relative_license.is_absolute()
                or ".." in relative_license.parts
            ):
                result.errors.append(f"{where}: allowed source requires a safe license_file")
            elif not (root / relative_license).is_file():
                result.errors.append(f"{where}: missing license_file {relative_license.as_posix()}")
            elif file_sha256(root / relative_license) != license_hash:
                result.errors.append(f"{where}: license_sha256 mismatch")
        if source_id in source_ids:
            result.errors.append(f"duplicate source_id: {source_id}")
        source_ids.add(source_id)

    raw_taxonomy = manifest.get("refusal_taxonomy")
    if not isinstance(raw_taxonomy, list):
        result.errors.append("manifest refusal_taxonomy must be a list")
        raw_taxonomy = []
    category_ids: set[str] = set()
    taxonomy_reviewed = 0
    for index, category in enumerate(raw_taxonomy):
        where = f"manifest.refusal_taxonomy[{index}]"
        if not isinstance(category, dict):
            result.errors.append(f"{where}: must be an object")
            continue
        category_id = _required_text(category, "category_id", where, result.errors)
        for field_name in ("label", "standard_clause", "source_url"):
            _required_text(category, field_name, where, result.errors)
        if category_id in category_ids:
            result.errors.append(f"duplicate refusal category_id: {category_id}")
        category_ids.add(category_id)
        if category.get("alignment_reviewed") is True:
            taxonomy_reviewed += 1

    rows: list[dict[str, Any]] = []
    declared_artifacts = manifest.get("artifacts") or []
    if not declared_artifacts:
        result.errors.append("manifest artifacts must be a non-empty list")
    for index, artifact in enumerate(declared_artifacts):
        where = f"manifest.artifacts[{index}]"
        if not isinstance(artifact, dict):
            result.errors.append(f"{where}: must be an object")
            continue
        relative = Path(str(artifact.get("path", "")))
        if not relative.name or relative.is_absolute() or ".." in relative.parts:
            result.errors.append(f"{where}: unsafe artifact path")
            continue
        path = root / relative
        if not path.is_file():
            result.errors.append(f"{where}: missing artifact {relative.as_posix()}")
            continue
        if file_sha256(path) != artifact.get("sha256"):
            result.errors.append(f"{where}: sha256 mismatch for {relative.as_posix()}")
        try:
            artifact_rows = load_jsonl(path)
        except ValueError as exc:
            result.errors.append(str(exc))
            continue
        for artifact_row in artifact_rows:
            artifact_row["_declared_cohort"] = artifact.get("cohort")
            artifact_row["_declared_split"] = artifact.get("split")
        if len(artifact_rows) != artifact.get("case_count"):
            result.errors.append(
                f"{where}: case_count={artifact.get('case_count')} but actual={len(artifact_rows)}"
            )
        rows.extend(artifact_rows)

    ids: set[str] = set()
    hashes: dict[str, list[str]] = defaultdict(list)
    group_splits: dict[str, set[str]] = defaultdict(set)
    cohort_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    reviewed_groups = 0
    for row in rows:
        where = f"{row.get('_artifact')}:{row.get('_line')}"
        case_id = _required_text(row, "case_id", where, result.errors)
        cohort = row.get("cohort")
        split = row.get("split")
        semantic_group = _required_text(row, "semantic_group_id", where, result.errors)
        payload = row.get("input_payload")
        if cohort not in COHORTS:
            result.errors.append(f"{where}: invalid cohort {cohort!r}")
        else:
            cohort_counts[cohort] += 1
        if split not in SPLITS:
            result.errors.append(f"{where}: invalid split {split!r}")
        if cohort != row.get("_declared_cohort"):
            result.errors.append(f"{where}: cohort does not match manifest artifact")
        if split != row.get("_declared_split"):
            result.errors.append(f"{where}: split does not match manifest artifact")
        if row.get("expected_refusal") is not (cohort == "refusal"):
            result.errors.append(f"{where}: expected_refusal must match cohort")
        if case_id in ids:
            result.errors.append(f"duplicate case_id: {case_id}")
        ids.add(case_id)
        if not isinstance(payload, dict) or not payload:
            result.errors.append(f"{where}: input_payload must be a non-empty object")
        else:
            computed_hash = payload_sha256(payload)
            if row.get("normalized_payload_sha256") != computed_hash:
                result.errors.append(f"{where}: normalized_payload_sha256 mismatch")
            hashes[computed_hash].append(case_id or where)
        refs = row.get("source_refs")
        if not isinstance(refs, list) or not refs:
            result.errors.append(f"{where}: source_refs must be a non-empty list")
        else:
            for ref in refs:
                if not isinstance(ref, dict) or ref.get("source_id") not in source_ids:
                    result.errors.append(f"{where}: source_ref points to an unknown source")
        if semantic_group and split in SPLITS:
            group_splits[semantic_group].add(split)
        if row.get("semantic_group_reviewed") is True:
            reviewed_groups += 1
        if cohort == "refusal":
            category = row.get("gb_category_id")
            if category not in category_ids:
                result.errors.append(f"{where}: invalid refusal gb_category_id {category!r}")
            else:
                category_counts[category] += 1

    for digest, case_ids in hashes.items():
        if len(case_ids) > 1:
            result.errors.append(f"duplicate normalized payload {digest}: {case_ids}")
    for semantic_group, splits in group_splits.items():
        if len(splits) > 1:
            result.errors.append(
                f"semantic_group_id {semantic_group!r} crosses splits: {sorted(splits)}"
            )

    result.counts = {
        "total": len(rows),
        "cohorts": dict(sorted(cohort_counts.items())),
        "refusal_categories": dict(sorted(category_counts.items())),
        "refusal_taxonomy_categories": len(category_ids),
        "refusal_taxonomy_reviewed": taxonomy_reviewed,
        "normalized_payloads_unique": len(hashes),
        "semantic_groups": len(group_splits),
        "semantic_groups_reviewed": reviewed_groups,
    }
    if profile == "formal":
        for cohort in sorted(COHORTS):
            if cohort_counts[cohort] < 500:
                result.errors.append(f"formal profile requires at least 500 {cohort} cases")
        if len(category_ids) != REQUIRED_REFUSAL_CATEGORY_COUNT:
            result.errors.append("formal profile requires exactly 17 refusal taxonomy categories")
        if taxonomy_reviewed != len(category_ids):
            result.errors.append("formal profile requires independent review of every taxonomy mapping")
        for category in sorted(category_ids):
            if category_counts[category] < 20:
                result.errors.append(f"formal profile requires at least 20 cases for {category}")
        if reviewed_groups != len(rows):
            result.errors.append("formal profile requires semantic_group_reviewed=true for every case")
        if not attestation_valid:
            result.errors.append("formal profile requires a hash-bound independent evaluator attestation")
    else:
        if cohort_counts["refusal"] < 500 or cohort_counts["non_refusal"] < 500:
            result.warnings.append("candidate corpus does not yet satisfy both 500-case cohort minima")
        if reviewed_groups != len(rows):
            result.warnings.append("semantic groups have not all been independently reviewed")
    return result


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")
