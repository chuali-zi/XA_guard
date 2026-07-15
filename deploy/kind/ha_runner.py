"""Kind HA, takeover, network-policy, migration, and Helm rollback runner.

This runner is intentionally evidence-oriented: a missing approved effect makes
the worker-takeover phase incomplete instead of manufacturing a passing result.
Use --dry-run to inspect the command plan without mutating Docker/Kubernetes.
"""

from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import os
import re
import secrets
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import urlopen

import yaml

import bootstrap_tools
import generate_values
import prepare_takeover as takeover_flow


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CHART = ROOT / "deploy" / "helm" / "xa-guard"
CLUSTER_CONFIG = HERE / "cluster.yaml"
GENERATED_VALUES = HERE / "values.generated.yaml"
COMPOSE_FILE = ROOT / "docker-compose.ha-external.yml"
REFERENCE_RUNTIME = ROOT / ".runtime" / "reference"
HA_RUNTIME = ROOT / ".runtime" / "kind-ha"

ACCEPTANCE_PHASES = (
    "install_previous",
    "upgrade_current",
    "migration_rerun",
    "api_pod_deletion",
    "worker_lease_takeover",
    "network_policy_probes",
    "helm_rollback",
)

EFFECT_ID = re.compile(r"^eff-[0-9a-f]{32}$")


@dataclass
class Evidence:
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    commands: list[dict[str, Any]] = field(default_factory=list)
    phases: dict[str, dict[str, Any]] = field(default_factory=dict)

    def phase(self, name: str, status: str, **details: Any) -> None:
        self.phases[name] = {"status": status, **details}


