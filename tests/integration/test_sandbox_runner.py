from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from xa_guard.sandbox import SandboxPolicy, build_docker_command


def _require_local_docker_image(image: str) -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker is not installed")
    inspect = subprocess.run(["docker", "image", "inspect", image], capture_output=True, text=True)
    if inspect.returncode != 0:
        pytest.skip(f"docker image {image!r} is not available locally")


def test_docker_sandbox_blocks_network_and_root_writes():
    image = "xa-guard/sandbox:latest"
    _require_local_docker_image(image)
    probe = (
        "import json, socket\n"
        "results = {}\n"
        "try:\n"
        "    open('/xa_guard_write_probe', 'w').write('x')\n"
        "    results['root_write'] = 'allowed'\n"
        "except Exception as exc:\n"
        "    results['root_write'] = type(exc).__name__\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 80), timeout=1).close()\n"
        "    results['network'] = 'allowed'\n"
        "except Exception as exc:\n"
        "    results['network'] = type(exc).__name__\n"
        "print(json.dumps(results, sort_keys=True))\n"
    )
    policy = SandboxPolicy(
        mode="docker",
        docker_image=image,
        network_disabled=True,
        readonly_rootfs=True,
        workspace_mount=False,
    )

    command = build_docker_command(["python", "-c", probe], policy, workspace_root=".")
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)

    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout.strip().splitlines()[-1])
    assert observed["root_write"] != "allowed"
    assert observed["network"] != "allowed"
