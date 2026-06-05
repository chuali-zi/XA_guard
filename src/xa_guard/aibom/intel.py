"""Offline vulnerability + reputation intelligence for AIBOM supply-chain gate.

Cross-references extracted dependencies against a LOCAL, OFFLINE vulnerability
database (OSV/CVE-style) and a LOCAL reputation feed. ZERO network calls.

DB files ship vendored under data/ and can be refreshed out-of-band by operators.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).parent / "data"
_DEFAULT_VULN_DB = _DATA_DIR / "vulndb.json"
_DEFAULT_REPUTATION = _DATA_DIR / "reputation.json"

# Severity ordering for max_severity computation (high→low)
_SEVERITY_ORDER = ("critical", "high", "medium", "low", "info", "unknown", "none")
_SEVERITY_RANK: dict[str, int] = {s: i for i, s in enumerate(_SEVERITY_ORDER)}


# ---------------------------------------------------------------------------
# Public data model
# ---------------------------------------------------------------------------

@dataclass
class VulnMatch:
    id: str
    severity: str          # critical / high / medium / low / info / unknown
    cvss: float | None
    status: str            # "affected" | "potentially_affected"
    summary: str = ""
    fixed: str = ""
    source: str = ""


@dataclass
class IntelReport:
    package: str
    version: str
    vulnerabilities: list[VulnMatch] = field(default_factory=list)
    reputation_score: int | None = None
    reputation_flags: list[str] = field(default_factory=list)
    max_severity: str = "none"


# ---------------------------------------------------------------------------
# Version parsing helpers  (stdlib only, no packaging dependency)
# ---------------------------------------------------------------------------

def _normalize_name(name: str) -> str:
    """PEP 503 normalise: lowercase, replace _ and . with -, strip extras/markers."""
    text = name.strip()
    # strip extras e.g. requests[security]
    text = re.sub(r"\[.*?\]", "", text)
    # strip environment markers
    text = re.split(r";", text, maxsplit=1)[0]
    return text.strip().lower().replace("_", "-").replace(".", "-")


def _parse_specifier(dep: str) -> tuple[str, str, str]:
    """Return (normalized_name, operator, version_str) from a raw specifier string.

    Supports == >= <= > < ~= and bare name (no operator).
    Returns ("", "", "") on parse failure.
    """
    dep = dep.strip()
    if not dep or dep.startswith(("#", "-e", "--", "./", "../", "/")):
        return ("", "", "")

    # strip editable / VCS prefixes
    if dep.lower().startswith(("-e ", "--editable")):
        dep = dep.split(maxsplit=1)[-1]
    if " @ " in dep:
        dep = dep.split(" @ ", 1)[0]

    # match name + optional constraint
    m = re.match(
        r"^([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)"
        r"\s*([=!<>~]{1,3})?\s*([^\s;,]*)?\s*",
        dep,
    )
    if not m:
        return ("", "", "")

    raw_name = m.group(1) or ""
    operator = m.group(2) or ""
    version = m.group(3) or ""

    # strip extras that may have slipped into name part
    raw_name = re.sub(r"\[.*?\]", "", raw_name)
    return (_normalize_name(raw_name), operator, version)


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse a PEP 440-ish version string into an integer tuple for comparison.

    Strips local identifiers (+...) and pre/post labels conservatively so that
    e.g. "1.26.5" -> (1, 26, 5).  Non-numeric segments become 0.
    """
    if not v:
        return (0,)
    # strip local version identifier
    v = v.split("+", 1)[0]
    # strip pre/post/dev suffixes (a/b/rc/post/dev followed by digits)
    v = re.sub(r"[._-]?(a|b|rc|alpha|beta|post|dev)\d*$", "", v, flags=re.IGNORECASE)
    parts = re.split(r"[._-]", v)
    result: list[int] = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            result.append(0)
    return tuple(result) if result else (0,)


def _version_in_range(version: str, introduced: str, fixed: str) -> bool:
    """Return True iff introduced <= version < fixed.

    Treats empty introduced as "0" and empty fixed as "infinity".
    """
    v = _parse_version(version)
    lo = _parse_version(introduced) if introduced not in ("", "0") else (0,)
    if fixed:
        hi = _parse_version(fixed)
        return v >= lo and v < hi
    return v >= lo


def _best_fixed_version(entry: dict[str, Any]) -> str:
    """Return a human-readable string of all fix versions from an entry."""
    parts: list[str] = []
    for r in entry.get("affected", []):
        if r.get("fixed"):
            parts.append(r["fixed"])
    for r in entry.get("also_affected_ranges", []):
        if r.get("fixed"):
            parts.append(r["fixed"])
    return ", ".join(parts) if parts else ""


def _entry_matches_version(version: str, entry: dict[str, Any]) -> tuple[bool, bool]:
    """Check if version matches any affected range in the entry.

    Returns (primary_match, secondary_match) where primary comes from
    the 'affected' list and secondary from 'also_affected_ranges'.
    Both are True/False.
    """
    for rng in entry.get("affected", []):
        if _version_in_range(version, rng.get("introduced", "0"), rng.get("fixed", "")):
            return (True, False)
    for rng in entry.get("also_affected_ranges", []):
        if _version_in_range(version, rng.get("introduced", "0"), rng.get("fixed", "")):
            return (True, True)
    return (False, False)


