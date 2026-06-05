from __future__ import annotations

from pathlib import Path

from xa_guard.sandbox import SandboxPolicy, build_docker_command


def test_build_docker_command_enforces_codex_like_boundaries(tmp_path: Path):
    policy = SandboxPolicy(
        mode="docker",
        docker_image="xa-guard/sandbox:test",
        network_disabled=True,
        readonly_rootfs=True,
        memory="512m",
        cpus="0.5",
        pids_limit=64,
    )

    command = build_docker_command(
        ["python", "-m", "demo.targets.ops_target"],
        policy,
        workspace_root=tmp_path,
    )

    assert command[:4] == ["docker", "run", "--rm", "-i"]
    assert "--network" in command
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command
    assert ["--cap-drop", "ALL"] == command[command.index("--cap-drop") : command.index("--cap-drop") + 2]
    assert ["--security-opt", "no-new-privileges"] == command[
        command.index("--security-opt") : command.index("--security-opt") + 2
    ]
    assert ["--pids-limit", "64"] == command[command.index("--pids-limit") : command.index("--pids-limit") + 2]
    assert ["--memory", "512m"] == command[command.index("--memory") : command.index("--memory") + 2]
    assert ["--cpus", "0.5"] == command[command.index("--cpus") : command.index("--cpus") + 2]
    assert ["-v", f"{tmp_path}:/workspace:ro"] == command[command.index("-v") : command.index("-v") + 2]
    assert command[-3:] == ["python", "-m", "demo.targets.ops_target"]


def test_build_docker_command_uses_runsc_for_gvisor_mode(tmp_path: Path):
    policy = SandboxPolicy(
        mode="docker_gvisor",
        docker_image="xa-guard/sandbox:test",
        runtime="runsc",
    )

    command = build_docker_command(["python", "-m", "demo.targets.ops_target"], policy, tmp_path)

    assert ["--runtime", "runsc"] == command[command.index("--runtime") : command.index("--runtime") + 2]
