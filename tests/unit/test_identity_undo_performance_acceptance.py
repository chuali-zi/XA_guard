from __future__ import annotations

from scripts.benchmark_identity_undo import (
    SCHEMA,
    _summarize_latency_run,
    bootstrap_p95_upper_bound,
    build_evidence,
    percentile,
    randomized_orders,
    sample_statistics,
)


def test_percentile_and_statistics_are_interpolated_and_stable() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0]

    assert percentile(values, 0.50) == 3.0
    assert percentile(values, 0.95) == 4.8
    assert sample_statistics(values) == {
        "count": 5,
        "min_ms": 1.0,
        "mean_ms": 3.0,
        "p50_ms": 3.0,
        "p95_ms": 4.8,
        "max_ms": 5.0,
    }


def test_randomized_orders_are_deterministic_and_balanced() -> None:
    first = randomized_orders(501, seed=20260712)
    second = randomized_orders(501, seed=20260712)

    assert first == second
    assert set(first) == {"AB", "BA"}
    assert abs(first.count("AB") - first.count("BA")) == 1
    assert first != (["AB"] * first.count("AB") + ["BA"] * first.count("BA"))


def test_one_sided_bootstrap_bound_is_deterministic() -> None:
    samples = [10.0] * 80 + [20.0] * 20

    first = bootstrap_p95_upper_bound(samples, seed=7, iterations=200)
    second = bootstrap_p95_upper_bound(samples, seed=7, iterations=200)

    assert first == second
    assert first == 20.0
    assert bootstrap_p95_upper_bound([12.5], seed=9, iterations=1) == 12.5


def _passing_run() -> dict[str, object]:
    return _summarize_latency_run(
        run_number=1,
        seed=11,
        orders=["AB", "BA", "AB", "BA"],
        baseline_ms=[10.0, 11.0, 12.0, 13.0],
        protected_ms=[20.0, 22.0, 24.0, 26.0],
        bootstrap_iterations=50,
    )


def test_latency_run_records_order_stats_ci_and_recalculable_samples() -> None:
    run = _passing_run()

    assert run["order_counts"] == {"AB": 2, "BA": 2}
    assert run["incremental"]["definition"] == "protected_ms - baseline_ms"  # type: ignore[index]
    assert run["incremental"]["bootstrap_p95_one_sided_95_upper_ms"] <= 50  # type: ignore[index]
    assert run["incremental_samples_ms"] == [10.0, 11.0, 12.0, 13.0]
    assert len(str(run["incremental_samples_sha256"])) == 64
    assert run["passed"] is True


def test_evidence_shape_marks_reference_and_development_profiles() -> None:
    flow = {
        "flow": 1,
        "approval_to_cancelled_ms": 800.0,
        "limit_seconds": 30.0,
        "passed": True,
    }
    reference = build_evidence(
        runs=[_passing_run()],
        undo_flows=[flow],
        config={"runs": 3, "concurrency": 10},
        generated_at="2026-07-12T00:00:00+00:00",
        development_mode=False,
    )
    development = build_evidence(
        runs=[_passing_run()],
        undo_flows=[flow],
        config={"runs": 1, "concurrency": 1},
        generated_at="2026-07-12T00:00:00+00:00",
        development_mode=True,
    )

    assert reference["schema"] == SCHEMA
    assert reference["status"] == "passed"
    assert reference["reference_ready_eligible"] is True
    assert reference["methodology"]["tokens_or_credentials_persisted"] is False
    assert development["profile"] == "development"
    assert development["reference_ready_eligible"] is False


def test_evidence_fails_if_any_write_or_undo_check_fails() -> None:
    failed_run = _passing_run()
    failed_run["passed"] = False
    evidence = build_evidence(
        runs=[failed_run],
        undo_flows=[{"passed": True}],
        config={},
        generated_at="2026-07-12T00:00:00+00:00",
        development_mode=False,
    )

    assert evidence["status"] == "failed"
    assert evidence["checks"] == {
        "all_write_runs_passed": False,
        "all_undo_flows_passed": True,
        "thresholds_passed": False,
    }
