"""Run L3 R8 AIBOM external-exchange and admission acceptance evidence.

The script consumes an already generated external CycloneDX 1.6 BOM. By
default it uses the cdxgen evidence archived under docs/acceptance/r8-aibom-
external, then creates fresh local artifact positive/negative samples for the
current run. It does not download or execute an external generator.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from xa_guard.aibom.external_generator import ExternalGeneratorSpec, load_external_cyclonedx
from xa_guard.aibom.gateway import admit_install_request

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = (
    ROOT
    / "docs"
    / "acceptance"
    / "r8-aibom-external"
    / "evidence"
    / "l3-r8-aibom-20260707T105519Z"
)
DEFAULT_BOM = DEFAULT_EVIDENCE / "aibom.cdxgen.json"
DEFAULT_SHA = DEFAULT_EVIDENCE / "aibom.sha256"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _expected_sha(path: Path, sha_file: Path | None) -> str:
    if sha_file and sha_file.exists():
        text = sha_file.read_text(encoding="utf-8").strip()
        parts = text.replace("\r", "").split()
        if parts and len(parts[0]) == 64:
            return parts[0].lower()
    return _sha256(path)


def _run_cli(args: list[str]) -> dict[str, Any]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-m", "xa_guard.aibom.cli", *args],
        cwd=str(ROOT),
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    parsed: Any = None
    try:
        parsed = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        parsed = None
    return {
        "argv": ["python", "-m", "xa_guard.aibom.cli", *args],
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "json": parsed,
    }


def _write_zip(root: Path, archive: Path) -> Path:
    with zipfile.ZipFile(archive, "w") as zf:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(root))
    return archive


def _make_artifacts(out_dir: Path) -> dict[str, Path]:
    samples = out_dir / "samples"
    clean = samples / "clean-plugin"
    risky = samples / "risky-plugin"
    clean.mkdir(parents=True, exist_ok=True)
    risky.mkdir(parents=True, exist_ok=True)
    (clean / "main.py").write_text("print('clean')\n", encoding="utf-8")
    (clean / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
    (risky / "main.py").write_text(
        "import subprocess\nsubprocess.Popen(['cmd', '/c', 'echo risky'])\n",
        encoding="utf-8",
    )
    clean_zip = _write_zip(clean, out_dir / "clean-plugin.zip")
    risky_zip = _write_zip(risky, out_dir / "risky-plugin.zip")
    return {"clean_dir": clean, "risky_dir": risky, "clean_zip": clean_zip, "risky_zip": risky_zip}


def _hash_manifest(out_dir: Path) -> None:
    artifacts = []
    for path in sorted(out_dir.rglob("*")):
        if path.is_file() and path.name != "artifact-hashes.json":
            artifacts.append({"path": str(path.relative_to(out_dir)), "bytes": path.stat().st_size, "sha256": _sha256(path)})
    (out_dir / "artifact-hashes.json").write_text(
        json.dumps({"schema_version": "xa-artifact-hashes/v1", "artifacts": artifacts}, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def run(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    bom_path = Path(args.bom).resolve()
    expected_sha = args.expected_sha256 or _expected_sha(bom_path, Path(args.sha_file).resolve() if args.sha_file else None)

    generator = ExternalGeneratorSpec(
        name=args.generator_name,
        source=args.generator_source,
        version=args.generator_version,
        license_expression=args.generator_license,
        commands=(tuple(args.generator_command),),
    )
    exchange_error = ""
    exchange = None
    try:
        exchange = load_external_cyclonedx(bom_path, expected_sha256=expected_sha, generator=generator)
    except Exception as exc:
        exchange_error = f"{type(exc).__name__}: {exc}"

    artifacts = _make_artifacts(out_dir)
    clean_sha = _sha256(artifacts["clean_zip"])
    risky_sha = _sha256(artifacts["risky_zip"])

    tampered_bom = out_dir / "tampered-valid-bom.json"
    tampered = json.loads(bom_path.read_text(encoding="utf-8"))
    tampered["version"] = int(tampered.get("version", 1)) + 1
    tampered_bom.write_text(json.dumps(tampered, ensure_ascii=False, indent=2), encoding="utf-8")

    missing_bom = out_dir / "missing-field-bom.json"
    missing = json.loads(bom_path.read_text(encoding="utf-8"))
    missing.pop("bomFormat", None)
    missing_bom.write_text(json.dumps(missing, ensure_ascii=False, indent=2), encoding="utf-8")

    cli = {
        "validate_external": _run_cli(["validate", str(bom_path), "--expected-sha256", expected_sha]),
        "validate_tampered_hash_mismatch": _run_cli(["validate", str(tampered_bom), "--expected-sha256", expected_sha]),
        "validate_missing_field": _run_cli(["validate", str(missing_bom)]),
        "admit_clean_artifact": _run_cli(["admit", str(artifacts["clean_zip"]), "--expected-sha256", clean_sha]),
        "admit_clean_artifact_hash_mismatch": _run_cli(
            ["admit", str(artifacts["clean_zip"]), "--expected-sha256", "0" * 64]
        ),
        "admit_risky_artifact": _run_cli(["admit", str(artifacts["risky_zip"]), "--expected-sha256", risky_sha]),
    }

    install_chain = {
        "clean": admit_install_request(
            {"name": "clean-plugin", "artifact_path": str(artifacts["clean_zip"]), "expected_sha256": clean_sha}
        ).__dict__,
        "malicious_snippet": admit_install_request(
            {"name": "bad-plugin", "code_snippet": "import subprocess\nsubprocess.Popen(['evil'])"}
        ).__dict__,
    }

    expectations = {
        "external_import": exchange is not None,
        "validate_external_exit0": cli["validate_external"]["returncode"] == 0,
        "tampered_hash_exit2": cli["validate_tampered_hash_mismatch"]["returncode"] == 2,
        "missing_field_exit2": cli["validate_missing_field"]["returncode"] == 2,
        "clean_admit_exit0": cli["admit_clean_artifact"]["returncode"] == 0,
        "clean_hash_mismatch_exit2": cli["admit_clean_artifact_hash_mismatch"]["returncode"] == 2,
        "risky_admit_exit2": cli["admit_risky_artifact"]["returncode"] == 2,
        "install_chain_clean_allow": install_chain["clean"]["decision"] == "allow",
        "install_chain_malicious_deny": install_chain["malicious_snippet"]["decision"] == "deny",
    }
    status = "pass" if all(expectations.values()) else "fail"
    report: dict[str, Any] = {
        "schema_version": "xa-l3-r8-aibom-acceptance/v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "external_bom": {
            "path": str(bom_path),
            "expected_sha256": expected_sha,
            "actual_sha256": _sha256(bom_path),
            "import_error": exchange_error,
            "spec_version": exchange.bom.get("specVersion") if exchange else "",
            "components": len(exchange.bom.get("components", [])) if exchange else 0,
            "generator": generator.as_dict(),
        },
        "cli": cli,
        "install_chain": install_chain,
        "expectations": expectations,
        "boundary": {
            "marketplace_or_ide_native_install_chain": "not_claimed",
            "note": "This run proves external CycloneDX exchange plus offline xa-aibom/install_plugin admission; it does not claim a marketplace/IDE native store hook.",
        },
    }
    report_path = out_dir / "r8-aibom-acceptance-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    _hash_manifest(out_dir)
    print(json.dumps({"status": status, "report": str(report_path)}, ensure_ascii=False, indent=2))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--bom", default=str(DEFAULT_BOM))
    parser.add_argument("--sha-file", default=str(DEFAULT_SHA))
    parser.add_argument("--expected-sha256", default="")
    parser.add_argument("--generator-name", default="@cyclonedx/cdxgen")
    parser.add_argument("--generator-source", default="https://github.com/cdxgen/cdxgen")
    parser.add_argument("--generator-version", default="12.7.0")
    parser.add_argument("--generator-license", default="Apache-2.0")
    parser.add_argument(
        "--generator-command",
        nargs="+",
        default=[
            "npx",
            "--yes",
            "@cyclonedx/cdxgen@12.7.0",
            "-r",
            "-t",
            "python",
            "--profile",
            "research",
            "--spec-version",
            "1.6",
        ],
    )
    args = parser.parse_args()
    report = run(args)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
