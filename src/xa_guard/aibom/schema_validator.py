"""CycloneDX 1.6 schema validator for XA-Guard AIBOM documents.

Validates the CycloneDX-standard portion of a BOM dict produced by
``xa_guard.aibom.exporter.export_cyclonedx``.

Design notes
------------
* XA-Guard adds two non-standard top-level extension keys (``findings`` and
  ``rating``) that are NOT part of the CycloneDX spec.  These are explicitly
  permitted and ignored during schema validation — they do not cause rejection.
* Validation strategy (two layers):
  1. JSON-schema layer: uses the vendored subset schema
     ``schema/cyclonedx-1.6.subset.schema.json`` via the ``jsonschema`` library
     when available.  Because the schema uses ``additionalProperties: true`` at
     top level and within component, the extension keys pass through safely.
  2. Python checks: referential-integrity (every ``dependencies[].ref`` and
     each ``dependsOn`` item must resolve to a known ``bom-ref``), plus
     structural checks that jsonschema alone cannot express conveniently.
* If ``jsonschema`` is not importable (offline / stripped environment) the module
  falls back to an equivalent built-in structural validator so that zero hard
  dependencies are introduced.  Mirror of the ``try: import yaml`` pattern in
  scanner.py.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Optional jsonschema import — degrade gracefully if absent
# ---------------------------------------------------------------------------
try:
    import jsonschema as _jsonschema  # type: ignore[import]
    _JSONSCHEMA_AVAILABLE = True
except Exception:  # pragma: no cover — exercised in monkeypatch tests
    _jsonschema = None  # type: ignore[assignment]
    _JSONSCHEMA_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants / enums (mirrored from the subset schema for the builtin path)
# ---------------------------------------------------------------------------

_VALID_SPEC_VERSIONS: frozenset[str] = frozenset({"1.5", "1.6"})

_VALID_COMPONENT_TYPES: frozenset[str] = frozenset(
    {
        "application",
        "framework",
        "library",
        "container",
        "platform",
        "operating-system",
        "device",
        "device-driver",
        "firmware",
        "file",
        "machine-learning-model",
        "data",
        "cryptographic-asset",
    }
)

_VALID_HASH_ALGS: frozenset[str] = frozenset(
    {
        "MD5",
        "SHA-1",
        "SHA-256",
        "SHA-384",
        "SHA-512",
        "SHA3-256",
        "SHA3-384",
        "SHA3-512",
        "BLAKE2b-256",
        "BLAKE2b-384",
        "BLAKE2b-512",
        "BLAKE3",
    }
)

_VALID_VULN_SEVERITIES: frozenset[str] = frozenset(
    {"critical", "high", "medium", "low", "info", "none", "unknown"}
)

# Extension keys introduced by XA-Guard — never treated as validation errors.
_XA_GUARD_EXTENSION_KEYS: frozenset[str] = frozenset({"findings", "rating"})

# Regex for checking hex content (at least 1 hex char)
_HEX_RE: re.Pattern[str] = re.compile(r"^[0-9a-fA-F]+$")

# Path to vendored subset schema (resolved relative to this file)
_SCHEMA_DIR = Path(__file__).parent / "schema"
_SUBSET_SCHEMA_PATH = _SCHEMA_DIR / "cyclonedx-1.6.subset.schema.json"

# ---------------------------------------------------------------------------
# Public data class
# ---------------------------------------------------------------------------


@dataclass
class SchemaValidationResult:
    """Result of validating a CycloneDX BOM document.

    Attributes
    ----------
    valid:
        ``True`` when the BOM passes all checks.
    errors:
        Human-readable error messages; empty when ``valid=True``.
    spec_version:
        The ``specVersion`` string found in the BOM, or ``""`` if absent.
    validator:
        Which validation path was used: ``"jsonschema"`` or ``"builtin"``.
    """

    valid: bool
    errors: list[str] = field(default_factory=list)
    spec_version: str = ""
    validator: str = ""


# ---------------------------------------------------------------------------
# Primary public interface
# ---------------------------------------------------------------------------


def validate_cyclonedx(bom: dict[str, Any]) -> SchemaValidationResult:
    """Validate *bom* against the CycloneDX 1.6 (or 1.5) standard subset.

    The XA-Guard extension keys ``findings`` and ``rating`` are explicitly
    permitted and do not cause a validation error.

    Returns a :class:`SchemaValidationResult`; ``valid=True`` means the BOM
    is acceptable for further pipeline processing.
    """
    errors: list[str] = []
    spec_version = str(bom.get("specVersion", ""))
    validator_name = "jsonschema" if _JSONSCHEMA_AVAILABLE else "builtin"

    if _JSONSCHEMA_AVAILABLE:
        _validate_with_jsonschema(bom, errors)
    else:
        _validate_builtin_schema(bom, errors)

    # Python-level checks that are independent of the schema engine
    _validate_referential_integrity(bom, errors)
    _validate_hash_content(bom, errors)
    _validate_vulnerability_severities(bom, errors)

    return SchemaValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        spec_version=spec_version,
        validator=validator_name,
    )


def assert_valid(bom: dict[str, Any]) -> None:
    """Convenience helper: raise ``ValueError`` with all errors if *bom* is invalid.

    Parameters
    ----------
    bom:
        A CycloneDX BOM dict (may contain XA-Guard extension keys).

    Raises
    ------
    ValueError
        When the BOM fails validation; the message contains all error details.
    """
    result = validate_cyclonedx(bom)
    if not result.valid:
        raise ValueError("BOM validation failed:\n" + "\n".join(f"  - {e}" for e in result.errors))


# ---------------------------------------------------------------------------
# JSON-schema validation path
# ---------------------------------------------------------------------------


def _load_subset_schema() -> dict[str, Any]:
    """Load the vendored CycloneDX subset schema from disk."""
    return json.loads(_SUBSET_SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate_with_jsonschema(bom: dict[str, Any], errors: list[str]) -> None:
    """Validate *bom* using the ``jsonschema`` library + vendored subset schema."""
    assert _jsonschema is not None  # guarded by caller
    try:
        schema = _load_subset_schema()
        validator_cls = _jsonschema.Draft7Validator
        validator_instance = validator_cls(schema)
        for error in sorted(validator_instance.iter_errors(bom), key=lambda e: str(e.path)):
            path = " > ".join(str(p) for p in error.absolute_path) or "(root)"
            errors.append(f"[schema] {path}: {error.message}")
    except Exception as exc:  # pragma: no cover
        errors.append(f"[schema] jsonschema internal error: {exc}")


# ---------------------------------------------------------------------------
# Built-in structural validation path (fallback when jsonschema is absent)
# ---------------------------------------------------------------------------


def _validate_builtin_schema(bom: dict[str, Any], errors: list[str]) -> None:
    """Pure-Python structural validator — equivalent to the subset schema."""
    _check_top_level(bom, errors)
    _check_metadata(bom.get("metadata"), errors)
    _check_components(bom.get("components", []), errors)
    _check_dependencies_shape(bom.get("dependencies", []), errors)
    _check_vulnerabilities_shape(bom.get("vulnerabilities", []), errors)


def _check_top_level(bom: dict[str, Any], errors: list[str]) -> None:
    bom_format = bom.get("bomFormat")
    if bom_format != "CycloneDX":
        errors.append(
            f"[builtin] bomFormat must be 'CycloneDX', got {bom_format!r}"
        )
    spec_version = bom.get("specVersion")
    if spec_version not in _VALID_SPEC_VERSIONS:
        errors.append(
            f"[builtin] specVersion must be one of {sorted(_VALID_SPEC_VERSIONS)}, got {spec_version!r}"
        )
    version = bom.get("version")
    if not isinstance(version, int) or version < 1:
        errors.append(
            f"[builtin] version must be an integer >= 1, got {version!r}"
        )


def _check_metadata(metadata: Any, errors: list[str]) -> None:
    if metadata is None:
        return  # metadata is optional
    if not isinstance(metadata, dict):
        errors.append("[builtin] metadata must be an object")
        return
    component = metadata.get("component")
    if component is not None:
        _check_single_component(component, "metadata.component", errors)
    for i, prop in enumerate(metadata.get("properties", [])):
        _check_property(prop, f"metadata.properties[{i}]", errors)


def _check_components(components: Any, errors: list[str]) -> None:
    if not isinstance(components, list):
        errors.append("[builtin] components must be an array")
        return
    for i, component in enumerate(components):
        _check_single_component(component, f"components[{i}]", errors)


def _check_single_component(component: Any, path: str, errors: list[str]) -> None:
    if not isinstance(component, dict):
        errors.append(f"[builtin] {path} must be an object")
        return
    comp_type = component.get("type")
    if comp_type not in _VALID_COMPONENT_TYPES:
        errors.append(
            f"[builtin] {path}.type must be one of valid CycloneDX component types, got {comp_type!r}"
        )
    name = component.get("name")
    if not isinstance(name, str) or not name:
        errors.append(f"[builtin] {path}.name must be a non-empty string")
    for j, h in enumerate(component.get("hashes", [])):
        _check_hash(h, f"{path}.hashes[{j}]", errors)
    for k, prop in enumerate(component.get("properties", [])):
        _check_property(prop, f"{path}.properties[{k}]", errors)


def _check_hash(h: Any, path: str, errors: list[str]) -> None:
    if not isinstance(h, dict):
        errors.append(f"[builtin] {path} must be an object")
        return
    alg = h.get("alg")
    if alg not in _VALID_HASH_ALGS:
        errors.append(
            f"[builtin] {path}.alg must be one of valid CycloneDX hash algorithms, got {alg!r}"
        )
    content = h.get("content")
    if not isinstance(content, str) or not content:
        errors.append(f"[builtin] {path}.content must be a non-empty string")


def _check_property(prop: Any, path: str, errors: list[str]) -> None:
    if not isinstance(prop, dict):
        errors.append(f"[builtin] {path} must be an object")
        return
    if not isinstance(prop.get("name"), str):
        errors.append(f"[builtin] {path}.name must be a string")


def _check_dependencies_shape(dependencies: Any, errors: list[str]) -> None:
    if not isinstance(dependencies, list):
        errors.append("[builtin] dependencies must be an array")
        return
    for i, dep in enumerate(dependencies):
        if not isinstance(dep, dict):
            errors.append(f"[builtin] dependencies[{i}] must be an object")
            continue
        if not isinstance(dep.get("ref"), str):
            errors.append(f"[builtin] dependencies[{i}].ref must be a string")
        depends_on = dep.get("dependsOn", [])
        if not isinstance(depends_on, list):
            errors.append(f"[builtin] dependencies[{i}].dependsOn must be an array")
        else:
            for j, ref in enumerate(depends_on):
                if not isinstance(ref, str):
                    errors.append(f"[builtin] dependencies[{i}].dependsOn[{j}] must be a string")


def _check_vulnerabilities_shape(vulnerabilities: Any, errors: list[str]) -> None:
    if not isinstance(vulnerabilities, list):
        errors.append("[builtin] vulnerabilities must be an array")
        return
    for i, vuln in enumerate(vulnerabilities):
        if not isinstance(vuln, dict):
            errors.append(f"[builtin] vulnerabilities[{i}] must be an object")
            continue
        if not isinstance(vuln.get("id"), str):
            errors.append(f"[builtin] vulnerabilities[{i}].id must be a string")
        for j, rating in enumerate(vuln.get("ratings", [])):
            sev = rating.get("severity") if isinstance(rating, dict) else None
            if sev is not None and sev not in _VALID_VULN_SEVERITIES:
                errors.append(
                    f"[builtin] vulnerabilities[{i}].ratings[{j}].severity must be one of "
                    f"{sorted(_VALID_VULN_SEVERITIES)}, got {sev!r}"
                )


# ---------------------------------------------------------------------------
# Python-level checks (run regardless of schema engine)
# ---------------------------------------------------------------------------


def _collect_bom_refs(bom: dict[str, Any]) -> set[str]:
    """Collect every bom-ref declared in metadata.component and components[]."""
    refs: set[str] = set()
    meta_component = bom.get("metadata", {}).get("component", {})
    if isinstance(meta_component, dict):
        ref = meta_component.get("bom-ref")
        if ref:
            refs.add(str(ref))
    for component in bom.get("components", []):
        if isinstance(component, dict):
            ref = component.get("bom-ref")
            if ref:
                refs.add(str(ref))
    return refs


def _validate_referential_integrity(bom: dict[str, Any], errors: list[str]) -> None:
    """Verify every dependencies[].ref and dependsOn[] entry resolves to a known bom-ref."""
    known_refs = _collect_bom_refs(bom)
    for i, dep in enumerate(bom.get("dependencies", [])):
        if not isinstance(dep, dict):
            continue
        ref = dep.get("ref")
        if isinstance(ref, str) and ref and ref not in known_refs:
            errors.append(
                f"[integrity] dependencies[{i}].ref {ref!r} is not a declared bom-ref"
            )
        for j, sub_ref in enumerate(dep.get("dependsOn", []) or []):
            if isinstance(sub_ref, str) and sub_ref and sub_ref not in known_refs:
                errors.append(
                    f"[integrity] dependencies[{i}].dependsOn[{j}] {sub_ref!r} is not a declared bom-ref"
                )


def _validate_hash_content(bom: dict[str, Any], errors: list[str]) -> None:
    """Validate hash content values are non-empty hex strings."""
    components: list[dict[str, Any]] = list(bom.get("components", []))
    meta_component = bom.get("metadata", {}).get("component")
    if isinstance(meta_component, dict):
        components = [meta_component] + components

    for i, component in enumerate(components):
        if not isinstance(component, dict):
            continue
        label = "metadata.component" if i == 0 and meta_component is not None else f"components[{i - (1 if meta_component is not None else 0)}]"
        for j, h in enumerate(component.get("hashes", [])):
            if not isinstance(h, dict):
                continue
            content = h.get("content", "")
            if isinstance(content, str) and content and not _HEX_RE.match(content):
                errors.append(
                    f"[integrity] {label}.hashes[{j}].content is not a valid hex string: {content!r}"
                )


def _validate_vulnerability_severities(bom: dict[str, Any], errors: list[str]) -> None:
    """Validate vulnerability rating severity values."""
    for i, vuln in enumerate(bom.get("vulnerabilities", []) or []):
        if not isinstance(vuln, dict):
            continue
        for j, rating in enumerate(vuln.get("ratings", []) or []):
            if not isinstance(rating, dict):
                continue
            sev = rating.get("severity")
            if sev is not None and sev not in _VALID_VULN_SEVERITIES:
                errors.append(
                    f"[integrity] vulnerabilities[{i}].ratings[{j}].severity {sev!r} "
                    f"is not a valid CycloneDX severity"
                )
