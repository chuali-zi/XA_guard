"""Tests for xa_guard.aibom.intel — offline vuln + reputation intelligence.

Coverage:
(a) Pinned dependency that matches a seeded CVE => status "affected", correct severity, max_severity set.
(b) Pinned version ABOVE the fixed version => no match.
(c) Unpinned dependency on vulnerable package => "potentially_affected".
(d) Reputation lookup: known score+flags, unknown package gets default.
(e) scan_dependencies(["urllib3==1.26.5", "requests==2.31.0", "totally-unknown-pkg"]) returns correct dict.
(f) Custom DB paths override vendored default.
Integration: scanner.scan output .dependencies fed through scan_dependencies.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from xa_guard.aibom.intel import ThreatIntel, IntelReport, VulnMatch
from xa_guard.aibom.scanner import scan


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def intel() -> ThreatIntel:
    return ThreatIntel()


# ---------------------------------------------------------------------------
# (a) Pinned dep matches seeded CVE => "affected" + correct severity
# ---------------------------------------------------------------------------

def test_pinned_urllib3_126_5_matches_cve_2024_37891(intel: ThreatIntel) -> None:
    """urllib3 1.26.5 is between 0 and 1.26.19 — must be flagged affected."""
    report = intel.lookup("urllib3", "1.26.5")
    assert report.package == "urllib3"
    assert report.version == "1.26.5"
    affected_ids = [v.id for v in report.vulnerabilities if v.status == "affected"]
    assert "CVE-2024-37891" in affected_ids, f"Expected CVE-2024-37891 in {affected_ids}"

    # Check severity and cvss on the specific vuln
    cve = next(v for v in report.vulnerabilities if v.id == "CVE-2024-37891")
    assert cve.severity == "medium"
    assert cve.cvss == 4.4
    assert cve.status == "affected"


def test_pinned_urllib3_126_5_max_severity_is_high_or_better(intel: ThreatIntel) -> None:
    """urllib3 1.26.5 also hits CVE-2023-43804 (high) — max_severity should be high."""
    report = intel.lookup("urllib3", "1.26.5")
    assert report.max_severity in ("critical", "high"), (
        f"Expected max_severity critical or high, got {report.max_severity}"
    )


def test_pinned_pyyaml_39_matches_critical_cve(intel: ThreatIntel) -> None:
    """pyyaml 3.9 is between 0 and 5.4 — critical CVE-2020-14343 should fire."""
    report = intel.lookup("pyyaml", "3.9")
    affected_ids = [v.id for v in report.vulnerabilities if v.status == "affected"]
    assert "CVE-2020-14343" in affected_ids, f"Expected CVE-2020-14343 in {affected_ids}"
    cve = next(v for v in report.vulnerabilities if v.id == "CVE-2020-14343")
    assert cve.severity == "critical"
    assert report.max_severity == "critical"


# ---------------------------------------------------------------------------
# (b) Pinned version ABOVE fixed => no match
# ---------------------------------------------------------------------------

def test_pinned_urllib3_12620_above_fixed_no_match(intel: ThreatIntel) -> None:
    """urllib3 1.26.20 > 1.26.19 fix boundary — CVE-2024-37891 must NOT match."""
    report = intel.lookup("urllib3", "1.26.20")
    matching = [v for v in report.vulnerabilities if v.id == "CVE-2024-37891" and v.status == "affected"]
    assert not matching, f"CVE-2024-37891 should not match urllib3 1.26.20, got {matching}"


def test_pinned_requests_23210_above_fixed_for_cve_2023_32681(intel: ThreatIntel) -> None:
    """requests 2.31.0 >= fixed 2.31.0 for CVE-2023-32681 — should NOT be affected."""
    report = intel.lookup("requests", "2.31.0")
    matching = [v for v in report.vulnerabilities if v.id == "CVE-2023-32681" and v.status == "affected"]
    assert not matching, f"CVE-2023-32681 should not affect requests 2.31.0: {matching}"


def test_pinned_pyyaml_54_above_fixed(intel: ThreatIntel) -> None:
    """pyyaml 5.4 is exactly at the fixed boundary — must NOT be in affected."""
    report = intel.lookup("pyyaml", "5.4")
    matching = [v for v in report.vulnerabilities if v.id == "CVE-2020-14343" and v.status == "affected"]
    assert not matching, f"CVE-2020-14343 should not affect pyyaml 5.4: {matching}"


def test_safe_package_version_returns_no_vulns(intel: ThreatIntel) -> None:
    """A package not in the DB at all returns empty vulnerabilities."""
    report = intel.lookup("totally-unknown-pkg", "1.0.0")
    assert report.vulnerabilities == []
    assert report.max_severity == "none"


# ---------------------------------------------------------------------------
# (c) Unpinned dep on vulnerable package => "potentially_affected"
# ---------------------------------------------------------------------------

def test_unpinned_urllib3_returns_potentially_affected(intel: ThreatIntel) -> None:
    """urllib3 with no version -> all CVEs become potentially_affected."""
    report = intel.lookup("urllib3", "")
    statuses = {v.status for v in report.vulnerabilities}
    assert "potentially_affected" in statuses, f"Expected potentially_affected, got {statuses}"
    assert "affected" not in statuses, f"Should not have confirmed 'affected' without version: {statuses}"


def test_scan_dependencies_unpinned_specifier_is_potentially_affected(intel: ThreatIntel) -> None:
    """urllib3>=1.26 (not ==) => all matches become potentially_affected."""
    results = intel.scan_dependencies(["urllib3>=1.26"])
    assert "urllib3" in results
    report = results["urllib3"]
    statuses = {v.status for v in report.vulnerabilities}
    assert "potentially_affected" in statuses
    assert "affected" not in statuses


def test_scan_dependencies_bare_name_is_potentially_affected(intel: ThreatIntel) -> None:
    """Bare 'pyyaml' (no operator) => potentially_affected."""
    results = intel.scan_dependencies(["pyyaml"])
    report = results["pyyaml"]
    statuses = {v.status for v in report.vulnerabilities}
    assert "potentially_affected" in statuses
    assert "affected" not in statuses


# ---------------------------------------------------------------------------
# (d) Reputation lookup: known + unknown + default
# ---------------------------------------------------------------------------

def test_known_package_reputation_score_and_flags(intel: ThreatIntel) -> None:
    """requests has a high reputation score and no flags."""
    report = intel.lookup("requests", "2.32.3")
    assert report.reputation_score == 95
    assert report.reputation_flags == []


def test_known_malware_package_has_low_score_and_flags(intel: ThreatIntel) -> None:
    """evil-sdk is seeded as known malware."""
    report = intel.lookup("evil-sdk", "1.0.0")
    assert report.reputation_score is not None
    assert report.reputation_score <= 10
    assert "known-malware" in report.reputation_flags


def test_unknown_package_gets_default_reputation(intel: ThreatIntel) -> None:
    """A package not in the reputation DB gets the default entry."""
    report = intel.lookup("totally-unknown-pkg", "1.0.0")
    assert report.reputation_score == 50
    assert "unknown" in report.reputation_flags


def test_name_normalisation_handles_underscores(intel: ThreatIntel) -> None:
    """Underscore names are normalised to dashes before DB lookup."""
    # pyyaml is stored as "pyyaml" (no underscores), but input may vary
    report = intel.lookup("PyYAML", "3.9")
    assert report.package == "pyyaml"
    assert any(v.id == "CVE-2020-14343" for v in report.vulnerabilities)


# ---------------------------------------------------------------------------
# (e) scan_dependencies with mixed pinned/unknown packages
# ---------------------------------------------------------------------------

def test_scan_dependencies_mixed_batch(intel: ThreatIntel) -> None:
    """scan_dependencies returns a dict keyed by normalized name."""
    deps = ["urllib3==1.26.5", "requests==2.31.0", "totally-unknown-pkg"]
    results = intel.scan_dependencies(deps)

    assert "urllib3" in results
    assert "requests" in results
    assert "totally-unknown-pkg" in results

    urllib3_report = results["urllib3"]
    affected_ids = [v.id for v in urllib3_report.vulnerabilities if v.status == "affected"]
    assert "CVE-2024-37891" in affected_ids

    requests_report = results["requests"]
    # requests 2.31.0 is affected by CVE-2024-35195 (fixed in 2.32.2)
    req_affected = [v.id for v in requests_report.vulnerabilities if v.status == "affected"]
    assert "CVE-2024-35195" in req_affected

    unknown_report = results["totally-unknown-pkg"]
    assert unknown_report.vulnerabilities == []
    assert unknown_report.max_severity == "none"
    assert unknown_report.reputation_score == 50  # default


def test_scan_dependencies_returns_intel_report_instances(intel: ThreatIntel) -> None:
    """All values in the result dict are IntelReport instances."""
    results = intel.scan_dependencies(["requests==2.31.0", "urllib3>=1.26"])
    for report in results.values():
        assert isinstance(report, IntelReport)
        for vuln in report.vulnerabilities:
            assert isinstance(vuln, VulnMatch)


def test_scan_dependencies_max_severity_propagated(intel: ThreatIntel) -> None:
    """max_severity is non-'none' for packages with matched CVEs."""
    results = intel.scan_dependencies(["urllib3==1.26.5"])
    assert results["urllib3"].max_severity != "none"


# ---------------------------------------------------------------------------
# (f) Custom DB paths override the vendored default
# ---------------------------------------------------------------------------

def test_custom_vuln_db_path_overrides_default(tmp_path: Path) -> None:
    """A custom vulndb.json is loaded instead of the vendored one."""
    custom_db = {
        "source": "test-custom-db",
        "generated": "2026-06-05",
        "packages": {
            "fake-lib": [
                {
                    "id": "TEST-CVE-0001",
                    "severity": "high",
                    "cvss": 8.0,
                    "affected": [{"introduced": "0", "fixed": "2.0.0"}],
                    "also_affected_ranges": [],
                    "summary": "test vulnerability in fake-lib",
                }
            ]
        },
    }
    custom_rep = {
        "source": "test-custom-rep",
        "packages": {"fake-lib": {"score": 30, "flags": ["test-flag"]}},
        "default": {"score": 50, "flags": ["unknown"]},
    }
    db_path = tmp_path / "vulndb.json"
    rep_path = tmp_path / "reputation.json"
    db_path.write_text(json.dumps(custom_db), encoding="utf-8")
    rep_path.write_text(json.dumps(custom_rep), encoding="utf-8")

    custom_intel = ThreatIntel(
        vuln_db_path=str(db_path),
        reputation_path=str(rep_path),
    )
    report = custom_intel.lookup("fake-lib", "1.5.0")
    assert any(v.id == "TEST-CVE-0001" and v.status == "affected" for v in report.vulnerabilities)
    assert report.reputation_score == 30
    assert "test-flag" in report.reputation_flags


def test_custom_db_does_not_contain_vendored_cves(tmp_path: Path) -> None:
    """When a custom (empty) DB is provided, vendored CVEs are NOT visible."""
    empty_db = {"source": "empty", "packages": {}}
    empty_rep = {"packages": {}, "default": {"score": 50, "flags": ["unknown"]}}
    db_path = tmp_path / "vulndb.json"
    rep_path = tmp_path / "reputation.json"
    db_path.write_text(json.dumps(empty_db), encoding="utf-8")
    rep_path.write_text(json.dumps(empty_rep), encoding="utf-8")

    custom_intel = ThreatIntel(vuln_db_path=str(db_path), reputation_path=str(rep_path))
    report = custom_intel.lookup("urllib3", "1.26.5")
    assert report.vulnerabilities == []


# ---------------------------------------------------------------------------
# Integration: scanner.scan output .dependencies -> scan_dependencies
# ---------------------------------------------------------------------------

def test_integration_scanner_dependencies_feed_through_scan_dependencies(tmp_path: Path) -> None:
    """Feed scanner.scan .dependencies into ThreatIntel.scan_dependencies."""
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "requirements.txt").write_text(
        "urllib3==1.26.5\nrequests==2.28.0\npyyaml==5.3\n",
        encoding="utf-8",
    )
    (plugin / "main.py").write_text("print('hello')\n", encoding="utf-8")

    scan_report = scan(plugin)
    assert len(scan_report.dependencies) >= 3

    intel = ThreatIntel()
    results = intel.scan_dependencies(scan_report.dependencies)

    # urllib3 1.26.5 should have affected CVEs
    assert "urllib3" in results
    urllib3_r = results["urllib3"]
    assert any(v.status == "affected" for v in urllib3_r.vulnerabilities)

    # pyyaml 5.3 < 5.4 fix => critical
    assert "pyyaml" in results
    pyyaml_r = results["pyyaml"]
    critical_cves = [v for v in pyyaml_r.vulnerabilities if v.severity == "critical" and v.status == "affected"]
    assert critical_cves, f"Expected critical CVEs for pyyaml 5.3, got {pyyaml_r.vulnerabilities}"

    # All values are IntelReport instances
    for report in results.values():
        assert isinstance(report, IntelReport)


def test_integration_scan_report_dependencies_shape() -> None:
    """Smoke-test: scan_dependencies accepts the exact list[str] shape from ScanReport.dependencies."""
    intel = ThreatIntel()
    # raw list as scanner would produce
    raw = ["requests==2.31.0", "urllib3>=1.26.0", "httpx"]
    results = intel.scan_dependencies(raw)
    assert isinstance(results, dict)
    assert all(isinstance(k, str) for k in results)
    assert all(isinstance(v, IntelReport) for v in results.values())


# ---------------------------------------------------------------------------
# Additional edge / correctness tests
# ---------------------------------------------------------------------------

def test_vuln_match_has_fixed_version_field(intel: ThreatIntel) -> None:
    """VulnMatch.fixed is populated for CVEs with fixed versions."""
    report = intel.lookup("urllib3", "1.26.5")
    for v in report.vulnerabilities:
        if v.id == "CVE-2024-37891":
            assert v.fixed != "", "fixed field should be populated"
            break


def test_vuln_match_source_field_populated(intel: ThreatIntel) -> None:
    """VulnMatch.source carries the DB source string."""
    report = intel.lookup("urllib3", "1.26.5")
    for v in report.vulnerabilities:
        assert v.source != "", f"source should not be empty for {v.id}"


def test_lookup_normalises_input_name(intel: ThreatIntel) -> None:
    """ThreatIntel.lookup normalises name before DB lookup."""
    r1 = intel.lookup("URLLIB3", "1.26.5")
    r2 = intel.lookup("urllib3", "1.26.5")
    assert r1.package == r2.package == "urllib3"
    assert len(r1.vulnerabilities) == len(r2.vulnerabilities)


def test_scan_dependencies_skips_blank_lines() -> None:
    """Blank / comment-like entries are silently skipped."""
    intel = ThreatIntel()
    results = intel.scan_dependencies(["", "  ", "# comment", "requests==2.32.3"])
    assert "requests" in results
    assert "" not in results


def test_max_severity_ordering_critical_beats_high() -> None:
    """max_severity picks the most severe across multiple matches."""
    vulns = [
        VulnMatch(id="A", severity="high", cvss=8.0, status="affected"),
        VulnMatch(id="B", severity="critical", cvss=9.8, status="affected"),
        VulnMatch(id="C", severity="medium", cvss=5.0, status="affected"),
    ]
    result = ThreatIntel._compute_max_severity(vulns)
    assert result == "critical"
