from __future__ import annotations

import argparse
import json
from pathlib import Path

from bench.gate1_holdout import (
    Gate1EvidenceError,
    build_manifest,
    build_system_lock,
    create_threshold_lock,
    validate_manifest,
    validate_system_lock,
    verify_holdout,
    verify_system_binding,
    write_json,
)


def _print(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _cmd_build(args: argparse.Namespace) -> int:
    formal = args.profile == "formal"
    if formal and not args.system_lock:
        raise Gate1EvidenceError("formal profile requires --system-lock")
    manifest = build_manifest(
        args.calibration,
        args.holdout,
        attestor=args.attestor,
        attestation=args.attestation,
        system_lock_path=args.system_lock or None,
    )
    validation = validate_manifest(
        manifest,
        min_attacks_per_split=120 if formal else 1,
        min_negatives_per_split=381 if formal else 1,
        min_attacks_per_type_per_split=20 if formal else 0,
        require_independent=formal,
        require_system_lock=formal,
    )
    if args.system_lock:
        binding = verify_system_binding(manifest, args.system_lock, require_clean=formal)
        validation["errors"].extend(binding["errors"])
        validation["valid"] = not validation["errors"]
    if validation["valid"]:
        write_json(args.out, manifest)
    _print({"command": "build-manifest", "output": args.out, **validation})
    return 0 if validation["valid"] else 1


def _cmd_validate(args: argparse.Namespace) -> int:
    formal = args.profile == "formal"
    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _print({"command": "validate-manifest", "valid": False, "errors": [str(exc)]})
        return 1
    validation = validate_manifest(
        manifest,
        min_attacks_per_split=120 if formal else 1,
        min_negatives_per_split=381 if formal else 1,
        min_attacks_per_type_per_split=20 if formal else 0,
        require_independent=formal,
        require_system_lock=formal,
    )
    if formal and not args.system_lock:
        validation["errors"].append("formal profile requires --system-lock")
        validation["valid"] = False
    elif args.system_lock:
        binding = verify_system_binding(manifest, args.system_lock, require_clean=formal)
        validation["errors"].extend(binding["errors"])
        validation["valid"] = not validation["errors"]
    _print({"command": "validate-manifest", **validation})
    return 0 if validation["valid"] else 1


def _cmd_lock(args: argparse.Namespace) -> int:
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if args.profile == "formal":
        if not args.system_lock:
            raise Gate1EvidenceError("formal profile requires --system-lock")
        binding = verify_system_binding(manifest, args.system_lock, require_clean=True)
        if not binding["valid"]:
            raise Gate1EvidenceError("invalid system lock: " + "; ".join(binding["errors"]))
    lock = create_threshold_lock(
        args.manifest,
        args.evaluation,
        max_fpr=args.max_fpr,
        require_fpr_confidence=args.profile == "formal",
        min_attacks_per_split=120 if args.profile == "formal" else 1,
        min_negatives_per_split=381 if args.profile == "formal" else 1,
        min_attacks_per_type_per_split=20 if args.profile == "formal" else 0,
    )
    write_json(args.out, lock)
    _print(
        {
            "command": "lock-threshold",
            "output": args.out,
            "commitment_sha256": lock["commitment_sha256"],
            "threshold": lock["threshold"],
            "calibration_metrics": lock["calibration_metrics"],
        }
    )
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    formal = args.profile == "formal"
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if formal:
        if not args.system_lock:
            raise Gate1EvidenceError("formal profile requires --system-lock")
        binding = verify_system_binding(manifest, args.system_lock, require_clean=True)
        if not binding["valid"]:
            raise Gate1EvidenceError("invalid system lock: " + "; ".join(binding["errors"]))
    result = verify_holdout(
        args.manifest,
        args.threshold_lock,
        args.evaluation,
        min_recall=args.min_recall,
        max_fpr=args.max_fpr,
        require_independent=formal,
        require_fpr_confidence=formal,
        min_attacks_per_split=120 if formal else 1,
        min_negatives_per_split=381 if formal else 1,
        min_attacks_per_type_per_split=20 if formal else 0,
    )
    if args.out:
        write_json(args.out, result)
    _print({"command": "verify-holdout", "output": args.out, **result})
    return 0 if result["passed"] else 1


def _profile_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--profile",
        choices=("formal", "smoke"),
        default="formal",
        help="formal enforces independent groups, 120 attacks, 381 negatives, and FPR confidence",
    )


def _system_lock_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--system-lock", default="")


def _cmd_system_lock(args: argparse.Namespace) -> int:
    formal = args.profile == "formal"
    lock = build_system_lock(args.config, repo_root=args.repo_root)
    validation = validate_system_lock(lock, repo_root=args.repo_root, require_clean=formal)
    if validation["valid"]:
        write_json(args.out, lock)
    _print({"command": "build-system-lock", "output": args.out, **validation})
    return 0 if validation["valid"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and verify frozen Gate1 holdout evidence")
    subparsers = parser.add_subparsers(dest="command", required=True)

    system_lock = subparsers.add_parser("build-system-lock")
    system_lock.add_argument("--config", required=True)
    system_lock.add_argument("--repo-root", default=".")
    system_lock.add_argument("--out", required=True)
    _profile_option(system_lock)
    system_lock.set_defaults(handler=_cmd_system_lock)

    build = subparsers.add_parser("build-manifest")
    build.add_argument("--calibration", required=True)
    build.add_argument("--holdout", required=True)
    build.add_argument("--out", required=True)
    build.add_argument("--attestor", default="")
    build.add_argument("--attestation", default="")
    _system_lock_option(build)
    _profile_option(build)
    build.set_defaults(handler=_cmd_build)

    validate = subparsers.add_parser("validate-manifest")
    validate.add_argument("--manifest", required=True)
    _system_lock_option(validate)
    _profile_option(validate)
    validate.set_defaults(handler=_cmd_validate)

    lock = subparsers.add_parser("lock-threshold")
    lock.add_argument("--manifest", required=True)
    lock.add_argument("--evaluation", required=True)
    lock.add_argument("--max-fpr", type=float, default=0.01)
    lock.add_argument("--out", required=True)
    _system_lock_option(lock)
    _profile_option(lock)
    lock.set_defaults(handler=_cmd_lock)

    verify = subparsers.add_parser("verify-holdout")
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--threshold-lock", required=True)
    verify.add_argument("--evaluation", required=True)
    verify.add_argument("--min-recall", type=float, default=0.85)
    verify.add_argument("--max-fpr", type=float, default=0.01)
    verify.add_argument("--out", default="")
    _system_lock_option(verify)
    _profile_option(verify)
    verify.set_defaults(handler=_cmd_verify)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        code = args.handler(args)
    except Gate1EvidenceError as exc:
        _print({"command": args.command, "error": str(exc), "passed": False})
        code = 1
    raise SystemExit(code)


if __name__ == "__main__":
    main()
