"""Policy YAML 加载器。

子 agent 实施职责：
- 读 policies/*.yaml → list[PolicyRule]
- 校验字段完整性（id, source, triggers, predicate, enforce 必填）
- 重复 id 抛错
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from xa_guard.types import Decision, PolicyRule


def load_policy_yaml(path: str | Path) -> list[PolicyRule]:
    """从 YAML 文件读取规则列表。"""
    with open(path, encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}
    rules_raw = raw.get("rules", [])
    rules: list[PolicyRule] = []
    seen: set[str] = set()
    for item in rules_raw:
        rid = item["id"]
        if rid in seen:
            raise ValueError(f"duplicate rule id: {rid}")
        seen.add(rid)
        rules.append(
            PolicyRule(
                id=rid,
                name=item["name"],
                source=item.get("source", ""),
                triggers=list(item.get("triggers", [])),
                predicate=item["predicate"],
                enforce=Decision(item["enforce"]),
                severity=item.get("severity", "medium"),
                audit=item.get("audit", "required"),
                description=item.get("description", ""),
            )
        )
    return rules
