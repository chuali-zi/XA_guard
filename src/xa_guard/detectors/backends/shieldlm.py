"""ShieldLM generative safety backend.

ShieldLM-14B-qwen is too large for many developer laptops, but the backend is
fully wired for environments that can load the weights or serve a smaller
compatible checkpoint.
"""
from __future__ import annotations

import re
from typing import Any, Sequence

from xa_guard.detectors.base import DetectionLabel, ModelBackend


DEFAULT_PROMPT_TEMPLATE = """You are ShieldLM, a bilingual safety detector.
Classify the user's content as exactly one of: safe, unsafe, controversial.
Return a short explanation.

User content:
{text}

Answer format:
Label: <safe|unsafe|controversial>
Explanation: <reason>
"""


class ShieldLMBackend(ModelBackend):
    """Real ShieldLM-style generative backend."""

    name: str = "shieldlm"

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        super().__init__(options)
        self._model: Any | None = None
        self._tokenizer: Any | None = None
        self._load_error: str | None = None
        self._model_path = str(self.options.get("model_path") or self.options.get("model") or "thu-coai/ShieldLM-14B-qwen")
        self._device = str(self.options.get("device", "cpu"))
        self._torch_dtype = str(self.options.get("torch_dtype", "float32" if self._device == "cpu" else "auto"))
        self._max_new_tokens = int(self.options.get("max_new_tokens", 128))
        self._prompt_template = str(self.options.get("prompt_template") or DEFAULT_PROMPT_TEMPLATE)

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def load(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
        except Exception as exc:  # pragma: no cover
            self._load_error = str(exc)
            raise RuntimeError("ShieldLMBackend requires transformers/torch.") from exc
        try:
            self._tokenizer = AutoTokenizer.from_pretrained(self._model_path, trust_remote_code=True)
            dtype = "auto" if self._torch_dtype == "auto" else getattr(torch, self._torch_dtype, torch.float32)
            kwargs: dict[str, Any] = {
                "torch_dtype": dtype,
                "trust_remote_code": True,
                "low_cpu_mem_usage": True,
            }
            if self._device == "auto":
                kwargs["device_map"] = "auto"
            self._model = AutoModelForCausalLM.from_pretrained(self._model_path, **kwargs)
            if self._device != "auto":
                self._model.to(self._device)
            self._model.eval()
            self._load_error = None
        except Exception as exc:  # pragma: no cover - resource dependent
            self._load_error = str(exc)
            raise RuntimeError(f"failed to load ShieldLM model {self._model_path!r}: {exc}") from exc

    def is_ready(self) -> bool:
        return self._model is not None and self._tokenizer is not None

    def classify(self, texts: Sequence[str], categories: Sequence[str] | None = None) -> list[list[DetectionLabel]]:
        if not self.is_ready():
            return [[] for _ in texts]
        return [self._classify_one(text, categories) for text in texts]

    def unload(self) -> None:
        self._model = None
        self._tokenizer = None

    def _classify_one(self, text: str, categories: Sequence[str] | None) -> list[DetectionLabel]:
        if self._model is None or self._tokenizer is None:
            return []
        try:
            prompt = self._prompt_template.format(text=text)
            model_inputs = self._tokenizer([prompt], return_tensors="pt").to(self._model.device)
            generated_ids = self._model.generate(**model_inputs, max_new_tokens=self._max_new_tokens, do_sample=False)
            output_ids = generated_ids[0][len(model_inputs.input_ids[0]):].tolist()
            content = self._tokenizer.decode(output_ids, skip_special_tokens=True)
        except Exception as exc:  # pragma: no cover
            self._load_error = str(exc)
            return []

        label, explanation = self._parse_output(content)
        if label == "safe":
            return []
        category = "unsafe" if label == "unsafe" else "controversial"
        score = 1.0 if label == "unsafe" else 0.45
        if categories is not None and category not in categories:
            return []
        return [
            DetectionLabel(
                category=category,
                score=score,
                detector=self.name,
                origin="",
                meta={"label": label, "explanation": explanation, "raw_output": content, "model_path": self._model_path},
            )
        ]

    def _parse_output(self, content: str) -> tuple[str, str]:
        match = re.search(r"\b(safe|unsafe|controversial)\b", content, flags=re.IGNORECASE)
        label = match.group(1).lower() if match else "controversial"
        explanation = content.strip()
        return label, explanation
