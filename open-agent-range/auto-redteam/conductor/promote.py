"""promote — 攻破 finding 自动晋级为回归资产（findings 分支 + PR）。

受限自治：cloud 引擎里，云端 agent 已在 findings 分支提交 injection + finding 报告并 autoCreatePR；
本模块在本地侧记录晋级意图、落 PROMOTE.md 标记，并可选触发 git（仅在 enable_git 且非 main）。
向 main 的合并保留为确定性步骤（见 SAFETY-AND-BUDGET.md）。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .evaluator import Verdict

PROTECTED_BRANCHES = {"main", "master"}


def record_promotion(run_dir: str | Path, verdict: Verdict, objective_id: str,
                    *, cursor_pr_url: str | None = None) -> Path:
    """在 run 目录落 PROMOTE.md 晋级标记（无论 cloud agent 是否已建 PR 都留痕）。"""
    run_dir = Path(run_dir)
    marker = run_dir / "PROMOTE.md"
    marker.write_text(
        "\n".join([
            f"# PROMOTED · {verdict.result_label}",
            f"- objective: {objective_id}",
            f"- risk: {verdict.risk}",
            f"- fingerprint: {verdict.fingerprint}",
            f"- breach_null: {verdict.breach_null}  breach_protected: {verdict.breach_protected}",
            f"- cursor_pr: {cursor_pr_url or '(not created automatically by local CLI mode)'}",
            "",
            "> local CLI mode keeps promotion as a deterministic Conductor-side marker.",
            "> 向 main 合并为确定性步骤（人工 review PR / CI）。",
        ]) + "\n",
        encoding="utf-8",
    )
    return marker


def local_git_promote(repo_root: str | Path, files: list[str], message: str,
                     *, branch: str = "auto-redteam/findings", enable: bool = False) -> dict:
    """可选：本地 git 侧晋级（仅 cli 回退引擎用）。默认 enable=False，不动仓库。"""
    if not enable:
        return {"skipped": True, "reason": "local git promote disabled (cloud agent handles commit+PR)"}
    if branch in PROTECTED_BRANCHES:
        raise ValueError(f"refusing to commit to protected branch {branch}")
    repo_root = str(repo_root)
    subprocess.run(["git", "-C", repo_root, "checkout", "-B", branch], check=True)
    subprocess.run(["git", "-C", repo_root, "add", *files], check=True)
    subprocess.run(["git", "-C", repo_root, "commit", "-m", message], check=True)
    return {"skipped": False, "branch": branch, "files": files}


def load_finding_report(run_dir: str | Path) -> dict | None:
    run_dir = Path(run_dir)
    for candidate in run_dir.rglob("finding*.json"):
        try:
            return json.loads(candidate.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
    return None