class Executor:
    def __init__(self, evidence: Evidence, *, dry_run: bool) -> None:
        self.evidence = evidence
        self.dry_run = dry_run

    def run(
        self,
        label: str,
        args: list[str],
        *,
        input_text: str | None = None,
        check: bool = True,
        env: dict[str, str] | None = None,
        record_output: bool = True,
        simulated_code: int = 0,
    ) -> subprocess.CompletedProcess[str]:
        started = time.monotonic()
        record: dict[str, Any] = {"label": label, "argv": args, "dry_run": self.dry_run}
        if self.dry_run:
            record.update({"returncode": simulated_code, "duration_seconds": 0.0})
            self.evidence.commands.append(record)
            return subprocess.CompletedProcess(args, simulated_code, "", "")
        completed = subprocess.run(
            args,
            cwd=ROOT,
            env=env,
            input=input_text,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        record.update(
            {
                "returncode": completed.returncode,
                "duration_seconds": round(time.monotonic() - started, 3),
            }
        )
        if record_output:
            record["stdout_tail"] = stdout[-2000:]
            record["stderr_tail"] = stderr[-2000:]
        self.evidence.commands.append(record)
        if check and completed.returncode:
            raise RuntimeError(f"{label} failed ({completed.returncode}): {stderr[-1000:]}")
        return completed


class HARunner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.evidence = Evidence()
        self.exec = Executor(self.evidence, dry_run=args.dry_run)
        key = bootstrap_tools.platform_key()
        paths = bootstrap_tools.expected_paths(key)
        self.kind = str(paths["kind"])
        self.kubectl = str(paths["kubectl"])
        self.helm = str(paths["helm"])
        self.calico = str(paths["calico"])
        self.context = f"kind-{args.cluster_name}"
        self.compose_env = {
            **os.environ,
            "REFERENCE_RUNTIME": str(REFERENCE_RUNTIME.relative_to(ROOT)),
            "HA_RUNTIME": str(HA_RUNTIME.relative_to(ROOT)),
            "HA_EXTERNAL_BIND_ADDRESS": args.external_bind_address,
            "HA_KEYCLOAK_PORT": str(args.keycloak_port),
            "HA_POSTGRES_PORT": str(args.postgres_port),
            "HA_KMS_PORT": str(args.kms_port),
        }

    def kubectl_cmd(self, *args: str) -> list[str]:
        return [self.kubectl, "--context", self.context, *args]

    def helm_cmd(self, *args: str) -> list[str]:
        return [self.helm, "--kube-context", self.context, *args]

    def compose_cmd(self, *args: str) -> list[str]:
        return ["docker", "compose", "-f", str(COMPOSE_FILE), *args]

    def bootstrap(self) -> None:
        bootstrap_tools.bootstrap(dry_run=self.args.dry_run)
        self._bootstrap_reference_material()
        self.exec.run(
            "external dependencies up",
            self.compose_cmd("up", "-d", "--build", "--wait", "--wait-timeout", "240"),
            env=self.compose_env,
        )
        self._create_cluster()
        self._install_calico()
        host_cidr = self.args.host_cidr or (
            "172.18.0.1/32" if self.args.dry_run else self._discover_host_cidr()
        )
        host_ip = str(ipaddress.ip_network(host_cidr).network_address)
        self._configure_host_dns(host_ip)
        if not self.args.dry_run:
            generate_values.write_values(
                GENERATED_VALUES,
                generate_values.values(
                    host_cidr,
                    keycloak_port=self.args.keycloak_port,
                    postgres_port=self.args.postgres_port,
                    kms_port=self.args.kms_port,
                ),
            )
        self._apply_secrets()
        self.evidence.phase("bootstrap", "PASS", host_cidr=host_cidr)

    def _bootstrap_reference_material(self) -> None:
        self.exec.run(
            "reference identity material",
            [sys.executable, str(ROOT / "scripts" / "reference_stack.py"), "bootstrap"],
        )
        token_path = HA_RUNTIME / "secrets" / "kms_api_token"
        if self.args.dry_run:
            return
        token_path.parent.mkdir(parents=True, exist_ok=True)
        if not token_path.exists() or not token_path.read_text(encoding="utf-8").strip():
            token_path.write_text(secrets.token_urlsafe(48) + "\n", encoding="utf-8")
            if os.name != "nt":
                token_path.chmod(0o600)

    def _create_cluster(self) -> None:
        listed = self.exec.run("list Kind clusters", [self.kind, "get", "clusters"], check=False)
        exists = self.args.cluster_name in listed.stdout.splitlines() if not self.args.dry_run else False
        if not exists:
            self.exec.run(
                "create Kind HA cluster",
                [
                    self.kind,
                    "create",
                    "cluster",
                    "--name",
                    self.args.cluster_name,
                    "--config",
                    str(CLUSTER_CONFIG),
                    "--wait",
                    "120s",
                ],
                env=kind_proxy_environment(os.environ),
            )

    def _install_calico(self) -> None:
        self.exec.run("install Calico", self.kubectl_cmd("apply", "-f", self.calico))
        self.exec.run(
            "wait Calico controllers",
            self.kubectl_cmd(
                "-n",
                "kube-system",
                "rollout",
                "status",
                "deployment/calico-kube-controllers",
                "--timeout=240s",
            ),
        )
        self.exec.run(
            "wait Calico nodes",
            self.kubectl_cmd(
                "-n", "kube-system", "rollout", "status", "daemonset/calico-node", "--timeout=240s"
            ),
        )
        self.exec.run(
            "wait Kubernetes nodes",
            self.kubectl_cmd("wait", "--for=condition=Ready", "nodes", "--all", "--timeout=180s"),
        )

    def _discover_host_cidr(self) -> str:
        node = f"{self.args.cluster_name}-control-plane"
        resolved = self.exec.run(
            "resolve host.docker.internal",
            ["docker", "exec", node, "getent", "ahostsv4", "host.docker.internal"],
            check=False,
        )
        candidates = [line.split()[0] for line in resolved.stdout.splitlines() if line.split()]
        if not candidates:
            gateway = self.exec.run(
                "inspect Kind Docker gateway",
                [
                    "docker",
                    "network",
                    "inspect",
                    "kind",
                    "--format",
                    "{{(index .IPAM.Config 0).Gateway}}",
                ],
            ).stdout.strip()
            candidates = [gateway]
        address = ipaddress.ip_address(candidates[0])
        return f"{address}/{address.max_prefixlen}"

    def _configure_host_dns(self, host_ip: str) -> None:
        result = self.exec.run(
            "read CoreDNS config",
            self.kubectl_cmd("-n", "kube-system", "get", "configmap", "coredns", "-o", "json"),
        )
        if self.args.dry_run:
            self.exec.run("patch CoreDNS host mapping", self.kubectl_cmd("replace", "-f", "-"))
            return
        config = json.loads(result.stdout)
        corefile = config["data"]["Corefile"]
        marker = "# xa-guard-host-docker-internal"
        if marker not in corefile:
            block = (
                ".:53 {\n"
                f"    hosts {{\n        {host_ip} host.docker.internal\n"
                f"        fallthrough\n    }} {marker}\n"
            )
            config["data"]["Corefile"] = corefile.replace(".:53 {\n", block, 1)
            self.exec.run(
                "patch CoreDNS host mapping",
                self.kubectl_cmd("replace", "-f", "-"),
                input_text=json.dumps(config),
            )
            self.exec.run(
                "restart CoreDNS",
                self.kubectl_cmd("-n", "kube-system", "rollout", "restart", "deployment/coredns"),
            )
            self.exec.run(
                "wait CoreDNS",
                self.kubectl_cmd(
                    "-n", "kube-system", "rollout", "status", "deployment/coredns", "--timeout=120s"
                ),
            )

    def _apply_secrets(self) -> None:
        if self.args.dry_run:
            self.exec.run(
                "apply external Secrets",
                self.kubectl_cmd("-n", self.args.namespace, "apply", "-f", "-"),
                record_output=False,
            )
            return
        secret_dir = REFERENCE_RUNTIME / "secrets"
        password = (secret_dir / "postgres_password").read_text(encoding="utf-8").strip()
        dsn = (
            f"postgresql://xaguard:{quote(password, safe='')}@host.docker.internal:"
            f"{self.args.postgres_port}/xaguard"
        )
        documents = [
            self._secret(
                "xa-guard-runtime",
                {
                    "database-url": dsn,
                    "oidc-client-secret": self._read(secret_dir / "bff_client_secret"),
                    "oidc-introspection-client-secret": self._read(secret_dir / "api_client_secret"),
                    "internal-authorization-key": self._read(secret_dir / "internal_auth_key"),
                },
            ),
            self._secret(
                "xa-guard-business-api",
                {"database-url": dsn, "api-key": self._read(secret_dir / "business_api_key")},
            ),
            self._secret(
                "xa-guard-key-provider",
                {"auth-token": self._read(HA_RUNTIME / "secrets" / "kms_api_token")},
            ),
        ]
        self.exec.run(
            "create HA namespace",
            self.kubectl_cmd("create", "namespace", self.args.namespace),
            check=False,
        )
        self.exec.run(
            "apply external Secrets",
            self.kubectl_cmd("-n", self.args.namespace, "apply", "-f", "-"),
            input_text=yaml.safe_dump_all(documents),
            record_output=False,
        )

    def _secret(self, name: str, values: dict[str, str]) -> dict[str, Any]:
        return {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": name, "namespace": self.args.namespace},
            "type": "Opaque",
            "data": {
                key: base64.b64encode(value.encode("utf-8")).decode("ascii") for key, value in values.items()
            },
        }

    @staticmethod
    def _read(path: Path) -> str:
        return path.read_text(encoding="utf-8").strip()

    def accept(self) -> bool:
        if not GENERATED_VALUES.exists() and not self.args.dry_run:
            raise RuntimeError("generated values are absent; run the bootstrap action first")
        self._load_images()
        previous_overrides = self._image_overrides(self.args.previous_image)
        current_overrides = self._image_overrides(self.args.current_image)
        previous_revision = self._deploy("install_previous", previous_overrides)
        self._deploy("upgrade_current", current_overrides)
        self._rerun_migration(current_overrides)
        self._delete_api_pod()
        if self.args.prepare_takeover and self.args.takeover_effect_id:
            raise RuntimeError("--prepare-takeover and --takeover-effect-id are mutually exclusive")
        takeover_effect_id = self.args.takeover_effect_id
        if self.args.prepare_takeover:
            takeover_effect_id = self._prepare_takeover_effect()
        takeover_complete = self._worker_takeover(takeover_effect_id)
        self._network_policy_probes()
        self._rollback(previous_revision, self.args.previous_image, takeover_effect_id)
        return takeover_complete

    def _load_images(self) -> None:
        for image in sorted({self.args.previous_image, self.args.current_image, self.args.console_image}):
            self.exec.run("inspect local image", ["docker", "image", "inspect", image])
            self.exec.run(
                "load image into Kind",
                [self.kind, "load", "docker-image", "--name", self.args.cluster_name, image],
            )

    def _deploy(self, phase: str, overrides: list[str]) -> int:
        command = self.helm_cmd(
            "upgrade",
            "--install",
            self.args.release,
            str(CHART),
            "--namespace",
            self.args.namespace,
            "--create-namespace",
            "--values",
            str(GENERATED_VALUES),
            "--atomic",
            "--wait",
            "--wait-for-jobs",
            "--timeout",
            "6m",
            "--history-max",
            "10",
            *overrides,
            *self._console_overrides(),
        )
        self.exec.run(phase.replace("_", " "), command)
        self._assert_ha_replicas()
        revision = self._current_revision()
        self.evidence.phase(phase, "PASS", revision=revision)
        return revision

    def _image_overrides(self, image: str) -> list[str]:
        repository, tag, digest = split_image(image)
        args: list[str] = []
        for component in ("api", "worker", "businessApi", "migration"):
            args.extend(
                [
                    "--set-string",
                    f"{component}.image.repository={repository}",
                    "--set-string",
                    f"{component}.image.tag={tag}",
                    "--set-string",
                    f"{component}.image.digest={digest}",
                    "--set-string",
                    f"{component}.image.pullPolicy=IfNotPresent",
                ]
            )
        return args

    def _console_overrides(self) -> list[str]:
        repository, tag, digest = split_image(self.args.console_image)
        return [
            "--set-string",
            f"console.image.repository={repository}",
            "--set-string",
            f"console.image.tag={tag}",
            "--set-string",
            f"console.image.digest={digest}",
            "--set-string",
            "console.image.pullPolicy=IfNotPresent",
        ]

    def _current_revision(self) -> int:
        result = self.exec.run(
            "read Helm history",
            self.helm_cmd(
                "history", self.args.release, "--namespace", self.args.namespace, "--output", "json"
            ),
        )
        if self.args.dry_run:
            return 1 + sum(1 for name in self.evidence.phases if name.startswith("upgrade"))
        history = json.loads(result.stdout)
        return max(int(item["revision"]) for item in history)

    def _assert_ha_replicas(self) -> None:
        for component in ("api", "worker"):
            result = self.exec.run(
                f"verify {component} replicas",
                self.kubectl_cmd(
                    "-n",
                    self.args.namespace,
                    "get",
                    "deployment",
                    "-l",
                    f"app.kubernetes.io/instance={self.args.release},app.kubernetes.io/component={component}",
                    "-o",
                    "json",
                ),
            )
            if not self.args.dry_run:
                items = json.loads(result.stdout)["items"]
                if len(items) != 1 or items[0]["status"].get("readyReplicas", 0) < 2:
                    raise RuntimeError(f"{component} does not have two ready replicas")

    def _rerun_migration(self, overrides: list[str]) -> None:
        suffix = f"rerun-{int(time.time())}"[-20:]
        rendered = self.exec.run(
            "render migration rerun",
            self.helm_cmd(
                "template",
                self.args.release,
                str(CHART),
                "--namespace",
                self.args.namespace,
                "--values",
                str(GENERATED_VALUES),
                "--show-only",
                "templates/migration-job.yaml",
                "--set-string",
                f"migration.nameSuffix={suffix}",
                *overrides,
            ),
        )
        if self.args.dry_run:
            self.exec.run("apply migration rerun", self.kubectl_cmd("apply", "-f", "-"))
        else:
            document = next(d for d in yaml.safe_load_all(rendered.stdout) if d)
            job_name = document["metadata"]["name"]
            self.exec.run(
                "apply migration rerun",
                self.kubectl_cmd("apply", "-f", "-"),
                input_text=rendered.stdout,
            )
            self.exec.run(
                "wait migration rerun",
                self.kubectl_cmd(
                    "-n",
                    self.args.namespace,
                    "wait",
                    "--for=condition=complete",
                    f"job/{job_name}",
                    "--timeout=300s",
                ),
            )
        self.evidence.phase("migration_rerun", "PASS")

    def _delete_api_pod(self) -> None:
        before = self._pods("api")
        victim = before[0] if before else "dry-run-api-pod"
        self.exec.run(
            "delete one API pod",
            self.kubectl_cmd("-n", self.args.namespace, "delete", "pod", victim, "--wait=false"),
        )
        self._wait_rollout("api")
        after = self._pods("api")
        if not self.args.dry_run and (victim in after or len(after) < 2):
            raise RuntimeError("API pod deletion did not recover to two distinct pods")
        self.evidence.phase("api_pod_deletion", "PASS", deleted_pod=victim)

    def _prepare_takeover_effect(self) -> str:
        """Create a real delayed compensation through the protected API."""

        if self.args.dry_run:
            effect_id = "eff-" + "0" * 32
            self.evidence.phase(
                "takeover_effect_prepared",
                "PLANNED",
                effect_id=effect_id,
                tokens_persisted=False,
            )
            return effect_id
        api_pod = (self._pods("api") or [""])[0]
        business_pod = (self._pods("business-api") or [""])[0]
        if not api_pod or not business_pod:
            raise RuntimeError("API and business pods are required for takeover preparation")
        self.exec.run(
            "seed reference assignments",
            self.kubectl_cmd(
                "-n",
                self.args.namespace,
                "exec",
                api_pod,
                "--",
                "python",
                "-m",
                "xa_guard.control.seed",
            ),
        )
        service = self._resource_name("service", "api")
        command = self.kubectl_cmd(
            "-n",
            self.args.namespace,
            "port-forward",
            f"service/{service}",
            f"{self.args.api_port_forward}:80",
            "--address=127.0.0.1",
        )
        started = time.monotonic()
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.evidence.commands.append(
            {
                "label": "port-forward protected API for takeover preparation",
                "argv": command,
                "dry_run": False,
                "returncode": 0,
            }
        )
        try:
            live_url = f"http://127.0.0.1:{self.args.api_port_forward}/livez"
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("API port-forward stopped before becoming ready")
                try:
                    with urlopen(live_url, timeout=2) as response:  # noqa: S310 - fixed loopback URL
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.25)
            else:
                raise RuntimeError("API port-forward did not become ready")

            def arm_delayed_commit() -> None:
                code = (
                    "from pathlib import Path; p=Path('/tmp/xa-guard-faults'); "
                    "p.mkdir(parents=True,exist_ok=True); "
                    "(p/'after_cancel_commit').write_text('120',encoding='utf-8')"
                )
                self.exec.run(
                    "arm delayed business response",
                    self.kubectl_cmd(
                        "-n",
                        self.args.namespace,
                        "exec",
                        business_pod,
                        "--",
                        "python",
                        "-c",
                        code,
                    ),
                )

            value = takeover_flow.prepare_takeover(
                base_url=f"http://127.0.0.1:{self.args.api_port_forward}",
                issuer=f"http://localhost:{self.args.keycloak_port}/realms/xa-guard",
                before_approve=arm_delayed_commit,
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        effect_id = validate_effect_id(value["effect_id"])
        self.evidence.phase(
            "takeover_effect_prepared",
            "PASS",
            effect_id=effect_id,
            request_id=value["request_id"],
            duration_seconds=round(time.monotonic() - started, 3),
            tokens_persisted=False,
        )
        return effect_id

    def _worker_takeover(self, takeover_effect_id: str | None) -> bool:
        if not takeover_effect_id:
            self.evidence.phase(
                "worker_lease_takeover",
                "NOT_RUN",
                reason="--takeover-effect-id was not supplied; an approved effect is required",
            )
            return False
        effect_id = validate_effect_id(takeover_effect_id)
        deadline = time.monotonic() + 120
        owner = ""
        status = ""
        while time.monotonic() < deadline:
            owner, status = self._effect_state(effect_id)
            if status == "compensating" and owner:
                break
            time.sleep(2)
        if status != "compensating" or not owner:
            raise RuntimeError(f"effect {effect_id} never acquired a compensation lease")
        pods = self._pods("worker")
        victim = (
            "dry-run-worker-pod"
            if self.args.dry_run
            else next((pod for pod in pods if owner.startswith(pod + "-")), "")
        )
        if not victim:
            raise RuntimeError(f"lease owner {owner!r} does not map to a current Worker pod")
        self.exec.run(
            "delete lease-owning Worker",
            self.kubectl_cmd("-n", self.args.namespace, "delete", "pod", victim, "--wait=false"),
        )
        if self.args.dry_run:
            status = "compensated"
        else:
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                _new_owner, status = self._effect_state(effect_id)
                if status == "compensated":
                    break
                time.sleep(2)
        if status != "compensated":
            raise RuntimeError(f"effect {effect_id} was not compensated after Worker deletion")
        starts = (
            2
            if self.args.dry_run
            else int(
                self._psql(
                    "SELECT count(DISTINCT actor_sub) FROM xa_effect_events "
                    f"WHERE effect_id='{effect_id}' AND event_type='compensation_started'"
                )
                or "0"
            )
        )
        if starts < 2:
            raise RuntimeError("effect completed without evidence of a second Worker lease owner")
        self._wait_rollout("worker")
        self.evidence.phase("worker_lease_takeover", "PASS", deleted_pod=victim, distinct_lease_owners=starts)
        return True

    def _network_policy_probes(self) -> None:
        host = "host.docker.internal"
        business_service = self._resource_name("service", "business-api")
        positive = [
            ("api", host, self.args.keycloak_port),
            ("api", host, self.args.postgres_port),
            ("api", host, self.args.kms_port),
            ("worker", host, self.args.postgres_port),
            ("worker", host, self.args.kms_port),
            ("worker", business_service, 80),
            ("business-api", host, self.args.postgres_port),
        ]
        negative = [
            ("worker", host, self.args.keycloak_port),
            ("business-api", host, self.args.kms_port),
        ]
        for component, target, port in positive:
            self._socket_probe(component, target, port, should_connect=True)
        for component, target, port in negative:
            self._socket_probe(component, target, port, should_connect=False)
        self.evidence.phase("network_policy_probes", "PASS", allowed=len(positive), denied=len(negative))

    def _socket_probe(self, component: str, host: str, port: int, *, should_connect: bool) -> None:
        pod = (self._pods(component) or [f"dry-run-{component}-pod"])[0]
        code = f"import socket; s=socket.create_connection(({host!r},{port}),timeout=3); s.close()"
        result = self.exec.run(
            f"network {'allow' if should_connect else 'deny'} {component} to {host}:{port}",
            self.kubectl_cmd("-n", self.args.namespace, "exec", pod, "--", "python", "-c", code),
            check=False,
            simulated_code=0 if should_connect else 1,
        )
        if should_connect and result.returncode:
            raise RuntimeError(f"permitted dependency probe failed: {component} -> {host}:{port}")
        if not should_connect and result.returncode == 0:
            raise RuntimeError(
                f"forbidden dependency probe unexpectedly connected: {component} -> {host}:{port}"
            )

    def _rollback(self, revision: int, previous_image: str, takeover_effect_id: str | None) -> None:
        self.exec.run(
            "Helm rollback",
            self.helm_cmd(
                "rollback",
                self.args.release,
                str(revision),
                "--namespace",
                self.args.namespace,
                "--wait",
                "--timeout",
                "6m",
            ),
        )
        self._wait_rollout("api")
        self._wait_rollout("worker")
        expected = previous_image
        for component in ("api", "worker"):
            image = self._deployment_image(component)
            if not self.args.dry_run and image != expected:
                raise RuntimeError(f"rollback left {component} on {image}, expected {expected}")
        if takeover_effect_id:
            if self.args.dry_run:
                status = "compensated"
            else:
                _owner, status = self._effect_state(validate_effect_id(takeover_effect_id))
            if status != "compensated":
                raise RuntimeError("effect is unreadable or changed after rollback")
        self.evidence.phase("helm_rollback", "PASS", target_revision=revision)

    def _pods(self, component: str) -> list[str]:
        result = self.exec.run(
            f"list {component} pods",
            self.kubectl_cmd(
                "-n",
                self.args.namespace,
                "get",
                "pods",
                "-l",
                f"app.kubernetes.io/instance={self.args.release},app.kubernetes.io/component={component}",
                "-o",
                "json",
            ),
        )
        if self.args.dry_run:
            return []
        return [item["metadata"]["name"] for item in json.loads(result.stdout)["items"]]

    def _resource_name(self, kind: str, component: str) -> str:
        result = self.exec.run(
            f"find {component} {kind}",
            self.kubectl_cmd(
                "-n",
                self.args.namespace,
                "get",
                kind,
                "-l",
                f"app.kubernetes.io/instance={self.args.release},app.kubernetes.io/component={component}",
                "-o",
                "json",
            ),
        )
        if self.args.dry_run:
            return f"{self.args.release}-business-api"
        items = json.loads(result.stdout)["items"]
        if len(items) != 1:
            raise RuntimeError(f"expected one {component} {kind}, got {len(items)}")
        return items[0]["metadata"]["name"]

    def _wait_rollout(self, component: str) -> None:
        name = self._resource_name("deployment", component)
        self.exec.run(
            f"wait {component} rollout",
            self.kubectl_cmd(
                "-n", self.args.namespace, "rollout", "status", f"deployment/{name}", "--timeout=240s"
            ),
        )

    def _deployment_image(self, component: str) -> str:
        name = self._resource_name("deployment", component)
        result = self.exec.run(
            f"read {component} image",
            self.kubectl_cmd(
                "-n",
                self.args.namespace,
                "get",
                f"deployment/{name}",
                "-o",
                "jsonpath={.spec.template.spec.containers[0].image}",
            ),
        )
        return result.stdout.strip()

    def _effect_state(self, effect_id: str) -> tuple[str, str]:
        if self.args.dry_run:
            return "dry-run-worker-pod-deadbeef", "compensating"
        value = self._psql(
            f"SELECT COALESCE(lease_owner,''),status FROM xa_effects WHERE effect_id='{effect_id}'"
        )
        owner, _, status = value.partition("|")
        return owner, status

    def _psql(self, sql: str) -> str:
        result = self.exec.run(
            "query HA PostgreSQL state",
            self.compose_cmd(
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "xaguard",
                "-d",
                "xaguard",
                "-tA",
                "-F",
                "|",
                "-c",
                sql,
            ),
            env=self.compose_env,
        )
        return result.stdout.strip()

    def destroy(self) -> None:
        self.exec.run(
            "uninstall Helm release",
            self.helm_cmd("uninstall", self.args.release, "--namespace", self.args.namespace),
            check=False,
        )
        self.exec.run(
            "delete Kind cluster",
            [self.kind, "delete", "cluster", "--name", self.args.cluster_name],
            check=False,
        )
        self.exec.run(
            "stop external dependencies",
            self.compose_cmd("down"),
            check=False,
            env=self.compose_env,
        )
        self.evidence.phase("destroy", "PASS")

    def write_evidence(self, complete: bool) -> Path:
        self.evidence.phases.setdefault(
            "summary",
            {
                "status": "PASS" if complete else "INCOMPLETE",
                "required_phases": list(ACCEPTANCE_PHASES),
            },
        )
        self.evidence.phases["summary"]["completed_at"] = datetime.now(timezone.utc).isoformat()
        output = self.args.evidence or (
            HERE / "evidence" / f"ha-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        )
        if not self.args.dry_run:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(self.evidence.__dict__, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return output


def split_image(image: str) -> tuple[str, str, str]:
    if "@sha256:" in image:
        repository, digest = image.rsplit("@", 1)
        return repository, "", digest
    last = image.rsplit("/", 1)[-1]
    if ":" in last:
        repository, tag = image.rsplit(":", 1)
        return repository, tag, ""
    return image, "latest", ""


def validate_effect_id(value: str) -> str:
    candidate = str(value or "")
    if EFFECT_ID.fullmatch(candidate) is None:
        raise ValueError("effect ID must use the eff-<32 lowercase hex> format")
    return candidate


def kind_proxy_environment(source: Mapping[str, str]) -> dict[str, str]:
    """Make host-loopback proxies reachable from Kind node containers."""

    result = dict(source)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        raw = result.get(name, "")
        parsed = urlsplit(raw)
        if parsed.hostname not in {"127.0.0.1", "localhost"}:
            continue
        userinfo = ""
        if "@" in parsed.netloc:
            userinfo = parsed.netloc.rsplit("@", 1)[0] + "@"
        port = f":{parsed.port}" if parsed.port is not None else ""
        result[name] = urlunsplit(
            (
                parsed.scheme,
                f"{userinfo}host.docker.internal{port}",
                parsed.path,
                parsed.query,
                parsed.fragment,
            )
        )
    for name in ("NO_PROXY", "no_proxy"):
        values = [item.strip() for item in result.get(name, "").split(",") if item.strip()]
        if "host.docker.internal" not in values:
            values.append("host.docker.internal")
        result[name] = ",".join(values)
    return result


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("action", choices=("bootstrap", "accept", "all", "destroy"))
    value.add_argument("--dry-run", action="store_true")
    value.add_argument("--cluster-name", default="xa-guard-ha")
    value.add_argument("--namespace", default="xa-guard")
    value.add_argument("--release", default="xa-guard-ha")
    value.add_argument("--host-cidr", help="explicit Docker host /32 or /128")
    value.add_argument("--external-bind-address", default="127.0.0.1")
    value.add_argument("--keycloak-port", type=int, default=13081)
    value.add_argument("--postgres-port", type=int, default=15432)
    value.add_argument("--kms-port", type=int, default=13083)
    value.add_argument("--previous-image", default="xa-guard-reference:0.2.0-n-1")
    value.add_argument("--current-image", default="xa-guard-reference:0.2.0")
    value.add_argument("--console-image", default="xa-guard-console:0.2.0")
    value.add_argument("--takeover-effect-id")
    value.add_argument(
        "--prepare-takeover",
        action="store_true",
        help="create a real delayed Alice/Dora effect after the current upgrade",
    )
    value.add_argument("--api-port-forward", type=int, default=18080)
    value.add_argument("--allow-incomplete", action="store_true")
    value.add_argument("--evidence", type=Path)
    return value


def main() -> None:
    args = parser().parse_args()
    runner = HARunner(args)
    complete = True
    try:
        if args.action in {"bootstrap", "all"}:
            runner.bootstrap()
        if args.action in {"accept", "all"}:
            complete = runner.accept()
        if args.action == "destroy":
            runner.destroy()
    except Exception as exc:
        runner.evidence.phase("fatal", "FAIL", error_type=type(exc).__name__, message=str(exc))
        output = runner.write_evidence(False)
        print(f"HA acceptance failed; evidence: {output}", file=sys.stderr)
        raise
    output = runner.write_evidence(complete)
    print(f"HA evidence: {output}")
    if not complete and not args.allow_incomplete:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
