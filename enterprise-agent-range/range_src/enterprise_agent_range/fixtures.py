from __future__ import annotations

from pathlib import Path
from typing import Any

from .io_utils import read_json, sha256_file
from .models import (
    CASE_KINDS,
    REQUIRED_CASE_FIELDS,
    SURFACES,
    LoadedManifest,
    ManifestValidation,
)
from .oracles import validate_expected_keys


def load_manifest(path: Path) -> LoadedManifest:
    manifest_path = path.resolve()
    data = read_json(manifest_path)
    root = manifest_path.parent.parent if manifest_path.parent.name == "cases" else manifest_path.parent
    validation = validate_manifest(data, root)
    return LoadedManifest(path=manifest_path, root=root.resolve(), data=data, validation=validation)


def validate_manifest(data: dict[str, Any], root: Path) -> ManifestValidation:
    errors: list[str] = []
    warnings: list[str] = []

    if not data.get("schema_version"):
        errors.append("missing top-level schema_version")
    if not isinstance(data.get("metadata"), dict):
        errors.append("missing top-level metadata object")
    cases = data.get("cases")
    fixtures = data.get("fixtures", [])
    if not isinstance(cases, list):
        errors.append("top-level cases must be a list")
        cases = []
    if not isinstance(fixtures, list):
        errors.append("top-level fixtures must be a list")
        fixtures = []

    case_ids: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"cases[{index}] must be an object")
            continue
        case_id = str(case.get("case_id", f"cases[{index}]"))
        missing = sorted(REQUIRED_CASE_FIELDS - set(case))
        if missing:
            errors.append(f"{case_id}: missing required fields {missing}")
        if case_id in case_ids:
            errors.append(f"{case_id}: duplicate case_id")
        case_ids.add(case_id)

        case_kind = case.get("case_kind")
        if case_kind not in CASE_KINDS:
            errors.append(f"{case_id}: invalid case_kind {case_kind!r}")
        surface = case.get("surface")
        if surface not in SURFACES:
            errors.append(f"{case_id}: invalid surface {surface!r}")
        taxonomy = case.get("taxonomy")
        if not isinstance(taxonomy, list) or not taxonomy:
            errors.append(f"{case_id}: taxonomy must be a non-empty list")
        expected = case.get("expected")
        if not isinstance(expected, dict) or not expected:
            errors.append(f"{case_id}: expected must be a non-empty object")
            expected = {}
        if isinstance(expected, dict):
            unknown_expected, has_machine_oracle = validate_expected_keys(expected)
            if unknown_expected:
                errors.append(f"{case_id}: unsupported expected fields {unknown_expected}")
            if not has_machine_oracle:
                errors.append(f"{case_id}: expected must include at least one machine-checkable oracle field")
        execution = case.get("execution", {})
        steps = execution.get("steps", []) if isinstance(execution, dict) else []
        if case_kind != "exploratory_finding" and (not isinstance(steps, list) or not steps):
            errors.append(f"{case_id}: execution.steps must be a non-empty list")
        for step_index, step in enumerate(steps):
            if not isinstance(step, dict) or "tool" not in step:
                errors.append(f"{case_id}: execution.steps[{step_index}] must include tool")
        fixture_refs = case.get("input", {}).get("fixture_refs", [])
        if fixture_refs and not isinstance(fixture_refs, list):
            errors.append(f"{case_id}: input.fixture_refs must be a list")
            fixture_refs = []
        for ref in fixture_refs:
            fixture_path = root / str(ref)
            if not fixture_path.exists():
                errors.append(f"{case_id}: missing fixture {ref}")

    fixture_ids: set[str] = set()
    for index, fixture in enumerate(fixtures):
        if not isinstance(fixture, dict):
            errors.append(f"fixtures[{index}] must be an object")
            continue
        fixture_id = str(fixture.get("fixture_id", f"fixtures[{index}]"))
        if fixture_id in fixture_ids:
            errors.append(f"{fixture_id}: duplicate fixture_id")
        fixture_ids.add(fixture_id)
        path_value = fixture.get("path")
        if not path_value:
            errors.append(f"{fixture_id}: missing fixture path")
            continue
        fixture_path = root / str(path_value)
        if not fixture_path.exists():
            errors.append(f"{fixture_id}: file does not exist at {path_value}")
        if fixture.get("synthetic") is not True:
            errors.append(f"{fixture_id}: synthetic must be true")
        if fixture.get("sha256") in (None, "", "pending"):
            warnings.append(f"{fixture_id}: sha256 is pending and will be recomputed by the runner")

    return ManifestValidation(errors=errors, warnings=warnings)


def fixture_hashes(manifest: LoadedManifest) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for fixture in manifest.fixtures:
        path_value = fixture.get("path")
        if not path_value:
            continue
        path = manifest.root / str(path_value)
        if path.exists() and path.is_file():
            hashes[str(path_value)] = sha256_file(path)
    return hashes


def read_fixture_text(root: Path, ref: str) -> str:
    path = root / ref
    return path.read_text(encoding="utf-8")
