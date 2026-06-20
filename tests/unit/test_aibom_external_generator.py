from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from xa_guard.aibom.external_generator import (
    ExternalGeneratorError,
    ExternalGeneratorSpec,
    load_external_cyclonedx,
)


def _generator() -> ExternalGeneratorSpec:
    return ExternalGeneratorSpec(
        name="fixture-generator",
        source="https://example.invalid/source/fixture-generator",
        version="1.2.3-fixture",
        license_expression="Apache-2.0",
        commands=(("fixture-generator", "--format", "cyclonedx-json", "--output", "bom.json"),),
    )


def _bom_bytes(*, spec_version: str = "1.6") -> bytes:
    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": spec_version,
        "version": 1,
        "components": [
            {"type": "library", "name": "fixture-lib", "bom-ref": "pkg:pypi/fixture-lib@1.0"}
        ],
        "dependencies": [{"ref": "pkg:pypi/fixture-lib@1.0", "dependsOn": []}],
    }
    return json.dumps(bom, sort_keys=True, separators=(",", ":")).encode()


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def test_load_bytes_preserves_provenance_and_validates_schema() -> None:
    output = _bom_bytes()
    exchange = load_external_cyclonedx(
        output, expected_sha256=_sha256(output), generator=_generator()
    )
    assert exchange.sha256 == _sha256(output)
    assert exchange.schema_validation.valid is True
    assert exchange.generator.as_dict()["commands"] == [
        ["fixture-generator", "--format", "cyclonedx-json", "--output", "bom.json"]
    ]


def test_load_path_hashes_exact_file_bytes(tmp_path: Path) -> None:
    output = _bom_bytes()
    path = tmp_path / "bom.json"
    path.write_bytes(output)
    exchange = load_external_cyclonedx(
        path, expected_sha256=_sha256(output).upper(), generator=_generator()
    )
    assert exchange.bom["components"][0]["name"] == "fixture-lib"


def test_rejects_sha256_mismatch() -> None:
    output = _bom_bytes()
    with pytest.raises(ExternalGeneratorError, match="SHA-256 mismatch"):
        load_external_cyclonedx(output, expected_sha256="0" * 64, generator=_generator())


def test_rejects_schema_valid_but_wrong_exchange_version() -> None:
    output = _bom_bytes(spec_version="1.5")
    with pytest.raises(ExternalGeneratorError, match="specVersion ''1.6''"):
        load_external_cyclonedx(output, expected_sha256=_sha256(output), generator=_generator())


def test_rejects_output_that_fails_existing_schema() -> None:
    output = b'{"bomFormat":"CycloneDX","specVersion":"1.6","version":1,"components":[{"type":"not-a-type","name":"x"}]}'
    with pytest.raises(ExternalGeneratorError, match="schema validation"):
        load_external_cyclonedx(output, expected_sha256=_sha256(output), generator=_generator())


@pytest.mark.parametrize("missing", ["name", "source", "version", "license_expression"])
def test_generator_identity_fields_are_mandatory(missing: str) -> None:
    values = {
        "name": "fixture-generator",
        "source": "https://example.invalid/source",
        "version": "1.0",
        "license_expression": "MIT",
    }
    values[missing] = ""
    with pytest.raises(ExternalGeneratorError, match=missing):
        ExternalGeneratorSpec(**values, commands=(("fixture-generator",),))


def test_command_inventory_is_mandatory() -> None:
    with pytest.raises(ExternalGeneratorError, match="commands"):
        ExternalGeneratorSpec("fixture", "local fixture", "1.0", "MIT", ())


def test_rejects_duplicate_json_keys() -> None:
    output = b'{"bomFormat":"CycloneDX","specVersion":"1.6","specVersion":"1.6","version":1}'
    with pytest.raises(ExternalGeneratorError, match="duplicate JSON object key"):
        load_external_cyclonedx(output, expected_sha256=_sha256(output), generator=_generator())


def test_rejects_oversized_fixture_without_execution() -> None:
    output = _bom_bytes()
    with pytest.raises(ExternalGeneratorError, match="exceeds max_bytes"):
        load_external_cyclonedx(
            output,
            expected_sha256=_sha256(output),
            generator=_generator(),
            max_bytes=len(output) - 1,
        )



def test_rejects_missing_generator_provenance() -> None:
    output = _bom_bytes()
    with pytest.raises(ExternalGeneratorError, match="ExternalGeneratorSpec"):
        load_external_cyclonedx(
            output,
            expected_sha256=_sha256(output),
            generator=None,  # type: ignore[arg-type]
        )
