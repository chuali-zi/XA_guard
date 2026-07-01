"""Policy predicate 编译器。

demo 阶段：predicate 是 Python 表达式字符串，编译为 lambda。
生产阶段（M3）：接 OPA Rego（implementation-notes Q9）。

predicate 表达式可用的变量（子 agent 在 sandbox 里执行）：
    tool       ctx.tool_name (str)
    args       ctx.arguments (dict)
    role       ctx.user_role (str)
    taint      ctx.taint (TaintLabel)
    risk       ctx.risk_level (RiskLevel)
    sources    [s.value for s in ctx.input_sources]
    tenant / principal / agent_id / data_domain / resource_owner / task_id
               governance envelope 中的企业身份与数据域字段
    contains(arg_key, keyword) 辅助函数

例：
    "tool == 'exec_command' and contains('cmd', 'rm -rf')"
"""
from __future__ import annotations

from typing import Callable

from xa_guard.types import GateContext


def compile_predicate(expr: str) -> Callable[[GateContext], bool]:
    """编译 predicate 字符串为可调用对象。

    安全注意：demo 用受限 eval（builtins=None）。生产前必须切 OPA。
    """
    code = compile(expr, "<policy>", "eval")

    def _run(ctx: GateContext) -> bool:
        def contains(key: str, keyword: str) -> bool:
            val = ctx.arguments.get(key, "")
            return keyword in str(val).lower()

        env = {
            "tool": ctx.tool_name,
            "args": ctx.arguments,
            "role": ctx.user_role,
            "taint": ctx.taint.value,
            "risk": ctx.risk_level.value,
            "sources": [s.value for s in ctx.input_sources],
            "tenant": ctx.tenant_id,
            "principal": ctx.human_principal,
            "agent_id": ctx.agent_id,
            "data_domain": ctx.data_domain,
            "resource_owner": ctx.resource_owner,
            "task_id": ctx.task_id,
            "governance": {
                "tenant_id": ctx.tenant_id,
                "human_principal": ctx.human_principal,
                "agent_id": ctx.agent_id,
                "data_domain": ctx.data_domain,
                "resource_owner": ctx.resource_owner,
                "task_id": ctx.task_id,
                "cost_estimate_usd": ctx.cost_estimate_usd,
                "output_estimate": ctx.output_estimate,
                "capability_token": ctx.capability_token_summary,
            },
            "contains": contains,
        }
        return bool(eval(code, {"__builtins__": {}}, env))

    return _run
