"""Qwen3Guard model backend for Gate 1.

The backend is intentionally dependency-light at import time. It only imports
``transformers`` inside ``load()`` so the rest of XA-Guard can compile and start
on machines without model dependencies or weights.

Qwen3Guard-Gen is a generative classifier. The official model card uses
``AutoModelForCausalLM`` and parses generated text such as:

    Safety: Unsafe
    Categories: Jailbreak
"""
from __future__ import annotations

import re
from typing import Any, Sequence

from xa_guard.detectors.base import DetectionLabel, ModelBackend


DEFAULT_CATEGORY_MAP: dict[str, str] = {
    "Violent": "shell_dangerous",
    "Non-violent Illegal Acts": "shell_dangerous",
    "Sexual Content or Sexual Acts": "unsafe",
    "Personally Identifiable Information": "pii_leak",
    "PII": "pii_leak",
    "Suicide & Self-Harm": "unsafe",
    "Unethical Acts": "unsafe",
    "Politically Sensitive Topics": "political_sensitive",
    "Copyright Violation": "unsafe",
    "Jailbreak": "jailbreak_zh",
    "jailbreak": "jailbreak_zh",
    "prompt_injection": "indirect_injection",
    "indirect_injection": "indirect_injection",
    "political_sensitive": "political_sensitive",
    "privacy_violation": "privacy_leak",
    "personal_information": "pii_leak",
    "system_prompt_leakage": "system_leak",
    "system_leak": "system_leak",
    "dangerous_content": "shell_dangerous",
    "dangerous_command": "shell_dangerous",
    "sql_injection": "sql_injection",
}


