"""Executable sandbox policy helpers for downstream MCP tool processes.

Gate5 decides *which* sandbox profile a call should use. This module turns
that decision into concrete process-launch arguments. The Linux Codex sandbox
model this mirrors is: read-only by default, explicit workspace mount, network
off unless allowed, and no privilege escalation.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from xa_guard.types import GateContext

SandboxMode = Literal["native", "docker", "docker_gvisor"]


@dataclass(frozen=True)
class SandboxPolicy:
    mode: SandboxMode = "native"
    docker_image: str = "xa-guard/sandbox:latest"
    runtime: str = "runc"
    network_disabled: bool = True
    readonly_rootfs: bool = True
    memory: str = "256m"
    cpus: str = "1"
    pids_limit: int = 128
    workspace_mount: bool = True
    workspace_target: str = "/workspace"
    workspace_readonly: bool = True

    @property
    def enforced(self) -> bool:
        return self.mode != "native"


def policy_from_context(ctx: GateContext) -> SandboxPolicy:
    """Extract the latest Gate5 sandbox policy from a context."""
    for result in reversed(ctx.gate_results):
        if result.gate_name not in ("gate5_sandbox", "gate5"):
            continue
        metadata = result.metadata
        mode = metadata.get("sandbox_mode", "native")
        if mode not in ("native", "docker", "docker_gvisor"):
            mode = "native"
        return SandboxPolicy(
            mode=mode,
            docker_image=str(metadata.get("docker_image") or "xa-guard/sandbox:latest"),
            runtime=str(metadata.get("runtime") or "runc"),
            network_disabled=bool(metadata.get("network_disabled", mode != "native")),
            readonly_rootfs=bool(metadata.get("readonly_rootfs", mode != "native")),
            memory=str(metadata.get("memory") or "256m"),
            cpus=str(metadata.get("cpus") or "1"),
            pids_limit=int(metadata.get("pids_limit") or 128),
            workspace_mount=bool(metadata.get("workspace_mount", True)),
            workspace_target=str(metadata.get("workspace_target") or "/workspace"),
            workspace_readonly=bool(metadata.get("workspace_readonly", True)),
        )
    return SandboxPolicy()


def build_docker_command(
    downstream_command: list[str],
    policy: SandboxPolicy,
    workspace_root: str | Path,
) -> list[str]:
    """Build a Docker command that runs the downstream MCP server on stdio."""
    if not downstream_command:
        raise ValueError("downstream command must not be empty")
    if policy.mode == "native":
        return list(downstream_command)

    workspace = str(Path(workspace_root).resolve())
    command = ["docker", "run", "--rm", "-i"]

    if policy.network_disabled:
        command.extend(["--network", "none"])
    if policy.readonly_rootfs:
        command.append("--read-only")

    command.extend(["--cap-drop", "ALL"])
    command.extend(["--security-opt", "no-new-privileges"])
    command.extend(["--pids-limit", str(policy.pids_limit)])
    command.extend(["--memory", policy.memory])
    command.extend(["--cpus", policy.cpus])

    if policy.mode == "docker_gvisor":
        command.extend(["--runtime", policy.runtime or "runsc"])

    if policy.workspace_mount:
        mode = "ro" if policy.workspace_readonly else "rw"
        command.extend(["-v", f"{workspace}:{policy.workspace_target}:{mode}"])
        command.extend(["--workdir", policy.workspace_target])
        command.extend(["-e", f"PYTHONPATH={policy.workspace_target}/src"])

    command.append(policy.docker_image)
    command.extend(downstream_command)
    return command
