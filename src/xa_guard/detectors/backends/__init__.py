"""后端注册表 —— 所有 ModelBackend 实现在此注册，ModelDetector 通过名字获取实例。

注册流程：
    @register_backend("my_model")
    class MyBackend(ModelBackend): ...

工厂函数：
    backend = get_backend("my_model", options={"device": "cpu"})

占位类（placeholder）：
    构造可成功（轻量），is_ready() 永远 False，load() 抛 NotImplementedError 并附说明。
    等真实模型接入时替换即可，调用方零改动。
"""
from __future__ import annotations

from typing import Any, Type

from xa_guard.detectors.base import ModelBackend

# ── 注册表：name -> class ──────────────────────────────────────────────────────
_REGISTRY: dict[str, Type[ModelBackend]] = {}


def register_backend(name: str):
    """装饰器：将 ModelBackend 子类以 name 注册到全局注册表。"""
    def decorator(cls: Type[ModelBackend]) -> Type[ModelBackend]:
        _REGISTRY[name] = cls
        return cls
    return decorator


def get_backend(name: str, options: dict[str, Any] | None = None) -> ModelBackend:
    """工厂函数：按名字从注册表实例化后端。

    未知名字时抛 KeyError，消息里列出所有已注册名字，方便排查配置错误。
    """
    if name not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY.keys())) or "(empty)"
        raise KeyError(
            f"未知后端名称 {name!r}。已注册的后端：{known}"
        )
    return _REGISTRY[name](options or {})


def list_backends() -> list[str]:
    """返回所有已注册后端名字（按字母序）。"""
    return sorted(_REGISTRY.keys())


# ── 内置：stub ────────────────────────────────────────────────────────────────
from xa_guard.detectors.backends.stub import StubBackend  # noqa: E402
from xa_guard.detectors.backends.qwen3guard import Qwen3GuardBackend  # noqa: E402
from xa_guard.detectors.backends.promptguard import PromptGuardBackend  # noqa: E402
from xa_guard.detectors.backends.shieldlm import ShieldLMBackend  # noqa: E402
from xa_guard.detectors.backends.llamaguard import LlamaGuardBackend  # noqa: E402

register_backend("stub")(StubBackend)
register_backend("qwen3guard")(Qwen3GuardBackend)
register_backend("promptguard")(PromptGuardBackend)
register_backend("shieldlm")(ShieldLMBackend)
register_backend("llamaguard")(LlamaGuardBackend)
