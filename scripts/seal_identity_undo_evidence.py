"""Create a deterministic, strictly SM2-signed Identity + Undo evidence manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from xa_guard.audit.sm_crypto import sm2_key_id, sm2_public_key_hex, sm2_sign_strict

try:
    from scripts.verify_identity_undo_evidence import (
        DEFAULT_MANIFEST,
        DEFAULT_SCHEMA,
        EvidenceError,
        enumerate_bundle_files,
        normalize_artifact_path,
        scan_bundle_for_secrets,
        scan_secret_bytes,
        unsigned_manifest_bytes,
        validate_against_json_schema,
        validate_manifest_shape,
        verify_acceptance,
        verify_artifacts,
        verify_bundle,
        verify_chains_and_links,
        verify_effect_chain,
        verify_gate6_chain,
        resolve_bundle_file,
    )
except ModuleNotFoundError:  # pragma: no cover - direct ``python scripts/...`` execution
    from verify_identity_undo_evidence import (  # type: ignore[no-redef]
        DEFAULT_MANIFEST,
        DEFAULT_SCHEMA,
        EvidenceError,
        enumerate_bundle_files,
        normalize_artifact_path,
        scan_bundle_for_secrets,
        scan_secret_bytes,
        unsigned_manifest_bytes,
        validate_against_json_schema,
        validate_manifest_shape,
        verify_acceptance,
        verify_artifacts,
        verify_bundle,
        verify_chains_and_links,
        verify_effect_chain,
        verify_gate6_chain,
        resolve_bundle_file,
    )


def _load_metadata(path: str | Path) -> dict[str, Any]:
    metadata_path = Path(path)

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant is not allowed: {value}")

    try:
        value = json.loads(metadata_path.read_text(encoding="utf-8"), parse_constant=reject_constant)
    except Exception as exc:
        raise EvidenceError(f"invalid sealing metadata: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError("sealing metadata must be a JSON object")
    expected = {"run", "source", "images", "tools", "chains", "cross_links", "acceptance"}
    if set(value) != expected:
        raise EvidenceError(f"sealing metadata keys must be exactly {sorted(expected)}")
    return value


def _normalized_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    try:
        images = sorted((dict(item) for item in metadata["images"]), key=lambda item: item["name"])
        tools = sorted((dict(item) for item in metadata["tools"]), key=lambda item: item["name"])
        assertions = []
        for item in metadata["acceptance"]["assertions"]:
            assertion = dict(item)
            assertion["evidence"] = sorted(assertion["evidence"])
            assertions.append(assertion)
        assertions.sort(key=lambda item: item["id"])
        boundaries = sorted(
            (dict(item) for item in metadata["acceptance"]["boundaries"]), key=lambda item: item["id"]
        )
        chains = {
            "gate6": dict(metadata["chains"]["gate6"]),
            "effect": dict(metadata["chains"]["effect"]),
        }
    except (KeyError, TypeError) as exc:
        raise EvidenceError(f"invalid sealing metadata structure: {exc}") from exc
    for name, chain in chains.items():
        if set(chain) != {"path", "algorithm"}:
            raise EvidenceError(f"metadata chains.{name} requires only path and algorithm")
        normalize_artifact_path(chain["path"])
    return {
        "run": dict(metadata["run"]),
        "source": dict(metadata["source"]),
        "images": images,
        "tools": tools,
        "chains": chains,
        "cross_links": dict(metadata["cross_links"]),
        "acceptance": {"assertions": assertions, "boundaries": boundaries},
    }


def _external_private_key(bundle: str | Path, private_key: str | Path) -> Path:
    root = Path(bundle).resolve(strict=True)
    key = Path(private_key)
    if key.is_symlink():
        raise EvidenceError("SM2 private key must not be a symlink")
    try:
        resolved = key.resolve(strict=True)
    except FileNotFoundError as exc:
        raise EvidenceError("SM2 private key file does not exist") from exc
    if not resolved.is_file():
        raise EvidenceError("SM2 private key path is not a regular file")
    try:
        resolved.relative_to(root)
    except ValueError:
        return resolved
    raise EvidenceError("SM2 private key must remain outside the evidence bundle")


def _artifact_entries(bundle: str | Path, paths: list[str]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for relative in paths:
        data = resolve_bundle_file(bundle, relative).read_bytes()
        artifacts.append({"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    return artifacts


def _write_manifest_atomic(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", dir=path.parent, prefix=".xa-evidence-", delete=False
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def seal_bundle(
    bundle: str | Path,
    metadata_path: str | Path,
    private_key: str | Path,
    *,
    manifest_name: str = DEFAULT_MANIFEST,
    schema_path: str | Path = DEFAULT_SCHEMA,
) -> dict[str, Any]:
    manifest_name = normalize_artifact_path(manifest_name)
    root = Path(bundle).resolve(strict=True)
    if not root.is_dir() or Path(bundle).is_symlink():
        raise EvidenceError("evidence bundle must be a real directory")
    output = root.joinpath(*manifest_name.split("/"))
    if output.exists() and output.is_symlink():
        raise EvidenceError("manifest output must not be a symlink")
    key_path = _external_private_key(root, private_key)
    metadata = _normalized_metadata(_load_metadata(metadata_path))
    paths = enumerate_bundle_files(root, exclude=[manifest_name])
    if not paths:
        raise EvidenceError("cannot seal an empty evidence bundle")
    scan_bundle_for_secrets(root, paths)

    gate6 = metadata["chains"]["gate6"]
    effect = metadata["chains"]["effect"]
    gate6_records = verify_gate6_chain(resolve_bundle_file(root, gate6["path"]), gate6["algorithm"])
    effect_records = verify_effect_chain(resolve_bundle_file(root, effect["path"]), effect["algorithm"])
    chains = {
        "gate6": {**gate6, "records": len(gate6_records)},
        "effect": {**effect, "records": len(effect_records)},
    }
    manifest: dict[str, Any] = {
        "schema": "xa-guard-evidence/v1",
        "run": metadata["run"],
        "source": metadata["source"],
        "images": metadata["images"],
        "tools": metadata["tools"],
        "artifacts": _artifact_entries(root, paths),
        "chains": chains,
        "cross_links": metadata["cross_links"],
        "acceptance": metadata["acceptance"],
        "signature": {
            "algorithm": "SM2-with-SM3",
            "key_id": "0" * 16,
            "public_key": "0" * 128,
            "value": "0" * 128,
        },
    }

    # Validate all producer-independent evidence before a signature is issued.
    validate_manifest_shape(manifest)
    verify_artifacts(root, manifest, manifest_name)
    verify_acceptance(manifest)
    verify_chains_and_links(root, manifest)

    try:
        public_key = sm2_public_key_hex(str(key_path))
        key_id = sm2_key_id(str(key_path))
        manifest["signature"] = {
            "algorithm": "SM2-with-SM3",
            "key_id": key_id,
            "public_key": public_key,
            "value": "0" * 128,
        }
        unsigned_findings = scan_secret_bytes(manifest_name, unsigned_manifest_bytes(manifest))
        if unsigned_findings:
            raise EvidenceError("manifest metadata secret scan failed: " + "; ".join(unsigned_findings))
        manifest["signature"]["value"] = sm2_sign_strict(unsigned_manifest_bytes(manifest), str(key_path))
    except Exception as exc:
        if isinstance(exc, EvidenceError):
            raise
        raise EvidenceError(f"strict SM2-with-SM3 signing failed: {exc}") from exc
    validate_manifest_shape(manifest)
    validate_against_json_schema(manifest, schema_path)
    _write_manifest_atomic(output, manifest)
    try:
        result = verify_bundle(root, manifest_name=manifest_name, schema_path=schema_path)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seal XA-Guard Identity + Undo evidence")
    parser.add_argument("--bundle", required=True, help="evidence bundle directory")
    parser.add_argument("--metadata", required=True, help="public sealing metadata JSON")
    parser.add_argument("--private-key", required=True, help="SM2 private key file outside the bundle")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST, help="manifest path relative to bundle")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="xa-guard-evidence/v1 JSON Schema")
    args = parser.parse_args(argv)
    try:
        result = seal_bundle(
            args.bundle,
            args.metadata,
            args.private_key,
            manifest_name=args.manifest,
            schema_path=args.schema,
        )
    except (EvidenceError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
