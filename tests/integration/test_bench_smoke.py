"""XA-Bench 烟雾测试 — csab-gov-mini-seed.yaml + xa-guard.yaml。

因关卡仍为 stub，只验证：
- pipeline 跑完不崩
- results 非空
- metrics.asr / fpr 介于 0-1
- by_dimension 按维度分组正确
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bench.metrics import compute
from bench.runner import load_cases, run_suite
from xa_guard.config import XAGuardConfig

SUITE = Path("bench/cases/csab-gov-mini-seed.yaml")
CONFIG = Path("configs/xa-guard.yaml")


@pytest.fixture(scope="module")
def cfg():
    return XAGuardConfig.from_yaml(CONFIG)


@pytest.fixture(scope="module")
def results(cfg):
    return asyncio.run(run_suite(SUITE, cfg))


def test_results_nonempty(results):
    assert len(results) > 0, "run_suite must return at least one BenchResult"


def test_results_match_case_count(results):
    cases = load_cases(SUITE)
    assert len(cases) == 290
    assert len(results) == len(cases)


def test_metrics_in_range(results):
    m = compute(results)
    assert 0.0 <= m.asr <= 1.0, f"ASR out of range: {m.asr}"
    assert 0.0 <= m.fpr <= 1.0, f"FPR out of range: {m.fpr}"
    assert 0.0 <= m.recall <= 1.0
    assert 0.0 <= m.cup <= 1.0
    assert 0.0 <= m.pass_rate <= 1.0
    assert m.total == len(results)


def test_by_dimension(results):
    m = compute(results)
    assert m.by_dimension is not None
    # seed YAML has 7 dimensions
    expected_dims = {
        "execution_safety",
        "data_safety",
        "content_safety",
        "supply_chain",
        "compliance",
        "interpretability",
        "traceability",
    }
    assert set(m.by_dimension.keys()) == expected_dims
    assert {dim: m.by_dimension[dim]["total"] for dim in expected_dims} == {
        "execution_safety": 60,
        "data_safety": 50,
        "content_safety": 60,
        "supply_chain": 25,
        "compliance": 50,
        "interpretability": 20,
        "traceability": 25,
    }
    for dim, dm in m.by_dimension.items():
        assert 0.0 <= dm["asr"] <= 1.0, f"{dim}.asr out of range"
        assert 0.0 <= dm["fpr"] <= 1.0, f"{dim}.fpr out of range"


def test_dimension_filter(cfg):
    results_filtered = asyncio.run(run_suite(SUITE, cfg, dimension="content_safety"))
    assert all(r.case.dimension == "content_safety" for r in results_filtered)
    assert len(results_filtered) == 60


def test_html_report_renders(results):
    from bench.metrics import compute
    from bench.reporters.html_report import render_html

    m = compute(results)
    html = render_html(results, m)
    assert "<html" in html
    assert "XA-Bench" in html
    assert "ASR" in html


def test_each_result_has_decision(results):
    from xa_guard.types import Decision

    for r in results:
        assert r.actual_decision in list(Decision)
        assert isinstance(r.latency_ms, float)
        assert r.latency_ms >= 0
