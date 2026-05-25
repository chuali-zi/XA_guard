"""HTML 报告生成器 — 单页内联 CSS，无构建链依赖。"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from bench.metrics import MetricsReport
from xa_guard.types import BenchResult

_CSS = """
body{font-family:-apple-system,"Microsoft YaHei",sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;line-height:1.6;color:#222;background:#f9fafb}
h1{border-bottom:3px solid #2a5298;padding-bottom:8px;color:#1a3a6e}
h2{color:#2a5298;margin-top:32px;border-left:4px solid #2a5298;padding-left:10px}
.cards{display:flex;flex-wrap:wrap;gap:14px;margin:18px 0}
.card{background:#fff;border-radius:8px;padding:16px 22px;min-width:130px;box-shadow:0 1px 4px rgba(0,0,0,.10);text-align:center}
.card .val{font-size:2em;font-weight:700;color:#2a5298}
.card .lbl{font-size:.85em;color:#666;margin-top:4px}
.card.warn .val{color:#d97706}
.card.bad .val{color:#dc2626}
.card.good .val{color:#16a34a}
table{width:100%;border-collapse:collapse;margin-top:10px;background:#fff;border-radius:6px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08)}
th{background:#2a5298;color:#fff;padding:9px 12px;text-align:left;font-size:.9em}
td{padding:8px 12px;font-size:.88em;border-bottom:1px solid #e5e7eb}
tr.pass td{background:#f0fdf4}
tr.fail td{background:#fef2f2}
tr:hover td{filter:brightness(.97)}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:.78em;font-weight:600}
.badge.allow{background:#dcfce7;color:#166534}
.badge.deny{background:#fee2e2;color:#991b1b}
.badge.warn{background:#fef9c3;color:#854d0e}
.badge.require_approval{background:#e0e7ff;color:#3730a3}
.dim-section{margin-top:28px}
.dim-table td:first-child{font-weight:600}
"""

_BADGE = {
    "allow": '<span class="badge allow">allow</span>',
    "deny": '<span class="badge deny">deny</span>',
    "warn": '<span class="badge warn">warn</span>',
    "require_approval": '<span class="badge require_approval">req_approval</span>',
}


def _badge(val: str) -> str:
    return _BADGE.get(val, f'<span class="badge">{val}</span>')


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _card(val: str, label: str, cls: str = "") -> str:
    return f'<div class="card {cls}"><div class="val">{val}</div><div class="lbl">{label}</div></div>'


def render_html(
    results: Sequence[BenchResult],
    metrics: MetricsReport,
    out_path: str | Path | None = None,
) -> str:
    rows_html = ""
    for r in results:
        tr_cls = "pass" if r.passed else "fail"
        exp = _badge(r.case.expected_decision.value)
        act = _badge(r.actual_decision.value)
        taint = r.actual_taint.value if r.actual_taint else "-"
        hits = ", ".join(r.rule_hits) if r.rule_hits else "-"
        rows_html += (
            f'<tr class="{tr_cls}">'
            f"<td>{r.case.case_id}</td>"
            f"<td>{r.case.dimension}</td>"
            f"<td>{r.case.attack_type}</td>"
            f"<td>{exp}</td>"
            f"<td>{act}</td>"
            f"<td>{'✓' if r.passed else '✗'}</td>"
            f"<td>{taint}</td>"
            f"<td>{hits}</td>"
            f"<td>{r.latency_ms:.1f}</td>"
            "</tr>\n"
        )

    # dimension sub-tables
    dim_html = ""
    if metrics.by_dimension:
        dim_html += '<h2>维度细分</h2>'
        dim_html += (
            '<table class="dim-table"><thead><tr>'
            "<th>维度</th><th>用例数</th><th>ASR</th><th>FPR</th><th>Recall</th><th>CuP</th><th>Pass%</th>"
            "</tr></thead><tbody>"
        )
        for dim, m in sorted(metrics.by_dimension.items()):
            dim_html += (
                f"<tr><td>{dim}</td>"
                f"<td>{m['total']}</td>"
                f"<td>{_pct(m['asr'])}</td>"
                f"<td>{_pct(m['fpr'])}</td>"
                f"<td>{_pct(m['recall'])}</td>"
                f"<td>{_pct(m['cup'])}</td>"
                f"<td>{_pct(m['pass_rate'])}</td></tr>"
            )
        dim_html += "</tbody></table>"

    asr_cls = "bad" if metrics.asr > 0.2 else ("warn" if metrics.asr > 0.05 else "good")
    fpr_cls = "bad" if metrics.fpr > 0.2 else ("warn" if metrics.fpr > 0.05 else "good")

    cards = (
        _card(f"{metrics.total}", "总用例")
        + _card(f"{metrics.attacks}", "攻击用例")
        + _card(f"{metrics.benign}", "合法用例")
        + _card(_pct(metrics.asr), "ASR (攻击成功率)", asr_cls)
        + _card(_pct(metrics.fpr), "FPR (误拦率)", fpr_cls)
        + _card(_pct(metrics.recall), "Recall", "good" if metrics.recall >= 0.8 else "warn")
        + _card(_pct(metrics.cup), "CuP (完成率)")
        + _card(f"{metrics.latency_p50:.0f}ms", "P50 延迟")
        + _card(f"{metrics.latency_p95:.0f}ms", "P95 延迟")
        + _card(_pct(metrics.pass_rate), "Pass Rate", "good" if metrics.pass_rate >= 0.7 else "warn")
        + _card(_pct(metrics.audit_completeness), "审计完整率", "good")
    )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>XA-Bench 评测报告</title>
<style>{_CSS}</style>
</head>
<body>
<h1>XA-Bench 评测报告</h1>
<h2>总体 Metrics</h2>
<div class="cards">{cards}</div>
{dim_html}
<h2>用例明细</h2>
<table>
<thead><tr>
<th>case_id</th><th>dimension</th><th>attack_type</th>
<th>expected</th><th>actual</th><th>passed</th>
<th>taint</th><th>rule_hits</th><th>latency_ms</th>
</tr></thead>
<tbody>
{rows_html}
</tbody>
</table>
</body>
</html>"""

    if out_path is not None:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(html, encoding="utf-8")

    return html
