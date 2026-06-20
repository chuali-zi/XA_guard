from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import mcp.types as mtypes
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from xa_guard.audit.completeness import record_completeness_score
from xa_guard.audit.merkle import ChainStore
from xa_guard.config import XAGuardConfig
from xa_guard.proxy.downstream import DownstreamRouter
from xa_guard.proxy.upstream import _build_streamable_http_asgi_app
from xa_guard.server import build_pipeline


SCHEMA_VERSION = "xa-streamable-http-multisession-benchmark/v0.1"


def _sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * quantile)))
    return round(ordered[index], 3)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _text(result: mtypes.CallToolResult) -> str:
    return "".join(
        block.text for block in (result.content or []) if isinstance(block, mtypes.TextContent)
    )


def _read_audit(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


async def _wait_started(server: uvicorn.Server, timeout: float = 10.0) -> None:
    started = time.perf_counter()
    while not server.started:
        if time.perf_counter() - started > timeout:
            raise TimeoutError("uvicorn did not start in time")
        if server.should_exit:
            raise RuntimeError("uvicorn exited before startup")
        await asyncio.sleep(0.02)


async def _memory_sampler(stop: asyncio.Event, samples: list[int]) -> None:
    try:
        import psutil
    except ImportError:
        psutil = None

    process = psutil.Process(os.getpid()) if psutil is not None else None

    def current_rss() -> int | None:
        if process is not None:
            return int(process.memory_info().rss)
        if sys.platform != "win32":
            return None
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
            if psapi.GetProcessMemoryInfo(
                kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
            ):
                return int(counters.WorkingSetSize)
        except Exception:
            return None
        return None

    while not stop.is_set():
        rss = current_rss()
        if rss is not None:
            samples.append(rss)
        await asyncio.sleep(0.02)
    rss = current_rss()
    if rss is not None:
        samples.append(rss)


async def _run_clients(
    *,
    url: str,
    sessions: int,
    requests: int,
    raw_samples: list[dict[str, Any]],
    phase: str,
) -> dict[str, Any]:
    ready = 0
    ready_lock = asyncio.Lock()
    all_ready = asyncio.Event()
    release = asyncio.Event()
    session_ids: list[str] = []
    initialization_latencies: list[float] = []
    call_latencies: list[float] = []
    errors: list[str] = []
    mismatches = 0

    assignments = [[] for _ in range(sessions)]
    for request_index in range(requests):
        assignments[request_index % sessions].append(request_index)

    async def worker(session_index: int) -> None:
        nonlocal ready, mismatches
        timeout = httpx.Timeout(30.0, read=120.0)
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as http_client:
            async with streamable_http_client(url, http_client=http_client) as streams:
                read_stream, write_stream, get_session_id = streams
                async with ClientSession(read_stream, write_stream) as client:
                    init_start = time.perf_counter()
                    await client.initialize()
                    initialization_latencies.append((time.perf_counter() - init_start) * 1000)
                    session_id = get_session_id() or ""
                    session_ids.append(session_id)
                    async with ready_lock:
                        ready += 1
                        if ready == sessions:
                            all_ready.set()
                    await release.wait()
                    for request_index in assignments[session_index]:
                        marker = f"{phase}-s{session_index}-r{request_index}"
                        started = time.perf_counter()
                        error = ""
                        matched = False
                        try:
                            result = await client.call_tool("get_cpu", {"host": marker})
                            payload = json.loads(_text(result))
                            matched = payload.get("host") == marker
                            if not matched:
                                mismatches += 1
                        except Exception as exc:
                            error = f"{type(exc).__name__}: {exc}"
                            errors.append(error)
                        latency_ms = (time.perf_counter() - started) * 1000
                        call_latencies.append(latency_ms)
                        raw_samples.append(
                            {
                                "phase": phase,
                                "session_index": session_index,
                                "session_id_sha256": hashlib.sha256(session_id.encode()).hexdigest(),
                                "request_index": request_index,
                                "marker": marker,
                                "latency_ms": round(latency_ms, 3),
                                "matched": matched,
                                "error": error,
                            }
                        )

    tasks = [asyncio.create_task(worker(index)) for index in range(sessions)]
    await asyncio.wait_for(all_ready.wait(), timeout=30)
    started = time.perf_counter()
    release.set()
    await asyncio.wait_for(asyncio.gather(*tasks), timeout=max(60.0, requests * 2.0))
    elapsed = time.perf_counter() - started
    return {
        "sessions": sessions,
        "requests": requests,
        "session_ids_total": len(session_ids),
        "session_ids_unique": len(set(session_ids)),
        "empty_session_ids": sum(not value for value in session_ids),
        "initialization_latency_ms": {
            "p50": _percentile(initialization_latencies, 0.50),
            "p95": _percentile(initialization_latencies, 0.95),
            "max": round(max(initialization_latencies, default=0.0), 3),
        },
        "call_latency_ms": {
            "p50": _percentile(call_latencies, 0.50),
            "p95": _percentile(call_latencies, 0.95),
            "p99": _percentile(call_latencies, 0.99),
            "max": round(max(call_latencies, default=0.0), 3),
        },
        "elapsed_seconds": round(elapsed, 6),
        "throughput_qps": round(requests / elapsed, 3) if elapsed else 0.0,
        "errors": errors,
        "response_mismatches": mismatches,
    }


async def benchmark(args: argparse.Namespace) -> dict[str, Any]:
    if args.sessions <= 0 or args.requests < args.sessions or args.warmup < 0:
        raise ValueError("sessions must be positive, requests >= sessions, and warmup >= 0")
    config_path = Path(args.config)
    cfg = XAGuardConfig.from_yaml(config_path)
    output_path = Path(args.output)
    audit_dir = output_path.parent / f".{output_path.stem}-audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_path = audit_dir / "audit.jsonl"
    if audit_path.exists():
        audit_path.unlink()
    cfg.gates.setdefault("gate6", cfg.gate("gate6")).options["audit_dir"] = str(audit_dir)

    router = DownstreamRouter(cfg.downstream)
    await router.start()
    pipeline = build_pipeline(cfg)
    port = _free_port()
    app = _build_streamable_http_asgi_app(
        pipeline,
        router,
        host="127.0.0.1",
        port=port,
        session_idle_timeout_seconds=60,
    )
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    )
    server_task = asyncio.create_task(server.serve())
    raw_samples: list[dict[str, Any]] = []
    memory_samples: list[int] = []
    memory_stop = asyncio.Event()
    memory_task = asyncio.create_task(_memory_sampler(memory_stop, memory_samples))
    startup_start = time.perf_counter()
    try:
        await _wait_started(server)
        startup_ms = (time.perf_counter() - startup_start) * 1000
        url = f"http://127.0.0.1:{port}/mcp"
        warmup_result = None
        if args.warmup:
            warmup_result = await _run_clients(
                url=url,
                sessions=min(args.sessions, args.warmup),
                requests=args.warmup,
                raw_samples=raw_samples,
                phase="warmup",
            )
        measured = await _run_clients(
            url=url,
            sessions=args.sessions,
            requests=args.requests,
            raw_samples=raw_samples,
            phase="measured",
        )
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            health = (await client.get(f"http://127.0.0.1:{port}/healthz")).json()
    finally:
        memory_stop.set()
        await memory_task
        server.should_exit = True
        await asyncio.wait_for(server_task, timeout=15)
        watcher = getattr(pipeline, "overlay_watcher", None)
        if watcher is not None:
            watcher.stop()
        await router.stop()

    records = _read_audit(audit_path)
    chain_ok, bad_line = ChainStore(audit_path, algo="sha256").verify()
    measured_records = records[-args.requests :]
    measured_trace_ids = [str(record.get("trace_id") or "") for record in measured_records]
    measured_scores = [record_completeness_score(record) for record in measured_records]
    expected_markers = {
        str(sample["marker"]) for sample in raw_samples if sample["phase"] == "measured"
    }
    audited_markers = {
        str((record.get("gen_ai.tool.parameters") or {}).get("host") or "")
        for record in measured_records
    }
    measured_audit_ok = (
        len(measured_records) == args.requests
        and all(measured_trace_ids)
        and len(set(measured_trace_ids)) == args.requests
        and len(measured_scores) == args.requests
        and all(score == 1.0 for score in measured_scores)
    )
    audit_mapping_ok = expected_markers == audited_markers and len(expected_markers) == args.requests
    raw_path = output_path.with_suffix(".samples.jsonl")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(
        "".join(json.dumps(sample, ensure_ascii=False, sort_keys=True) + "\n" for sample in raw_samples),
        encoding="utf-8",
    )

    targets = {
        "initialization_success_rate": measured["session_ids_total"] == args.sessions,
        "session_id_unique_rate": (
            measured["session_ids_unique"] == args.sessions and measured["empty_session_ids"] == 0
        ),
        "call_success_rate": len(measured["errors"]) == 0,
        "response_isolation": measured["response_mismatches"] == 0,
        "audit_completeness": measured_audit_ok,
        "audit_request_mapping": audit_mapping_ok,
        "audit_chain": chain_ok,
        "session_reclamation": health.get("active_sessions") == 0,
        "p95_le_300ms": measured["call_latency_ms"]["p95"] <= 300.0,
        "throughput_ge_50qps": measured["throughput_qps"] >= 50.0,
        "peak_rss_le_1024mb": bool(memory_samples)
        and max(memory_samples) <= 1024 * 1024 * 1024,
    }
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "claim_scope": "single_process_uvicorn_stateful_mcp_multisession",
        "benchmark": {
            "path": str(Path(__file__).resolve()),
            "sha256": _sha256(__file__),
        },
        "config": {"path": str(config_path), "sha256": _sha256(config_path)},
        "environment": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "cpu_count": os.cpu_count(),
        },
        "server": {
            "url": f"http://127.0.0.1:{port}/mcp",
            "worker_count": 1,
            "startup_ms": round(startup_ms, 3),
            "session_mode": "stateful",
            "session_idle_timeout_seconds": 60,
        },
        "workload": {
            "sessions": args.sessions,
            "requests": args.requests,
            "warmup": args.warmup,
            "tool": "get_cpu",
            "case_distribution": {"allow": 1.0},
        },
        "warmup": warmup_result,
        "measured": measured,
        "audit": {
            "path": str(audit_path),
            "records_total": len(records),
            "measured_records": len(measured_records),
            "measured_trace_ids_unique": len(set(measured_trace_ids)),
            "measured_completeness_min": min(measured_scores, default=0.0),
            "request_markers_expected": len(expected_markers),
            "request_markers_audited": len(audited_markers),
            "request_markers_missing": sorted(expected_markers - audited_markers),
            "request_markers_unexpected": sorted(audited_markers - expected_markers),
            "chain_verified": chain_ok,
            "bad_line": bad_line,
            "sha256": _sha256(audit_path),
        },
        "memory": {
            "peak_rss_mb": round(max(memory_samples, default=0) / (1024 * 1024), 3),
            "samples": len(memory_samples),
        },
        "health_after": health,
        "targets": targets,
        "overall_pass": all(targets.values()),
        "artifacts": {
            "raw_samples_path": str(raw_path),
            "raw_samples_sha256": _sha256(raw_path),
        },
        "limitations": [
            "single uvicorn worker",
            "single shared stdio downstream session",
            "allow-only workload",
            "no TLS or external reverse proxy",
            "not a multi-process pending-ledger claim",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark stateful Streamable HTTP MCP sessions")
    parser.add_argument("--config", default="configs/xa-guard.opencode-smoke.yaml")
    parser.add_argument("--sessions", type=int, default=10)
    parser.add_argument("--requests", type=int, default=500)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument(
        "--output",
        default="docs/evidence/l3-streamable-http-benchmark-2026-06-18.json",
    )
    parser.add_argument("--require-targets", action="store_true")
    args = parser.parse_args()
    report = asyncio.run(benchmark(args))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.require_targets and not report["overall_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
