from __future__ import annotations

from pathlib import Path

from xa_guard.aibom.drift_monitor import DriftMonitor
from xa_guard.aibom.scanner import scan


def _write_plugin(root: Path, requirements: str, main: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "requirements.txt").write_text(requirements, encoding="utf-8")
    (root / "main.py").write_text(main, encoding="utf-8")
    return root


def test_first_record_only_snapshots_no_event(tmp_path: Path) -> None:
    plugin = _write_plugin(tmp_path / "plugin", "requests==2.31.0\n", "print('ok')\n")
    monitor = DriftMonitor(tmp_path / "store")

    result = monitor.record(scan(plugin), component_id="demo")

    assert result.first_seen is True
    assert result.changed is False
    assert result.event is None
    assert monitor.latest_snapshot("demo") is not None
    assert monitor.history() == []


def test_no_change_second_record_reports_no_drift(tmp_path: Path) -> None:
    plugin = _write_plugin(tmp_path / "plugin", "requests==2.31.0\n", "print('ok')\n")
    monitor = DriftMonitor(tmp_path / "store")
    monitor.record(scan(plugin), component_id="demo")

    result = monitor.record(scan(plugin), component_id="demo")

    assert result.changed is False
    assert monitor.history("demo") == []


def test_dangerous_capability_addition_is_high_severity(tmp_path: Path) -> None:
    plugin = _write_plugin(tmp_path / "plugin", "requests==2.31.0\n", "print('ok')\n")
    monitor = DriftMonitor(tmp_path / "store")
    monitor.record(scan(plugin), component_id="demo")

    # 上线后偷偷加了 subprocess 进程执行能力。
    (plugin / "main.py").write_text("import subprocess\nsubprocess.Popen(['id'])\n", encoding="utf-8")
    result = monitor.record(scan(plugin), component_id="demo")

    assert result.changed is True
    assert result.event is not None
    assert result.event.severity == "high"
    assert "drift_capability_change" in result.event.drift_keys
    history = monitor.history("demo")
    assert len(history) == 1
    assert history[0].severity == "high"


def test_benign_dependency_change_is_medium(tmp_path: Path) -> None:
    plugin = _write_plugin(tmp_path / "plugin", "requests==2.31.0\n", "print('ok')\n")
    monitor = DriftMonitor(tmp_path / "store")
    monitor.record(scan(plugin), component_id="demo")

    (plugin / "requirements.txt").write_text("httpx==0.27.0\n", encoding="utf-8")
    result = monitor.record(scan(plugin), component_id="demo")

    assert result.changed is True
    assert result.event is not None
    assert result.event.severity in {"medium", "high"}
    assert "drift_dependency_change" in result.event.drift_keys


def test_scan_and_record_and_history_filtering(tmp_path: Path) -> None:
    plugin_a = _write_plugin(tmp_path / "a", "requests==2.31.0\n", "print('ok')\n")
    plugin_b = _write_plugin(tmp_path / "b", "httpx==0.27.0\n", "print('ok')\n")
    monitor = DriftMonitor(tmp_path / "store")

    monitor.scan_and_record(plugin_a, component_id="a")
    monitor.scan_and_record(plugin_b, component_id="b")
    (plugin_a / "main.py").write_text("eval('1+1')\n", encoding="utf-8")
    monitor.scan_and_record(plugin_a, component_id="a")

    assert len(monitor.history()) == 1
    assert len(monitor.history("a")) == 1
    assert monitor.history("b") == []
