"""Offline tests for tools/remote-runner/supervisor.py.

No network, no model calls, no money: the orchestrator is replaced by
fake_orchestrator.py via XA_RUNNER_EXEC_OVERRIDE and both gates are disabled
through the runner config (empty network_urls list, clock_enabled=false).
Requires `sh` on PATH (Git Bash on Windows, any POSIX shell on Linux).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FAKE = Path(__file__).with_name("fake_orchestrator.py")

spec = importlib.util.spec_from_file_location(
    "xa_supervisor", REPO / "tools" / "remote-runner" / "supervisor.py"
)
supervisor_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supervisor_module)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    home = tmp_path / "xa-runner"
    home.mkdir()
    evidence = tmp_path / "xa-evidence"
    runner_config = {
        "shorthost": "test01",
        "operator": "pytest",
        "repo_dir": str(REPO.as_posix()),
        "acceptance_template": "configs/r2-r3-acceptance.example.json",
        "gates": {"clock_enabled": False, "network_urls": []},
        "batch": {"max_jobs": 8, "reduced_max_jobs": 2, "cooldown_seconds": 0},
        "quota": {"poll_seconds": 0, "warn_after_hours": 24},
        "heartbeat_seconds": 0,
    }
    (home / "runner.json").write_text(json.dumps(runner_config), encoding="utf-8")
    scenario = tmp_path / "scenario.json"
    monkeypatch.setenv("XA_RUNNER_HOME", str(home))
    monkeypatch.setenv("XA_EVIDENCE_ROOT", str(evidence))
    monkeypatch.setenv(
        "XA_RUNNER_EXEC_OVERRIDE",
        f"{Path(sys.executable).as_posix()} {FAKE.as_posix()}",
    )
    monkeypatch.setenv("XA_FAKE_SCENARIO", str(scenario))
    return type("Env", (), {"home": home, "evidence": evidence, "scenario": scenario, "tmp": tmp_path})


def write_scenario(env, steps):
    env.scenario.write_text(json.dumps(steps), encoding="utf-8")


def make_supervisor(env):
    return supervisor_module.Supervisor(env.home)


def init_run(env, monkeypatch):
    write_scenario(env, [{"exit": 0, "stdout": "planned"}])
    sup = make_supervisor(env)
    assert sup.cmd_init(skip_plan=False) == 0
    fresh = make_supervisor(env)
    monkeypatch.setenv("XA_FAKE_OUTPUT_DIR", str(fresh.orchestrator_dir))
    env.scenario.with_suffix(".counter").unlink()
    env.scenario.with_suffix(".calls.jsonl").unlink()  # drop init's budget-plan call
    return fresh


def set_phase(sup, phase):
    state = sup.load_state()
    state["phase"] = phase
    sup.save_state(state)


def read_alert_codes(sup):
    path = sup.sup_dir / "ALERTS.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line)["code"] for line in path.read_text(encoding="utf-8").splitlines()]


def test_init_creates_spec_run_layout(env, monkeypatch):
    sup = init_run(env, monkeypatch)
    assert sup.run_id.startswith("l3-r2r3-budget60-")
    assert sup.run_id.endswith("-test01")
    run_dir = env.evidence / "runs" / sup.run_id
    for name in ("meta.json", "environment.txt", "commands.txt", "console.log", "RESULTS.md"):
        assert (run_dir / name).is_file(), name
    local = json.loads(sup.local_config.read_text(encoding="utf-8"))
    assert local["output_dir"] == sup.orchestrator_dir.as_posix()
    assert sup.load_state()["phase"] == "READY"
    # budget-plan was recorded with transcript discipline
    assert "budget-plan" in (run_dir / "commands.txt").read_text(encoding="utf-8")
    assert "planned" in (run_dir / "console.log").read_text(encoding="utf-8")


def test_ready_waits_for_calibration_gate(env, monkeypatch):
    sup = init_run(env, monkeypatch)
    write_scenario(env, [{"exit": 0}])
    sup.cmd_run(max_loops=2)
    assert sup.load_state()["phase"] == "READY"
    health = json.loads((sup.sup_dir / "health.json").read_text(encoding="utf-8"))
    assert health["phase"] == "READY"
    assert not env.scenario.with_suffix(".calls.jsonl").exists()  # nothing paid was run


def test_calibration_runs_until_no_pending(env, monkeypatch):
    sup = init_run(env, monkeypatch)
    write_scenario(env, [
        {"exit": 0, "stdout": "BATCH_COMPLETE remaining_jobs=8"},
        {"exit": 0, "stdout": "BATCH_COMPLETE no pending jobs"},
    ])
    sup.cmd_approve("calibration")
    sup.cmd_run(max_loops=4)
    assert sup.load_state()["phase"] == "CALIB_DONE"
    calls = [json.loads(line) for line in env.scenario.with_suffix(".calls.jsonl").read_text().splitlines()]
    assert all(call[0] == "budget-resume" and "--phase" in call and "calibration" in call for call in calls)
    assert all("--max-jobs" in call for call in calls)


def test_exit1_reduces_batch_size_then_recovers(env, monkeypatch):
    sup = init_run(env, monkeypatch)
    write_scenario(env, [
        {"exit": 1, "stdout": "[1/8] RUN attempt=1 j1\n[1/8] FAILED j1"},
        {"exit": 0, "stdout": "BATCH_COMPLETE remaining_jobs=3"},
    ])
    sup.cmd_approve("calibration")
    sup.cmd_run(max_loops=3)
    calls = [json.loads(line) for line in env.scenario.with_suffix(".calls.jsonl").read_text().splitlines()]
    max_jobs_args = [call[call.index("--max-jobs") + 1] for call in calls]
    assert max_jobs_args[0] == "8"
    assert max_jobs_args[1] == "2"  # reduced after the failed batch
    assert sup.load_state()["current_max_jobs"] == 8  # restored after the clean batch


def test_quota_pause_waits_without_halting(env, monkeypatch):
    sup = init_run(env, monkeypatch)
    write_scenario(env, [{"exit": 4, "stdout": "PROVIDER_QUOTA_PAUSED j1"}])
    sup.cmd_approve("calibration")
    sup.cmd_run(max_loops=3)
    assert sup.load_state()["phase"] == "CALIBRATION"
    assert not sup.halt_file.is_file()
    assert "quota_paused" in read_alert_codes(sup)


def test_budget_exhausted_halts(env, monkeypatch):
    sup = init_run(env, monkeypatch)
    write_scenario(env, [{"exit": 2, "stdout": "BUDGET_EXHAUSTED total"}])
    sup.cmd_approve("calibration")
    sup.cmd_run(max_loops=3)
    assert sup.halt_file.is_file()
    assert json.loads(sup.halt_file.read_text())["reason"] == "budget_exhausted"
    # halted loop only heartbeats; revive clears the flag
    sup.cmd_run(max_loops=1)
    assert json.loads((sup.sup_dir / "health.json").read_text())["halted"] is True
    sup.cmd_revive()
    assert not sup.halt_file.is_file()


def test_lock_drift_halts(env, monkeypatch):
    sup = init_run(env, monkeypatch)
    write_scenario(env, [{"exit": 3, "stdout": "EXECUTION_LOCK_FAILED execution_commit_changed:repository"}])
    sup.cmd_approve("calibration")
    sup.cmd_run(max_loops=2)
    assert json.loads(sup.halt_file.read_text())["reason"] == "execution_lock_failed"


def test_failed_terminal_burst_trips_breaker(env, monkeypatch):
    sup = init_run(env, monkeypatch)
    terminal = {"status": "FAILED_TERMINAL", "attempts": [{}, {}]}
    write_scenario(env, [{
        "exit": 1,
        "stdout": "[1/8] FAILED j1",
        "write_states": {"job-a": {**terminal, "job_id": "job-a"}, "job-b": {**terminal, "job_id": "job-b"}},
    }])
    sup.cmd_approve("calibration")
    sup.cmd_run(max_loops=2)
    assert json.loads(sup.halt_file.read_text())["reason"] == "failed_terminal_burst"


def test_freeze_and_main_gates(env, monkeypatch):
    sup = init_run(env, monkeypatch)
    set_phase(sup, "CALIB_DONE")
    write_scenario(env, [{"exit": 0, "stdout": '{"status": "FROZEN", "jobs": 100}'}])
    sup.cmd_run(max_loops=2)
    assert sup.load_state()["phase"] == "CALIB_DONE"  # freeze gate not armed yet
    sup.cmd_approve("freeze")
    sup.cmd_run(max_loops=3)
    assert sup.load_state()["phase"] == "FROZEN"
    sup.cmd_approve("main")
    write_scenario(env, [{"exit": 0, "stdout": "BATCH_COMPLETE no pending jobs"}])
    env.scenario.with_suffix(".counter").unlink()
    sup.cmd_run(max_loops=2)
    assert sup.load_state()["phase"] == "MAIN_DONE"


def test_freeze_inconclusive_halts(env, monkeypatch):
    sup = init_run(env, monkeypatch)
    set_phase(sup, "CALIB_DONE")
    sup.cmd_approve("freeze")
    write_scenario(env, [{"exit": 2, "stdout": '{"status": "INCONCLUSIVE_BUDGET"}'}])
    sup.cmd_run(max_loops=3)
    assert json.loads(sup.halt_file.read_text())["reason"] == "freeze_inconclusive"


def test_aggregate_verify_reach_await_seal(env, monkeypatch):
    sup = init_run(env, monkeypatch)
    set_phase(sup, "MAIN_DONE")
    # aggregate exits 2 (sampled target missed) - still a reportable outcome
    write_scenario(env, [
        {"exit": 2, "stdout": '{"status": "DOES_NOT_MEET_SAMPLED_TARGET"}'},
        {"exit": 0, "stdout": '{"status": "PASS", "errors": []}'},
    ])
    sup.cmd_run(max_loops=4)
    assert sup.load_state()["phase"] == "AWAIT_SEAL"
    assert "ready_to_seal" in read_alert_codes(sup)


def test_dry_run_passthrough(env, monkeypatch):
    sup = init_run(env, monkeypatch)
    monkeypatch.setenv("XA_RUNNER_DRY_RUN", "1")
    write_scenario(env, [{"exit": 0, "stdout": "printed commands only"}])
    sup.cmd_approve("calibration")
    sup.cmd_run(max_loops=2)
    calls = [json.loads(line) for line in env.scenario.with_suffix(".calls.jsonl").read_text().splitlines()]
    assert all("--dry-run" in call for call in calls)


def test_health_and_state_stay_valid_json(env, monkeypatch):
    sup = init_run(env, monkeypatch)
    write_scenario(env, [{"exit": 1, "stdout": "[1/8] FAILED j1"}])
    sup.cmd_approve("calibration")
    sup.cmd_run(max_loops=3)
    for name in ("health.json", "state.json"):
        json.loads((sup.sup_dir / name).read_text(encoding="utf-8"))
    for line in (sup.sup_dir / "supervisor-events.jsonl").read_text(encoding="utf-8").splitlines():
        json.loads(line)
