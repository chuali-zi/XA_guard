"""AIBOM 准入网关 CLI — 面向运维/审核员 — 赛题方向 3。

子命令::

    xa-aibom admit <path|url> [--intel] [--sign-key K --key-id ID --trust-store DIR]
                              [--drift-store DIR] [--offline-cache DIR] [--no-validate]
    xa-aibom bom <path>                 # 仅导出 CycloneDX 1.6 BOM
    xa-aibom validate <bom.json>        # 校验一个 BOM 文件是否符合 CycloneDX schema
    xa-aibom drift <path> --store DIR [--component ID]

设计：纯离线；所有重型子能力按需 import；缺库时 fail-safe 降级。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _cmd_admit(args: argparse.Namespace) -> int:
    from xa_guard.aibom.gateway import admit

    intel = None
    if args.intel:
        from xa_guard.aibom.intel import ThreatIntel

        intel = ThreatIntel(vuln_db_path=args.vuln_db, reputation_path=args.reputation_db)

    offline_store = None
    if args.offline_cache:
        from xa_guard.aibom.offline_fetch import OfflinePackageStore

        offline_store = OfflinePackageStore(args.offline_cache)

    result = admit(
        args.target,
        intel=intel,
        validate=not args.no_validate,
        sign_key=args.sign_key,
        key_id=args.key_id,
        sign_algorithm=args.sign_algorithm,
        trust_store=args.trust_store,
        drift_store=args.drift_store,
        component_id=args.component,
        offline_store=offline_store,
        expected_sha256=args.expected_sha256,
    )

    summary = {
        "component": result.component,
        "decision": result.decision,
        "grade": result.grade,
        "reason": result.reason,
        "schema_valid": result.schema_valid,
        "schema_validator": result.schema_validator,
        "schema_errors": result.schema_errors,
        "signature_verified": result.signature_verified,
        "signature_algorithm": result.signature_algorithm,
        "vulnerabilities": result.vulnerabilities,
        "max_vuln_severity": result.max_vuln_severity,
        "reputation_flags": result.reputation_flags,
        "drift_changed": result.drift_changed,
        "drift_severity": result.drift_severity,
    }
    if args.bom_out:
        Path(args.bom_out).write_text(json.dumps(result.bom, ensure_ascii=False, indent=2), encoding="utf-8")
        summary["bom_written"] = args.bom_out
    _print_json(summary)
    # deny → 退出码 2，warn → 1，allow → 0，便于 CI/脚本接管。
    return {"allow": 0, "warn": 1, "deny": 2}.get(result.decision, 1)


def _cmd_bom(args: argparse.Namespace) -> int:
    from xa_guard.aibom.exporter import export_cyclonedx
    from xa_guard.aibom.scanner import scan

    bom = export_cyclonedx(scan(args.target))
    if args.out:
        Path(args.out).write_text(json.dumps(bom, ensure_ascii=False, indent=2), encoding="utf-8")
        _print_json({"bom_written": args.out, "grade": bom["rating"]["grade"]})
    else:
        _print_json(bom)
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    from xa_guard.aibom.schema_validator import validate_cyclonedx

    bom = json.loads(Path(args.bom).read_text(encoding="utf-8"))
    result = validate_cyclonedx(bom)
    _print_json(
        {
            "valid": result.valid,
            "spec_version": result.spec_version,
            "validator": result.validator,
            "errors": result.errors,
        }
    )
    return 0 if result.valid else 2


def _cmd_drift(args: argparse.Namespace) -> int:
    from xa_guard.aibom.drift_monitor import DriftMonitor

    monitor = DriftMonitor(args.store)
    report = monitor.scan_and_record(args.target, component_id=args.component)
    out: dict[str, Any] = {
        "component": report.component,
        "first_seen": report.first_seen,
        "changed": report.changed,
    }
    if report.event is not None:
        out["event"] = {
            "severity": report.event.severity,
            "drift_keys": report.event.drift_keys,
            "previous_grade": report.event.previous_grade,
            "current_grade": report.event.current_grade,
            "findings": report.event.findings,
        }
    _print_json(out)
    return 2 if (report.event and report.event.severity in {"high", "critical"}) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="xa-aibom", description="XA-Guard AIBOM 准入网关")
    sub = parser.add_subparsers(dest="command", required=True)

    p_admit = sub.add_parser("admit", help="完整准入评估（扫描+漏洞+schema+签名+漂移）")
    p_admit.add_argument("target", help="本地路径 / 远程 URL")
    p_admit.add_argument("--intel", action="store_true", help="启用离线漏洞/信誉库富化")
    p_admit.add_argument("--vuln-db", default=None, help="自定义漏洞库 JSON 路径")
    p_admit.add_argument("--reputation-db", default=None, help="自定义信誉库 JSON 路径")
    p_admit.add_argument("--no-validate", action="store_true", help="跳过 CycloneDX schema 校验")
    p_admit.add_argument("--sign-key", default=None, help="签名私钥/对称密钥路径")
    p_admit.add_argument("--key-id", default=None, help="签名 keyId")
    p_admit.add_argument("--sign-algorithm", default="ed25519", help="ed25519 / sm2 / hmac")
    p_admit.add_argument("--trust-store", default=None, help="验签公钥目录")
    p_admit.add_argument("--drift-store", default=None, help="漂移监测存储目录")
    p_admit.add_argument("--offline-cache", default=None, help="离线包缓存目录（远程引用必经）")
    p_admit.add_argument("--expected-sha256", default=None, help="期望 artifact sha256")
    p_admit.add_argument("--component", default=None, help="组件标识（漂移/审计键）")
    p_admit.add_argument("--bom-out", default=None, help="把完整 BOM 写到文件")
    p_admit.set_defaults(func=_cmd_admit)

    p_bom = sub.add_parser("bom", help="仅导出 CycloneDX 1.6 BOM")
    p_bom.add_argument("target", help="本地插件路径")
    p_bom.add_argument("--out", default=None, help="输出文件")
    p_bom.set_defaults(func=_cmd_bom)

    p_val = sub.add_parser("validate", help="校验 BOM 文件是否符合 CycloneDX schema")
    p_val.add_argument("bom", help="BOM JSON 文件路径")
    p_val.set_defaults(func=_cmd_validate)

    p_drift = sub.add_parser("drift", help="扫描并记录一次漂移")
    p_drift.add_argument("target", help="本地插件路径")
    p_drift.add_argument("--store", required=True, help="漂移监测存储目录")
    p_drift.add_argument("--component", default=None, help="组件标识")
    p_drift.set_defaults(func=_cmd_drift)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
