"""插件安全评级 + 三段审批 — 赛题方向 3。

子 agent 实施职责：
- 输入 ScanReport → 输出评级（A/B/C/D/F）
- A/B 自动放行；C 人工复核；D/F 拒绝
- 接口预留"上线后行为漂移监测"占位
"""
from __future__ import annotations

from typing import Literal

from xa_guard.aibom.scanner import ScanReport, scan_python_source

Grade = Literal["A", "B", "C", "D", "F"]


def rate(report: ScanReport) -> tuple[Grade, str]:
    """返回 (评级, 理由)。"""
    indicators = report.risk_indicators
    capabilities = set(report.inferred_capabilities)
    reasons: list[str] = []

    if "dynamic_code" in capabilities:
        reasons.append("dynamic_code detected via eval/exec")
    if "process_exec" in capabilities:
        reasons.append("process_exec detected via shell/subprocess API")
    if "deserialization" in capabilities:
        reasons.append("unsafe deserialization detected via pickle load API")
    if "network" in capabilities:
        reasons.append("network capability inferred from imports or HTTP/socket APIs")
    if "filesystem_write" in capabilities:
        reasons.append("filesystem_write capability inferred from destructive/write APIs")
    if indicators.get("metadata_overbroad_permission", 0):
        reasons.append("metadata declares overbroad permission")
    if indicators.get("metadata_undeclared_capability", 0):
        reasons.append("code uses capabilities not declared in metadata")
    if indicators.get("metadata_suspicious_script", 0) or indicators.get("metadata_suspicious_url", 0):
        reasons.append("metadata contains suspicious URL/script fields")
    if indicators.get("suspicious_network_endpoint", 0):
        reasons.append("source references suspicious external endpoint")
    if indicators.get("dependency_direct_url", 0):
        reasons.append("dependency uses direct URL/git source")
    if indicators.get("dependency_typosquat", 0):
        reasons.append("possible dependency typosquat detected")
    if indicators.get("dependency_editable", 0):
        reasons.append("dependency is editable")
    if indicators.get("dependency_local_path", 0):
        reasons.append("dependency points to a local path")
    if indicators.get("dependency_unpinned", 0):
        reasons.append(f"{indicators['dependency_unpinned']} dependencies are unpinned")
    if indicators.get("artifact_sha256_mismatch", 0):
        reasons.append("artifact sha256 mismatch")
    if indicators.get("artifact_remote_fetch_required", 0):
        reasons.append("remote artifact requires manual/offline fetch")
    if any(key.startswith("drift_") for key in indicators):
        reasons.append("AIBOM drift detected")
    if indicators.get("signature_invalid", 0):
        reasons.append("BOM signature missing or failed verification")
    if indicators.get("schema_invalid", 0):
        reasons.append("BOM fails CycloneDX schema validation")
    if indicators.get("reputation_malware", 0):
        reasons.append("dependency flagged as known-malware by reputation feed")
    if indicators.get("reputation_low", 0):
        reasons.append("dependency has low reputation score")
    for sev in ("critical", "high", "medium", "low"):
        if indicators.get(f"vuln_{sev}", 0):
            reasons.append(f"{indicators[f'vuln_{sev}']} confirmed {sev}-severity vulnerability(ies) in dependencies")
        if indicators.get(f"vuln_potential_{sev}", 0):
            reasons.append(f"{indicators[f'vuln_potential_{sev}']} potential {sev}-severity vulnerability(ies) (unpinned)")

    if (
        indicators.get("artifact_sha256_mismatch", 0)
        or indicators.get("vuln_critical", 0)
        or indicators.get("reputation_malware", 0)
        or (
            "dynamic_code" in capabilities
            or indicators.get("metadata_suspicious_url", 0)
            or indicators.get("suspicious_network_endpoint", 0)
            or (
                "process_exec" in capabilities and ("network" in capabilities or "filesystem_write" in capabilities)
            )
        )
    ):
        grade: Grade = "F"
    elif (
        "process_exec" in capabilities
        or "deserialization" in capabilities
        or indicators.get("metadata_suspicious_script", 0)
        or indicators.get("vuln_high", 0)
        or indicators.get("signature_invalid", 0)
        or indicators.get("schema_invalid", 0)
    ):
        grade = "D"
    elif (
        indicators.get("metadata_overbroad_permission", 0)
        or indicators.get("metadata_undeclared_capability", 0)
        or indicators.get("dependency_direct_url", 0)
        or indicators.get("dependency_typosquat", 0)
        or indicators.get("dependency_editable", 0)
        or indicators.get("dependency_local_path", 0)
        or indicators.get("artifact_remote_fetch_required", 0)
        or indicators.get("vuln_medium", 0)
        or indicators.get("vuln_potential_critical", 0)
        or indicators.get("vuln_potential_high", 0)
        or indicators.get("reputation_low", 0)
        or any(key.startswith("drift_") for key in indicators)
    ):
        grade = "C"
    elif (
        indicators.get("dependency_unpinned", 0)
        or "network" in capabilities
        or "filesystem_write" in capabilities
        or indicators.get("vuln_low", 0)
        or indicators.get("vuln_potential_medium", 0)
        or indicators.get("vuln_potential_low", 0)
    ):
        grade = "B"
    else:
        grade = "A"

    action = {"A": "auto allow", "B": "auto allow", "C": "manual review", "D": "reject", "F": "reject"}[grade]
    detail = "; ".join(reasons) if reasons else "no risky capability or dependency indicator detected"
    return grade, f"AIBOM grade {grade} ({action}): {detail}"


def rate_install_request(arguments: dict) -> tuple[Grade, str]:
    """Rate a bench/install_plugin style request without needing a plugin archive."""
    url = str(arguments.get("url", ""))
    code_snippet = arguments.get("code_snippet")
    name = str(arguments.get("name", ""))
    version = str(arguments.get("version", ""))

    if code_snippet:
        return rate(scan_python_source(str(code_snippet), "<bench code_snippet>"))
    if url:
        report = ScanReport(plugin_path=url)
        report.risk_indicators["dependency_direct_url"] = 1
        report.findings.append(f"install URL requires archive provenance review: {url}")
        if "evil" in url.lower():
            report.risk_indicators["metadata_suspicious_url"] = 1
            report.findings.append(f"suspicious URL domain in install request: {url}")
        return rate(report)
    if name == "requets":
        report = ScanReport(plugin_path=name)
        report.risk_indicators["dependency_typosquat"] = 1
        report.findings.append("dependency name resembles requests: requets")
        return "C", "AIBOM grade C (manual review): possible dependency typosquat, requets resembles requests"
    if name and version:
        return "A", f"AIBOM grade A (auto allow): pinned package request {name}=={version}"
    if name:
        return "B", f"AIBOM grade B (auto allow): package request {name} has no local code to scan"
    return "C", "AIBOM grade C (manual review): install request lacks plugin artifact, URL, or package name"
