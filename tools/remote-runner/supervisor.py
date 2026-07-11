"""Unattended supervisor for the R2/R3 budget60 acceptance run on a remote host.

Wraps scripts/run_r2_r3_acceptance.py without modifying it. Responsibilities:
clock + network gating before every paid batch (a campus-net outage must not
burn the orchestrator's max_job_resume_attempts and turn jobs FAILED_TERMINAL),
a phase state machine with manual approval gates before money is spent, an
explosion breaker that halts on suspicious failure patterns, and power-loss
safe heartbeat/alert files (atomic replace / O_APPEND + fsync) under the
evidence run directory so they are sealed with the run.

Evidence layout follows docs/acceptance/remote-evidence/EVIDENCE-LAYOUT-SPEC.md:
the orchestrator's output_dir lives at <run>/artifacts/orchestrator/ and every
command is appended to commands.txt and tee'd verbatim into console.log.

Subcommands:
  init             create the evidence run, freeze the local config, budget-plan
  run              the daemon loop (systemd ExecStart)
  status           print health.json and recent alerts
  approve <gate>   arm a manual gate: calibration | freeze | main
  revive           clear a breaker/budget halt so `run` can continue
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TARGET = "l3-r2r3-budget60"
GATES = ("calibration", "freeze", "main")
HALTED_PHASES = frozenset({"SEALED"})

DEFAULT_CONFIG: dict[str, Any] = {
    "shorthost": "",
    "operator": "codex",
    "repo_dir": "~/xa-runner/XA_guard",
    "venv_python": "~/xa-runner/venv/bin/python",
    "acceptance_template": "configs/r2-r3-acceptance.example.json",
    "opencode_executable": "opencode",
    "opencode_config_home": "~/xa-runner/oc-config",
    "opencode_data_home": "~/xa-runner/oc-data",
    "agentdojo_upstream_dir": "~/xa-runner/agentdojo-upstream",
    "injecagent_upstream_dir": "~/xa-runner/injecagent-upstream",
    "gates": {
        "clock_enabled": True,
        "clock_max_offset_seconds": 2.0,
        "clock_wait_max_seconds": 600,
        "network_urls": ["https://opencode.ai/"],
        "network_confirm_count": 2,
        "network_confirm_interval_seconds": 15,
        "network_timeout_seconds": 10,
        "network_backoff_start_seconds": 60,
        "network_backoff_max_seconds": 300,
        "network_warn_after_seconds": 600,
    },
    "batch": {
        "max_jobs": 8,
        "reduced_max_jobs": 2,
        "cooldown_seconds": 300,
    },
    "quota": {"poll_seconds": 1800, "warn_after_hours": 24.0},
    "explosion": {
        "failed_terminal_window_minutes": 30,
        "failed_terminal_max": 2,
        "at_risk_infra_max": 6,
        "bad_batch_failure_ratio": 0.5,
        "consecutive_bad_batches": 2,
        "consecutive_crash_exits": 3,
        "budget_warn_ratio": 0.80,
        "budget_critical_ratio": 0.95,
    },
    "heartbeat_seconds": 60,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def posix_shell() -> str:
    """Return a POSIX shell, including Git for Windows when it is installed."""
    shell = shutil.which("sh")
    if shell:
        return shell
    if os.name == "nt":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        for candidate in (
            Path(program_files) / "Git" / "bin" / "sh.exe",
            Path(program_files) / "Git" / "usr" / "bin" / "sh.exe",
        ):
            if candidate.is_file():
                return str(candidate)
    raise SystemExit("POSIX shell `sh` is required (install Git Bash on Windows)")


def utc_iso(moment: datetime | None = None) -> str:
    return (moment or utc_now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def runner_home() -> Path:
    return Path(os.environ.get("XA_RUNNER_HOME", "~/xa-runner")).expanduser()


def evidence_root() -> Path:
    return Path(os.environ.get("XA_EVIDENCE_ROOT", "~/xa-evidence")).expanduser()


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(line.rstrip("\n") + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return default


class Supervisor:
    def __init__(self, home: Path) -> None:
        self.home = home
        config_path = home / "runner.json"
        loaded = read_json(config_path)
        if not isinstance(loaded, dict):
            raise SystemExit(f"missing or invalid runner config: {config_path}")
        self.config = deep_merge(DEFAULT_CONFIG, loaded)
        if not self.config["shorthost"]:
            raise SystemExit("runner.json must set shorthost")
        self.repo = Path(self.config["repo_dir"]).expanduser()
        run_id_path = home / "current-run"
        self.run_id = run_id_path.read_text(encoding="utf-8").strip() if run_id_path.is_file() else ""
        self.run_dir = evidence_root() / "runs" / self.run_id if self.run_id else None
        self._stopping = False
        self._child: subprocess.Popen[str] | None = None
        self._gate_outage_alerted = False
        self._quota_wait_started: datetime | None = None
        self._budget_alerted_level = ""
        self._consecutive_bad_batches = 0
        self._consecutive_crashes = 0

    # ----- run-scoped paths -------------------------------------------------

    def _require_run(self) -> Path:
        if not self.run_dir or not self.run_dir.is_dir():
            raise SystemExit("no active run; execute `supervisor.py init` first")
        return self.run_dir

    @property
    def sup_dir(self) -> Path:
        return self._require_run() / "artifacts" / "supervisor"

    @property
    def control_dir(self) -> Path:
        return self.sup_dir / "control"

    @property
    def orchestrator_dir(self) -> Path:
        return self._require_run() / "artifacts" / "orchestrator"

    @property
    def local_config(self) -> Path:
        return self._require_run() / "artifacts" / "config" / "acceptance.local.json"

    @property
    def halt_file(self) -> Path:
        return self.control_dir / "HALT.json"

    # ----- state / health / alerts ------------------------------------------

    def load_state(self) -> dict[str, Any]:
        state = read_json(self.sup_dir / "state.json", {})
        return state if isinstance(state, dict) else {}

    def save_state(self, state: dict[str, Any]) -> None:
        state["updated_utc"] = utc_iso()
        atomic_write_json(self.sup_dir / "state.json", state)

    def alert(self, level: str, code: str, message: str, **details: Any) -> None:
        record = {
            "ts_utc": utc_iso(),
            "level": level,
            "code": code,
            "message": message,
            "details": details,
        }
        append_line(self.sup_dir / "ALERTS.jsonl", json.dumps(record, ensure_ascii=False))
        print(f"[{level}] {code}: {message}", file=sys.stderr, flush=True)

    def event(self, code: str, **details: Any) -> None:
        record = {"ts_utc": utc_iso(), "code": code, "details": details}
        append_line(self.sup_dir / "supervisor-events.jsonl", json.dumps(record, ensure_ascii=False))

    def write_health(self, phase: str, note: str, **extra: Any) -> None:
        ledger = read_json(self.orchestrator_dir / "budget-ledger.json", {})
        spend = {"total_usd": None, "buckets_usd": {}, "caps_usd": {}}
        if isinstance(ledger, dict) and isinstance(ledger.get("entries"), list):
            buckets: dict[str, float] = {key: 0.0 for key in ledger.get("bucket_caps_usd", {})}
            for entry in ledger["entries"]:
                amount = entry.get("charged_usd")
                if amount is None:
                    amount = entry.get("reserved_usd", 0.0)
                buckets[entry["bucket"]] = buckets.get(entry["bucket"], 0.0) + float(amount)
            spend = {
                "total_usd": round(sum(buckets.values()), 6),
                "buckets_usd": {key: round(value, 6) for key, value in buckets.items()},
                "caps_usd": ledger.get("bucket_caps_usd", {}),
                "halted": ledger.get("halted", False),
            }
        health = {
            "ts_utc": utc_iso(),
            "run_id": self.run_id,
            "pid": os.getpid(),
            "phase": phase,
            "note": note,
            "halted": self.halt_file.is_file(),
            "halt": read_json(self.halt_file),
            "jobs": self.job_counts(),
            "ledger": spend,
            **extra,
        }
        atomic_write_json(self.sup_dir / "health.json", health)

    def halt(self, reason_code: str, message: str, **details: Any) -> None:
        atomic_write_json(
            self.halt_file,
            {"ts_utc": utc_iso(), "reason": reason_code, "message": message, "details": details},
        )
        self.alert("CRITICAL", reason_code, message, **details)

    # ----- job/ledger inspection ---------------------------------------------

    def job_counts(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        at_risk = 0
        jobs_dir = self.orchestrator_dir / "jobs"
        if jobs_dir.is_dir():
            for state_path in jobs_dir.glob("*/state.json"):
                state = read_json(state_path, {})
                status = state.get("status", "unknown") if isinstance(state, dict) else "unknown"
                counts[status] = counts.get(status, 0) + 1
                if status == "infra_error" and len(state.get("attempts", [])) == 1:
                    at_risk += 1
        totals = {}
        for phase, manifest in (
            ("calibration", "calibration-manifest.json"),
            ("main", "sample-manifest.json"),
        ):
            data = read_json(self.orchestrator_dir / manifest, {})
            if isinstance(data, dict) and data.get("job_count") is not None:
                totals[phase] = data["job_count"]
        return {"by_status": counts, "at_risk_infra": at_risk, "manifest_job_counts": totals}

    def terminal_job_ids(self) -> set[str]:
        jobs_dir = self.orchestrator_dir / "jobs"
        found: set[str] = set()
        if jobs_dir.is_dir():
            for state_path in jobs_dir.glob("*/state.json"):
                state = read_json(state_path, {})
                if isinstance(state, dict) and state.get("status") == "FAILED_TERMINAL":
                    found.add(state.get("job_id", state_path.parent.name))
        return found

    # ----- transcript discipline (spec §2.4) ----------------------------------

    def orchestrator_argv(self, *args: str) -> list[str]:
        override = os.environ.get("XA_RUNNER_EXEC_OVERRIDE")
        if override:
            return shlex.split(override, posix=True) + list(args)
        python = Path(self.config["venv_python"]).expanduser()
        return [str(python), str(self.repo / "scripts" / "run_r2_r3_acceptance.py"), *args]

    def run_logged(self, argv: list[str], label: str) -> tuple[int, str]:
        """Run a command, append it to commands.txt, tee output to console.log."""
        run_dir = self._require_run()
        append_line(run_dir / "commands.txt", subprocess.list2cmdline(argv))
        tail: list[str] = []
        with open(run_dir / "console.log", "a", encoding="utf-8", newline="\n") as console:
            console.write(f"\n=== {utc_iso()} supervisor {label}: {subprocess.list2cmdline(argv)}\n")
            console.flush()
            # The orchestrator imports the repo-root `bench` package; running the
            # script by absolute path does not put the repo on sys.path.
            env = dict(os.environ)
            extra = os.pathsep.join([str(self.repo), str(self.repo / "src")])
            env["PYTHONPATH"] = (
                extra + os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else extra
            )
            process = subprocess.Popen(
                argv,
                cwd=self.repo if self.repo.is_dir() else None,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self._child = process
            assert process.stdout is not None
            for line in process.stdout:
                console.write(line)
                console.flush()
                tail.append(line)
                if len(tail) > 400:
                    tail.pop(0)
            code = process.wait()
            self._child = None
            console.write(f"=== {utc_iso()} exit={code}\n")
            console.flush()
            os.fsync(console.fileno())
        return code, "".join(tail)

    # ----- gates ---------------------------------------------------------------

    def clock_synced(self) -> tuple[bool, str]:
        gates = self.config["gates"]
        if not gates.get("clock_enabled", True):
            return True, "clock gate disabled"
        try:
            output = subprocess.run(
                ["chronyc", "tracking"], capture_output=True, text=True, timeout=10,
                encoding="utf-8", errors="replace",
            ).stdout
            leap = re.search(r"Leap status\s*:\s*(\S+)", output)
            offset = re.search(r"System time\s*:\s*([0-9.]+) seconds (fast|slow)", output)
            if leap and leap.group(1) == "Normal" and offset:
                drift = float(offset.group(1))
                if drift <= float(gates["clock_max_offset_seconds"]):
                    return True, f"chrony ok (offset {drift}s)"
                return False, f"chrony offset {drift}s too large"
            return False, "chrony not synchronized"
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            output = subprocess.run(
                ["timedatectl", "show", "--property=NTPSynchronized", "--value"],
                capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
            ).stdout.strip()
            if output == "yes":
                return True, "timedatectl NTPSynchronized=yes"
            return False, f"timedatectl NTPSynchronized={output or 'unknown'}"
        except (OSError, subprocess.SubprocessError):
            return False, "no chronyc/timedatectl available"

    def clock_gate(self, phase: str) -> None:
        gates = self.config["gates"]
        waited = 0.0
        while not self._stopping:
            ok, detail = self.clock_synced()
            if ok:
                return
            if waited == 0:
                self.event("clock_gate_waiting", detail=detail)
            if waited >= float(gates["clock_wait_max_seconds"]):
                self.alert("CRITICAL", "clock_unsynced", f"clock still unsynced: {detail}")
                waited = 0.0
            self.write_health(phase, f"clock gate: waiting ({detail})")
            time.sleep(min(30, self.config["heartbeat_seconds"]))
            waited += 30

    def _url_reachable(self, url: str) -> bool:
        request = urllib.request.Request(url, method="HEAD")
        timeout = float(self.config["gates"]["network_timeout_seconds"])
        try:
            urllib.request.urlopen(request, timeout=timeout)
            return True
        except urllib.error.HTTPError:
            return True  # server answered; the network path is up
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def network_gate(self, phase: str) -> None:
        gates = self.config["gates"]
        urls = gates["network_urls"]
        backoff = float(gates["network_backoff_start_seconds"])
        outage_started: datetime | None = None
        while not self._stopping:
            confirmations = 0
            while confirmations < int(gates["network_confirm_count"]):
                if all(self._url_reachable(url) for url in urls):
                    confirmations += 1
                    if confirmations < int(gates["network_confirm_count"]):
                        time.sleep(float(gates["network_confirm_interval_seconds"]))
                else:
                    break
            else:
                if self._gate_outage_alerted:
                    self.alert("INFO", "network_recovered", "provider endpoints reachable again")
                    self._gate_outage_alerted = False
                return
            if outage_started is None:
                outage_started = utc_now()
                self.event("network_gate_waiting", urls=urls)
            outage = (utc_now() - outage_started).total_seconds()
            if outage >= float(gates["network_warn_after_seconds"]) and not self._gate_outage_alerted:
                self.alert("WARN", "network_outage", f"provider unreachable for {int(outage)}s", urls=urls)
                self._gate_outage_alerted = True
            self.write_health(phase, f"network gate: waiting ({int(outage)}s down, retry in {int(backoff)}s)")
            time.sleep(backoff)
            backoff = min(backoff * 2, float(gates["network_backoff_max_seconds"]))

    # ----- explosion breaker ----------------------------------------------------

    def breaker_check(self, batch_stdout: str) -> bool:
        """Returns True (and halts) when a suspicious failure pattern is detected."""
        explosion = self.config["explosion"]
        state = self.load_state()
        known: dict[str, str] = state.get("terminal_seen", {})
        now = utc_now()
        for job_id in self.terminal_job_ids():
            known.setdefault(job_id, utc_iso(now))
        state["terminal_seen"] = known
        window = timedelta(minutes=float(explosion["failed_terminal_window_minutes"]))
        recent = [
            job_id for job_id, seen in known.items()
            if now - datetime.strptime(seen, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) <= window
        ]
        self.save_state(state)
        if len(recent) >= int(explosion["failed_terminal_max"]):
            self.halt(
                "failed_terminal_burst",
                f"{len(recent)} jobs went FAILED_TERMINAL within {window}; halting to protect the matrix",
                jobs=sorted(recent),
            )
            return True
        at_risk = self.job_counts()["at_risk_infra"]
        if at_risk >= int(explosion["at_risk_infra_max"]):
            self.halt(
                "infra_error_pileup",
                f"{at_risk} jobs are one resume attempt away from FAILED_TERMINAL; investigate before resuming",
            )
            return True
        ran = len(re.findall(r"^\[\d+/\d+\] RUN ", batch_stdout, flags=re.M))
        failed = len(re.findall(r"^\[\d+/\d+\] FAILED ", batch_stdout, flags=re.M))
        if ran > 0 and failed / ran >= float(explosion["bad_batch_failure_ratio"]):
            self._consecutive_bad_batches += 1
        else:
            self._consecutive_bad_batches = 0
        if self._consecutive_bad_batches >= int(explosion["consecutive_bad_batches"]):
            self.halt(
                "bad_batch_streak",
                f"{self._consecutive_bad_batches} consecutive batches with >= "
                f"{explosion['bad_batch_failure_ratio']:.0%} failures despite gates passing",
            )
            return True
        return False

    def budget_watch(self) -> None:
        explosion = self.config["explosion"]
        ledger = read_json(self.orchestrator_dir / "budget-ledger.json", {})
        if not isinstance(ledger, dict) or not ledger.get("total_cap_usd"):
            return
        total = 0.0
        for entry in ledger.get("entries", []):
            amount = entry.get("charged_usd")
            total += float(entry.get("reserved_usd", 0.0) if amount is None else amount)
        ratio = total / float(ledger["total_cap_usd"])
        level = (
            "CRITICAL" if ratio >= float(explosion["budget_critical_ratio"])
            else "WARN" if ratio >= float(explosion["budget_warn_ratio"])
            else ""
        )
        if level and level != self._budget_alerted_level:
            self.alert(level, "budget_high_water", f"spend at {ratio:.0%} of ${ledger['total_cap_usd']}")
            self._budget_alerted_level = level

    # ----- gate flags -------------------------------------------------------------

    def gate_armed(self, gate: str) -> bool:
        return (self.control_dir / f"approve-{gate}").is_file()

    def consume_gate(self, gate: str) -> None:
        flag = self.control_dir / f"approve-{gate}"
        consumed = self.control_dir / f"approve-{gate}.consumed-{utc_iso().replace(':', '')}"
        os.replace(flag, consumed)
        self.event("gate_consumed", gate=gate)

    # ----- phases -----------------------------------------------------------------

    def run_phase_batches(self, phase_name: str, cli_phase: str) -> str:
        """One batch of budget-resume; returns the (possibly new) phase."""
        state = self.load_state()
        batch_config = self.config["batch"]
        max_jobs = int(state.get("current_max_jobs") or batch_config["max_jobs"])
        self.clock_gate(phase_name)
        self.network_gate(phase_name)
        if self._stopping:
            return phase_name
        self.write_health(phase_name, f"running batch (max_jobs={max_jobs})")
        argv = self.orchestrator_argv(
            "budget-resume", "--config", str(self.local_config),
            "--phase", cli_phase, "--max-jobs", str(max_jobs),
        )
        # Pre-spend smoke mode: the orchestrator prints runner commands without
        # calling the model. Batches never complete, so bound the loop yourself.
        if os.environ.get("XA_RUNNER_DRY_RUN"):
            argv.append("--dry-run")
        code, output = self.run_logged(argv, label=f"{phase_name} batch")
        self.event("batch_finished", phase=phase_name, exit=code, max_jobs=max_jobs)
        self.budget_watch()
        if code != 4:
            self._quota_wait_started = None
        state = self.load_state()

        if code == 0:
            self._consecutive_crashes = 0
            self._consecutive_bad_batches = 0
            state["current_max_jobs"] = batch_config["max_jobs"]
            self.save_state(state)
            if "BATCH_COMPLETE no pending jobs" in output:
                return "CALIB_DONE" if cli_phase == "calibration" else "MAIN_DONE"
            return phase_name
        if code == 1:
            self._consecutive_crashes = 0
            if self.breaker_check(output):
                return phase_name
            state["current_max_jobs"] = batch_config["reduced_max_jobs"]
            self.save_state(state)
            self.event("batch_had_failures", cooldown_seconds=batch_config["cooldown_seconds"])
            self.sleep_with_heartbeat(phase_name, float(batch_config["cooldown_seconds"]), "cooldown after failed batch")
            return phase_name
        if code == 2:
            self.halt("budget_exhausted", "orchestrator reported BUDGET_EXHAUSTED; operator review required")
            return phase_name
        if code == 3:
            self.halt(
                "execution_lock_failed",
                "frozen repo/upstream/opencode-permission state drifted; refusing to spend money",
            )
            return phase_name
        if code == 4:
            if self._quota_wait_started is None:
                self._quota_wait_started = utc_now()
                self.alert("INFO", "quota_paused", "provider usage window exhausted; polling until it reopens")
            waited_hours = (utc_now() - self._quota_wait_started).total_seconds() / 3600
            if waited_hours >= float(self.config["quota"]["warn_after_hours"]):
                self.alert("WARN", "quota_paused_long", f"quota still closed after {waited_hours:.1f}h")
                self._quota_wait_started = utc_now()  # re-arm so the warning repeats per period
            self.sleep_with_heartbeat(
                phase_name, float(self.config["quota"]["poll_seconds"]), "QUOTA_WAIT: provider window closed",
            )
            return phase_name
        # Unexpected exit (uncaught exception and so on).
        self._consecutive_crashes += 1
        self.alert("WARN", "batch_crashed", f"orchestrator exited {code}", tail=output[-2000:])
        if self._consecutive_crashes >= int(self.config["explosion"]["consecutive_crash_exits"]):
            self.halt("crash_loop", f"{self._consecutive_crashes} consecutive abnormal orchestrator exits")
            return phase_name
        self.sleep_with_heartbeat(phase_name, float(self.config["batch"]["cooldown_seconds"]), "cooldown after crash")
        return phase_name

    def sleep_with_heartbeat(self, phase: str, seconds: float, note: str) -> None:
        deadline = time.monotonic() + seconds
        while not self._stopping:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            self.write_health(phase, f"{note} ({int(remaining)}s left)")
            time.sleep(min(float(self.config["heartbeat_seconds"]), remaining))

    def step(self, phase: str) -> str:
        if phase == "READY":
            if self.gate_armed("calibration"):
                self.consume_gate("calibration")
                self.alert("INFO", "phase_start", "calibration approved; paid execution begins")
                return "CALIBRATION"
            self.write_health(phase, "waiting for `runnerctl approve calibration`")
            time.sleep(self.config["heartbeat_seconds"])
            return phase
        if phase == "CALIBRATION":
            return self.run_phase_batches(phase, "calibration")
        if phase == "CALIB_DONE":
            if self.gate_armed("freeze"):
                self.consume_gate("freeze")
                return "FREEZE"
            self.write_health(
                phase,
                "calibration complete; review the ledger + calibration jobs, then `runnerctl approve freeze`",
            )
            time.sleep(self.config["heartbeat_seconds"])
            return phase
        if phase == "FREEZE":
            code, output = self.run_logged(
                self.orchestrator_argv("budget-freeze", "--config", str(self.local_config)),
                label="freeze",
            )
            if code == 0:
                self.alert("INFO", "sample_frozen", "main sample manifest FROZEN; review it, then `runnerctl approve main`")
                return "FROZEN"
            if code == 2:
                self.halt("freeze_inconclusive", "budget-freeze returned INCONCLUSIVE_BUDGET", tail=output[-2000:])
            else:
                self.halt("freeze_failed", f"budget-freeze exited {code}", tail=output[-2000:])
            return phase
        if phase == "FROZEN":
            if self.gate_armed("main"):
                self.consume_gate("main")
                self.alert("INFO", "phase_start", "main phase approved; paid execution begins")
                return "MAIN"
            self.write_health(phase, "sample frozen; review sample-manifest.json, then `runnerctl approve main`")
            time.sleep(self.config["heartbeat_seconds"])
            return phase
        if phase == "MAIN":
            return self.run_phase_batches(phase, "main")
        if phase == "MAIN_DONE":
            return "AGGREGATE"
        if phase == "AGGREGATE":
            code, output = self.run_logged(
                self.orchestrator_argv("budget-aggregate", "--config", str(self.local_config)),
                label="aggregate",
            )
            # aggregate exits 2 when the sampled target is missed; that is still a
            # valid, reportable outcome - only other codes are infrastructure errors.
            if code in (0, 2):
                self.event("aggregate_done", meets_target=(code == 0))
                return "VERIFY"
            self.halt("aggregate_failed", f"budget-aggregate exited {code}", tail=output[-2000:])
            return phase
        if phase == "VERIFY":
            code, output = self.run_logged(
                self.orchestrator_argv("budget-verify", "--config", str(self.local_config)),
                label="verify",
            )
            if code == 0:
                self.alert(
                    "INFO", "ready_to_seal",
                    "aggregate+verify complete; finalize RESULTS.md and run `runnerctl seal --result <R>`",
                )
                return "AWAIT_SEAL"
            self.halt("verify_failed", "budget-verify reported artifact/ledger errors", tail=output[-2000:])
            return phase
        if phase == "AWAIT_SEAL":
            self.write_health(phase, "waiting for operator seal (`runnerctl seal --result <R>`)")
            time.sleep(self.config["heartbeat_seconds"])
            return phase
        if phase == "SEALED":
            self.write_health(phase, "run sealed; nothing to do")
            time.sleep(max(self.config["heartbeat_seconds"], 300))
            return phase
        raise SystemExit(f"unknown phase in state.json: {phase}")

    # ----- commands ------------------------------------------------------------------

    def cmd_run(self, max_loops: int | None) -> int:
        self._require_run()

        def handle_stop(signum: int, _frame: Any) -> None:
            self._stopping = True
            child = getattr(self, "_child", None)
            if child is not None:
                child.terminate()

        signal.signal(signal.SIGTERM, handle_stop)
        signal.signal(signal.SIGINT, handle_stop)
        self.event("supervisor_started", pid=os.getpid())
        loops = 0
        while not self._stopping:
            if max_loops is not None and loops >= max_loops:
                break
            loops += 1
            if self.halt_file.is_file():
                self.write_health(self.load_state().get("phase", "UNKNOWN"), "halted; `runnerctl revive` after fixing the cause")
                time.sleep(self.config["heartbeat_seconds"])
                continue
            state = self.load_state()
            phase = state.get("phase", "READY")
            new_phase = self.step(phase)
            if new_phase != phase:
                state = self.load_state()
                state["phase"] = new_phase
                self.save_state(state)
                self.event("phase_transition", from_phase=phase, to_phase=new_phase)
                self.write_health(new_phase, f"entered {new_phase}")
        self.write_health(self.load_state().get("phase", "UNKNOWN"), "supervisor stopping")
        self.event("supervisor_stopped")
        return 0

    def cmd_init(self, skip_plan: bool) -> int:
        if self.run_id and self.run_dir and self.run_dir.is_dir():
            raise SystemExit(f"active run already exists: {self.run_id} (seal it or remove {self.home / 'current-run'})")
        ok, detail = self.clock_synced()
        if not ok:
            raise SystemExit(f"refusing to init with unsynced clock ({detail}); provenance timestamps must be trustworthy")
        new_run = self.repo / "tools" / "evidence" / "new-run.sh"
        result = subprocess.run(
            [posix_shell(), str(new_run), TARGET, "--shorthost", self.config["shorthost"],
             "--repo", str(self.repo), "--operator", self.config["operator"]],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            raise SystemExit(f"new-run.sh failed: {result.stderr.strip()}")
        self.run_id = result.stdout.strip().splitlines()[-1]
        self.run_dir = evidence_root() / "runs" / self.run_id
        template = self.repo / self.config["acceptance_template"]
        acceptance = read_json(Path(template).expanduser())
        if not isinstance(acceptance, dict):
            raise SystemExit(f"cannot read acceptance template: {template}")
        acceptance["output_dir"] = str(self.orchestrator_dir.as_posix())
        acceptance["opencode"] = {
            **acceptance.get("opencode", {}),
            "executable": self.config["opencode_executable"],
            "config_home": str(Path(self.config["opencode_config_home"]).expanduser().as_posix()),
            "data_home": str(Path(self.config["opencode_data_home"]).expanduser().as_posix()),
        }
        acceptance["agentdojo"] = {
            **acceptance.get("agentdojo", {}),
            "upstream_dir": str(Path(self.config["agentdojo_upstream_dir"]).expanduser().as_posix()),
        }
        acceptance["injecagent"] = {
            **acceptance.get("injecagent", {}),
            "upstream_dir": str(Path(self.config["injecagent_upstream_dir"]).expanduser().as_posix()),
        }
        atomic_write_json(self.local_config, acceptance)
        self.sup_dir.mkdir(parents=True, exist_ok=True)
        self.control_dir.mkdir(parents=True, exist_ok=True)
        if not skip_plan:
            code, output = self.run_logged(
                self.orchestrator_argv("budget-plan", "--config", str(self.local_config)),
                label="budget-plan",
            )
            if code != 0:
                raise SystemExit(f"budget-plan failed ({code}):\n{output[-2000:]}")
        self.save_state({"phase": "READY", "current_max_jobs": self.config["batch"]["max_jobs"]})
        (self.home).mkdir(parents=True, exist_ok=True)
        (self.home / "current-run").write_text(self.run_id + "\n", encoding="utf-8")
        self.write_health("READY", "initialized; arm with `runnerctl approve calibration`")
        self.event("run_initialized", run_id=self.run_id)
        print(self.run_id)
        return 0

    def cmd_status(self) -> int:
        health = read_json(self.sup_dir / "health.json", {})
        print(json.dumps(health, ensure_ascii=False, indent=2))
        alerts_path = self.sup_dir / "ALERTS.jsonl"
        if alerts_path.is_file():
            lines = alerts_path.read_text(encoding="utf-8").splitlines()
            if lines:
                print("--- last alerts ---")
                for line in lines[-10:]:
                    print(line)
        return 0

    def cmd_approve(self, gate: str) -> int:
        if gate not in GATES:
            raise SystemExit(f"unknown gate {gate!r}; expected one of {', '.join(GATES)}")
        self.control_dir.mkdir(parents=True, exist_ok=True)
        flag = self.control_dir / f"approve-{gate}"
        flag.write_text(utc_iso() + "\n", encoding="utf-8")
        self.event("gate_armed", gate=gate)
        print(f"armed approve-{gate}; the supervisor will proceed on its next loop")
        return 0

    def cmd_revive(self) -> int:
        if self.halt_file.is_file():
            halt = read_json(self.halt_file, {})
            archived = self.control_dir / f"HALT.cleared-{utc_iso().replace(':', '')}.json"
            os.replace(self.halt_file, archived)
            self.event("halt_cleared", previous=halt)
            print(f"cleared halt ({halt.get('reason')}); restart the service to resume")
        else:
            print("no halt flag present")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "run", "status", "approve", "revive"))
    parser.add_argument("gate", nargs="?", help="gate name for `approve`")
    parser.add_argument("--max-loops", type=int, help="stop the run loop after N iterations (tests)")
    parser.add_argument("--skip-plan", action="store_true", help="init without running budget-plan (tests)")
    args = parser.parse_args()
    supervisor = Supervisor(runner_home())
    if args.command == "init":
        return supervisor.cmd_init(skip_plan=args.skip_plan)
    if args.command == "run":
        return supervisor.cmd_run(max_loops=args.max_loops)
    if args.command == "status":
        return supervisor.cmd_status()
    if args.command == "approve":
        if not args.gate:
            parser.error("approve requires a gate name")
        return supervisor.cmd_approve(args.gate)
    return supervisor.cmd_revive()


if __name__ == "__main__":
    raise SystemExit(main())
