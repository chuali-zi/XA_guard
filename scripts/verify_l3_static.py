"""Unified static-only L3 repository verifier."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from bench.corpus import validate_corpus

SECTIONS = ("corpus", "faithfulness", "langchain", "gvisor", "opa", "trae", "aibom", "deployment", "crypto", "benchmarks", "docs")
RUNTIME_EVIDENCE = {
    "corpus": ("independent_corpus_review", "Formal status needs hash-bound independent taxonomy and semantic review."),
    "faithfulness": ("faithfulness_runtime_replay", "Real agent decisions and traces must be replayed."),
    "langchain": ("real_langchain_agent_run", "A supported real LangChain agent and transport must be exercised."),
    "gvisor": ("linux_gvisor_acceptance", "runsc isolation, egress denial, rollback, and performance require a Linux host run."),
    "opa": ("opa_runtime_parity", "OPA provenance, strict startup, policy parity, and performance require runtime evidence."),
    "trae": ("real_trae_acceptance", "Discovery, decisions, HITL UI behavior, logs, and screenshots require a real Trae client."),
    "aibom": ("marketplace_installer_acceptance", "A real marketplace or IDE installer interception must be demonstrated."),
    "deployment": ("deployment_runtime_acceptance", "Compose build/up, health, sandbox execution, and soak require Docker."),
    "crypto": ("production_crypto_acceptance", "Production key custody, HSM/KMS, rotation, and a trusted external TSA remain required."),
    "benchmarks": ("official_external_benchmark_run", "Official environments, model calls, ASR/utility, and reproducibility require runtime evidence."),
    "docs": ("delivery_artifact_review", "Submission PDF, video, forms, screenshots, and attestations need human acceptance."),
}


class Checks:
    def __init__(self, root: Path) -> None:
        self.root, self.items = root, []

    def add(self, check_id: str, ok: bool, detail: str, paths: list[str] | None = None) -> None:
        self.items.append({"id": check_id, "status": "pass" if ok else "fail", "detail": detail, "paths": paths or []})

    def files(self, check_id: str, paths: list[str]) -> bool:
        missing = [path for path in paths if not (self.root / path).is_file()]
        detail = "all required files exist" if not missing else "missing: " + ", ".join(missing)
        self.add(check_id, not missing, detail, paths)
        return not missing

    def text(self, path: str) -> str:
        return (self.root / path).read_text(encoding="utf-8")

    def json(self, path: str) -> Any:
        return json.loads(self.text(path))

    def yaml(self, path: str) -> Any:
        return yaml.safe_load(self.text(path))


def _source(c: Checks, name: str, paths: list[str], required: dict[str, tuple[str, ...]]) -> None:
    if not c.files(f"{name}_assets", paths):
        return
    for path, symbols in required.items():
        c.add(f"{name}_{Path(path).stem}", all(x in c.text(path) for x in symbols), "required symbols: " + ", ".join(symbols), [path])


def _corpus(c: Checks) -> None:
    base = "bench/cases/csab-gov-v1-candidate"
    paths = [
        f"{base}/manifest.json",
        f"{base}/non-refusal.jsonl",
        f"{base}/refusal.jsonl",
        "bench/schema/csab-corpus-manifest.schema.json",
        "bench/schema/csab-corpus-case.schema.json",
    ]
    if not c.files("corpus_assets", paths):
        return
    result = validate_corpus(c.root / base, profile="implementation")
    counts = result.counts
    detail = json.dumps(
        {"counts": counts, "errors": result.errors, "warnings": result.warnings},
        ensure_ascii=False,
        sort_keys=True,
    )
    expected_counts = (
        counts.get("total") == 1000
        and counts.get("cohorts") == {"non_refusal": 500, "refusal": 500}
        and counts.get("normalized_payloads_unique") == 1000
    )
    c.add(
        "corpus_implementation_validation",
        result.valid and expected_counts,
        detail,
        paths,
    )

def _faithfulness(c: Checks) -> None:
    _source(c, "faithfulness", ["src/xa_guard/audit/faithfulness.py", "src/xa_guard/gates/gate6_audit.py", "src/xa_guard/types.py", "tests/unit/test_gate6_audit.py"], {"src/xa_guard/audit/faithfulness.py": ("ALGORITHM_VERSION", "assess_decision_faithfulness"), "src/xa_guard/gates/gate6_audit.py": ("assess_decision_faithfulness", "faithfulness.algorithm", "faithfulness.evidence")})


def _langchain(c: Checks) -> None:
    _source(c, "langchain", ["src/xa_guard/integrations/langchain.py", "src/xa_guard/integrations/langgraph.py", "tests/test_langchain_integration.py"], {"src/xa_guard/integrations/langchain.py": ("protect_tool", "protect_tools", "guard_callable", "XAGuardCallbackHandler", "XAGuardApprovalRequired")})


def _gvisor(c: Checks) -> None:
    paths = ["deploy/gvisor/docker-compose.gvisor.yml", "deploy/gvisor/daemon-system.json", "deploy/gvisor/daemon-rootless.json", "deploy/gvisor/README.md", "configs/xa-guard.gvisor.yaml"]
    if not c.files("gvisor_assets", paths):
        return
    services = c.yaml(paths[0])["services"]
    guard, helper = services["xa-guard"], services["sandbox-image"]
    hardened = all(x.get("runtime") == "runsc" and x.get("read_only") is True and x.get("cap_drop") == ["ALL"] for x in (guard, helper)) and helper.get("network_mode") == "none"
    c.add("gvisor_hardening", hardened, "runsc, read-only, dropped capabilities, and no-network are set", paths[:1])
    daemons = [c.json(paths[1]), c.json(paths[2])]
    registered = all(x.get("default-runtime") == "runc" and x.get("runtimes", {}).get("runsc", {}).get("path") == "/usr/local/bin/runsc" for x in daemons)
    c.add("gvisor_daemon_registration", registered, "runsc is opt-in and runc remains default", paths[1:3])
    gate5 = c.yaml(paths[4])["xa_guard"]["gates"]["gate5"]
    c.add("gvisor_gate5_profile", gate5.get("runtime") == "runsc" and gate5.get("network_disabled") is True and gate5.get("sandbox_all_tools") is True, "Gate5 selects isolated runsc children", paths[4:])


def _opa(c: Checks) -> None:
    paths = ["deploy/opa/docker-compose.opa.yml", "deploy/opa/README.md", "docker/xa-guard.opa.Dockerfile", "configs/xa-guard.opa.yaml", "scripts/export_opa_policy.py", "src/xa_guard/policy/opa_export.py"]
    if not c.files("opa_assets", paths):
        return
    profile = c.yaml(paths[3])["xa_guard"]["gates"]["gate3"]
    c.add("opa_strict_profile", profile.get("backend") == "rego" and profile.get("strict_opa") is True and profile.get("opa_path") == "/usr/local/bin/opa", "Gate3 uses strict Rego and explicit OPA path", paths[3:4])
    dockerfile = c.text(paths[2])
    c.add("opa_image_template", "openpolicyagent/opa" in dockerfile and "COPY --from" in dockerfile, "official OPA image is a versioned template", paths[2:3])


def _trae(c: Checks) -> None:
    paths = ["configs/trae/mcp-stdio.windows.template.json", "configs/trae/mcp-stdio.linux.template.json", "configs/trae/mcp-http.template.json", "docs/L3-trae-static-integration.md"]
    if not c.files("trae_assets", paths):
        return
    templates = [c.json(path) for path in paths[:3]]
    stdio = [next(iter(x["mcpServers"].values())) for x in templates[:2]]
    env_ok = all({"XA_GUARD_APPROVAL_OPERATOR_TOKEN", "XA_GUARD_PENDING_APPROVAL_STORE"} <= set(x.get("env", {})) for x in stdio)
    module_ok = all(x.get("args", [])[:2] == ["-m", "xa_guard.server"] and "--config" in x.get("args", []) for x in stdio)
    c.add("trae_stdio_templates", env_ok and module_ok, "stdio templates configure server, pending store, and operator token", paths[:2])
    url = next(iter(templates[2]["mcpServers"].values())).get("url")
    c.add("trae_http_template", url == "http://127.0.0.1:13000/mcp", "HTTP template targets the Compose MCP endpoint", paths[2:3])


def _aibom(c: Checks) -> None:
    paths = ["src/xa_guard/aibom/gateway.py", "src/xa_guard/aibom/scanner.py", "src/xa_guard/aibom/schema_validator.py", "src/xa_guard/aibom/signing.py", "src/xa_guard/aibom/offline_fetch.py", "src/xa_guard/aibom/drift_monitor.py", "src/xa_guard/aibom/schema/cyclonedx-1.6.subset.schema.json", "src/xa_guard/aibom/schema/README.txt", "tests/unit/test_aibom_gateway.py", "pyproject.toml", "src/xa_guard/aibom/external_generator.py", "tests/unit/test_aibom_external_generator.py", "docs/L3-aibom-external-generator.md"]
    if not c.files("aibom_assets", paths):
        return
    schema, project = c.json(paths[6]), c.text(paths[9])
    c.add("aibom_schema", "$schema" in schema and "CycloneDX" in schema.get("title", ""), "local CycloneDX subset schema parses", paths[6:8])
    c.add("aibom_dependencies", "aibom =" in project and "cryptography" in project and "jsonschema" in project, "optional dependencies are declared", paths[9:])
    external_source = c.text(paths[10])
    external_tests = c.text(paths[11])
    external_docs = c.text(paths[12])
    c.add(
        "aibom_external_generator_api",
        all(symbol in external_source for symbol in ("class ExternalGeneratorSpec", "def load_external_cyclonedx", "validate_cyclonedx"))
        and all(symbol in external_tests for symbol in ("ExternalGeneratorSpec", "load_external_cyclonedx")),
        "external exchange implementation and tests cover the declared generator spec and loader API",
        paths[10:12],
    )
    c.add(
        "aibom_external_cyclonedx_16_contract",
        'bom.get("specVersion") != "1.6"' in external_source
        and 'spec_version: str = "1.6"' in external_tests
        and "specVersion" in external_docs and "1.6" in external_docs,
        "implementation, tests, and documentation pin the external exchange to CycloneDX 1.6",
        paths[10:13],
    )


def _deployment(c: Checks) -> None:
    paths = ["docker-compose.yml", "configs/xa-guard.docker.yaml", "docker/xa-guard.Dockerfile", "docker/sandbox.Dockerfile", ".dockerignore"]
    if not c.files("deployment_assets", paths):
        return
    services = c.yaml(paths[0])["services"]
    guard, profile = services["xa-guard"], c.yaml(paths[1])["xa_guard"]
    c.add("deployment_compose", {"xa-guard", "sandbox-image"} <= set(services) and bool(guard.get("healthcheck")) and "13000:3000" in guard.get("ports", []), "API and sandbox, health check, and MCP port are configured", paths[:1])
    gate5 = profile["gates"]["gate5"]
    c.add("deployment_profile", profile["upstream"].get("transport") == "streamable-http" and gate5.get("sandbox_all_tools") is True and gate5.get("network_disabled") is True, "HTTP and isolated Gate5 are enabled", paths[1:2])


def _crypto(c: Checks) -> None:
    paths = ["src/xa_guard/audit/sm_crypto.py", "src/xa_guard/audit/tsa.py", "src/xa_guard/audit/tsa_client.py", "tests/unit/test_sm3_pure.py", "tests/unit/test_sm2_sign.py", "tests/unit/test_tsa_client.py", "docs/evidence/l3-sm2-tsa-evidence-2026-06-18.json"]
    if not c.files("crypto_assets", paths):
        return
    source, evidence = c.text(paths[0]), c.json(paths[6])
    c.add("crypto_implementations", all(x in source for x in ("sm3_hash", "sm2_sign_strict", "sm2_verify_strict")), "SM3 and strict SM2-with-SM3 paths are implemented", paths[:1])
    scoped = evidence.get("hash_algo") == "sm3" and evidence.get("signature_algo") == "SM2-with-SM3" and "not a production trusted TSA" in evidence.get("evidence_note", "")
    c.add("crypto_evidence_scope", scoped, "evidence identifies algorithms and limits local TSA trust", paths[6:])


def _benchmarks(c: Checks) -> None:
    paths = ["scripts/benchmark_l3_performance.py", "scripts/benchmark_streamable_http.py", "bench/external/agentdojo_xa_guard.py", "bench/external/injecagent_opencode.py", "bench/schema/external-benchmark-result.schema.json", "docs/external-benchmarks.md", "docs/evidence/l3-performance-benchmark-2026-06-18.json"]
    if not c.files("benchmark_assets", paths):
        return
    evidence = c.json(paths[6])
    summary, workload = evidence.get("summary", {}), evidence.get("workload", {})
    ok = workload.get("requests", 0) >= 500 and summary.get("targets_met") is True and summary.get("audit", {}).get("chain_verified") is True
    c.add("benchmark_evidence_shape", ok, "archived local run has 500+ requests, met targets, and a verified audit chain", paths[6:])
    c.add("external_adapters", "AgentDojo" in c.text(paths[2]) and "InjecAgent" in c.text(paths[3]), "AgentDojo and InjecAgent adapters are present", paths[2:4])


def _docs(c: Checks) -> None:
    paths = [
        "LICENSE",
        "docs/PRD.md",
        "docs/README.md",
        "docs/L3-test-and-acceptance.md",
        "docs/L3-trae-static-integration.md",
        "deploy/gvisor/README.md",
        "deploy/opa/README.md",
        "docs/external-benchmarks.md",
    ]
    if not c.files("l3_documentation", paths):
        return
    text = "\n".join(c.text(path).lower() for path in paths[4:])
    c.add(
        "documentation_boundaries",
        "not proof" in text and "runtime" in text and "real trae" in text,
        "runbooks distinguish static readiness from runtime acceptance",
        paths[3:],
    )


CHECKERS: dict[str, Callable[[Checks], None]] = {
    "corpus": _corpus, "faithfulness": _faithfulness, "langchain": _langchain,
    "gvisor": _gvisor, "opa": _opa, "trae": _trae, "aibom": _aibom,
    "deployment": _deployment, "crypto": _crypto, "benchmarks": _benchmarks, "docs": _docs,
}


def build_report(root: str | Path = ".", section: str = "all") -> dict[str, Any]:
    if section != "all" and section not in SECTIONS:
        raise ValueError(f"unknown section: {section}")
    root_path = Path(root).resolve()
    selected = list(SECTIONS) if section == "all" else [section]
    sections: dict[str, Any] = {}
    for name in selected:
        checks = Checks(root_path)
        try:
            CHECKERS[name](checks)
        except Exception as exc:
            checks.add("static_parse_error", False, f"{type(exc).__name__}: {exc}")
        failed = sum(item["status"] == "fail" for item in checks.items)
        sections[name] = {"status": "pass" if checks.items and not failed else "fail", "passed": len(checks.items) - failed, "failed": failed, "checks": checks.items}
    failed_sections = [name for name, result in sections.items() if result["status"] == "fail"]
    runtime = [
        {
            "section": name,
            "id": RUNTIME_EVIDENCE[name][0],
            "reason": RUNTIME_EVIDENCE[name][1],
            "status": "required",
            "scope": "former-l3-formal-reference",
            "delivery_v2_blocker": False,
        }
        for name in selected
    ]
    return {
        "schema_version": "xa-guard-l3-static-verification/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "mode": "static_only",
        "delivery_authority": "docs/acceptance/DELIVERY-v2.md",
        "runtime_evidence_semantics": (
            "Compatibility requirements for upgrading a static section to the former formal L3 "
            "claim; they are engineering references and are not Delivery v2 blockers."
        ),
        "repository_root": str(root_path),
        "selected_sections": selected,
        "sections": sections,
        "runtime_evidence_required": runtime,
        "summary": {
            "status": "pass" if not failed_sections else "fail",
            "sections_checked": len(selected),
            "sections_passed": len(selected) - len(failed_sections),
            "sections_failed": len(failed_sections),
            "failed_sections": failed_sections,
            "runtime_evidence_items": len(runtime),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python scripts/verify_l3_static.py")
    parser.add_argument("--section", choices=("all", *SECTIONS), default="all")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    report = build_report(args.root, args.section)
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if report["summary"]["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
