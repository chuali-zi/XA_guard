# L3 R4 Performance Acceptance - 2026-07-05

Scope: R4 performance acceptance per `docs/acceptance/L3-test-and-acceptance.md`, run on Windows 11 / Python 3.12.10 with `PYTHONPATH=src`.

## Result

R4 PASS for the declared support scope: in-process 500 requests and Streamable HTTP 10 sessions / 500 requests both met the PRD medium targets.

20 sessions / 500 requests was run as capacity boundary evidence only. It did not meet the P95 target and is recorded as LIMIT, not supported capacity.

## Commands

```powershell
$env:PYTHONPATH = "src"
python -m pytest -q -p no:cacheprovider tests/unit/test_l3_performance_benchmark.py
python scripts/benchmark_l3_performance.py --requests 500 --warmup 30 --concurrency 10 --audit-dir "docs\evidence\l3-r4-20260705-current\perf-impl-audit" --output "docs\evidence\l3-r4-20260705-current\perf-implementation-500.json" --require-targets
python scripts/benchmark_streamable_http.py --sessions 10 --requests 500 --warmup 30 --output "docs\evidence\l3-r4-20260705-current\perf-http-10x500.json" --require-targets
python scripts/benchmark_streamable_http.py --sessions 20 --requests 500 --warmup 30 --output "docs\evidence\l3-r4-20260705-current\perf-http-20x500-limit.json"
```

## Metrics

| Run | Result | P50 | P95 | QPS | Peak RSS | Audit |
|---|---:|---:|---:|---:|---:|---|
| in-process 500 / concurrency 10 | PASS | 4.362 ms | 36.042 ms | 262.301 | 62.172 MB | 530 records, chain verified |
| HTTP 10 sessions / 500 requests | PASS | 139.618 ms | 185.518 ms | 69.876 | 102.867 MB | 500/500 measured markers, chain verified |
| HTTP 20 sessions / 500 requests | LIMIT | 315.353 ms | 483.732 ms | 59.652 | 131.992 MB | 500/500 measured markers, chain verified |

## Boundary

This is a single-process, single-worker, local Windows run. HTTP benchmark uses one uvicorn worker and one shared stdio downstream session with allow-only workload. It does not claim multi-worker, TLS, container networking, real model inference, real tool latency, or multi-machine soak performance.
