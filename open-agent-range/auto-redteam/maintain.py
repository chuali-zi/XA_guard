"""Keep the local Auto-RedTeam conductor healthy without weakening its guards."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_RUNTIME = ROOT / ".state" / "maintainer"
DEFAULT_CONDUCTOR_STATE = ROOT / ".state"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information, False, pid
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


def latest_mtime(root: Path, *, ignore: Path | None = None) -> float:
    latest = 0.0
    if not root.exists():
        return latest
    ignored = ignore.resolve() if ignore else None
    for path in root.rglob("*"):
        try:
            if ignored and (path.resolve() == ignored or ignored in path.resolve().parents):
                continue
            if path.is_file() and path.name not in {"campaign.lock", "stop.flag"}:
                latest = max(latest, path.stat().st_mtime)
        except OSError:
            continue
    return latest


def rotate_log(path: Path, max_bytes: int, backups: int) -> None:
    if not path.is_file() or path.stat().st_size < max_bytes:
        return
    path.with_name(path.name + f".{backups}").unlink(missing_ok=True)
    for index in range(backups - 1, 0, -1):
        source = path.with_name(path.name + f".{index}")
        target = path.with_name(path.name + f".{index + 1}")
        if source.exists():
            os.replace(source, target)
    os.replace(path, path.with_name(path.name + ".1"))


class InstanceLock:
    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> "InstanceLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            old = read_json(self.path).get("pid")
            if pid_alive(old):
                raise RuntimeError(f"maintainer already running with pid {old}")
            self.path.unlink(missing_ok=True)
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"pid": os.getpid(), "started_at": utc_now()}, stream)
        return self

    def __exit__(self, *_: object) -> None:
        self.path.unlink(missing_ok=True)


def terminate_process(process: subprocess.Popen, grace_s: float) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=grace_s)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        if os.name == "nt":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass


class Maintainer:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.runtime = args.runtime.resolve()
        self.conductor_state = args.state_dir.resolve()
        self.status_path = self.runtime / "status.json"
        self.stop_path = self.runtime / "stop.flag"
        self.log_path = self.runtime / "conductor.log"
        self.process: subprocess.Popen | None = None
        self.restart_times: deque[float] = deque()
        self.started_at = utc_now()
        self.last_exit_code: int | None = None
        self.last_reason = "starting"
        self.stopping = False

    def command(self) -> list[str]:
        command = [
            sys.executable,
            "-m",
            "conductor.conductor",
            "--config",
            str(self.args.config.resolve()),
            "--state-dir",
            str(self.conductor_state),
        ]
        if self.args.continuous:
            command.append("--continuous")
        return command

    def write_status(self, state: str, **extra: object) -> None:
        value = {
            "state": state,
            "healthy": state == "running",
            "updated_at": utc_now(),
            "started_at": self.started_at,
            "supervisor_pid": os.getpid(),
            "child_pid": self.process.pid if self.process and self.process.poll() is None else None,
            "restart_count_window": len(self.restart_times),
            "last_exit_code": self.last_exit_code,
            "last_reason": self.last_reason,
            "config": str(self.args.config.resolve()),
            "conductor_state_dir": str(self.conductor_state),
            "log": str(self.log_path),
        }
        value.update(extra)
        atomic_json(self.status_path, value)

    def start_child(self) -> None:
        rotate_log(self.log_path, self.args.log_max_bytes, self.args.log_backups)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log = self.log_path.open("a", encoding="utf-8")
        log.write(f"\n[{utc_now()}] starting: {' '.join(self.command())}\n")
        log.flush()
        options: dict = {
            "cwd": str(ROOT),
            "stdout": log,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.DEVNULL,
        }
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options["start_new_session"] = True
        try:
            self.process = subprocess.Popen(self.command(), **options)
        finally:
            log.close()
        self.last_reason = "child-started"
        self.write_status("running")

    def restart_allowed(self) -> bool:
        now = time.monotonic()
        while self.restart_times and now - self.restart_times[0] > self.args.restart_window_s:
            self.restart_times.popleft()
        return len(self.restart_times) < self.args.max_restarts

    def run(self) -> int:
        if self.stop_path.exists():
            self.write_status("stopped", detail="persistent stop flag present; use `resume`")
            return 0
        baseline_activity = max(
            time.time(), latest_mtime(self.conductor_state, ignore=self.runtime)
        )
        while not self.stopping:
            self.start_child()
            while self.process.poll() is None and not self.stopping:
                if self.stop_path.exists():
                    self.last_reason = "operator-stop"
                    self.stopping = True
                    break
                activity = latest_mtime(self.conductor_state, ignore=self.runtime)
                if activity:
                    baseline_activity = max(baseline_activity, activity)
                stale_for = time.time() - baseline_activity
                if stale_for > self.args.stale_after_s:
                    self.last_reason = "progress-stale"
                    terminate_process(self.process, self.args.stop_grace_s)
                    break
                self.write_status("running", progress_stale_for_s=round(stale_for, 1))
                time.sleep(self.args.check_interval_s)

            if self.stopping:
                (self.conductor_state / "stop.flag").parent.mkdir(parents=True, exist_ok=True)
                (self.conductor_state / "stop.flag").write_text("stop\n", encoding="utf-8")
                terminate_process(self.process, self.args.stop_grace_s)
                self.last_exit_code = self.process.poll()
                self.write_status("stopped")
                return 0

            self.last_exit_code = self.process.poll()
            if self.last_reason != "progress-stale":
                self.last_reason = "normal-exit" if self.last_exit_code == 0 else "unexpected-exit"
            if self.last_exit_code == 0:
                self.write_status("completed")
                return 0
            if not self.restart_allowed():
                self.write_status("halted", detail="restart circuit breaker open")
                return 4
            self.restart_times.append(time.monotonic())
            delay = min(
                self.args.backoff_max_s,
                self.args.backoff_initial_s * (2 ** (len(self.restart_times) - 1)),
            )
            self.write_status("backoff", restart_in_s=delay)
            deadline = time.monotonic() + delay
            while time.monotonic() < deadline:
                if self.stop_path.exists():
                    self.stopping = True
                    break
                time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
            baseline_activity = time.time()
        self.write_status("stopped")
        return 0


def preflight(args: argparse.Namespace) -> list[str]:
    errors = []
    if not args.config.is_file():
        errors.append(f"config not found: {args.config}")
    if not (ROOT / "conductor" / "conductor.py").is_file():
        errors.append("conductor source is missing; merge/install the auto-redteam implementation first")
    if args.stale_after_s <= args.check_interval_s:
        errors.append("stale-after must be greater than check-interval")
    if args.max_restarts < 1:
        errors.append("max-restarts must be at least 1")
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Auto-RedTeam health monitor and restart supervisor")
    sub = parser.add_subparsers(dest="action", required=True)
    run = sub.add_parser("run", help="run the foreground supervisor")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    run.add_argument("--state-dir", type=Path, default=DEFAULT_CONDUCTOR_STATE)
    run.add_argument("--continuous", action=argparse.BooleanOptionalAction, default=True)
    run.add_argument("--check-interval-s", type=float, default=15)
    run.add_argument("--stale-after-s", type=float, default=2400)
    run.add_argument("--stop-grace-s", type=float, default=30)
    run.add_argument("--max-restarts", type=int, default=5)
    run.add_argument("--restart-window-s", type=float, default=3600)
    run.add_argument("--backoff-initial-s", type=float, default=5)
    run.add_argument("--backoff-max-s", type=float, default=300)
    run.add_argument("--log-max-bytes", type=int, default=10 * 1024 * 1024)
    run.add_argument("--log-backups", type=int, default=3)
    for name in ("status", "stop", "resume"):
        command = sub.add_parser(name)
        command.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
        command.add_argument("--state-dir", type=Path, default=DEFAULT_CONDUCTOR_STATE)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = args.runtime.resolve()
    status_path = runtime / "status.json"
    stop_path = runtime / "stop.flag"
    if args.action == "status":
        status = read_json(status_path)
        if not status:
            print(json.dumps({"state": "not-started", "healthy": False}))
            return 3
        status["supervisor_alive"] = pid_alive(status.get("supervisor_pid"))
        status["child_alive"] = pid_alive(status.get("child_pid"))
        status["healthy"] = bool(status.get("state") == "running" and status["supervisor_alive"] and status["child_alive"])
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0 if status["healthy"] else 3
    if args.action == "stop":
        runtime.mkdir(parents=True, exist_ok=True)
        stop_path.write_text("stop\n", encoding="utf-8")
        args.state_dir.resolve().mkdir(parents=True, exist_ok=True)
        (args.state_dir.resolve() / "stop.flag").write_text("stop\n", encoding="utf-8")
        print("stop requested; the maintainer will terminate the conductor at the next health check")
        return 0
    if args.action == "resume":
        stop_path.unlink(missing_ok=True)
        (args.state_dir.resolve() / "stop.flag").unlink(missing_ok=True)
        print("persistent stop flags cleared; start the maintainer service to resume")
        return 0

    errors = preflight(args)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    maintainer = Maintainer(args)
    try:
        with InstanceLock(runtime / "maintainer.lock"):
            return maintainer.run()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        maintainer.stopping = True
        if maintainer.process:
            terminate_process(maintainer.process, args.stop_grace_s)
        maintainer.write_status("stopped", detail="keyboard interrupt")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
