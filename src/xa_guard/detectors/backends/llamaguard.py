"""Llama Guard 3 generative safety backend."""
from __future__ import annotations

import re
from typing import Any, Sequence

from xa_guard.detectors.base import DetectionLabel, ModelBackend


DEFAULT_CATEGORY_MAP: dict[str, str] = {
    "S1": "unsafe",
    "S2": "unsafe",
    "S3": "unsafe",
    "S4": "unsafe",
    "S5": "unsafe",
    "S6": "unsafe",
    "S7": "unsafe",
    "S8": "unsafe",
    "S9": "unsafe",
    "S10": "unsafe",
    "S11": "unsafe",
    "S12": "unsafe",
    "S13": "unsafe",
    "S14": "unsafe",
}


class LlamaGuardBackend(ModelBackend):
    """Real Llama Guard backend when gated weights are available."""

    name: str = "llamaguard"

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        super().__init__(options)
        self._model: Any | None = None
        self._tokenizer: Any | None = None
        self._load_error: str | None = None
        self._model_path = str(self.options.get("model_path") or self.options.get("model") or "meta-llama/Llama-Guard-3-1B")
        self._device = str(self.options.get("device", "cpu"))
        self._torch_dtype = str(self.options.get("torch_dtype", "float32" if self._device == "cpu" else "auto"))
        self._max_new_tokens = int(self.options.get("max_new_tokens", 64))
        self._category_map = {**DEFAULT_CATEGORY_MAP, **dict(self.options.get("category_map", {}) or {})}

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
            raise RuntimeError("LlamaGuardBackend requires transformers/torch.") from exc
        try:
            self._tokenizer = AutoTokenizer.from_pretrained(self._model_path)
            dtype = "auto" if self._torch_dtype == "auto" else getattr(torch, self._torch_dtype, torch.float32)
            kwargs: dict[str, Any] = {"torch_dtype": dtype, "low_cpu_mem_usage": True}
            if self._device == "auto":
                kwargs["device_map"] = "auto"
            self._model = AutoModelForCausalLM.from_pretrained(self._model_path, **kwargs)
            if self._device != "auto":
                self._model.to(self._device)
            self._model.eval()
            self._load_error = None
        except Exception as exc:  # pragma: no cover - gated/resource dependent
            self._load_error = str(exc)
            raise RuntimeError(f"failed to load Llama Guard model {self._model_path!r}: {exc}") from exc

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
            messages = [{"role": "user", "content": text}]
            prompt = self._tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            model_inputs = self._tokenizer([prompt], return_tensors="pt").to(self._model.device)
            generated_ids = self._model.generate(**model_inputs, max_new_tokens=self._max_new_tokens, do_sample=False)
            output_ids = generated_ids[0][len(model_inputs.input_ids[0]):].tolist()
            content = self._tokenizer.decode(output_ids, skip_special_tokens=True)
        except Exception as exc:  # pragma: no cover
            self._load_error = str(exc)
            return []

        lowered = content.lower()
        if lowered.startswith("safe"):
            return []
        native_categories = re.findall(r"S\d{1,2}", content)
        labels: list[DetectionLabel] = []
        for native in native_categories or ["unsafe"]:
            unified = self._category_map.get(native, "unsafe")
            if categories is not None and unified not in categories:
                continue
            labels.append(
                DetectionLabel(
                    category=unified,
                    score=1.0,
                    detector=self.name,
                    origin="",
                    meta={"native_category": native, "raw_output": content, "model_path": self._model_path},
                )
            )
        return labels
