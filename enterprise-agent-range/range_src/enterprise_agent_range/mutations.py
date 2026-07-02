from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_MUTATIONS = ("zero_width", "case_flip", "line_split", "language_hint")


def mutate_text(text: str, mutation: str) -> str:
    if mutation == "zero_width":
        return "\u200b".join(text)
    if mutation == "case_flip":
        return "".join(char.upper() if index % 2 else char.lower() for index, char in enumerate(text))
    if mutation == "line_split":
        words = text.split()
        if len(words) <= 1:
            return text
        midpoint = len(words) // 2
        return " ".join(words[:midpoint]) + "\n" + " ".join(words[midpoint:])
    if mutation == "language_hint":
        return f"[Synthetic bilingual paraphrase requested]\n{text}"
    raise ValueError(f"unsupported mutation: {mutation}")


def mutated_case_variants(case: dict[str, Any], mutations: list[str] | tuple[str, ...] = DEFAULT_MUTATIONS) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    task = str(case.get("input", {}).get("task", ""))
    for mutation in mutations:
        variant = deepcopy(case)
        variant["case_id"] = f"{case.get('case_id')}-M-{mutation.replace('_', '-').upper()}"
        variant["title"] = f"{case.get('title', 'case')} [{mutation}]"
        variant.setdefault("input", {})["task"] = mutate_text(task, mutation)
        variant["mutation"] = {
            "source_case_id": case.get("case_id"),
            "operator": mutation,
            "deterministic": True,
        }
        variants.append(variant)
    return variants
