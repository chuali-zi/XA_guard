from __future__ import annotations

from pathlib import Path

from xa_guard.aibom.gateway import admit, enrich_with_intel
from xa_guard.aibom.intel import ThreatIntel
from xa_guard.aibom.offline_fetch import OfflinePackageStore
from xa_guard.aibom.scanner import scan
from xa_guard.aibom.signing import generate_ed25519_keypair


def _clean_plugin(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
    (root / "main.py").write_text("print('hello')\n", encoding="utf-8")
    return root


def test_admit_clean_plugin_passes_schema_and_allows(tmp_path: Path) -> None:
    plugin = _clean_plugin(tmp_path / "plugin")

    result = admit(plugin)

    assert result.schema_valid is True
    assert result.schema_validator in {"jsonschema", "builtin"}
    assert result.grade in {"A", "B"}
    assert result.decision == "allow"
    assert result.bom["specVersion"] == "1.6"


def test_admit_with_intel_flags_vulnerable_dependency(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    # urllib3 1.26.5 < fixed 1.26.19 → 命中 CVE-2024-37891。
    (plugin / "requirements.txt").write_text("urllib3==1.26.5\n", encoding="utf-8")
    (plugin / "main.py").write_text("print('ok')\n", encoding="utf-8")

    result = admit(plugin, intel=ThreatIntel())

    assert result.vulnerabilities >= 1
    assert result.max_vuln_severity != "none"
    assert "vulnerabilities" in result.bom
    assert any(v["id"].startswith("CVE") for v in result.bom["vulnerabilities"])
    # 评级应因漏洞被下调，不再是 A。
    assert result.grade in {"B", "C", "D", "F"}


def test_enrich_with_intel_is_noop_without_dependencies(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "main.py").write_text("print('ok')\n", encoding="utf-8")
    report = scan(plugin)

    enrich_with_intel(report, ThreatIntel())

    assert report.vulnerabilities == []


def test_admit_signs_and_verifies_with_trust_store(tmp_path: Path) -> None:
    plugin = _clean_plugin(tmp_path / "plugin")
    keys = tmp_path / "keys"
    priv, _pub = generate_ed25519_keypair(str(keys), "xa-aibom-1")

    result = admit(
        plugin,
        sign_key=priv,
        key_id="xa-aibom-1",
        sign_algorithm="ed25519",
        trust_store=str(keys),
    )

    assert "signature" in result.bom
    assert result.signature_verified is True
    assert result.signature_algorithm.lower().startswith("ed25519")


def test_admit_remote_without_offline_store_requires_fetch(tmp_path: Path) -> None:
    result = admit("https://evil.example.com/plugin.tar.gz")

    # 远程引用未提供离线缓存 → 标记需离线拉取，进入人工复核档。
    assert result.decision in {"warn", "deny"}
    assert result.bom["rating"]["grade"] in {"C", "D", "F"}


def test_admit_remote_resolves_from_offline_store(tmp_path: Path) -> None:
    import zipfile

    plugin = _clean_plugin(tmp_path / "plugin")
    archive = tmp_path / "plugin.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for path in plugin.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(plugin))

    store = OfflinePackageStore(tmp_path / "cache")
    url = "https://mirror.internal/plugin.zip"
    store.add(archive, url=url, source_url=url)

    result = admit(url, offline_store=store)

    assert result.schema_valid is True
    assert any(c.get("name") == "requests" for c in result.bom["components"])
    assert result.decision == "allow"


def test_admit_records_drift_across_two_runs(tmp_path: Path) -> None:
    plugin = _clean_plugin(tmp_path / "plugin")
    drift_store = tmp_path / "drift"

    first = admit(plugin, drift_store=drift_store, component_id="demo")
    assert first.drift_changed is False  # 首见只落快照

    (plugin / "main.py").write_text("import subprocess\nsubprocess.Popen(['id'])\n", encoding="utf-8")
    second = admit(plugin, drift_store=drift_store, component_id="demo")

    assert second.drift_changed is True
    assert second.drift_severity in {"medium", "high"}
