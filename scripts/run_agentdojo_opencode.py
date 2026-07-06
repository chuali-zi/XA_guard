from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


FORCE_RERUN_COMPLETED_TASKS = False


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(upstream: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={upstream.as_posix()}", *args],
        cwd=upstream,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _repo_git(*args: str) -> str:
    root = Path(__file__).resolve().parents[1]
    return subprocess.run(
        ["git", "-c", f"safe.directory={root.as_posix()}", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _git_dirty(path: Path) -> bool:
    process = subprocess.Popen(
        ["git", "-c", f"safe.directory={path.as_posix()}", "ls-files", "-m", "-o", "--exclude-standard"],
        cwd=path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        return bool(process.stdout and process.stdout.readline())
    finally:
        process.terminate()
        try:
            process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()


def _repo_dirty() -> bool:
    return bool(_repo_git("ls-files", "-m", "-o", "--exclude-standard"))


def _config_hash(path: str | None) -> str | None:
    if path is None:
        return None
    root = Path(path)
    if root.is_file():
        return _sha256(root)
    if not root.is_dir():
        return None
    opencode_config = root / "opencode"
    if opencode_config.is_dir():
        digest = hashlib.sha256()
        matched = False
        for name in ("opencode.json", "opencode.jsonc"):
            item = opencode_config / name
            if item.is_file():
                matched = True
                digest.update(str(item.relative_to(root)).replace("\\", "/").encode("utf-8"))
                digest.update(b"\0")
                digest.update(item.read_bytes())
                digest.update(b"\0")
        if matched:
            return digest.hexdigest()
    digest = hashlib.sha256()
    for item in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(item.relative_to(root)).replace("\\", "/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(item.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-dir", required=True)
    parser.add_argument("--opencode-executable", default="opencode.cmd")
    parser.add_argument("--opencode-model", required=True)
    parser.add_argument("--opencode-config-home", required=False, default=None)
    parser.add_argument("--opencode-data-home", required=False, default=None)
    parser.add_argument("--benchmark-version", default="v1.2.2")
    parser.add_argument("--suite", default="workspace")
    parser.add_argument("--user-task", required=True)
    parser.add_argument("--injection-task", required=True)
    parser.add_argument("--attack", default="important_instructions")
    parser.add_argument("--logdir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--xa-guard-defense", action="store_true")
    parser.add_argument("--budget-ledger")
    parser.add_argument("--budget-bucket")
    parser.add_argument("--retry-budget-bucket")
    parser.add_argument("--budget-job-id")
    parser.add_argument("--max-invocation-reserve-usd", type=float)
    parser.add_argument("--max-turn-retries", type=int, default=2)
    parser.add_argument("--acceptance-config-sha256")
    args = parser.parse_args()

    from agentdojo.agent_pipeline.agent_pipeline import (
        AgentPipeline,
        PipelineConfig,
        load_system_message,
    )
    from agentdojo.agent_pipeline.basic_elements import InitQuery, SystemMessage
    from agentdojo.agent_pipeline.tool_execution import ToolsExecutionLoop, ToolsExecutor
    from agentdojo.attacks.attack_registry import load_attack
    from agentdojo.benchmark import benchmark_suite_with_injections
    from agentdojo.logging import OutputLogger
    from agentdojo.task_suite.load_suites import get_suite

    from bench.external.agentdojo_opencode import OpenCodeLLM

    from bench.external.agentdojo_xa_guard import XAGuardPIDetector
    upstream = Path(args.upstream_dir).resolve()
    logdir = Path(args.logdir).resolve()
    output = Path(args.output).resolve()
    logdir.mkdir(parents=True, exist_ok=True)
    invocation_log = logdir / "opencode-invocations.jsonl"
    opencode_runtime = Path(tempfile.gettempdir()) / "xa-guard-opencode-agentdojo-runtime"
    opencode_runtime.mkdir(parents=True, exist_ok=True)

    llm = OpenCodeLLM(
        executable=args.opencode_executable,
        model=args.opencode_model,
        cwd=opencode_runtime,
        config_home=args.opencode_config_home,
        data_home=args.opencode_data_home,
        timeout_seconds=args.timeout_seconds,
        invocation_log=invocation_log,
        budget_ledger=args.budget_ledger,
        budget_bucket=args.budget_bucket,
        retry_budget_bucket=args.retry_budget_bucket,
        budget_job_id=args.budget_job_id,
        max_invocation_reserve_usd=args.max_invocation_reserve_usd,
        max_turn_retries=args.max_turn_retries,
    )
    decision_log = logdir / "xa-guard-decisions.jsonl"
    if args.xa_guard_defense:
        defense = XAGuardPIDetector(decision_log=decision_log)
        pipeline = AgentPipeline(
            [
                SystemMessage(load_system_message(None)),
                InitQuery(),
                llm,
                ToolsExecutionLoop([ToolsExecutor(), defense, llm]),
            ]
        )
        pipeline.name = f"{llm.name}-xa-guard"
    else:
        pipeline = AgentPipeline.from_config(
            PipelineConfig(
                llm=llm,
                model_id=None,
                defense=None,
                system_message_name=None,
                system_message=None,
            )
        )
    suite = get_suite(args.benchmark_version, args.suite)
    # AgentDojo's attack registry maps pipeline name → model name via a fixed
    # lookup table (MODEL_NAMES) using substring matching on keys.  Custom
    # models like opencode-go/glm-5.2 are not in that table, so we append the
    # recognized key "local" to let the attack resolve to "Local model".
    # This does not change any scorer, parser, or benchmark semantics.
    from agentdojo.models import MODEL_NAMES

    if pipeline.name and not any(key in pipeline.name for key in MODEL_NAMES):
        pipeline.name = f"{pipeline.name}--local"
    attack = load_attack(args.attack, suite, pipeline)

    started_at = datetime.now(timezone.utc)
    with OutputLogger(str(logdir)):
        results = benchmark_suite_with_injections(
            pipeline,
            suite,
            attack,
            logdir=logdir,
            # Preserve official completed task traces in this job logdir so a
            # resumed child reruns only the interrupted task, not earlier ones.
            force_rerun=FORCE_RERUN_COMPLETED_TASKS,
            user_tasks=[args.user_task],
            injection_tasks=[args.injection_task],
            benchmark_version=args.benchmark_version,
        )
    finished_at = datetime.now(timezone.utc)

    utility = {
        f"{user_task}|{injection_task}": value
        for (user_task, injection_task), value in results["utility_results"].items()
    }
    security = {
        f"{user_task}|{injection_task}": value
        for (user_task, injection_task), value in results["security_results"].items()
    }
    artifacts = {
        "trace_root": str(logdir),
        "opencode_invocations": str(invocation_log),
        "opencode_invocations_sha256": _sha256(invocation_log),
    }
    injection_utility = results["injection_tasks_utility_results"]
    if args.xa_guard_defense and decision_log.exists():
        artifacts.update(
            {
                "xa_guard_decisions": str(decision_log),
                "xa_guard_decisions_sha256": _sha256(decision_log),
            }
        )
    limitations = [
        "single_user_task_single_injection_task_smoke",
        "custom_opencode_model_adapter",
        "not_paper_model_reproduction",
        "not_official_leaderboard_score",
    ]
    limitations.append("xa_guard_gate1_rule_defense" if args.xa_guard_defense else "no_xa_guard_defense_in_baseline")
    license_path = upstream / "LICENSE"
    payload = {
        "schema_version": "xa-agentdojo-official-code-smoke/v0.1",
        "claim_scope": (
            "official_agentdojo_code_custom_opencode_model_xa_guard_defense_smoke"
            if args.xa_guard_defense
            else "official_agentdojo_code_custom_opencode_model_smoke"
        ),
        "official_claim": False,
        "not_paper_model_reproduction": True,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "upstream": {
            "repository": "https://github.com/ethz-spylab/agentdojo",
            "commit": _git(upstream, "rev-parse", "HEAD"),
            "dirty": _git_dirty(upstream),
            "version": "0.1.35",
            "license": "MIT",
            "license_sha256": _sha256(license_path),
        },
        "run": {
            "model_adapter": "opencode-run-json",
            "runner_commit": _repo_git("rev-parse", "HEAD"),
            "runner_dirty": _repo_dirty(),
            "adapter_commit": _repo_git("rev-parse", "HEAD"),
            "acceptance_config_sha256": args.acceptance_config_sha256,
            "opencode_permission_config_sha256": _config_hash(args.opencode_config_home),
            "model": args.opencode_model,
            "benchmark_version": args.benchmark_version,
            "suite": args.suite,
            "user_task": args.user_task,
            "injection_task": args.injection_task,
            "attack": args.attack,
            "xa_guard_defense": args.xa_guard_defense,
        },
        "official_scorer_results": {
            "utility_results": utility,
            "security_results": security,
            "security_result_semantics": "true_means_injection_task_succeeded_attack_success",
            "attack_success_results": security,
            "injection_tasks_utility_results": injection_utility,
            "eligible_for_asr": all(injection_utility.values()),
        },
        "artifacts": artifacts,
        "limitations": limitations,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
