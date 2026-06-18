"""Reproducible L3 performance evidence for the in-process XA-Guard pipeline.

This benchmark exercises the configured six-gate pipeline and Gate6 JSONL
audit writes. It deliberately does not claim MCP transport, remote model, or
container runtime performance; those require separate deployment load tests.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from xa_guard.audit.merkle import ChainStore
from xa_guard.config import XAGuardConfig
from xa_guard.server import build_pipeline
from xa_guard.types import GateContext, InputSource

SCHEMA_VERSION = "xa-l3-performance-benchmark/v0.1"
_WORKLOAD = (
    ("allow", "get_cpu", {"host": "web03"}),
    ("deny", "exec_command", {"host": "web03", "cmd": "rm -rf /var/log"}),
    ("approval", "restart_service", {"host": "web03", "name": "nginx"}),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[rank]


def _memory_mb() -> tuple[float | None, float | None, str]:
    try:
        import psutil

        info = psutil.Process().memory_info()
        peak = getattr(info, "peak_wset", info.rss)
        return info.rss / (1024 * 1024), peak / (1024 * 1024), "psutil"
    except Exception:
        pass

    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            kernel32 = ctypes.WinDLL("kernel32.dll")
            psapi = ctypes.WinDLL("psapi.dll")
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(ProcessMemoryCounters),
                wintypes.DWORD,
            ]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            handle = kernel32.GetCurrentProcess()
            ok = psapi.GetProcessMemoryInfo(
                handle, ctypes.byref(counters), counters.cb
            )
            if ok:
                unit = 1024 * 1024
                return (
                    counters.WorkingSetSize / unit,
                    counters.PeakWorkingSetSize / unit,
                    "windows_working_set",
                )
        except Exception:
            pass
    return None, None, "unavailable"


def _run_dir(root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    target = root / f"run-{stamp}-{os.getpid()}"
    target.mkdir(parents=True, exist_ok=False)
    return target


async def _execute_workload(
    pipeline: Any,
    *,
    requests: int,
    concurrency: int,
    collect: bool,
) -> tuple[list[float], Counter[str]]:
    semaphore = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    decisions: Counter[str] = Counter()

    async def executor(ctx: GateContext) -> dict[str, Any]:
        await asyncio.sleep(0)
        return {"benchmark_noop": True, "tool": ctx.tool_name}

    async def one(index: int) -> None:
        label, tool_name, arguments = _WORKLOAD[index % len(_WORKLOAD)]
        ctx = GateContext(
            tool_name=tool_name,
            arguments=dict(arguments),
            input_sources=[InputSource.USER],
        )
        async with semaphore:
            started = time.perf_counter()
            result = await pipeline.run(ctx, executor)
            latency_ms = (time.perf_counter() - started) * 1000
        if collect:
            latencies.append(latency_ms)
            decisions[result.final_decision.value] += 1
            decisions[f"case:{label}"] += 1

    await asyncio.gather(*(one(index) for index in range(requests)))
    return latencies, decisions


def run_benchmark(
    config_path: str | Path,
    *,
    requests: int = 500,
    warmup: int = 30,
    concurrency: int = 10,
    audit_dir: str | Path = "logs/performance",
) -> dict[str, Any]:
    """Run the local six-gate workload and return a JSON-serializable report."""
    if requests <= 0:
        raise ValueError("requests must be greater than zero")
    if warmup < 0:
        raise ValueError("warmup must be zero or greater")
    if concurrency <= 0:
        raise ValueError("concurrency must be greater than zero")

    config = Path(config_path).resolve()
    if not config.is_file():
        raise FileNotFoundError(f"config not found: {config}")

    run_dir = _run_dir(Path(audit_dir).resolve())
    cfg = XAGuardConfig.from_yaml(config)
    cfg.gates.setdefault("gate6", cfg.gate("gate6"))
    cfg.gates["gate6"].options["audit_dir"] = str(run_dir)
    cfg.audit_dir = str(run_dir)
    pipeline = build_pipeline(cfg)

    if warmup:
        asyncio.run(
            _execute_workload(
                pipeline,
                requests=warmup,
                concurrency=min(concurrency, warmup),
                collect=False,
            )
        )

    rss_start, peak_start, rss_provider = _memory_mb()
    started = time.perf_counter()
    latencies, decisions = asyncio.run(
        _execute_workload(
            pipeline,
            requests=requests,
            concurrency=min(concurrency, requests),
            collect=True,
        )
    )
    elapsed = time.perf_counter() - started
    rss_end, peak_end, _ = _memory_mb()

    audit_path = run_dir / "audit.jsonl"
    chain_ok, bad_line = ChainStore(audit_path, algo=str(cfg.gate("gate6").options.get("hash_algo", "sha256"))).verify()
    audit_records = 0
    if audit_path.exists():
        audit_records = sum(1 for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip())

    latency = {
        "min_ms": round(min(latencies), 3),
        "mean_ms": round(sum(latencies) / len(latencies), 3),
        "p50_ms": round(_percentile(latencies, 0.50), 3),
        "p95_ms": round(_percentile(latencies, 0.95), 3),
        "p99_ms": round(_percentile(latencies, 0.99), 3),
        "max_ms": round(max(latencies), 3),
    }
    throughput_qps = requests / elapsed if elapsed else 0.0
    memory = {
        "provider": rss_provider,
        "rss_start_mb": round(rss_start, 3) if rss_start is not None else None,
        "rss_end_mb": round(rss_end, 3) if rss_end is not None else None,
        "rss_delta_mb": round(rss_end - rss_start, 3) if rss_start is not None and rss_end is not None else None,
        "rss_peak_mb": round(max(value for value in (peak_start, peak_end) if value is not None), 3)
        if peak_start is not None or peak_end is not None
        else None,
    }
    targets = {
        "profile": "PRD medium",
        "p50_ms_lte": 100.0,
        "p95_ms_lte": 300.0,
        "qps_gte": 50.0,
        "rss_mb_lte": 1024.0,
        "results": {
            "p50": latency["p50_ms"] <= 100.0,
            "p95": latency["p95_ms"] <= 300.0,
            "qps": throughput_qps >= 50.0,
            "memory": peak_end is not None and peak_end <= 1024.0,
        },
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "claim_scope": "local_in_process_six_gate_pipeline",
        "benchmark": {
            "path": str(Path(__file__).resolve()),
            "sha256": _sha256(Path(__file__).resolve()),
        },
        "config": {"path": str(config), "sha256": _sha256(config)},
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
        },
        "workload": {
            "requests": requests,
            "warmup": warmup,
            "concurrency": min(concurrency, requests),
            "cases": [label for label, _tool, _args in _WORKLOAD],
            "includes_gate6_audit_write": True,
        },
        "summary": {
            "elapsed_seconds": round(elapsed, 6),
            "throughput_qps": round(throughput_qps, 3),
            "latency": latency,
            "memory": memory,
            "decisions": dict(sorted(decisions.items())),
            "audit": {
                "path": str(audit_path),
                "records": audit_records,
                "chain_verified": chain_ok,
                "bad_line": bad_line,
            },
            "targets": targets,
            "targets_met": all(targets["results"].values()),
        },
        "limitations": [
            "Does not include MCP stdio/HTTP transport overhead.",
            "Does not include remote or local model inference.",
            "Uses a no-op downstream executor; tool runtime is excluded.",
            "Single-process local evidence is not a multi-host soak test.",
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/xa-guard.opencode-smoke.yaml")
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--warmup", type=int, default=30)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--audit-dir", default="logs/performance")
    parser.add_argument("--output", default="logs/runtime/l3_performance_benchmark.json")
    parser.add_argument("--require-targets", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = run_benchmark(
            args.config,
            requests=args.requests,
            warmup=args.warmup,
            concurrency=args.concurrency,
            audit_dir=args.audit_dir,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"benchmark error: {exc}", file=sys.stderr)
        return 2

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"report={output.resolve()}")
    if args.require_targets and not report["summary"]["targets_met"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
