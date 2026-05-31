"""Meta PromptGuard / Llama Prompt Guard backend.

PromptGuard 2 is a sequence-classification model. The public model cards are
gated, so this backend preserves fail-open semantics when no HF token/access is
available while still using the real classifier path when weights are present.
"""
from __future__ import annotations

from typing import Any, Sequence

from xa_guard.detectors.base import DetectionLabel, ModelBackend


DEFAULT_LABEL_MAP: dict[str, str] = {
    "INJECTION": "indirect_injection",
    "PROMPT_INJECTION": "indirect_injection",
    "JAILBREAK": "jailbreak_en",
    "BENIGN": "",
    "LABEL_0": "",
    "LABEL_1": "indirect_injection",
    "LABEL_2": "jailbreak_en",
}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class PromptGuardBackend(ModelBackend):
    """Real PromptGuard sequence-classification backend."""

    name: str = "promptguard"

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        super().__init__(options)
        self._model: Any | None = None
        self._tokenizer: Any | None = None
        self._load_error: str | None = None
        self._model_path = str(
            self.options.get("model_path")
            or self.options.get("model")
            or "meta-llama/Llama-Prompt-Guard-2-86M"
        )
        self._device = str(self.options.get("device", "cpu"))
        self._threshold = _to_float(self.options.get("threshold"), 0.5)
        self._max_length = int(self.options.get("max_length", 512))
        self._label_map: dict[str, str] = {
            **DEFAULT_LABEL_MAP,
            **dict(self.options.get("category_map", {}) or {}),
        }

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def load(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer  # type: ignore
        except Exception as exc:  # pragma: no cover - env dependent
            self._load_error = str(exc)
            raise RuntimeError("PromptGuardBackend requires transformers/torch.") from exc

        try:
            self._tokenizer = AutoTokenizer.from_pretrained(self._model_path)
            self._model = AutoModelForSequenceClassification.from_pretrained(self._model_path)
            self._model.to(self._device)
            self._model.eval()
            self._torch = torch
            self._load_error = None
        except Exception as exc:  # pragma: no cover - network/gated/model dependent
            self._load_error = str(exc)
            raise RuntimeError(f"failed to load PromptGuard model {self._model_path!r}: {exc}") from exc

    def is_ready(self) -> bool:
        return self._model is not None and self._tokenizer is not None

    def classify(
        self,
        texts: Sequence[str],
        categories: Sequence[str] | None = None,
    ) -> list[list[DetectionLabel]]:
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
            torch = self._torch
            inputs = self._tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=self._max_length,
            ).to(self._model.device)
            with torch.no_grad():
                logits = self._model(**inputs).logits[0]
                probs = torch.softmax(logits, dim=-1).detach().cpu().tolist()
        except Exception as exc:  # pragma: no cover - runtime dependent
            self._load_error = str(exc)
            return []

        id2label = getattr(self._model.config, "id2label", {}) or {}
        labels: list[DetectionLabel] = []
        for idx, score in enumerate(probs):
            native = str(id2label.get(idx, f"LABEL_{idx}")).upper()
            unified = self._label_map.get(native, self._label_map.get(native.lower(), native.lower()))
            if not unified:
                continue
            if score < self._threshold:
                continue
            if categories is not None and unified not in categories:
                continue
            labels.append(
                DetectionLabel(
                    category=unified,
                    score=float(score),
                    detector=self.name,
                    origin="",
                    meta={
                        "native_category": native,
                        "model_path": self._model_path,
                        "probabilities": {str(id2label.get(i, f"LABEL_{i}")): float(p) for i, p in enumerate(probs)},
                    },
                )
            )
        return labels
