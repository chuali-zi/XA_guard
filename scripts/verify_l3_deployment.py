"""Verify L3 Docker Compose deployment readiness and write JSON evidence.

Default mode is safe: it checks files, hashes, Docker daemon availability, and
`docker compose config`. It only builds or starts services when explicitly asked.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tail(text: str, limit: int = 4000) -> str:
    return text[-limit:] if len(text) > limit else text


def run_command(command: list[str], *, timeout: int = 120) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": command,
            "status": "pass" if proc.returncode == 0 else "fail",
            "exit_code": proc.returncode,
            "duration_ms": (time.perf_counter() - started) * 1000,
            "stdout_tail": _tail(proc.stdout or ""),
            "stderr_tail": _tail(proc.stderr or ""),
        }
    except FileNotFoundError as exc:
        return {
            "command": command,
            "status": "blocked",
            "exit_code": None,
            "duration_ms": (time.perf_counter() - started) * 1000,
            "stdout_tail": "",
            "stderr_tail": str(exc),
            "blocker": "command_not_found",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "status": "fail",
            "exit_code": None,
            "duration_ms": (time.perf_counter() - started) * 1000,
            "stdout_tail": _tail(exc.stdout or ""),
            "stderr_tail": _tail(exc.stderr or ""),
            "blocker": "timeout",
        }


def _file_inventory(paths: list[Path]) -> list[dict[str, Any]]:
    out = []
    for path in paths:
        item: dict[str, Any] = {"path": str(path), "exists": path.exists()}
        if path.exists() and path.is_file():
            item.update({"bytes": path.stat().st_size, "sha256": _sha256(path)})
        out.append(item)
    return out


def _static_summary(compose_file: Path, config_file: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "services": [],
        "images": [],
        "published_ports": [],
        "docker_socket_mounted": False,
        "healthcheck_present": False,
        "config_transport": "",
        "gate5_sandbox_all_tools": None,
        "gate5_docker_image": "",
        "gate5_runtime": "",
    }
    try:
        compose = yaml.safe_load(compose_file.read_text(encoding="utf-8")) or {}
        services = compose.get("services", {}) or {}
        summary["services"] = sorted(services)
        images = []
        ports = []
        for service in services.values():
            if service.get("image"):
                images.append(str(service["image"]))
            ports.extend(str(port) for port in service.get("ports", []) or [])
            volumes = [str(volume) for volume in service.get("volumes", []) or []]
            if any("/var/run/docker.sock" in volume for volume in volumes):
                summary["docker_socket_mounted"] = True
            if service.get("healthcheck"):
                summary["healthcheck_present"] = True
        summary["images"] = sorted(set(images))
        summary["published_ports"] = ports
    except Exception as exc:
        summary["compose_parse_error"] = f"{type(exc).__name__}: {exc}"

    try:
        cfg = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
        root = cfg.get("xa_guard", cfg) or {}
        upstream = root.get("upstream", {}) or {}
        gate5 = ((root.get("gates", {}) or {}).get("gate5", {}) or {})
        summary["config_transport"] = str(upstream.get("transport") or "")
        summary["gate5_sandbox_all_tools"] = gate5.get("sandbox_all_tools")
        summary["gate5_docker_image"] = str(gate5.get("docker_image") or "")
        summary["gate5_runtime"] = str(gate5.get("runtime") or "")
    except Exception as exc:
        summary["config_parse_error"] = f"{type(exc).__name__}: {exc}"
    return summary


def _health_check(url: str, *, timeout: int = 10) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return {
                "url": url,
                "status": "pass",
                "http_status": response.status,
                "duration_ms": (time.perf_counter() - started) * 1000,
                "body_tail": _tail(body),
            }
    except Exception as exc:
        return {
            "url": url,
            "status": "fail",
            "http_status": None,
            "duration_ms": (time.perf_counter() - started) * 1000,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _looks_like_docker_daemon_unavailable(step: dict[str, Any]) -> bool:
    text = f"{step.get('stdout_tail', '')}\n{step.get('stderr_tail', '')}".lower()
    markers = [
        "daemon is running",
        "cannot connect to the docker daemon",
        "failed to connect to the docker api",
        "dockerdesktoplinuxengine",
        "is the docker daemon running",
    ]
    return any(marker in text for marker in markers)


def _summary(steps: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [step for step in steps if step.get("status") == "fail"]
    blocked = [step for step in steps if step.get("status") == "blocked"]
    if failed:
        status = "fail"
    elif blocked:
        status = "blocked_external_dependency"
    else:
        status = "pass"
    return {
        "status": status,
        "passed": sum(1 for step in steps if step.get("status") == "pass"),
        "failed": len(failed),
        "blocked": len(blocked),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    compose_file = Path(args.compose_file)
    config_file = Path(args.config)
    required_files = [
        compose_file,
        config_file,
        Path("docker/xa-guard.Dockerfile"),
        Path("docker/sandbox.Dockerfile"),
        Path(".dockerignore"),
    ]
    steps: list[dict[str, Any]] = []

    inventory = _file_inventory(required_files)
    static = _static_summary(compose_file, config_file)
    missing = [item["path"] for item in inventory if not item["exists"]]
    steps.append(
        {
            "name": "required_files",
            "status": "pass" if not missing else "fail",
            "missing": missing,
        }
    )

    docker_version = run_command(["docker", "version"], timeout=args.timeout)
    docker_version["name"] = "docker_version"
    if docker_version["status"] == "fail" and _looks_like_docker_daemon_unavailable(docker_version):
        docker_version["status"] = "blocked"
        docker_version["blocker"] = "docker_daemon_unavailable"
    steps.append(docker_version)
    docker_available = docker_version["status"] == "pass"

    compose_config = run_command(
        ["docker", "compose", "-f", str(compose_file), "config"],
        timeout=args.timeout,
    )
    compose_config["name"] = "docker_compose_config"
    steps.append(compose_config)

    if args.run_build:
        if docker_available:
            build = run_command(
                ["docker", "compose", "-f", str(compose_file), "build"],
                timeout=args.build_timeout,
            )
            build["name"] = "docker_compose_build"
            steps.append(build)
        else:
            steps.append(
                {
                    "name": "docker_compose_build",
                    "status": "blocked",
                    "blocker": "docker_daemon_unavailable",
                }
            )

    if args.run_up:
        if docker_available:
            up = run_command(
                ["docker", "compose", "-f", str(compose_file), "up", "--build", "-d", "xa-guard"],
                timeout=args.build_timeout,
            )
            up["name"] = "docker_compose_up"
            steps.append(up)
            health = _health_check(args.health_url, timeout=args.timeout)
            health["name"] = "healthz"
            steps.append(health)
        else:
            steps.append(
                {
                    "name": "docker_compose_up",
                    "status": "blocked",
                    "blocker": "docker_daemon_unavailable",
                }
            )

    report = {
        "schema_version": "xa-l3-deployment-verification/v0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "claim_scope": "l3_docker_compose_deployment_evidence",
        "inputs": {
            "compose_file": str(compose_file),
            "config_file": str(config_file),
            "health_url": args.health_url,
            "run_build": bool(args.run_build),
            "run_up": bool(args.run_up),
        },
        "file_inventory": inventory,
        "static": static,
        "steps": steps,
        "summary": _summary(steps),
        "limitations": [
            "docker_build_and_up_require_local_docker_daemon",
            "gvisor_runsc_requires_linux_host_and_runtime_installation",
            "health_check_does_not_replace_real_client_ide_evidence",
        ],
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(prog="python scripts/verify_l3_deployment.py")
    parser.add_argument("--compose-file", default="docker-compose.yml")
    parser.add_argument("--config", default="configs/xa-guard.docker.yaml")
    parser.add_argument("--output", default="logs/runtime/l3_deployment_verification.json")
    parser.add_argument("--health-url", default="http://127.0.0.1:3000/healthz")
    parser.add_argument("--run-build", action="store_true")
    parser.add_argument("--run-up", action="store_true")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--build-timeout", type=int, default=900)
    args = parser.parse_args()

    report = build_report(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    output.write_text(payload, encoding="utf-8")
    print(payload, end="")

    status = report["summary"]["status"]
    raise SystemExit(0 if status == "pass" else 2)


if __name__ == "__main__":
    main()
