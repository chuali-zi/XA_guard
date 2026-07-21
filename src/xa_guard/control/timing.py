"""Opt-in request timing for reference and development diagnostics."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class TimingRecorder:
    durations_ms: dict[str, float] = field(default_factory=dict)

    def add(self, name: str, duration_ms: float) -> None:
        self.durations_ms[name] = self.durations_ms.get(name, 0.0) + duration_ms

    def server_timing(self) -> str:
        return ", ".join(
            f"{name};dur={duration:.3f}"
            for name, duration in sorted(self.durations_ms.items())
        )


_CURRENT: ContextVar[TimingRecorder | None] = ContextVar(
    "xa_guard_control_timing", default=None
)


def request_enabled(header_value: str) -> bool:
    profile = os.getenv("XA_GUARD_DEPLOYMENT_PROFILE", "development").strip().lower()
    return (
        profile != "production"
        and os.getenv("XA_GUARD_CONTROL_TIMING", "").strip().lower() in {"1", "true", "yes"}
        and header_value.strip().lower() == "timing"
    )


@contextmanager
def request_timing(enabled: bool) -> Iterator[TimingRecorder | None]:
    if not enabled:
        yield None
        return
    recorder = TimingRecorder()
    token = _CURRENT.set(recorder)
    started = time.perf_counter_ns()
    try:
        yield recorder
    finally:
        recorder.add("xa-total", (time.perf_counter_ns() - started) / 1_000_000.0)
        _CURRENT.reset(token)


@contextmanager
def span(name: str) -> Iterator[None]:
    recorder = _CURRENT.get()
    if recorder is None:
        yield
        return
    started = time.perf_counter_ns()
    try:
        yield
    finally:
        recorder.add(name, (time.perf_counter_ns() - started) / 1_000_000.0)


def add_duration(name: str, duration_ms: float) -> None:
    recorder = _CURRENT.get()
    if recorder is not None:
        recorder.add(name, duration_ms)
