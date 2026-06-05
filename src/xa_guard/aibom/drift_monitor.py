"""持续漂移监测 — 赛题方向 3（插件供应链安全）。

上线后的插件/Skill 不是一次评级就永久可信：依赖会变、能力会扩、哈希会改、
评级会降。本模块把一次性的 ``exporter.compare_drift`` 升级成**带持久化的持续监测**：

- 为每个组件保存最近一次 CycloneDX 快照（``snapshots/<component>.json``）
- 每次重新扫描时与上次快照比对，产出结构化 ``DriftEvent``
- 漂移事件按严重度分级并追加进 JSONL 账本（``drift_ledger.jsonl``）
- 写入新快照，形成可审计的时间线

设计要点：
- 纯离线、纯 stdlib（json / pathlib / datetime / hashlib）。
- 严重度分级面向**安全恶化**：新增危险能力 / 评级下调 / 出现漏洞 → 高危。
- 与 ``exporter.compare_drift`` 复用同一比对内核，避免口径分裂。
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from xa_guard.aibom.exporter import compare_drift, export_cyclonedx
from xa_guard.aibom.scanner import ScanReport

# 触发"高危"漂移的危险能力：新增其一即视为安全恶化。
_DANGEROUS_CAPABILITIES = {"process_exec", "dynamic_code", "deserialization", "network"}
_GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
_SEVERITY_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class DriftEvent:
    """一次比对产生的单条漂移记录。"""

    component: str
    severity: str  # none / low / medium / high / critical
    drift_keys: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    previous_grade: str = ""
    current_grade: str = ""
    timestamp: str = ""
    snapshot_sha256: str = ""


@dataclass
class DriftReport:
    """``record`` 的返回值：是否首见、是否漂移、事件详情。"""

    component: str
    changed: bool
    first_seen: bool
    event: DriftEvent | None = None


class DriftMonitor:
    """带持久化的持续漂移监测器。

    目录布局::

        <store>/
          snapshots/<component>.json    # 每个组件最近一次 CycloneDX 快照
          drift_ledger.jsonl            # 追加式漂移事件账本（每行一个 DriftEvent）
    """

    def __init__(self, store_dir: str | Path) -> None:
        self.root = Path(store_dir)
        self.snapshots_dir = self.root / "snapshots"
        self.ledger_path = self.root / "drift_ledger.jsonl"

    # ------------------------------------------------------------------ public
    def record(self, report: ScanReport, *, component_id: str | None = None) -> DriftReport:
        """扫描结果入库并与上次快照比对。

        首次见到该组件：只落快照，``first_seen=True``、``changed=False``。
        再次见到：比对 → 落漂移事件（如有）→ 覆盖快照。
        """
        component = component_id or _component_key(report)
        current_bom = export_cyclonedx(report)
        previous_bom = self._load_snapshot(component)

        if previous_bom is None:
            self._save_snapshot(component, current_bom)
            return DriftReport(component=component, changed=False, first_seen=True)

        drift = compare_drift(report, previous_bom)
        drift_keys = sorted(drift.risk_indicators.keys())
        if not drift_keys:
            self._save_snapshot(component, current_bom)
            return DriftReport(component=component, changed=False, first_seen=False)

        severity = self._classify(drift, previous_bom, current_bom, report)
        event = DriftEvent(
            component=component,
            severity=severity,
            drift_keys=drift_keys,
            findings=list(drift.findings),
            previous_grade=str(previous_bom.get("rating", {}).get("grade", "")),
            current_grade=str(current_bom.get("rating", {}).get("grade", "")),
            timestamp=datetime.now(timezone.utc).isoformat(),
            snapshot_sha256=_bom_sha256(current_bom),
        )
        self._append_event(event)
        self._save_snapshot(component, current_bom)
        return DriftReport(component=component, changed=True, first_seen=False, event=event)

    def scan_and_record(self, path: str | Path, *, component_id: str | None = None) -> DriftReport:
        """便捷入口：扫描一个路径并入库（避免调用方重复 import scanner）。"""
        from xa_guard.aibom.scanner import scan

        report = scan(path)
        return self.record(report, component_id=component_id)

    def history(self, component: str | None = None) -> list[DriftEvent]:
        """读取漂移账本；``component`` 为空时返回全部。"""
        if not self.ledger_path.exists():
            return []
        events: list[DriftEvent] = []
        for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if component is not None and data.get("component") != component:
                continue
            events.append(DriftEvent(**{k: data.get(k) for k in DriftEvent.__dataclass_fields__}))
        return events

    def latest_snapshot(self, component: str) -> dict[str, Any] | None:
        """返回组件最近一次快照 BOM（无则 None）。"""
        return self._load_snapshot(component)

    # --------------------------------------------------------------- internals
    def _classify(
        self,
        drift: ScanReport,
        previous_bom: dict[str, Any],
        current_bom: dict[str, Any],
        report: ScanReport,
    ) -> str:
        severity = "low"
        indicators = drift.risk_indicators

        # 评级下调（如 B→D）= 高危。
        prev_grade = str(previous_bom.get("rating", {}).get("grade", ""))
        cur_grade = str(current_bom.get("rating", {}).get("grade", ""))
        if prev_grade in _GRADE_ORDER and cur_grade in _GRADE_ORDER:
            if _GRADE_ORDER[cur_grade] > _GRADE_ORDER[prev_grade]:
                severity = _max_severity(severity, "high")

        # 新增危险能力 = 高危。
        if "drift_capability_change" in indicators:
            added = _added_capabilities(previous_bom, current_bom)
            if added & _DANGEROUS_CAPABILITIES:
                severity = _max_severity(severity, "high")
            else:
                severity = _max_severity(severity, "medium")

        # 哈希变更 / 依赖变更 = 中危（可能是恶意替换或供应链投毒）。
        if "drift_hash_change" in indicators:
            severity = _max_severity(severity, "medium")
        if "drift_dependency_change" in indicators:
            severity = _max_severity(severity, "medium")

        # 当前扫描已带漏洞情报（经 gateway 富化）时，按最高漏洞严重度抬升。
        vuln_sev = _vuln_severity(report)
        if vuln_sev != "none":
            severity = _max_severity(severity, "high" if vuln_sev in {"high", "critical"} else "medium")

        return severity

    def _load_snapshot(self, component: str) -> dict[str, Any] | None:
        path = self._snapshot_path(component)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def _save_snapshot(self, component: str, bom: dict[str, Any]) -> None:
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        path = self._snapshot_path(component)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(bom, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def _append_event(self, event: DriftEvent) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self.ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

    def _snapshot_path(self, component: str) -> Path:
        return self.snapshots_dir / f"{_safe_name(component)}.json"


# ---------------------------------------------------------------------- helpers
def _component_key(report: ScanReport) -> str:
    name = Path(report.plugin_path).name or report.plugin_path
    return name or "unknown-component"


def _safe_name(component: str) -> str:
    """把组件名压成安全文件名，避免路径穿越。"""
    digest = hashlib.sha256(component.encode("utf-8")).hexdigest()[:12]
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in component)[:80]
    return f"{cleaned}-{digest}" if cleaned else digest


def _bom_sha256(bom: dict[str, Any]) -> str:
    payload = json.dumps(bom, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _capabilities_from_bom(bom: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    props = list(bom.get("properties", [])) + list(bom.get("metadata", {}).get("properties", []))
    for prop in props:
        if prop.get("name") == "xa_guard:aibom:capability":
            values.add(str(prop.get("value", "")))
    return values


def _added_capabilities(previous_bom: dict[str, Any], current_bom: dict[str, Any]) -> set[str]:
    return _capabilities_from_bom(current_bom) - _capabilities_from_bom(previous_bom)


def _vuln_severity(report: ScanReport) -> str:
    """从 gateway 富化后的 risk_indicators 读取最高漏洞严重度。"""
    best = "none"
    for key in report.risk_indicators:
        if key.startswith("vuln_"):
            sev = key[len("vuln_"):]
            if _SEVERITY_ORDER.get(sev, 0) > _SEVERITY_ORDER.get(best, 0):
                best = sev
    return best


def _max_severity(current: str, candidate: str) -> str:
    if _SEVERITY_ORDER.get(candidate, 0) > _SEVERITY_ORDER.get(current, 0):
        return candidate
    return current
