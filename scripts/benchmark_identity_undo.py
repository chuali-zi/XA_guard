"""Measure the reference Identity + Effect overhead and real Undo recovery latency.

The write benchmark is deliberately paired: each pair creates one ticket through
the authenticated XA-Guard control plane and one ticket directly through the
stateful reference business API.  Both sides therefore include JSON encoding,
HTTP transport, and a PostgreSQL write.  AB/BA order is balanced and shuffled to
reduce order bias; the reported increment is ``protected - baseline``.

This program never emits bearer tokens or service credentials.  A run using
reduced sample counts must opt in with ``--dev`` and is explicitly marked as
ineligible for REFERENCE-READY evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import math
import random
import re
import statistics
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

import httpx

if __package__:
    # The shared helper is also an executable script and therefore imports its
    # PKCE sibling by its script name.  Register that sibling when this module is
    # imported as ``scripts.*`` by unit tests.
    sys.modules.setdefault(
        "verify_reference_e2e",
        importlib.import_module("scripts.verify_reference_e2e"),
    )
    _acceptance = importlib.import_module("scripts.reference_acceptance_lib")
else:
    _acceptance = importlib.import_module("reference_acceptance_lib")

AcceptanceFailure = _acceptance.AcceptanceFailure
ROOT = _acceptance.ROOT
ReferenceIdentity = _acceptance.ReferenceIdentity
read_secret = _acceptance.read_secret
sql = _acceptance.sql
wait_url = _acceptance.wait_url
write_json = _acceptance.write_json


SCHEMA = "xa-guard.identity-undo-performance.v1"
DEFAULT_OUTPUT = ROOT / ".runtime" / "evidence" / "identity-undo-performance.json"
INCREMENTAL_LIMIT_MS = 50.0
UNDO_LIMIT_SECONDS = 30.0


class PerformanceFailure(AcceptanceFailure):
    """A benchmark failure whose message is safe to print."""


def percentile(values: Sequence[float], quantile: float) -> float:
    """Return a linearly interpolated quantile, matching common latency tools."""

    if not values:
        raise ValueError("at least one sample is required")
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be between zero and one")
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def sample_statistics(values: Sequence[float]) -> dict[str, float | int]:
    """Create the stable summary persisted in the evidence bundle."""

    if not values:
        raise ValueError("at least one sample is required")
    samples = [float(value) for value in values]
    return {
        "count": len(samples),
        "min_ms": round(min(samples), 6),
        "mean_ms": round(statistics.fmean(samples), 6),
        "p50_ms": round(percentile(samples, 0.50), 6),
        "p95_ms": round(percentile(samples, 0.95), 6),
        "max_ms": round(max(samples), 6),
    }


def bootstrap_p95_upper_bound(
    values: Sequence[float],
    *,
    seed: int,
    iterations: int = 5_000,
    confidence: float = 0.95,
) -> float:
    """Return a deterministic one-sided bootstrap upper bound for sample p95."""

    samples = [float(value) for value in values]
    if not samples:
        raise ValueError("at least one sample is required")
    if iterations < 1:
        raise ValueError("bootstrap iterations must be positive")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be strictly between zero and one")
    if len(samples) == 1:
        return samples[0]
    rng = random.Random(seed)
    estimates = [
        percentile(rng.choices(samples, k=len(samples)), 0.95)
        for _ in range(iterations)
    ]
    return percentile(estimates, confidence)


def randomized_orders(count: int, seed: int) -> list[str]:
    """Build a deterministic, balanced, randomly shuffled AB/BA sequence."""

    if count < 1:
        raise ValueError("pair count must be positive")
    rng = random.Random(seed)
    orders = ["AB"] * (count // 2) + ["BA"] * (count // 2)
    if count % 2:
        orders.append("AB" if rng.getrandbits(1) else "BA")
    rng.shuffle(orders)
    return orders


def _summarize_latency_run(
    *,
    run_number: int,
    seed: int,
    orders: Sequence[str],
    baseline_ms: Sequence[float],
    protected_ms: Sequence[float],
    bootstrap_iterations: int,
    limit_ms: float = INCREMENTAL_LIMIT_MS,
) -> dict[str, Any]:
    if not (len(orders) == len(baseline_ms) == len(protected_ms)):
        raise ValueError("paired latency vectors must have identical lengths")
    increments = [
        float(protected) - float(baseline)
        for baseline, protected in zip(baseline_ms, protected_ms, strict=True)
    ]
    incremental = sample_statistics(increments)
    upper = round(
        bootstrap_p95_upper_bound(
            increments,
            seed=seed + 7919,
            iterations=bootstrap_iterations,
        ),
        6,
    )
    p95_ok = float(incremental["p95_ms"]) <= limit_ms
    confidence_ok = upper <= limit_ms
    return {
        "run": run_number,
        "seed": seed,
        "pair_count": len(orders),
        "order_counts": {"AB": orders.count("AB"), "BA": orders.count("BA")},
        "baseline": sample_statistics(baseline_ms),
        "protected": sample_statistics(protected_ms),
        "incremental": {
            **incremental,
            "definition": "protected_ms - baseline_ms",
            "bootstrap_p95_one_sided_95_upper_ms": upper,
            "bootstrap_iterations": bootstrap_iterations,
        },
        "checks": {
            "incremental_p95_at_most_50ms": p95_ok,
            "bootstrap_upper_at_most_50ms": confidence_ok,
        },
        "passed": p95_ok and confidence_ok,
        # Retain paired increments for independent recalculation without storing
        # business content, identity tokens, or service credentials.
        "incremental_samples_ms": [round(value, 6) for value in increments],
        "incremental_samples_sha256": hashlib.sha256(
            json.dumps(
                [round(value, 6) for value in increments],
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    }


def build_evidence(
    *,
    runs: Sequence[dict[str, Any]],
    undo_flows: Sequence[dict[str, Any]],
    config: dict[str, Any],
    generated_at: str,
    development_mode: bool,
) -> dict[str, Any]:
    """Assemble the secret-free evidence envelope (also exercised by unit tests)."""

    write_passed = bool(runs) and all(bool(run.get("passed")) for run in runs)
    undo_passed = bool(undo_flows) and all(bool(flow.get("passed")) for flow in undo_flows)
    thresholds_passed = write_passed and undo_passed
    return {
        "schema": SCHEMA,
        "generated_at": generated_at,
        "profile": "development" if development_mode else "reference-acceptance",
        "reference_ready_eligible": not development_mode,
        "methodology": {
            "write_comparison": "paired stateful PostgreSQL writes over HTTP",
            "incremental_definition": "protected_ms - direct_business_baseline_ms",
            "pair_order": "balanced deterministic shuffle of AB and BA",
            "confidence": "one-sided nonparametric bootstrap 95% upper bound of p95",
            "undo_interval": "xa_undo_requests.decided_at to xa_reference_tickets.cancelled_at",
            "tokens_or_credentials_persisted": False,
        },
        "config": config,
        "write_latency_runs": list(runs),
        "undo_flows": list(undo_flows),
        "checks": {
            "all_write_runs_passed": write_passed,
            "all_undo_flows_passed": undo_passed,
            "thresholds_passed": thresholds_passed,
        },
        "status": "passed" if thresholds_passed else "failed",
    }


async def _timed_request(
    request: Callable[[], Any],
    *,
    expected_status: int,
    label: str,
) -> float:
    started = time.perf_counter_ns()
    response = await request()
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
    if response.status_code != expected_status:
        raise PerformanceFailure(f"{label} failed with HTTP {response.status_code}")
    return elapsed_ms


async def _measure_pairs(
    *,
    control_url: str,
    business_url: str,
    agent_token: str,
    business_api_key: str,
    pair_count: int,
    concurrency: int,
    seed: int,
    namespace: str,
) -> tuple[list[str], list[float], list[float]]:
    orders = randomized_orders(pair_count, seed)
    baseline_ms = [0.0] * pair_count
    protected_ms = [0.0] * pair_count
    semaphore = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(max_connections=max(20, concurrency * 2), max_keepalive_connections=20)

    async with httpx.AsyncClient(timeout=30.0, limits=limits) as client:
        async def one_pair(index: int, order: str) -> None:
            unique = f"{namespace}-{index:06d}-{uuid.uuid4().hex[:12]}"
            baseline_effect_id = f"perf-{unique}"
            title = f"Performance acceptance {unique}"
            description = f"Stateful paired write {unique}"

            async def baseline() -> float:
                return await _timed_request(
                    lambda: client.post(
                        business_url + "/tickets",
                        headers={
                            "Authorization": f"Bearer {business_api_key}",
                            "X-XA-Effect-ID": baseline_effect_id,
                            "Idempotency-Key": baseline_effect_id,
                            "X-Correlation-ID": f"perf-baseline-{unique}",
                        },
                        json={
                            "tenant_id": "acme-corp",
                            "title": title,
                            "description": description,
                            "priority": "normal",
                        },
                    ),
                    expected_status=201,
                    label="direct business baseline write",
                )

            async def protected() -> float:
                headers = ReferenceIdentity.headers(agent_token)
                headers["X-Correlation-ID"] = f"perf-protected-{unique}"
                return await _timed_request(
                    lambda: client.post(
                        control_url + "/control/v1/tickets",
                        headers=headers,
                        json={
                            "title": title,
                            "description": description,
                            "priority": "normal",
                            "data_domain": "engineering_docs",
                        },
                    ),
                    expected_status=201,
                    label="protected control-plane write",
                )

            async with semaphore:
                if order == "AB":
                    baseline_ms[index] = await baseline()
                    protected_ms[index] = await protected()
                else:
                    protected_ms[index] = await protected()
                    baseline_ms[index] = await baseline()

        await asyncio.gather(*(one_pair(index, order) for index, order in enumerate(orders)))
    return orders, baseline_ms, protected_ms


async def _run_write_benchmark(
    *,
    control_url: str,
    business_url: str,
    agent_token: str,
    business_api_key: str,
    runs: int,
    pairs: int,
    warmups: int,
    concurrency: int,
    bootstrap_iterations: int,
    seed: int,
) -> list[dict[str, Any]]:
    namespace = f"{int(time.time())}-{uuid.uuid4().hex[:10]}"
    results: list[dict[str, Any]] = []
    for run_index in range(runs):
        run_number = run_index + 1
        run_seed = seed + run_index * 104_729
        await _measure_pairs(
            control_url=control_url,
            business_url=business_url,
            agent_token=agent_token,
            business_api_key=business_api_key,
            pair_count=warmups,
            concurrency=concurrency,
            seed=run_seed - 1,
            namespace=f"{namespace}-warmup-r{run_number}",
        )
        orders, baseline_ms, protected_ms = await _measure_pairs(
            control_url=control_url,
            business_url=business_url,
            agent_token=agent_token,
            business_api_key=business_api_key,
            pair_count=pairs,
            concurrency=concurrency,
            seed=run_seed,
            namespace=f"{namespace}-measured-r{run_number}",
        )
        results.append(
            _summarize_latency_run(
                run_number=run_number,
                seed=run_seed,
                orders=orders,
                baseline_ms=baseline_ms,
                protected_ms=protected_ms,
                bootstrap_iterations=bootstrap_iterations,
            )
        )
    return results


def _expect_object(response: httpx.Response, status: int, label: str) -> dict[str, Any]:
    if response.status_code != status:
        raise PerformanceFailure(f"{label} failed with HTTP {response.status_code}")
    try:
        value = response.json()
    except ValueError as exc:
        raise PerformanceFailure(f"{label} returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise PerformanceFailure(f"{label} returned a non-object response")
    return value


def _safe_identifier(value: Any, label: str) -> str:
    candidate = str(value or "")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", candidate) is None:
        raise PerformanceFailure(f"{label} was missing or malformed")
    return candidate


def _undo_timestamps(request_id: str) -> tuple[str, str, float] | None:
    # request_id is restricted to a quote-free identifier before entering this
    # fixed SQL statement.
    row = sql(
        "SELECT r.decided_at::text || '|' || t.cancelled_at::text || '|' || "
        "round((extract(epoch FROM (t.cancelled_at-r.decided_at))*1000)::numeric,3)::text "
        "FROM xa_undo_requests r "
        "JOIN xa_reference_tickets t ON t.create_effect_id=r.effect_id "
        f"WHERE r.request_id='{request_id}' AND t.cancelled_at IS NOT NULL"
    )
    if not row:
        return None
    parts = row.split("|")
    if len(parts) != 3:
        raise PerformanceFailure("Undo timestamp query returned an invalid shape")
    try:
        return parts[0], parts[1], float(parts[2])
    except ValueError as exc:
        raise PerformanceFailure("Undo timestamp query returned invalid values") from exc


def _measure_undo_flows(
    *,
    control_url: str,
    identity: ReferenceIdentity,
    flow_count: int,
    timeout_seconds: float = 45.0,
) -> list[dict[str, Any]]:
    # Fresh tokens keep the Undo phase independent of benchmark duration.  They
    # remain in memory only and are never included in the returned evidence.
    alice_token = identity.agent_token("alice")
    dora_token = identity.agent_token("dora")
    namespace = f"undo-perf-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    results: list[dict[str, Any]] = []
    with httpx.Client(timeout=30.0) as client:
        for index in range(flow_count):
            unique = f"{namespace}-{index:02d}"
            create = _expect_object(
                client.post(
                    control_url + "/control/v1/tickets",
                    headers=ReferenceIdentity.headers(alice_token),
                    json={
                        "title": f"Undo performance {unique}",
                        "description": f"Real approval-to-cancellation measurement {unique}",
                        "priority": "normal",
                        "data_domain": "engineering_docs",
                    },
                ),
                201,
                "Undo benchmark ticket creation",
            )
            effect_id = _safe_identifier(create.get("effect_id"), "effect_id")
            business = create.get("business") or {}
            ticket_id = str(((business.get("body") or {}).get("ticket_id")) or "")
            if not ticket_id:
                raise PerformanceFailure("Undo benchmark creation returned no ticket_id")

            undo = _expect_object(
                client.post(
                    f"{control_url}/control/v1/effects/{effect_id}/undo-requests",
                    headers=ReferenceIdentity.headers(
                        alice_token,
                        idempotency_key=f"undo-performance-{effect_id}",
                    ),
                    json={"reason": "Performance acceptance controlled recovery."},
                ),
                201,
                "Undo benchmark request",
            )
            request_id = _safe_identifier(undo.get("request_id"), "request_id")
            _expect_object(
                client.post(
                    f"{control_url}/control/v1/undo-requests/{request_id}/decision",
                    headers=ReferenceIdentity.headers(dora_token),
                    json={
                        "decision": "approve",
                        "reason": "Independent performance acceptance approval.",
                    },
                ),
                200,
                "Undo benchmark approval",
            )

            deadline = time.monotonic() + timeout_seconds
            timestamps = _undo_timestamps(request_id)
            while timestamps is None and time.monotonic() < deadline:
                time.sleep(0.25)
                timestamps = _undo_timestamps(request_id)
            if timestamps is None:
                raise PerformanceFailure("Undo did not reach cancelled state before polling timeout")
            decided_at, cancelled_at, elapsed_ms = timestamps
            passed = elapsed_ms <= UNDO_LIMIT_SECONDS * 1000.0
            results.append(
                {
                    "flow": index + 1,
                    "effect_id": effect_id,
                    "request_id": request_id,
                    "ticket_id": ticket_id,
                    "decided_at": decided_at,
                    "cancelled_at": cancelled_at,
                    "approval_to_cancelled_ms": round(elapsed_ms, 3),
                    "limit_seconds": UNDO_LIMIT_SECONDS,
                    "passed": passed,
                }
            )
    return results


def _validate_args(args: argparse.Namespace) -> None:
    positive = ("runs", "pairs", "warmups", "concurrency", "bootstrap_iterations", "undo_flows")
    if any(int(getattr(args, name)) < 1 for name in positive):
        raise PerformanceFailure("benchmark counts must all be positive")
    if args.dev:
        return
    if args.runs < 3:
        raise PerformanceFailure("reference acceptance requires at least 3 independent runs")
    if args.pairs < 500:
        raise PerformanceFailure("reference acceptance requires at least 500 measured pairs per run")
    if args.warmups < 30:
        raise PerformanceFailure("reference acceptance requires at least 30 warmup pairs per run")
    if args.concurrency != 10:
        raise PerformanceFailure("reference acceptance requires concurrency=10")
    if args.bootstrap_iterations < 2_000:
        raise PerformanceFailure("reference acceptance requires at least 2000 bootstrap iterations")
    if args.undo_flows < 10:
        raise PerformanceFailure("reference acceptance requires at least 10 real Undo flows")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-url", default="http://localhost:13000")
    parser.add_argument("--business-url", default="http://localhost:13082")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--pairs", type=int, default=500)
    parser.add_argument("--warmups", type=int, default=30)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--bootstrap-iterations", type=int, default=5_000)
    parser.add_argument("--undo-flows", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20_260_712)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--dev",
        action="store_true",
        help="allow reduced counts; resulting evidence is not REFERENCE-READY eligible",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    try:
        _validate_args(args)
        control_url = args.control_url.rstrip("/")
        business_url = args.business_url.rstrip("/")
        wait_url(control_url + "/readyz")
        wait_url(business_url + "/readyz")
        identity = ReferenceIdentity(control_url=control_url)
        agent_token = identity.agent_token("alice")
        business_api_key = read_secret("business_api_key")
        runs = asyncio.run(
            _run_write_benchmark(
                control_url=control_url,
                business_url=business_url,
                agent_token=agent_token,
                business_api_key=business_api_key,
                runs=args.runs,
                pairs=args.pairs,
                warmups=args.warmups,
                concurrency=args.concurrency,
                bootstrap_iterations=args.bootstrap_iterations,
                seed=args.seed,
            )
        )
        undo_flows = _measure_undo_flows(
            control_url=control_url,
            identity=identity,
            flow_count=args.undo_flows,
        )
        evidence = build_evidence(
            runs=runs,
            undo_flows=undo_flows,
            config={
                "runs": args.runs,
                "measured_pairs_per_run": args.pairs,
                "warmup_pairs_per_run": args.warmups,
                "concurrency": args.concurrency,
                "bootstrap_iterations": args.bootstrap_iterations,
                "bootstrap_seed": args.seed,
                "incremental_p95_limit_ms": INCREMENTAL_LIMIT_MS,
                "undo_flows": args.undo_flows,
                "undo_limit_seconds": UNDO_LIMIT_SECONDS,
            },
            generated_at=datetime.now(timezone.utc).isoformat(),
            development_mode=args.dev,
        )
        write_json(args.output.resolve(), evidence)
    except (OSError, ValueError, KeyError, httpx.HTTPError, AcceptanceFailure) as exc:
        raise SystemExit(f"IDENTITY + UNDO PERFORMANCE FAILED: {exc}") from None

    summary = {
        "schema": evidence["schema"],
        "status": evidence["status"],
        "profile": evidence["profile"],
        "reference_ready_eligible": evidence["reference_ready_eligible"],
        "output": str(args.output.resolve()),
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    if evidence["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
