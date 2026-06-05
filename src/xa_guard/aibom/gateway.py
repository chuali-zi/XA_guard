"""AIBOM 生产化准入网关 — 赛题方向 3 总装。

把五块生产能力串成一条可审计的准入流水线：

1. **离线拉包**（``offline_fetch``）：远程引用只允许命中操作员预置的离线缓存，
   未命中 fail-closed，绝不联网。
2. **静态扫描 + 依赖分析**（``scanner``）：AST 危险 API / 依赖风险 / provenance。
3. **外部信誉/漏洞库富化**（``intel``）：依赖比对离线 OSV/CVE 漏洞库 + 信誉feed，
   把命中写进 ScanReport 的 risk_indicators 与 CycloneDX vulnerabilities。
4. **导出 + 评级**（``exporter`` / ``rater``）：CycloneDX 1.6 JSON + A–F 评级。
5. **schema 校验 + 签名**（``schema_validator`` / ``signing``）：CycloneDX schema
   合规校验 + Ed25519/SM2/HMAC 签名与公钥验签。
6. **持续漂移监测**（``drift_monitor``）：与上次快照比对并落账本。

所有外部子能力都按需 import，缺库时 fail-safe 降级，保持离线可跑。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from xa_guard.aibom.exporter import export_cyclonedx
from xa_guard.aibom.rater import Grade, rate
from xa_guard.aibom.scanner import ScanReport, scan, scan_artifact

# 评级 → 准入动作（与 rater 的 action 口径一致）。
_GRADE_DECISION = {"A": "allow", "B": "allow", "C": "warn", "D": "deny", "F": "deny"}
_SEVERITY_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
_REPUTATION_LOW_THRESHOLD = 40


@dataclass
class AdmissionResult:
    """一次准入评估的完整结论（可直接写审计）。"""

    component: str
    grade: Grade
    reason: str
    decision: str  # allow / warn / deny
    schema_valid: bool = True
    schema_errors: list[str] = field(default_factory=list)
    schema_validator: str = ""
    signature_verified: bool | None = None  # None=未要求签名
    signature_algorithm: str = ""
    vulnerabilities: int = 0
    max_vuln_severity: str = "none"
    reputation_flags: list[str] = field(default_factory=list)
    drift_changed: bool | None = None  # None=未启用漂移监测
    drift_severity: str = ""
    bom: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------- 富化
def enrich_with_intel(report: ScanReport, intel: Any) -> None:
    """用离线漏洞/信誉库富化 ScanReport（就地修改）。

    - 命中确诊漏洞 → ``vuln_<severity>`` 计数 + CycloneDX vulnerabilities 条目（exploitable）。
    - 未固定版本的潜在漏洞 → ``vuln_potential_<severity>`` + 条目（in_triage）。
    - 信誉 known-malware → ``reputation_malware``；低分 → ``reputation_low``。
    """
    if intel is None or not report.dependencies:
        return
    reports = intel.scan_dependencies(report.dependencies)
    for name, intel_report in sorted(reports.items()):
        ref = f"pkg:pypi/{name}" + (f"@{intel_report.version}" if intel_report.version else "")
        for vuln in intel_report.vulnerabilities:
            confirmed = getattr(vuln, "status", "affected") == "affected"
            sev = (getattr(vuln, "severity", "") or "unknown").lower()
            key = f"vuln_{sev}" if confirmed else f"vuln_potential_{sev}"
            report.risk_indicators[key] = report.risk_indicators.get(key, 0) + 1
            report.findings.append(
                f"intel: {name} {intel_report.version or '(unpinned)'} -> {vuln.id} "
                f"[{sev}/{getattr(vuln, 'status', 'affected')}] {getattr(vuln, 'summary', '')}".rstrip()
            )
            report.vulnerabilities.append(_cyclonedx_vuln(vuln, ref, confirmed))

        flags = [str(f).lower() for f in (intel_report.reputation_flags or [])]
        if any(flag in {"known-malware", "malware", "typosquat"} for flag in flags):
            report.risk_indicators["reputation_malware"] = report.risk_indicators.get("reputation_malware", 0) + 1
            report.findings.append(f"intel: {name} reputation flags {sorted(set(flags))}")
        elif intel_report.reputation_score is not None and intel_report.reputation_score < _REPUTATION_LOW_THRESHOLD:
            report.risk_indicators["reputation_low"] = report.risk_indicators.get("reputation_low", 0) + 1
            report.findings.append(f"intel: {name} low reputation score {intel_report.reputation_score}")


def _cyclonedx_vuln(vuln: Any, ref: str, confirmed: bool) -> dict[str, Any]:
    rating: dict[str, Any] = {"severity": (getattr(vuln, "severity", "") or "unknown").lower()}
    if getattr(vuln, "cvss", None) is not None:
        rating["score"] = vuln.cvss
        rating["method"] = "CVSSv3"
    entry: dict[str, Any] = {
        "bom-ref": f"vuln-{getattr(vuln, 'id', 'UNKNOWN')}-{ref}",
        "id": getattr(vuln, "id", "UNKNOWN"),
        "source": {"name": getattr(vuln, "source", "") or "XA-Guard offline intel"},
        "ratings": [rating],
        "description": getattr(vuln, "summary", ""),
        "affects": [{"ref": ref}],
        "analysis": {"state": "exploitable" if confirmed else "in_triage"},
    }
    if getattr(vuln, "fixed", ""):
        entry["recommendation"] = f"upgrade to {vuln.fixed} or later"
    return entry


def _max_vuln_severity(report: ScanReport) -> str:
    best = "none"
    for key, count in report.risk_indicators.items():
        if not count:
            continue
        sev = ""
        if key.startswith("vuln_potential_"):
            sev = key[len("vuln_potential_"):]
        elif key.startswith("vuln_"):
            sev = key[len("vuln_"):]
        if sev and _SEVERITY_ORDER.get(sev, 0) > _SEVERITY_ORDER.get(best, 0):
            best = sev
    return best


# ------------------------------------------------------------------- 准入主流程
def admit(
    target: str | Path | ScanReport,
    *,
    intel: Any = None,
    validate: bool = True,
    sign_key: str | None = None,
    key_id: str | None = None,
    sign_algorithm: str = "ed25519",
    trust_store: str | None = None,
    drift_store: str | Path | None = None,
    component_id: str | None = None,
    offline_store: Any = None,
    expected_sha256: str | None = None,
) -> AdmissionResult:
    """对一个插件/包做完整准入评估。

    ``target`` 可以是：本地路径 / ScanReport / 远程引用（需配 ``offline_store`` 命中离线缓存）。
    """
    report = _resolve_report(target, offline_store=offline_store, expected_sha256=expected_sha256)
    enrich_with_intel(report, intel)

    bom = export_cyclonedx(report)

    schema_valid, schema_errors, schema_validator = True, [], ""
    if validate:
        schema_valid, schema_errors, schema_validator = _validate(bom)
        if not schema_valid:
            report.risk_indicators["schema_invalid"] = 1

    signature_verified: bool | None = None
    signature_algorithm = ""
    if sign_key and key_id:
        bom, signature_verified, signature_algorithm = _sign_and_verify(
            bom, sign_key=sign_key, key_id=key_id, algorithm=sign_algorithm, trust_store=trust_store
        )
        if signature_verified is False:
            report.risk_indicators["signature_invalid"] = 1

    # 漏洞/签名/schema 富化后重算评级，保证 BOM 的 rating 与 risk_indicators 一致。
    grade, reason = rate(report)
    bom["rating"] = {"grade": grade, "reason": reason}

    drift_changed: bool | None = None
    drift_severity = ""
    if drift_store is not None:
        drift_changed, drift_severity = _record_drift(report, drift_store, component_id)

    decision = _GRADE_DECISION.get(grade, "warn")
    component = component_id or (Path(report.plugin_path).name or report.plugin_path)
    return AdmissionResult(
        component=component,
        grade=grade,
        reason=reason,
        decision=decision,
        schema_valid=schema_valid,
        schema_errors=schema_errors,
        schema_validator=schema_validator,
        signature_verified=signature_verified,
        signature_algorithm=signature_algorithm,
        vulnerabilities=len(report.vulnerabilities),
        max_vuln_severity=_max_vuln_severity(report),
        reputation_flags=sorted(
            {k for k in ("reputation_malware", "reputation_low") if report.risk_indicators.get(k)}
        ),
        drift_changed=drift_changed,
        drift_severity=drift_severity,
        bom=bom,
    )


# ----------------------------------------------------------------- 子能力封装
def _resolve_report(
    target: str | Path | ScanReport, *, offline_store: Any, expected_sha256: str | None
) -> ScanReport:
    if isinstance(target, ScanReport):
        return target
    source = str(target)
    if offline_store is not None and _looks_remote(source):
        fetched = offline_store.resolve(url=source, expected_sha256=expected_sha256)
        if not fetched.available:
            report = ScanReport(plugin_path=source)
            report.risk_indicators["artifact_remote_fetch_required"] = 1
            report.findings.append(
                f"offline cache miss for {source}: {'; '.join(fetched.errors) or 'not mirrored'}"
            )
            return report
        report = scan_artifact(str(fetched.path), expected_sha256=fetched.sha256)
        report.plugin_path = source
        report.provenance["offline_source"] = fetched.source
        return report
    if _looks_remote(source):
        return scan_artifact(source, expected_sha256=expected_sha256)
    return scan(source)


def _looks_remote(source: str) -> bool:
    return source.startswith(("http://", "https://", "git+", "ssh://"))


def _validate(bom: dict[str, Any]) -> tuple[bool, list[str], str]:
    try:
        from xa_guard.aibom.schema_validator import validate_cyclonedx
    except Exception:  # pragma: no cover - validator module always present
        return True, [], "skipped"
    result = validate_cyclonedx(bom)
    return result.valid, list(result.errors), result.validator


def _sign_and_verify(
    bom: dict[str, Any], *, sign_key: str, key_id: str, algorithm: str, trust_store: str | None
) -> tuple[dict[str, Any], bool | None, str]:
    from xa_guard.aibom.signing import sign_bom, verify_bom

    signed = sign_bom(bom, key_path=sign_key, key_id=key_id, algorithm=algorithm)
    algo = str(signed.get("signature", {}).get("algorithm", ""))
    if not trust_store:
        return signed, None, algo
    result = verify_bom(signed, trust_store=trust_store)
    return signed, result.verified, result.algorithm or algo


def _record_drift(report: ScanReport, drift_store: str | Path, component_id: str | None) -> tuple[bool, str]:
    from xa_guard.aibom.drift_monitor import DriftMonitor

    monitor = DriftMonitor(drift_store)
    drift = monitor.record(report, component_id=component_id)
    severity = drift.event.severity if drift.event else ""
    return drift.changed, severity
