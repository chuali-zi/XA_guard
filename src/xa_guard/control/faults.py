"""Deterministic, file-armed fault hooks restricted to acceptance deployments."""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
from pathlib import Path
from typing import Any


_LOCK = threading.Lock()
_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


class FaultController:
    """Consume one-shot files under a container-local directory.

    Nothing is exposed over HTTP.  Operators arm a test container with
    ``docker exec`` or ``kubectl exec``.  Production refuses to start with the
    feature enabled so these hooks cannot become an accidental control plane.
    """

    def __init__(self) -> None:
        self.enabled = _truthy(os.getenv("XA_GUARD_TEST_FAULTS", "false"))
        profile = os.getenv("XA_GUARD_DEPLOYMENT_PROFILE", "development").lower()
        if self.enabled and profile == "production":
            raise RuntimeError("test fault injection cannot be enabled in production")
        self.root = Path(os.getenv("XA_GUARD_TEST_FAULT_DIR", "/tmp/xa-guard-faults"))

    def _path(self, name: str) -> Path:
        if not _NAME.fullmatch(name):
            raise ValueError("invalid fault name")
        return self.root / name

    def consume(self, name: str) -> str | None:
        """Atomically consume a one-shot marker and return its optional payload."""
        if not self.enabled:
            return None
        path = self._path(name)
        with _LOCK:
            try:
                payload = path.read_text(encoding="utf-8").strip()
                path.unlink()
            except FileNotFoundError:
                return None
        self._mark_reached(name)
        return payload

    def next_step(self, name: str) -> dict[str, Any] | None:
        """Pop the next JSON fault-plan step, retaining remaining steps safely."""
        if not self.enabled:
            return None
        path = self._path(name)
        with _LOCK:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return None
            if isinstance(value, dict):
                steps = value.get("steps")
            else:
                steps = value
            if not isinstance(steps, list) or not steps or not isinstance(steps[0], dict):
                raise RuntimeError(f"fault plan {name!r} is invalid")
            step = dict(steps.pop(0))
            if steps:
                temporary = path.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps({"steps": steps}, sort_keys=True),
                    encoding="utf-8",
                )
                temporary.replace(path)
            else:
                path.unlink()
        self._mark_reached(name)
        return step

    def crash_if_armed(self, name: str, exit_code: int = 86) -> None:
        if self.consume(name) is not None:
            os._exit(exit_code)

    async def delay_if_armed(self, name: str, default_seconds: float = 120.0) -> bool:
        payload = self.consume(name)
        if payload is None:
            return False
        try:
            seconds = float(payload) if payload else default_seconds
        except ValueError as exc:
            raise RuntimeError(f"fault delay {name!r} is invalid") from exc
        if seconds <= 0 or seconds > 600:
            raise RuntimeError(f"fault delay {name!r} is outside 0..600 seconds")
        await asyncio.sleep(seconds)
        return True

    def _mark_reached(self, name: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._path(f"reached-{name}").write_text("reached\n", encoding="utf-8")


faults = FaultController()
