"""CycloneDX-like AIBOM export and drift comparison helpers."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from xa_guard.aibom.rater import rate
from xa_guard.aibom.scanner import ScanReport


def export_cyclonedx(report: ScanReport) -> dict[str, Any]:
    grade, reason = rate(report)
    component_name = Path(report.plugin_path).name or report.plugin_path
    root_ref = f"pkg:xa-guard/{component_name}"
    dependencies = [_dependency_component(dep) for dep in sorted(set(report.dependencies))]
    component_hash = report.provenance.get("sha256") or _path_hash(report.plugin_path)

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": component_name,
                "bom-ref": root_ref,
                "hashes": [{"alg": "SHA-256", "content": component_hash}],
            },
            "properties": _properties(report),
        },
        "components": dependencies,
        "dependencies": [
            {
                "ref": root_ref,
                "dependsOn": [component["bom-ref"] for component in dependencies],
            }
        ],
        "properties": _properties(report),
        "findings": [{"id": f"AIBOM-{index + 1:04d}", "detail": finding} for index, finding in enumerate(report.findings)],
        "rating": {"grade": grade, "reason": reason},
    }


def compare_drift(current: ScanReport, previous: ScanReport | dict[str, Any]) -> ScanReport:
    previous_bom = export_cyclonedx(previous) if isinstance(previous, ScanReport) else previous
    current_bom = export_cyclonedx(current)
    drift = ScanReport(plugin_path=current.plugin_path)

    _compare_set(
        drift,
        "drift_capability_change",
        "capabilities changed",
        _capabilities_from_bom(previous_bom),
        set(current.inferred_capabilities),
    )
    _compare_set(
        drift,
        "drift_dependency_change",
        "dependencies changed",
        _component_names(previous_bom),
        _component_names(current_bom),
    )
    if _component_hash(previous_bom) != _component_hash(current_bom):
        _add_drift(drift, "drift_hash_change", "component hash changed")
    if previous_bom.get("rating", {}).get("grade") != current_bom.get("rating", {}).get("grade"):
        _add_drift(drift, "drift_rating_change", "rating changed")

    return drift


def _dependency_component(dep: str) -> dict[str, Any]:
    name, version = _split_dependency(dep)
    component = {
        "type": "library",
        "name": name,
        "bom-ref": f"pkg:pypi/{name}{('@' + version) if version else ''}",
        "properties": [{"name": "xa_guard:aibom:specifier", "value": dep}],
    }
    if version:
        component["version"] = version
    return component


def _split_dependency(dep: str) -> tuple[str, str]:
    text = dep.strip()
    if " @ " in text:
        text = text.split(" @ ", 1)[0]
    match = re.match(r"^([A-Za-z0-9_.-]+)(?:={2,3}([^;\s]+))?", text)
    if not match:
        return text, ""
    return match.group(1).replace("_", "-").lower(), match.group(2) or ""


def _properties(report: ScanReport) -> list[dict[str, str]]:
    properties = [
        {"name": f"xa_guard:aibom:risk:{key}", "value": str(value)}
        for key, value in sorted(report.risk_indicators.items())
    ]
    properties.extend({"name": "xa_guard:aibom:capability", "value": capability} for capability in sorted(set(report.inferred_capabilities)))
    properties.extend({"name": f"xa_guard:aibom:provenance:{key}", "value": str(value)} for key, value in sorted(report.provenance.items()))
    return properties


def _path_hash(path_text: str) -> str:
    path = Path(path_text)
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if path.is_dir():
        hasher = hashlib.sha256()
        for child in sorted((p for p in path.rglob("*") if p.is_file()), key=lambda p: str(p)):
            hasher.update(str(child.relative_to(path)).replace("\\", "/").encode("utf-8"))
            hasher.update(child.read_bytes())
        return hasher.hexdigest()
    return hashlib.sha256(path_text.encode("utf-8")).hexdigest()


def _capabilities_from_bom(bom: dict[str, Any]) -> set[str]:
    values = set()
    for prop in bom.get("properties", []) + bom.get("metadata", {}).get("properties", []):
        if prop.get("name") == "xa_guard:aibom:capability":
            values.add(str(prop.get("value", "")))
    return values


def _component_names(bom: dict[str, Any]) -> set[str]:
    return {str(component.get("name", "")) for component in bom.get("components", []) if component.get("name")}


def _component_hash(bom: dict[str, Any]) -> str:
    hashes = bom.get("metadata", {}).get("component", {}).get("hashes", [])
    return str(hashes[0].get("content", "")) if hashes else ""


def _compare_set(drift: ScanReport, key: str, label: str, previous: set[str], current: set[str]) -> None:
    if previous != current:
        _add_drift(drift, key, f"{label}: previous={sorted(previous)} current={sorted(current)}")


def _add_drift(report: ScanReport, key: str, finding: str) -> None:
    report.risk_indicators[key] = report.risk_indicators.get(key, 0) + 1
    report.findings.append(finding)
