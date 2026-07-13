from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


AUTO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AUTO_ROOT))

from maintain import (  # noqa: E402
    InstanceLock,
    Maintainer,
    atomic_json,
    latest_mtime,
    pid_alive,
    preflight,
)


def test_atomic_json_and_pid_health(tmp_path):
    path = tmp_path / "status.json"
    atomic_json(path, {"state": "running"})
    assert json.loads(path.read_text(encoding="utf-8"))["state"] == "running"
    assert pid_alive(__import__("os").getpid())
    assert not pid_alive(-1)


def test_instance_lock_reclaims_stale_lock(tmp_path):
    path = tmp_path / "maintainer.lock"
    path.write_text('{"pid": -1}', encoding="utf-8")
    with InstanceLock(path):
        assert path.exists()
    assert not path.exists()


def test_progress_mtime_ignores_maintainer_heartbeat(tmp_path):
    state = tmp_path / "state"
    maintainer = state / "maintainer"
    state.mkdir()
    progress = state / "state.json"
    progress.write_text("{}", encoding="utf-8")
    before = latest_mtime(state, ignore=maintainer)
    maintainer.mkdir()
    (maintainer / "status.json").write_text("{}", encoding="utf-8")
    assert latest_mtime(state, ignore=maintainer) == before


def test_preflight_reports_missing_conductor_and_config(tmp_path):
    args = argparse.Namespace(
        config=tmp_path / "missing.yaml",
        stale_after_s=10,
        check_interval_s=10,
        max_restarts=0,
    )
    errors = preflight(args)
    assert any("config not found" in error for error in errors)
    assert any("stale-after" in error for error in errors)
    assert any("max-restarts" in error for error in errors)


def test_maintainer_restarts_failed_child_then_completes(tmp_path, monkeypatch):
    counter = tmp_path / "counter.txt"
    child = tmp_path / "child.py"
    child.write_text(
        "from pathlib import Path\n"
        f"p=Path({str(counter)!r})\n"
        "n=int(p.read_text() or '0') if p.exists() else 0\n"
        "p.write_text(str(n+1))\n"
        "raise SystemExit(1 if n == 0 else 0)\n",
        encoding="utf-8",
    )
    config = tmp_path / "config.yaml"
    config.write_text("continuous: true\n", encoding="utf-8")
    args = argparse.Namespace(
        config=config,
        runtime=tmp_path / "runtime",
        state_dir=tmp_path / "state",
        continuous=True,
        check_interval_s=0.02,
        stale_after_s=5,
        stop_grace_s=0.2,
        max_restarts=2,
        restart_window_s=60,
        backoff_initial_s=0.01,
        backoff_max_s=0.01,
        log_max_bytes=100000,
        log_backups=1,
    )
    maintainer = Maintainer(args)
    monkeypatch.setattr(maintainer, "command", lambda: [sys.executable, str(child)])
    assert maintainer.run() == 0
    status = json.loads((args.runtime / "status.json").read_text(encoding="utf-8"))
    assert status["state"] == "completed"
    assert int(counter.read_text(encoding="utf-8")) == 2


def test_status_command_detects_dead_process(tmp_path):
    runtime = tmp_path / "runtime"
    atomic_json(
        runtime / "status.json",
        {"state": "running", "supervisor_pid": -1, "child_pid": -1},
    )
    result = subprocess.run(
        [sys.executable, str(AUTO_ROOT / "maintain.py"), "status", "--runtime", str(runtime)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 3
    assert json.loads(result.stdout)["healthy"] is False
