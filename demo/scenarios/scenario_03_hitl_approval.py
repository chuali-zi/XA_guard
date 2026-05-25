"""场景 3 · HITL 人工审批演示

故事线：
  ops 角色发起 exec_command(host="web03", cmd="uptime")。
  exec_command 被标记为 RED 风险工具。
  XA-Guard 关卡 2（办事大厅 HITL）应返回 REQUIRE_APPROVAL。
  fallback=stdout 时在终端打印审批提示。

运行：
    python -m demo.scenarios.scenario_03_hitl_approval
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import io
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from xa_guard.config import GateConfig, XAGuardConfig
from xa_guard.gates.gate1_input import Gate1Input
from xa_guard.gates.gate2_plan import Gate2Plan
from xa_guard.gates.gate3_policy import Gate3Policy
from xa_guard.gates.gate4_taint import Gate4Taint
from xa_guard.gates.gate5_sandbox import Gate5Sandbox
from xa_guard.gates.gate6_audit import Gate6Audit
from xa_guard.pipeline import Pipeline
from xa_guard.types import Decision, GateContext, InputSource, RiskLevel

console = Console(file=io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8"), highlight=False)


async def mock_executor(ctx: GateContext) -> str:
    return "(mock) uptime output: 10:05:03 up 42 days, 3:17, 1 user, load average: 0.08, 0.12, 0.10"


def _stub_cfg() -> XAGuardConfig:
    cfg = XAGuardConfig()
    for gate in ("gate1", "gate2", "gate3", "gate4", "gate5", "gate6"):
        cfg.gates[gate] = GateConfig(enabled=True)
    # gate2 配置：exec_command → red → hitl required
    cfg.gates["gate2"].options["hitl_required_for"] = ["red"]
    cfg.gates["gate2"].options["elicitation_fallback"] = "stdout"
    return cfg


def _build_ctx() -> GateContext:
    """构造场景 3 的 GateContext：
    - exec_command 属于 RED 高危工具
    - cmd="uptime" 本身无害，但工具风险等级触发 HITL
    """
    return GateContext(
        tool_name="exec_command",
        arguments={"host": "web03", "cmd": "uptime"},
        user_role="ops",
        input_sources=[InputSource.USER],
        session_history=[
            {"role": "user", "content": "查一下 web03 服务器运行时间"},
        ],
    )


async def run_scenario() -> None:
    console.rule("[bold magenta]场景 3 · HITL 人工审批 (Human-In-The-Loop)")
    console.print()
    console.print(Panel(
        "[bold]触发链[/bold]\n"
        "  ops 角色发起 exec_command(host='web03', cmd='uptime')\n"
        "  ↓ exec_command 风险等级 = RED（高危）\n"
        "  ↓ 关卡 2 判定需要人工审批\n"
        "  [green]-> 期望关卡 2 返回 REQUIRE_APPROVAL\n"
        "  [cyan]-> fallback=stdout 在终端打印审批提示",
        title="场景概述", border_style="magenta"
    ))
    console.print()

    cfg = _stub_cfg()
    pipeline = Pipeline(
        gate1=Gate1Input(cfg.gate("gate1")),
        gate2=Gate2Plan(cfg.gate("gate2")),
        gate3=Gate3Policy(cfg.gate("gate3")),
        gate4=Gate4Taint(cfg.gate("gate4")),
        gate5=Gate5Sandbox(cfg.gate("gate5")),
        gate6=Gate6Audit(cfg.gate("gate6")),
        cfg=cfg,
    )

    ctx = _build_ctx()

    # --- 模拟 gate2 HITL stdout fallback ---
    console.print(Panel(
        "[bold yellow]★ 模拟 HITL stdout fallback 提示[/bold yellow]\n\n"
        "[bold]待审批操作[/bold]\n"
        f"  工具名  : exec_command\n"
        f"  主机    : web03\n"
        f"  命令    : uptime\n"
        f"  风险等级: [bold red]RED[/bold red]\n\n"
        "[dim]（demo 模式自动跳过，生产模式需运维人员在此确认 Y/N）[/dim]",
        title="[yellow]▶ 审批弹窗 / stdout 提示[/yellow]",
        border_style="yellow",
    ))
    console.print()

    result = await pipeline.run(ctx, mock_executor)

    table = Table(title="关卡决策详情", show_lines=True)
    table.add_column("关卡", style="cyan", width=22)
    table.add_column("决策", width=22)
    table.add_column("命中规则", width=22)
    table.add_column("风险描述 / 备注", width=40)
    table.add_column("note", width=20)

    decision_style = {
        "allow": "green",
        "warn": "yellow",
        "deny": "bold red",
        "require_approval": "bold magenta",
    }

    for gr in ctx.gate_results:
        d = gr.decision.value
        style = decision_style.get(d, "white")
        risk_col = "\n".join(gr.risks) if gr.risks else (gr.note or "-")
        table.add_row(
            gr.gate_name,
            f"[{style}]{d}[/{style}]",
            ", ".join(gr.rule_hits) or "-",
            risk_col,
            gr.note or "-",
        )

    console.print(table)
    console.print()

    fd = result.final_decision.value
    fs = decision_style.get(fd, "white")
    console.print(Panel(
        f"[bold]最终决策[/bold]: [{fs}]{fd}[/{fs}]\n"
        f"[bold]原因[/bold]: {result.final_reason or '(无)'}\n"
        f"[bold]命中规则[/bold]: {', '.join(ctx.rule_hits) or '(无)'}\n"
        f"[bold]工具结果[/bold]: {result.tool_result or '(未执行)'}",
        title="最终结果",
        border_style="yellow" if fd == "allow" else "magenta",
    ))

    if fd == "require_approval":
        console.print("[bold green]>> HITL 触发成功！等待人工审批。[/bold green]")
    elif fd == "allow":
        console.print("[bold yellow]!! gate2 为 stub，HITL 未触发（exec_command 直接放行）[/bold yellow]")
        console.print("  提示：实现 Gate2Plan 中的 TOOL_RISK_MAP 后即可触发 REQUIRE_APPROVAL。")
    else:
        console.print(f"[bold red]XX 操作被拒绝: {result.final_reason}[/bold red]")


def main() -> None:
    asyncio.run(run_scenario())


if __name__ == "__main__":
    main()
