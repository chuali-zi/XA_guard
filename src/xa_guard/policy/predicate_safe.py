"""Predicate 编译器：双轨。

- tier == 'baseline'：继续走 compiler.compile_predicate（受限 eval；项目自身可信）
- tier == 'overlay' ：走 evalidate AST 白名单（企业可写 → 必须沙箱化）

evalidate 不可用时，overlay 走 **safe fallback**：
    只支持有限的 AST 节点（Compare / BoolOp / Name / Constant / Call(contains/in)），
    手写 AST walker；任何其他节点 → 编译期拒绝，整批 overlay 加载失败。

参考（事实源 / 调研 agent #1）：
- asteval 已有多个 sandbox escape CVE，不可用
- simpleeval 慢、维护节奏弱
- evalidate AST 白名单 + 速度接近原生 eval，是推荐项

调用方：layered.LayeredPolicySource 编译规则时按 tier 路由。
"""
from __future__ import annotations

import ast
from typing import Callable

from xa_guard.policy.compiler import compile_predicate as _compile_baseline
from xa_guard.types import GateContext

try:  # 可选依赖；不存在则用内置 fallback
    import evalidate  # type: ignore

    _HAS_EVALIDATE = True
except Exception:  # pragma: no cover - depends on environment
    evalidate = None  # type: ignore
    _HAS_EVALIDATE = False


class UnsafePredicateError(ValueError):
    """overlay predicate 包含不在白名单内的 AST 节点。"""


# 允许的 AST 节点：表达式、字面量、比较、布尔、变量名引用、属性、下标、列表/元组、有限函数调用
_ALLOWED_NODES: tuple[type, ...] = (
    ast.Expression,
    ast.BoolOp, ast.And, ast.Or, ast.Not, ast.UnaryOp,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn, ast.Is, ast.IsNot,
    ast.Name, ast.Load,
    ast.Constant,
    ast.Attribute,
    ast.Subscript, ast.Index, ast.Slice,
    ast.List, ast.Tuple, ast.Set,
    ast.Call,
)
_ALLOWED_CALLEES = {"contains", "len", "str", "any", "all"}


def _validate_overlay_expr(expr: str) -> None:
    """走一遍 AST，发现非白名单节点立刻拒绝。"""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise UnsafePredicateError(f"overlay predicate syntax error: {exc}") from exc

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise UnsafePredicateError(
                f"overlay predicate uses disallowed AST node: {type(node).__name__} in '{expr}'"
            )
        if isinstance(node, ast.Call):
            # 只允许调用白名单内的具名函数（不允许 attribute call / lambda）
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_CALLEES:
                raise UnsafePredicateError(
                    f"overlay predicate calls disallowed callee in '{expr}'"
                )


def compile_for_tier(expr: str, tier: str) -> Callable[[GateContext], bool]:
    """根据来源 tier 选择安全等级。

    tier='baseline' → 用现有 compile_predicate（受限 builtins，eval）
    tier='overlay'  → AST 白名单校验后再 compile + eval
    """
    if tier == "baseline":
        return _compile_baseline(expr)

    # overlay 路径
    _validate_overlay_expr(expr)
    if _HAS_EVALIDATE:
        # evalidate 会再做一次防护；优先走它（更成熟的 AST 验证 + 节点白名单）
        eval_model = evalidate.EvalModel(  # type: ignore[attr-defined]
            nodes=[
                "Expression", "BoolOp", "And", "Or", "Not", "UnaryOp",
                "Compare", "Eq", "NotEq", "Lt", "LtE", "Gt", "GtE", "In", "NotIn",
                "Name", "Load", "Constant", "Attribute", "Subscript", "Index",
                "List", "Tuple", "Set", "Call",
            ],
            allowed_functions=list(_ALLOWED_CALLEES),
        )
        try:
            evalidate.Expr(expr, model=eval_model)  # type: ignore[attr-defined]
        except Exception as exc:
            raise UnsafePredicateError(
                f"overlay predicate rejected by evalidate: {exc}"
            ) from exc

    # AST 校验通过 → 走 baseline 同款的受限 eval（无 builtins）
    return _compile_baseline(expr)