DRY_RUN_KEYWORDS: dict[str, str] = {
    "ignore previous instructions": "jailbreak_en",
    "忘掉前面的指令": "jailbreak_zh",
    "开发者模式": "jailbreak_zh",
    "system prompt": "system_leak",
    "系统提示": "system_leak",
    "rm -rf": "shell_dangerous",
    "mkfs": "shell_dangerous",
    "drop table": "sql_injection",
    "union select": "sql_injection",
    "[system_instruction]": "indirect_injection",
    "admin_override": "indirect_injection",
    "/etc/passwd": "pii_leak",
    "id_rsa": "pii_leak",
}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class Qwen3GuardBackend(ModelBackend):
    """Qwen3Guard-Gen backend with real-model and explicit dry-run modes.

    Options:
        model_path: HuggingFace/ModelScope id or local path.
        device: ``cpu`` by default. ``auto`` delegates to accelerate device_map.
        torch_dtype: ``float32`` on CPU by default, ``auto`` otherwise.
        max_new_tokens: generation budget for the safety verdict.
        threshold: minimum native probability/score emitted as a label.
        category_map: native category -> unified XA-Guard category.
        dry_run: if true, skip model loading and use deterministic keyword
            labels. This is for CI and wiring checks only.
    """

    name: str = "qwen3guard"

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        super().__init__(options)
        self._model: Any | None = None
        self._tokenizer: Any | None = None
        self._load_error: str | None = None
        self._loaded = False
        self._dry_run = bool(self.options.get("dry_run", False))
        self._model_path: str = str(
            self.options.get("model_path")
            or self.options.get("model")
            or "Qwen/Qwen3Guard-Gen-0.6B"
        )
        self._device: str = str(self.options.get("device", "cpu"))
        self._torch_dtype: str = str(self.options.get("torch_dtype", "float32" if self._device == "cpu" else "auto"))
        self._max_new_tokens: int = int(self.options.get("max_new_tokens", 64))
        self._threshold: float = _to_float(self.options.get("threshold"), 0.5)
        self._controversial_score: float = _to_float(self.options.get("controversial_score"), 0.4)
        self._category_map: dict[str, str] = {
            **DEFAULT_CATEGORY_MAP,
            **dict(self.options.get("category_map", {}) or {}),
        }

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def load(self) -> None:
        """Load the model lazily.

        Missing optional dependencies or weights are surfaced as
        ``RuntimeError``. ``ModelDetector`` catches this and marks the detector
        unavailable, preserving the current rule-only fallback behavior.
        """
        if self._dry_run:
            self._loaded = True
            self._load_error = None
            return
        if self._model is not None and self._tokenizer is not None:
            return

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on env
            self._load_error = str(exc)
            raise RuntimeError(
                "Qwen3GuardBackend requires optional dependencies: "
                "install xa-guard[model] or transformers/torch."
            ) from exc

        try:
            self._tokenizer = AutoTokenizer.from_pretrained(self._model_path)
            dtype = self._resolve_torch_dtype(torch)
            kwargs: dict[str, Any] = {"torch_dtype": dtype, "low_cpu_mem_usage": True}
            if self._device == "auto":
                kwargs["device_map"] = "auto"
            self._model = AutoModelForCausalLM.from_pretrained(self._model_path, **kwargs)
            if self._device != "auto":
                self._model.to(self._device)
            self._model.eval()
            self._loaded = True
            self._load_error = None
        except Exception as exc:  # pragma: no cover - depends on env/model
            self._load_error = str(exc)
            raise RuntimeError(f"failed to load Qwen3Guard model {self._model_path!r}: {exc}") from exc

    def is_ready(self) -> bool:
        if self._dry_run:
            return self._loaded
        return self._model is not None and self._tokenizer is not None

    def classify(
        self,
        texts: Sequence[str],
        categories: Sequence[str] | None = None,
    ) -> list[list[DetectionLabel]]:
        if not self.is_ready():
            return [[] for _ in texts]
        if self._dry_run:
            return [self._classify_dry_run(text, categories) for text in texts]
        return [self._classify_with_generation(text, categories) for text in texts]

    def unload(self) -> None:
        self._model = None
        self._tokenizer = None
        self._loaded = False

    def _resolve_torch_dtype(self, torch: Any) -> Any:
        if self._torch_dtype == "auto":
            return "auto"
        dtype = getattr(torch, self._torch_dtype, None)
        if dtype is None:
            return torch.float32
        return dtype

    def _classify_dry_run(
        self,
        text: str,
        categories: Sequence[str] | None,
    ) -> list[DetectionLabel]:
        lowered = text.lower()
        labels: list[DetectionLabel] = []
        for keyword, category in DRY_RUN_KEYWORDS.items():
            if keyword.lower() not in lowered:
                continue
            if categories is not None and category not in categories:
                continue
            labels.append(
                DetectionLabel(
                    category=category,
                    score=max(self._threshold, 0.9),
                    detector=self.name,
                    term=keyword,
                    origin="",
                    meta={"mode": "dry_run", "model_path": self._model_path},
                )
            )
        return labels

    def _classify_with_generation(
        self,
        text: str,
        categories: Sequence[str] | None,
    ) -> list[DetectionLabel]:
        if self._model is None or self._tokenizer is None:
            return []
        try:
            messages = [{"role": "user", "content": text}]
            prompt = self._tokenizer.apply_chat_template(messages, tokenize=False)
            model_inputs = self._tokenizer([prompt], return_tensors="pt").to(self._model.device)
            generated_ids = self._model.generate(
                **model_inputs,
                max_new_tokens=self._max_new_tokens,
                do_sample=False,
            )
            output_ids = generated_ids[0][len(model_inputs.input_ids[0]):].tolist()
            content = self._tokenizer.decode(output_ids, skip_special_tokens=True)
        except Exception as exc:  # pragma: no cover - depends on model runtime
            self._load_error = str(exc)
            return []

        severity, raw_categories = self._extract_label_and_categories(content)
        if severity in {None, "Safe"}:
            return []

        severity_score = 1.0 if severity == "Unsafe" else self._controversial_score
        labels: list[DetectionLabel] = []
        for native in raw_categories or [severity]:
            if native == "None":
                continue
            unified = self._category_map.get(native, self._category_map.get(native.lower(), native))
            if categories is not None and unified not in categories:
                continue
            if severity_score < self._threshold:
                continue
            labels.append(
                DetectionLabel(
                    category=unified,
                    score=severity_score,
                    detector=self.name,
                    term="",
                    origin="",
                    meta={
                        "native_category": native,
                        "safety": severity,
                        "raw_output": content,
                        "model_path": self._model_path,
                    },
                )
            )
        return labels

    def _extract_label_and_categories(self, content: str) -> tuple[str | None, list[str]]:
        safe_match = re.search(r"Safety:\s*(Safe|Unsafe|Controversial)", content, flags=re.IGNORECASE)
        label = safe_match.group(1).title() if safe_match else None
        category_pattern = (
            r"Violent|Non-violent Illegal Acts|Sexual Content or Sexual Acts|"
            r"Personally Identifiable Information|PII|Suicide & Self-Harm|"
            r"Unethical Acts|Politically Sensitive Topics|Copyright Violation|Jailbreak|None"
        )
        raw_categories = re.findall(category_pattern, content, flags=re.IGNORECASE)
        canonical: list[str] = []
        for cat in raw_categories:
            for known in DEFAULT_CATEGORY_MAP:
                if cat.lower() == known.lower():
                    canonical.append(known)
                    break
            else:
                canonical.append(cat)
        return label, canonical