# ---------------------------------------------------------------------------
# ThreatIntel engine
# ---------------------------------------------------------------------------

class ThreatIntel:
    """Offline vulnerability and reputation intelligence engine.

    Args:
        vuln_db_path: Path to a vulndb.json file.  Defaults to vendored seed.
        reputation_path: Path to a reputation.json file.  Defaults to vendored seed.
    """

    def __init__(
        self,
        vuln_db_path: str | None = None,
        reputation_path: str | None = None,
    ) -> None:
        self._vuln_db: dict[str, Any] = self._load_json(
            vuln_db_path or _DEFAULT_VULN_DB
        )
        self._rep_db: dict[str, Any] = self._load_json(
            reputation_path or _DEFAULT_REPUTATION
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def lookup(self, name: str, version: str = "") -> IntelReport:
        """Look up a single package by normalised name and optional version string.

        Args:
            name: Package name (will be normalised).
            version: Exact version string (e.g. "1.26.5").  Empty means unpinned.

        Returns:
            IntelReport populated with matched vulns and reputation data.
        """
        norm = _normalize_name(name)
        report = IntelReport(package=norm, version=version)

        self._populate_vulns(report)
        self._populate_reputation(report)
        report.max_severity = self._compute_max_severity(report.vulnerabilities)
        return report

    def scan_dependencies(self, dependencies: list[str]) -> dict[str, IntelReport]:
        """Scan a list of raw requirement specifier strings (as from scanner.ScanReport).

        Each item may be like "requests==2.31.0", "urllib3>=1.26", "httpx".
        Unpinned (no == specifier) deps are checked against the vuln DB with
        status "potentially_affected" since the resolved version is unknown.

        Returns:
            Mapping of normalized package name → IntelReport.
        """
        results: dict[str, IntelReport] = {}
        for dep in dependencies:
            norm_name, operator, version = _parse_specifier(dep)
            if not norm_name:
                continue
            # Only treat == as a confirmed pin
            pinned_version = version if operator == "==" else ""
            report = self.lookup(norm_name, pinned_version)
            # If unpinned but operator is not ==, override confirmed→potentially for any vulns
            if operator != "==" and operator != "":
                for vuln in report.vulnerabilities:
                    if vuln.status == "affected":
                        vuln.status = "potentially_affected"
                report.max_severity = self._compute_max_severity(report.vulnerabilities)
            results[norm_name] = report
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_json(path: str | Path) -> dict[str, Any]:
        p = Path(path)
        with p.open(encoding="utf-8") as fh:
            return json.load(fh)

    def _populate_vulns(self, report: IntelReport) -> None:
        packages: dict[str, list[dict[str, Any]]] = self._vuln_db.get("packages", {})
        entries = packages.get(report.package, [])
        version = report.version

        for entry in entries:
            cve_id = entry.get("id", "unknown")
            severity = entry.get("severity", "unknown").lower()
            cvss = entry.get("cvss")
            if isinstance(cvss, (int, float)):
                cvss = float(cvss)
            else:
                cvss = None
            summary = entry.get("summary", "")
            fixed = _best_fixed_version(entry)
            source = self._vuln_db.get("source", "")

            if not version:
                # No pinned version — cannot confirm, mark potentially_affected
                match = VulnMatch(
                    id=cve_id,
                    severity=severity,
                    cvss=cvss,
                    status="potentially_affected",
                    summary=summary,
                    fixed=fixed,
                    source=source,
                )
                report.vulnerabilities.append(match)
            else:
                primary, _secondary = _entry_matches_version(version, entry)
                if primary:
                    match = VulnMatch(
                        id=cve_id,
                        severity=severity,
                        cvss=cvss,
                        status="affected",
                        summary=summary,
                        fixed=fixed,
                        source=source,
                    )
                    report.vulnerabilities.append(match)

    def _populate_reputation(self, report: IntelReport) -> None:
        packages: dict[str, Any] = self._rep_db.get("packages", {})
        default: dict[str, Any] = self._rep_db.get("default", {"score": 50, "flags": ["unknown"]})
        entry = packages.get(report.package, default)

        score = entry.get("score")
        report.reputation_score = int(score) if score is not None else None
        flags = entry.get("flags", [])
        report.reputation_flags = list(flags)

    @staticmethod
    def _compute_max_severity(vulns: list[VulnMatch]) -> str:
        """Return the highest severity string across all matched vulns.

        Uses _SEVERITY_ORDER where lower index = higher severity.
        Returns "none" when there are no vulns.
        """
        if not vulns:
            return "none"
        best = "none"
        best_rank = _SEVERITY_RANK.get("none", len(_SEVERITY_ORDER))
        for v in vulns:
            rank = _SEVERITY_RANK.get(v.severity, _SEVERITY_RANK.get("unknown", len(_SEVERITY_ORDER) - 2))
            if rank < best_rank:
                best_rank = rank
                best = v.severity
        return best
