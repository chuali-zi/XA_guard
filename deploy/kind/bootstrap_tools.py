"""Install the exact Kind/Helm/kubectl/Calico artifacts in tools.lock.json.

Downloads are cached below deploy/kind/.tools (gitignored). Every downloaded
byte stream is SHA-256 verified before it is made executable or extracted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
LOCK_PATH = HERE / "tools.lock.json"
TOOLS_DIR = HERE / ".tools"


def platform_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        architecture = "amd64"
    else:
        raise RuntimeError(f"unsupported architecture: {machine}; lock contains amd64 only")
    if system not in {"linux", "windows"}:
        raise RuntimeError(f"unsupported operating system: {system}; lock contains Linux/Windows only")
    return f"{system}-{architecture}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verified_download(url: str, expected: str, target: Path, force: bool) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not force and sha256(target) == expected:
        return target
    request = urllib.request.Request(url, headers={"User-Agent": "xa-guard-ha-bootstrap/0.2.0"})
    pending_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as pending:
            pending_path = Path(pending.name)
            with urllib.request.urlopen(request, timeout=60) as response:
                shutil.copyfileobj(response, pending)
    except Exception:
        if pending_path is not None:
            pending_path.unlink(missing_ok=True)
        raise
    assert pending_path is not None
    actual = sha256(pending_path)
    if actual != expected:
        pending_path.unlink(missing_ok=True)
        raise RuntimeError(f"checksum mismatch for {url}: expected {expected}, got {actual}")
    os.replace(pending_path, target)
    return target


def install_raw(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    if os.name != "nt":
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def install_helm(source: Path, target: Path, archive: str, key: str) -> None:
    member = "windows-amd64/helm.exe" if key.startswith("windows-") else "linux-amd64/helm"
    target.parent.mkdir(parents=True, exist_ok=True)
    if archive == "zip":
        with zipfile.ZipFile(source) as bundle, bundle.open(member) as handle, target.open("wb") as output:
            shutil.copyfileobj(handle, output)
    elif archive == "tar.gz":
        with tarfile.open(source, "r:gz") as bundle:
            handle = bundle.extractfile(member)
            if handle is None:
                raise RuntimeError(f"{member} is absent from {source}")
            with handle, target.open("wb") as output:
                shutil.copyfileobj(handle, output)
    else:
        raise RuntimeError(f"unsupported Helm archive type: {archive}")
    if os.name != "nt":
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def expected_paths(key: str) -> dict[str, Path]:
    suffix = ".exe" if key.startswith("windows-") else ""
    return {
        "kind": TOOLS_DIR / "bin" / f"kind{suffix}",
        "kubectl": TOOLS_DIR / "bin" / f"kubectl{suffix}",
        "helm": TOOLS_DIR / "bin" / f"helm{suffix}",
        "calico": TOOLS_DIR / "manifests" / "calico-v3.32.1.yaml",
    }


def bootstrap(*, force: bool = False, verify_only: bool = False, dry_run: bool = False) -> dict[str, Any]:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    key = platform_key()
    paths = expected_paths(key)
    plan = {
        "platform": key,
        "versions": {name: lock[name]["version"] for name in ("kind", "kubectl", "helm", "calico")},
        "paths": {name: str(path) for name, path in paths.items()},
    }
    if dry_run:
        return plan
    downloads = TOOLS_DIR / "downloads"
    for name in ("kind", "kubectl", "helm"):
        artifact = lock[name]["artifacts"][key]
        filename = artifact["url"].rsplit("/", 1)[-1]
        cached = verified_download(artifact["url"], artifact["sha256"], downloads / filename, force)
        if verify_only:
            if not paths[name].exists():
                raise RuntimeError(f"installed tool is absent: {paths[name]}")
        elif name == "helm":
            install_helm(cached, paths[name], artifact["archive"], key)
        else:
            install_raw(cached, paths[name])
    manifest = lock["calico"]["manifest"]
    verified_download(manifest["url"], manifest["sha256"], paths["calico"], force)
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="redownload all locked artifacts")
    parser.add_argument("--verify-only", action="store_true", help="verify cache and installed paths")
    parser.add_argument("--dry-run", action="store_true", help="print the platform-specific plan only")
    args = parser.parse_args()
    result = bootstrap(force=args.force, verify_only=args.verify_only, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
