"""evidence_sync — 本地/云端 artifacts → 标准 run 目录 → git 锚定溯源封存。

对齐 ../docs/EVIDENCE-CONTRACT.md 与 docs/acceptance/remote-evidence/EVIDENCE-LAYOUT-SPEC.md。
seal 优先调 tools/evidence/seal-run.sh；不可用时回退到确定性 python tar，永不静默失败。
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import shutil
import socket
import subprocess
import tarfile
from pathlib import Path

from .evaluator import RESULT_BLOCKED, RESULT_INFRA, RESULT_LIMIT, RESULT_PASS, Verdict


def utc_stamp() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def short_host() -> str:
    return socket.gethostname().split(".")[0][:12] or "host"


def new_run_id() -> str:
    return f"oar-rt-{utc_stamp()}-{short_host()}"


def _sha256_file(p: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    n = 0
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
            n += len(chunk)
    return h.hexdigest(), n


def build_run_dir(
    evidence_root: str | Path,
    run_id: str,
    *,
    meta: dict,
    console_log: str,
    commands: list[str],
    artifacts: dict[str, bytes],
    verdict: Verdict | None,
) -> Path:
    """把一次 run 的证据落成标准 run 目录，返回目录路径。"""
    root = Path(evidence_root) / run_id
    (root / "artifacts").mkdir(parents=True, exist_ok=True)

    for relpath, data in artifacts.items():
        dest = root / "artifacts" / relpath
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    (root / "console.log").write_text(console_log, encoding="utf-8")
    (root / "commands.txt").write_text("\n".join(commands) + "\n", encoding="utf-8")
    (root / "environment.txt").write_text(
        f"host={short_host()}\npython={os.sys.version.split()[0]}\ngenerated={utc_stamp()}\n",
        encoding="utf-8",
    )

    meta = dict(meta)
    meta.setdefault("run_id", run_id)
    meta.setdefault("target", "oar-auto-redteam")
    if verdict is not None:
        meta["verdict"] = {"result": verdict.result_label,
                           "breach_null": verdict.breach_null,
                           "breach_protected": verdict.breach_protected,
                           "asr_null": verdict.null_asr,
                           "asr_protected": verdict.protected_asr,
                           "fingerprint": verdict.fingerprint}
    (root / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    results_map = {
        RESULT_PASS: "PASS — NullSUT 破 且 防御被绕过（发现漏洞，高价值）",
        RESULT_BLOCKED: "BLOCKED — NullSUT 破 且 XA-Guard 拦截（防御有效，正样本回归）",
        RESULT_LIMIT: "LIMIT — NullSUT 未破，攻击未成立（负样本）",
        RESULT_INFRA: "INFRA_ERROR — run 出错/超时",
    }
    label = verdict.result_label if verdict else RESULT_INFRA
    (root / "RESULTS.md").write_text(
        f"# {label}\n\n{results_map.get(label, label)}\n", encoding="utf-8"
    )

    # artifact-hashes.json（对所有落盘文件，除自身）
    hashes = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name != "artifact-hashes.json":
            digest, size = _sha256_file(p)
            hashes[str(p.relative_to(root)).replace("\\", "/")] = {"sha256": digest, "bytes": size}
    (root / "artifact-hashes.json").write_text(
        json.dumps(hashes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return root


def seal(run_dir: str | Path, *, seal_script: str | Path | None = None) -> Path:
    """封存为确定性 tar.gz + .sha256。优先用 tools/evidence/seal-run.sh。返回 tarball 路径。"""
    run_dir = Path(run_dir)
    sealed_dir = run_dir.parent.parent / "sealed"
    sealed_dir.mkdir(parents=True, exist_ok=True)
    tarball = sealed_dir / f"{run_dir.name}.tar.gz"

    shell = None if os.name == "nt" else _find_posix_shell()
    if seal_script and Path(seal_script).is_file() and shell:
        subprocess.run([shell, str(seal_script), str(run_dir)], check=True)
    else:
        _deterministic_tar(run_dir, tarball)
    digest, _ = _sha256_file(tarball)
    (tarball.with_suffix(".gz.sha256")).write_text(f"{digest}  {tarball.name}\n", encoding="utf-8")
    return tarball


def _find_posix_shell() -> str | None:
    found = shutil.which("sh")
    if found:
        return found
    if os.name != "nt":
        return None
    for candidate in (
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git" / "usr" / "bin" / "sh.exe",
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git" / "bin" / "sh.exe",
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Git" / "usr" / "bin" / "sh.exe",
        Path(os.environ.get("LocalAppData", "")) / "Programs" / "Git" / "usr" / "bin" / "sh.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def _deterministic_tar(run_dir: Path, tarball: Path) -> None:
    files = sorted(p for p in run_dir.rglob("*") if p.is_file())
    with tarfile.open(tarball, "w:gz") as tar:
        for p in files:
            info = tar.gettarinfo(str(p), arcname=f"{run_dir.name}/{p.relative_to(run_dir).as_posix()}")
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            with p.open("rb") as fh:
                tar.addfile(info, fh)


def append_provenance(manifest_path: str | Path, run_id: str, tarball: str | Path,
                      *, git_head: str, objective_id: str, verdict: Verdict | None) -> None:
    """向 git 锚定的 provenance-manifest.jsonl 追加一行（信任根）。"""
    tarball = Path(tarball)
    digest, size = _sha256_file(tarball)
    line = {
        "run_id": run_id,
        "target": "oar-auto-redteam",
        "objective_id": objective_id,
        "tarball": tarball.name,
        "tarball_sha256": digest,
        "tarball_bytes": size,
        "git_head": git_head,
        "verdict": verdict.result_label if verdict else RESULT_INFRA,
        "sealed_at": utc_stamp(),
    }
    manifest = Path(manifest_path)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
