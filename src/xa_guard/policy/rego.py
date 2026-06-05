"""OPA/Rego adapter for Gate3 policy rules.

The policy file is still authored as XA-Guard's existing Python-like DSL. This
module compiles that DSL into a Rego module for OPA deployments and keeps a
Python fallback with the same predicates so local demo/test environments do not
need the OPA binary installed.
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from xa_guard.policy.compiler import compile_predicate
from xa_guard.types import GateContext, PolicyRule


class RegoCompileError(ValueError):
    """Raised when a policy predicate cannot be represented as Rego."""


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _local_opa_path() -> str | None:
    suffix = "opa.exe" if os.name == "nt" else "opa"
    candidate = Path(__file__).resolve().parents[3] / "tools" / "opa" / suffix
    return str(candidate) if candidate.exists() else None


def _rego_value(node: ast.AST) -> str:
    if isinstance(node, ast.Constant):
        return _json(node.value)
    if isinstance(node, ast.Name):
        mapping = {
            "tool": "input.tool",
            "role": "input.role",
            "taint": "input.taint",
            "risk": "input.risk",
            "sources": "input.sources",
        }
        if node.id in mapping:
            return mapping[node.id]
        raise RegoCompileError(f"unsupported name: {node.id}")
    if isinstance(node, (ast.Tuple, ast.List)):
        return "[" + ", ".join(_rego_value(item) for item in node.elts) + "]"
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "args":
        return f"object.get(input.args, {_rego_value(node.slice)}, null)"
    if isinstance(node, ast.Call):
        return _rego_call(node)
    raise RegoCompileError(f"unsupported expression: {ast.dump(node, include_attributes=False)}")


def _rego_call(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name) and node.func.id == "contains" and len(node.args) == 2:
        key = _rego_value(node.args[0])
        keyword = _rego_value(node.args[1])
        value = f"lower(sprintf(\"%v\", [object.get(input.args, {key}, \"\")]))"
        return f"contains({value}, lower({keyword}))"
    if (
        isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "args"
        and node.func.attr == "get"
        and 1 <= len(node.args) <= 2
    ):
        key = _rego_value(node.args[0])
        default = _rego_value(node.args[1]) if len(node.args) == 2 else "null"
        return f"object.get(input.args, {key}, {default})"
    raise RegoCompileError(f"unsupported call: {ast.dump(node, include_attributes=False)}")


def _rego_expr(node: ast.AST) -> str:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return f"not ({_rego_expr(node.operand)})"
    if isinstance(node, ast.Compare):
        left = _rego_value(node.left)
        parts: list[str] = []
        for op, comparator in zip(node.ops, node.comparators, strict=False):
            right = _rego_value(comparator)
            if isinstance(op, ast.Eq):
                parts.append(f"{left} == {right}")
            elif isinstance(op, ast.NotEq):
                parts.append(f"{left} != {right}")
            elif isinstance(op, ast.Lt):
                parts.append(f"{left} < {right}")
            elif isinstance(op, ast.LtE):
                parts.append(f"{left} <= {right}")
            elif isinstance(op, ast.Gt):
                parts.append(f"{left} > {right}")
            elif isinstance(op, ast.GtE):
                parts.append(f"{left} >= {right}")
            elif isinstance(op, ast.In):
                parts.append(f"{right}[_] == {left}")
            elif isinstance(op, ast.NotIn):
                parts.append(f"not ({right}[_] == {left})")
            else:
                raise RegoCompileError(f"unsupported compare op: {type(op).__name__}")
            left = right
        return "(" + " and ".join(parts) + ")"
    if isinstance(node, ast.Call):
        return _rego_call(node)
    return _rego_value(node)


def _rego_bodies(node: ast.AST) -> list[list[str]]:
    """Return disjunctive Rego bodies.

    Rego expresses AND as multiple body lines and OR as multiple rules with the
    same head, so we expand the Python-like predicate AST into DNF.
    """

    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        bodies: list[list[str]] = [[]]
        for item in node.values:
            item_bodies = _rego_bodies(item)
            bodies = [left + right for left in bodies for right in item_bodies]
        return bodies
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        bodies: list[list[str]] = []
        for item in node.values:
            bodies.extend(_rego_bodies(item))
        return bodies
    return [[_rego_expr(node)]]


def predicate_to_rego(expr: str) -> str:
    """Translate the project predicate DSL into a Rego boolean expression."""

    parsed = ast.parse(expr, mode="eval")
    return " or ".join("(" + "; ".join(body) + ")" for body in _rego_bodies(parsed.body))


def _rule_name(rule_id: str) -> str:
    return "rule_" + "".join(ch if ch.isalnum() else "_" for ch in rule_id)


def build_rego_module(rules: list[PolicyRule], package: str = "xa_guard.gate3") -> str:
    lines = [
        f"package {package}",
        "",
        "import rego.v1",
        "",
        "# Generated from XA-Guard PolicyRule DSL. Do not edit by hand.",
        "",
    ]
    for rule in rules:
        bodies = _rego_bodies(ast.parse(rule.predicate, mode="eval").body)
        name = _rule_name(rule.id)
        for body in bodies:
            lines.append(f"{name} if {{")
            for expr in body:
                lines.append(f"  {expr}")
            lines.extend(["}", ""])
        lines.extend(
            [
                f"hit contains {_json(rule.id)} if {{",
                f"  {name}",
                "}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def context_to_input(ctx: GateContext) -> dict[str, object]:
    return {
        "tool": ctx.tool_name,
        "args": ctx.arguments,
        "role": ctx.user_role,
        "taint": ctx.taint.value,
        "risk": ctx.risk_level.value,
        "sources": [source.value for source in ctx.input_sources],
    }


@dataclass
class RegoPolicyEngine:
    rules: list[PolicyRule]
    opa_path: str | None = None
    package: str = "xa_guard.gate3"

    def __post_init__(self) -> None:
        if self.opa_path:
            configured = Path(self.opa_path)
            if not configured.exists():
                self.opa_path = shutil.which(self.opa_path) or self.opa_path
        else:
            self.opa_path = shutil.which("opa") or _local_opa_path()
        self.module = build_rego_module(self.rules, self.package)
        self._fallback: dict[str, Callable[[GateContext], bool]] = {
            rule.id: compile_predicate(rule.predicate) for rule in self.rules
        }

    @property
    def opa_available(self) -> bool:
        return bool(self.opa_path and Path(self.opa_path).exists())

    @property
    def mode(self) -> str:
        return "opa_cli" if self.opa_available else "python_fallback"

    def evaluate_hits(self, ctx: GateContext) -> list[str]:
        if self.opa_available:
            return self._evaluate_opa(ctx)
        hits: list[str] = []
        for rule in self.rules:
            try:
                if self._fallback[rule.id](ctx):
                    hits.append(rule.id)
            except Exception:
                continue
        return hits

    def _evaluate_opa(self, ctx: GateContext) -> list[str]:
        with tempfile.TemporaryDirectory(prefix="xa_guard_rego_") as tmp:
            tmpdir = Path(tmp)
            policy_path = tmpdir / "gate3.rego"
            input_path = tmpdir / "input.json"
            policy_path.write_text(self.module, encoding="utf-8")
            input_path.write_text(json.dumps(context_to_input(ctx), ensure_ascii=False), encoding="utf-8")
            query = f"data.{self.package}.hit"
            proc = subprocess.run(
                [
                    str(self.opa_path),
                    "eval",
                    "--format",
                    "json",
                    "--data",
                    policy_path.name,
                    "--input",
                    input_path.name,
                    query,
                ],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                cwd=str(tmpdir),
            )
        payload = json.loads(proc.stdout or "{}")
        result = payload.get("result") or []
        if not result:
            return []
        value = result[0].get("expressions", [{}])[0].get("value", [])
        return [str(item) for item in value]
