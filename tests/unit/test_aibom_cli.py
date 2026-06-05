from __future__ import annotations

import json
from pathlib import Path

from xa_guard.aibom.cli import main


def _clean_plugin(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
    (root / "main.py").write_text("print('ok')\n", encoding="utf-8")
    return root


def test_cli_admit_allows_clean_plugin(tmp_path: Path, capsys) -> None:
    plugin = _clean_plugin(tmp_path / "plugin")

    code = main(["admit", str(plugin)])
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert out["decision"] == "allow"
    assert out["schema_valid"] is True


def test_cli_bom_writes_cyclonedx_16(tmp_path: Path, capsys) -> None:
    plugin = _clean_plugin(tmp_path / "plugin")
    out_path = tmp_path / "bom.json"

    code = main(["bom", str(plugin), "--out", str(out_path)])

    assert code == 0
    bom = json.loads(out_path.read_text(encoding="utf-8"))
    assert bom["specVersion"] == "1.6"
    assert bom["bomFormat"] == "CycloneDX"


def test_cli_validate_reports_valid(tmp_path: Path, capsys) -> None:
    from xa_guard.aibom.exporter import export_cyclonedx
    from xa_guard.aibom.scanner import scan

    plugin = _clean_plugin(tmp_path / "plugin")
    bom_path = tmp_path / "bom.json"
    bom_path.write_text(json.dumps(export_cyclonedx(scan(plugin))), encoding="utf-8")

    code = main(["validate", str(bom_path)])
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert out["valid"] is True


def test_cli_validate_rejects_broken_bom(tmp_path: Path, capsys) -> None:
    bom_path = tmp_path / "bad.json"
    bom_path.write_text(json.dumps({"bomFormat": "NOPE", "specVersion": "9.9", "version": 1}), encoding="utf-8")

    code = main(["validate", str(bom_path)])
    out = json.loads(capsys.readouterr().out)

    assert code == 2
    assert out["valid"] is False
    assert out["errors"]


def test_cli_drift_first_then_change(tmp_path: Path, capsys) -> None:
    plugin = _clean_plugin(tmp_path / "plugin")
    store = tmp_path / "drift"

    code1 = main(["drift", str(plugin), "--store", str(store), "--component", "demo"])
    capsys.readouterr()
    (plugin / "main.py").write_text("import subprocess\nsubprocess.Popen(['id'])\n", encoding="utf-8")
    code2 = main(["drift", str(plugin), "--store", str(store), "--component", "demo"])
    out2 = json.loads(capsys.readouterr().out)

    assert code1 == 0
    assert code2 == 2  # high severity → non-zero exit
    assert out2["changed"] is True
    assert out2["event"]["severity"] == "high"
