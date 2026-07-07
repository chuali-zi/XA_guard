"""Tests for xa_guard.aibom.schema_validator — CycloneDX 1.6 validation.

Test coverage:
  (a) Valid BOM from real exporter (specVersion 1.5) passes.
  (b) specVersion 1.6 accepted.
  (c) Various invalid BOMs are rejected with specific errors.
  (d) XA-Guard extension keys 'findings'/'rating' do NOT cause rejection.
  (e) Built-in fallback path works (monkeypatch jsonschema unavailable).
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from xa_guard.aibom.schema_validator import (
    SchemaValidationResult,
    assert_valid,
    validate_cyclonedx,
)

# ---------------------------------------------------------------------------
# Helpers to build minimal valid BOMs
# ---------------------------------------------------------------------------

_VALID_BOM_BASE: dict[str, Any] = {
    "bomFormat": "CycloneDX",
    "specVersion": "1.6",
    "version": 1,
    "metadata": {
        "component": {
            "type": "application",
            "name": "test-app",
            "bom-ref": "pkg:xa-guard/test-app",
            "hashes": [{"alg": "SHA-256", "content": "a" * 64}],
        },
        "properties": [],
    },
    "components": [
        {
            "type": "library",
            "name": "requests",
            "bom-ref": "pkg:pypi/requests@2.31.0",
            "version": "2.31.0",
            "properties": [],
        }
    ],
    "dependencies": [
        {
            "ref": "pkg:xa-guard/test-app",
            "dependsOn": ["pkg:pypi/requests@2.31.0"],
        }
    ],
    "properties": [],
    "findings": [{"id": "AIBOM-0001", "detail": "test finding"}],
    "rating": {"grade": "A", "reason": "no risk"},
}


def _bom(**overrides: Any) -> dict[str, Any]:
    """Return a deep-copy of the valid base BOM with overrides applied at top level."""
    bom = copy.deepcopy(_VALID_BOM_BASE)
    bom.update(overrides)
    return bom


# ---------------------------------------------------------------------------
# (a) Valid BOM from the real exporter passes
# ---------------------------------------------------------------------------

class TestRealExporterBOM:
    def test_real_exporter_passes(self, tmp_path: Path) -> None:
        """Build a real BOM via scan + export_cyclonedx and expect it to pass."""
        from xa_guard.aibom.exporter import export_cyclonedx
        from xa_guard.aibom.scanner import scan

        plugin = tmp_path / "myplugin.py"
        plugin.write_text("# minimal clean plugin\n\ndef hello():\n    return 'hi'\n", encoding="utf-8")

        report = scan(str(tmp_path))
        bom = export_cyclonedx(report)

        result = validate_cyclonedx(bom)
        assert result.valid, f"Real exporter BOM failed: {result.errors}"
        # exporter 已生产化升级到 CycloneDX 1.6（见 exporter.export_cyclonedx）。
        assert result.spec_version == "1.6"
        assert result.validator in ("jsonschema", "builtin")

    def test_real_exporter_with_deps_passes(self, tmp_path: Path) -> None:
        """BOM with dependencies should still pass referential-integrity checks."""
        from xa_guard.aibom.exporter import export_cyclonedx
        from xa_guard.aibom.scanner import ScanReport

        report = ScanReport(
            plugin_path=str(tmp_path / "myplugin.py"),
            dependencies=["requests==2.31.0", "flask==3.0.0"],
        )
        bom = export_cyclonedx(report)
        result = validate_cyclonedx(bom)
        assert result.valid, f"BOM with deps failed: {result.errors}"


# ---------------------------------------------------------------------------
# (a2) metadata.tools accepts both CycloneDX forms
# ---------------------------------------------------------------------------

class TestMetadataToolsForms:
    """CycloneDX 1.5+ allows metadata.tools as the legacy array OR an object.

    Real external generators (e.g. @cyclonedx/cdxgen 12.x) emit the object form
    ``{"components": [...], "services": [...]}``; the legacy array form must keep
    working for older producers.
    """

    def test_metadata_tools_legacy_array_accepted(self) -> None:
        bom = _bom()
        bom["metadata"]["tools"] = [
            {"vendor": "XA-Guard", "name": "scanner", "version": "1.0"}
        ]
        result = validate_cyclonedx(bom)
        assert result.valid, result.errors

    def test_metadata_tools_object_form_accepted(self) -> None:
        bom = _bom()
        bom["metadata"]["tools"] = {
            "components": [
                {
                    "type": "application",
                    "name": "cdxgen",
                    "group": "@cyclonedx",
                    "version": "12.7.0",
                    "purl": "pkg:npm/%40cyclonedx/cdxgen@12.7.0",
                    "bom-ref": "pkg:npm/@cyclonedx/cdxgen@12.7.0",
                }
            ]
        }
        result = validate_cyclonedx(bom)
        assert result.valid, result.errors


# ---------------------------------------------------------------------------
# (b) specVersion 1.6 accepted
# ---------------------------------------------------------------------------

class TestSpecVersion:
    def test_spec_version_16_accepted(self) -> None:
        bom = _bom(specVersion="1.6")
        result = validate_cyclonedx(bom)
        assert result.valid, result.errors
        assert result.spec_version == "1.6"

    def test_spec_version_15_accepted(self) -> None:
        bom = _bom(specVersion="1.5")
        result = validate_cyclonedx(bom)
        assert result.valid, result.errors

    def test_spec_version_14_rejected(self) -> None:
        bom = _bom(specVersion="1.4")
        result = validate_cyclonedx(bom)
        assert not result.valid
        assert any("specVersion" in e or "1.4" in e for e in result.errors)

    def test_spec_version_missing_rejected(self) -> None:
        bom = copy.deepcopy(_VALID_BOM_BASE)
        del bom["specVersion"]
        result = validate_cyclonedx(bom)
        assert not result.valid


# ---------------------------------------------------------------------------
# (c) Invalid BOMs are rejected with specific errors
# ---------------------------------------------------------------------------

class TestInvalidBOMs:
    def test_wrong_bom_format(self) -> None:
        bom = _bom(bomFormat="SPDX")
        result = validate_cyclonedx(bom)
        assert not result.valid
        assert any("bomFormat" in e or "CycloneDX" in e or "SPDX" in e for e in result.errors), result.errors

    def test_missing_bom_format(self) -> None:
        bom = copy.deepcopy(_VALID_BOM_BASE)
        del bom["bomFormat"]
        result = validate_cyclonedx(bom)
        assert not result.valid

    def test_version_zero_rejected(self) -> None:
        bom = _bom(version=0)
        result = validate_cyclonedx(bom)
        assert not result.valid
        assert any("version" in e for e in result.errors), result.errors

    def test_version_string_rejected(self) -> None:
        bom = _bom(version="1")
        result = validate_cyclonedx(bom)
        assert not result.valid

    def test_bad_component_type_enum(self) -> None:
        bom = copy.deepcopy(_VALID_BOM_BASE)
        bom["components"][0]["type"] = "widget"  # not a valid CycloneDX type
        result = validate_cyclonedx(bom)
        assert not result.valid
        assert any("widget" in e or "type" in e for e in result.errors), result.errors

    def test_bad_metadata_component_type(self) -> None:
        bom = copy.deepcopy(_VALID_BOM_BASE)
        bom["metadata"]["component"]["type"] = "gadget"
        result = validate_cyclonedx(bom)
        assert not result.valid

    def test_bad_hash_alg(self) -> None:
        bom = copy.deepcopy(_VALID_BOM_BASE)
        bom["metadata"]["component"]["hashes"][0]["alg"] = "MD4"  # not valid
        result = validate_cyclonedx(bom)
        assert not result.valid
        assert any("MD4" in e or "alg" in e for e in result.errors), result.errors

    def test_dangling_depends_on_ref(self) -> None:
        bom = copy.deepcopy(_VALID_BOM_BASE)
        bom["dependencies"][0]["dependsOn"].append("pkg:pypi/nonexistent@9.9.9")
        result = validate_cyclonedx(bom)
        assert not result.valid
        assert any("nonexistent" in e or "bom-ref" in e for e in result.errors), result.errors

    def test_dangling_dependency_ref(self) -> None:
        bom = copy.deepcopy(_VALID_BOM_BASE)
        bom["dependencies"].append({"ref": "pkg:pypi/ghost@1.0.0", "dependsOn": []})
        result = validate_cyclonedx(bom)
        assert not result.valid
        assert any("ghost" in e for e in result.errors), result.errors

    def test_bad_vulnerability_severity(self) -> None:
        bom = copy.deepcopy(_VALID_BOM_BASE)
        bom["vulnerabilities"] = [
            {
                "id": "CVE-2024-0001",
                "ratings": [{"severity": "catastrophic"}],  # not valid
            }
        ]
        result = validate_cyclonedx(bom)
        assert not result.valid
        assert any("catastrophic" in e or "severity" in e for e in result.errors), result.errors

    def test_valid_vulnerability_severity_values(self) -> None:
        """All spec-defined severity values should be accepted."""
        for sev in ("critical", "high", "medium", "low", "info", "none", "unknown"):
            bom = copy.deepcopy(_VALID_BOM_BASE)
            bom["vulnerabilities"] = [
                {"id": "CVE-2024-0001", "ratings": [{"severity": sev}]}
            ]
            result = validate_cyclonedx(bom)
            assert result.valid, f"Severity {sev!r} unexpectedly rejected: {result.errors}"

    def test_non_hex_hash_content_rejected(self) -> None:
        bom = copy.deepcopy(_VALID_BOM_BASE)
        bom["metadata"]["component"]["hashes"][0]["content"] = "not-hex-at-all!!"
        result = validate_cyclonedx(bom)
        assert not result.valid
        assert any("hex" in e or "content" in e for e in result.errors), result.errors

    def test_component_missing_name(self) -> None:
        bom = copy.deepcopy(_VALID_BOM_BASE)
        del bom["components"][0]["name"]
        result = validate_cyclonedx(bom)
        assert not result.valid


# ---------------------------------------------------------------------------
# (d) Extension keys 'findings' and 'rating' do NOT cause rejection
# ---------------------------------------------------------------------------

class TestExtensionKeys:
    def test_findings_key_allowed(self) -> None:
        bom = copy.deepcopy(_VALID_BOM_BASE)
        bom["findings"] = [{"id": "AIBOM-0001", "detail": "something suspicious"}]
        result = validate_cyclonedx(bom)
        assert result.valid, f"findings key caused rejection: {result.errors}"

    def test_rating_key_allowed(self) -> None:
        bom = copy.deepcopy(_VALID_BOM_BASE)
        bom["rating"] = {"grade": "B", "reason": "some risk"}
        result = validate_cyclonedx(bom)
        assert result.valid, f"rating key caused rejection: {result.errors}"

    def test_both_extension_keys_together(self) -> None:
        bom = copy.deepcopy(_VALID_BOM_BASE)
        bom["findings"] = []
        bom["rating"] = {"grade": "A", "reason": "clean"}
        result = validate_cyclonedx(bom)
        assert result.valid, f"extension keys together caused rejection: {result.errors}"

    def test_bom_without_extension_keys_also_valid(self) -> None:
        bom = copy.deepcopy(_VALID_BOM_BASE)
        bom.pop("findings", None)
        bom.pop("rating", None)
        result = validate_cyclonedx(bom)
        assert result.valid, result.errors


# ---------------------------------------------------------------------------
# (e) Built-in fallback path — monkeypatch jsonschema as unavailable
# ---------------------------------------------------------------------------

class TestBuiltinFallback:
    """Force the built-in validator path by making jsonschema appear unavailable."""

    @pytest.fixture(autouse=True)
    def _patch_jsonschema_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import xa_guard.aibom.schema_validator as sv
        monkeypatch.setattr(sv, "_JSONSCHEMA_AVAILABLE", False)
        monkeypatch.setattr(sv, "_jsonschema", None)

    def test_valid_bom_passes_builtin(self) -> None:
        result = validate_cyclonedx(copy.deepcopy(_VALID_BOM_BASE))
        assert result.valid, result.errors
        assert result.validator == "builtin"

    def test_wrong_bom_format_builtin(self) -> None:
        bom = _bom(bomFormat="SPDX")
        result = validate_cyclonedx(bom)
        assert not result.valid
        assert result.validator == "builtin"

    def test_bad_component_type_builtin(self) -> None:
        bom = copy.deepcopy(_VALID_BOM_BASE)
        bom["components"][0]["type"] = "widget"
        result = validate_cyclonedx(bom)
        assert not result.valid

    def test_bad_hash_alg_builtin(self) -> None:
        bom = copy.deepcopy(_VALID_BOM_BASE)
        bom["metadata"]["component"]["hashes"][0]["alg"] = "MD4"
        result = validate_cyclonedx(bom)
        assert not result.valid

    def test_dangling_ref_builtin(self) -> None:
        bom = copy.deepcopy(_VALID_BOM_BASE)
        bom["dependencies"][0]["dependsOn"].append("pkg:pypi/ghost@1.0.0")
        result = validate_cyclonedx(bom)
        assert not result.valid

    def test_bad_vuln_severity_builtin(self) -> None:
        bom = copy.deepcopy(_VALID_BOM_BASE)
        bom["vulnerabilities"] = [
            {"id": "CVE-2024-0001", "ratings": [{"severity": "catastrophic"}]}
        ]
        result = validate_cyclonedx(bom)
        assert not result.valid

    def test_extension_keys_allowed_builtin(self) -> None:
        bom = copy.deepcopy(_VALID_BOM_BASE)
        bom["findings"] = [{"id": "AIBOM-0001", "detail": "ok"}]
        bom["rating"] = {"grade": "A", "reason": "clean"}
        result = validate_cyclonedx(bom)
        assert result.valid, result.errors

    def test_spec_version_15_passes_builtin(self) -> None:
        bom = _bom(specVersion="1.5")
        result = validate_cyclonedx(bom)
        assert result.valid, result.errors

    def test_spec_version_14_rejected_builtin(self) -> None:
        bom = _bom(specVersion="1.4")
        result = validate_cyclonedx(bom)
        assert not result.valid


# ---------------------------------------------------------------------------
# assert_valid helper
# ---------------------------------------------------------------------------

class TestAssertValid:
    def test_assert_valid_passes_for_valid_bom(self) -> None:
        assert_valid(copy.deepcopy(_VALID_BOM_BASE))  # must not raise

    def test_assert_valid_raises_for_invalid_bom(self) -> None:
        bom = _bom(bomFormat="SPDX")
        with pytest.raises(ValueError, match="BOM validation failed"):
            assert_valid(bom)

    def test_assert_valid_error_message_contains_details(self) -> None:
        bom = copy.deepcopy(_VALID_BOM_BASE)
        bom["components"][0]["type"] = "widget"
        with pytest.raises(ValueError) as exc_info:
            assert_valid(bom)
        assert "widget" in str(exc_info.value) or "type" in str(exc_info.value)


# ---------------------------------------------------------------------------
# SchemaValidationResult dataclass contract
# ---------------------------------------------------------------------------

class TestSchemaValidationResultContract:
    def test_result_fields_present(self) -> None:
        result = validate_cyclonedx(copy.deepcopy(_VALID_BOM_BASE))
        assert hasattr(result, "valid")
        assert hasattr(result, "errors")
        assert hasattr(result, "spec_version")
        assert hasattr(result, "validator")

    def test_errors_empty_when_valid(self) -> None:
        result = validate_cyclonedx(copy.deepcopy(_VALID_BOM_BASE))
        assert result.valid
        assert result.errors == []

    def test_spec_version_captured(self) -> None:
        bom = _bom(specVersion="1.6")
        result = validate_cyclonedx(bom)
        assert result.spec_version == "1.6"

    def test_validator_field_is_known_value(self) -> None:
        result = validate_cyclonedx(copy.deepcopy(_VALID_BOM_BASE))
        assert result.validator in ("jsonschema", "builtin")

    def test_default_errors_list(self) -> None:
        r = SchemaValidationResult(valid=True)
        assert r.errors == []
        assert r.spec_version == ""
        assert r.validator == ""
