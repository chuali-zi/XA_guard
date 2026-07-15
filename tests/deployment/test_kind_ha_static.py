from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy" / "helm" / "xa-guard"
KIND_DIR = ROOT / "deploy" / "kind"


def _helm() -> str:
    configured = os.environ.get("HELM_BIN", "")
    if configured and Path(configured).exists():
        return configured
    discovered = shutil.which("helm")
    if discovered:
        return discovered
    pytest.skip("Helm binary is not available for static rendering")


def _render(*extra: str) -> list[dict[str, Any]]:
    completed = subprocess.run(
        [_helm(), "template", "ha-static", str(CHART), "--namespace", "xa-guard", *extra],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return [document for document in yaml.safe_load_all(completed.stdout) if document]


def _one(documents: list[dict[str, Any]], kind: str, component: str | None = None) -> dict[str, Any]:
    matches = [
        document
        for document in documents
        if document["kind"] == kind
        and (
            component is None
            or document["metadata"].get("labels", {}).get("app.kubernetes.io/component")
            == component
        )
    ]
    assert len(matches) == 1, (kind, component, [item["metadata"]["name"] for item in matches])
    return matches[0]


def _container(deployment: dict[str, Any]) -> dict[str, Any]:
    return deployment["spec"]["template"]["spec"]["containers"][0]


def _env(container: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["name"]: item for item in container.get("env", [])}


def _external_ports(policy: dict[str, Any]) -> set[int]:
    ports: set[int] = set()
    for rule in policy["spec"].get("egress", []):
        if any("ipBlock" in target for target in rule.get("to", [])):
            ports.update(int(item["port"]) for item in rule.get("ports", []))
    return ports


def test_versions_and_kind_topology_are_fully_pinned() -> None:
    chart = yaml.safe_load((CHART / "Chart.yaml").read_text(encoding="utf-8"))
    assert chart["version"] == "0.2.0"
    assert chart["appVersion"] == "0.2.0"

    cluster = yaml.safe_load((KIND_DIR / "cluster.yaml").read_text(encoding="utf-8"))
    assert cluster["networking"]["disableDefaultCNI"] is True
    assert [node["role"] for node in cluster["nodes"]] == ["control-plane", "worker", "worker"]
    expected = (
        "kindest/node:v1.34.3@sha256:"
        "08497ee19eace7b4b5348db5c6a1591d7752b164530a36f855cb0f2bdcbadd48"
    )
    assert {node["image"] for node in cluster["nodes"]} == {expected}

    lock = json.loads((KIND_DIR / "tools.lock.json").read_text(encoding="utf-8"))
    assert lock["kind"]["version"] == "v0.31.0"
    assert lock["kubectl"]["version"] == "v1.34.3"
    assert lock["calico"]["version"] == "v3.32.1"
    assert lock["kind_node"]["image"] == expected
    for tool in ("kind", "kubectl", "helm"):
        for artifact in lock[tool]["artifacts"].values():
            assert len(artifact["sha256"]) == 64
    assert len(lock["calico"]["manifest"]["sha256"]) == 64


def test_bootstrap_checksum_is_enforced_without_network(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("bootstrap_tools", KIND_DIR / "bootstrap_tools.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "source.bin"
    source.write_bytes(b"locked artifact")
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    target = tmp_path / "cache" / "artifact.bin"
    assert module.verified_download(source.as_uri(), expected, target, False) == target
    assert target.read_bytes() == b"locked artifact"
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        module.verified_download(source.as_uri(), "0" * 64, target, True)


def test_production_render_has_real_ha_and_http_key_provider_contract() -> None:
    documents = _render()
    api = _one(documents, "Deployment", "api")
    worker = _one(documents, "Deployment", "worker")
    for deployment in (api, worker):
        pod = deployment["spec"]["template"]["spec"]
        assert deployment["spec"]["replicas"] == 2
        assert pod["terminationGracePeriodSeconds"] >= 45
        anti = pod["affinity"]["podAntiAffinity"]
        assert anti["requiredDuringSchedulingIgnoredDuringExecution"]
        assert pod["topologySpreadConstraints"][0]["whenUnsatisfiable"] == "DoNotSchedule"
        assert _container(deployment)["lifecycle"]["preStop"]["exec"]["command"]

    worker_container = _container(worker)
    assert worker_container["ports"] == [
        {"name": "http", "containerPort": 8082, "protocol": "TCP"}
    ]
    assert worker_container["livenessProbe"]["httpGet"] == {"path": "/livez", "port": "http"}
    assert worker_container["readinessProbe"]["httpGet"] == {"path": "/readyz", "port": "http"}
    worker_service = _one(documents, "Service", "worker")
    assert worker_service["spec"]["ports"][0]["targetPort"] == "http"

    for component in ("api", "worker"):
        workload = _one(documents, "Deployment", component)
        container = workload["spec"]["template"]["spec"]["containers"][0]
        names = _env(container)
        assert names["XA_GUARD_KEY_PROVIDER"]["value"] == "http"
        assert "XA_GUARD_KEY_PROVIDER_URL" in names
        assert "XA_GUARD_KEY_PROVIDER_AUTH_TOKEN" in names
        assert "XA_GUARD_KEK_KEYRING" not in names
    migration_env = _env(
        _one(documents, "Job", "migration")["spec"]["template"]["spec"]["containers"][0]
    )
    assert set(migration_env) == {"XA_GUARD_DATABASE_URL"}

    policies = [document for document in documents if document["kind"] == "NetworkPolicy"]
    assert len(policies) == 6
    default_deny = next(item for item in policies if item["metadata"]["name"].endswith("default-deny"))
    assert default_deny["spec"]["podSelector"] == {}
    assert default_deny["spec"]["policyTypes"] == ["Ingress", "Egress"]
    assert all(not _external_ports(policy) for policy in policies)
    rendered = yaml.safe_dump_all(documents)
    assert "0.0.0.0/0" not in rendered
    assert "kek-keyring" not in rendered


def test_local_key_provider_is_mutually_exclusive() -> None:
    documents = _render("--set", "global.kms.provider=local")
    rendered = yaml.safe_dump_all(documents)
    for component in ("api", "worker"):
        workload = _one(documents, "Deployment", component)
        names = _env(workload["spec"]["template"]["spec"]["containers"][0])
        assert names["XA_GUARD_KEY_PROVIDER"]["value"] == "local"
        assert "XA_GUARD_KEK_KEYRING" in names
        assert "XA_GUARD_KEY_PROVIDER_URL" not in names
        assert "XA_GUARD_KEY_PROVIDER_AUTH_TOKEN" not in names
    assert "xa-guard-key-provider" not in rendered

    unsafe = subprocess.run(
        [
            _helm(),
            "template",
            "unsafe",
            str(CHART),
            "--set-string",
            "global.kms.endpoint=http://kms.example.test",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert unsafe.returncode != 0
    assert "must use https://" in unsafe.stderr


def test_reference_values_render_dependency_specific_cidrs(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("generate_values", KIND_DIR / "generate_values.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(ValueError, match="exactly one"):
        module.values("172.18.0.0/24", keycloak_port=13081, postgres_port=15432, kms_port=13083)
    output = tmp_path / "values.yaml"
    module.write_values(
        output,
        module.values("172.18.0.1/32", keycloak_port=13081, postgres_port=15432, kms_port=13083),
    )
    documents = _render("--values", str(output))
    policies = {
        item["metadata"]["labels"].get("app.kubernetes.io/component"): item
        for item in documents
        if item["kind"] == "NetworkPolicy"
        and item["metadata"]["labels"].get("app.kubernetes.io/component")
    }
    assert _external_ports(policies["api"]) == {13081, 15432, 13083}
    assert _external_ports(policies["worker"]) == {15432, 13083}
    assert _external_ports(policies["business-api"]) == {15432}
    assert _external_ports(policies["console"]) == {13081}
    assert _external_ports(policies["migration"]) == {15432}
    for policy in policies.values():
        cidrs = {
            target["ipBlock"]["cidr"]
            for rule in policy["spec"].get("egress", [])
            for target in rule.get("to", [])
            if "ipBlock" in target
        }
        assert cidrs <= {"172.18.0.1/32"}
    config = _one(documents, "ConfigMap")["data"]
    assert config["XA_GUARD_DEPLOYMENT_PROFILE"] == "reference"
    assert "host.docker.internal" in config["XA_GUARD_OIDC_BACKCHANNEL_BASE_URL"]


def test_external_compose_and_dry_run_runner_are_honest() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.ha-external.yml").read_text(encoding="utf-8"))
    assert set(compose["services"]) == {"postgres", "keycloak", "key-provider"}
    assert "@sha256:" in compose["services"]["postgres"]["image"]
    assert "@sha256:" in compose["services"]["keycloak"]["image"]
    assert compose["services"]["key-provider"]["command"] == [
        "python",
        "-m",
        "xa_guard.reference.kms_api",
    ]

    tools = subprocess.run(
        [sys.executable, str(KIND_DIR / "bootstrap_tools.py"), "--dry-run"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(tools.stdout)["versions"]["kind"] == "v0.31.0"

    runner = subprocess.run(
        [
            sys.executable,
            str(KIND_DIR / "ha_runner.py"),
            "accept",
            "--dry-run",
            "--allow-incomplete",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert runner.returncode == 0, runner.stderr
    assert "HA evidence:" in runner.stdout
