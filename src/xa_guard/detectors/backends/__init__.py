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

register_backend("stub")(StubBackend)


# ── 占位类（placeholder）：真实模型留空插槽 ────────────────────────────────────

@register_backend("qwen3guard")
class Qwen3GuardBackend(ModelBackend):
    """占位：Qwen3-Guard 护栏模型后端。

    接入方式：
        1. 安装依赖：pip install transformers torch accelerate
        2. 下载权重：modelscope download Qwen/Qwen3-Guard 或 HF 镜像
        3. 在 load() 中加载 AutoModelForSequenceClassification / pipeline
        4. classify() 调用 model(**tokenizer(texts, ...)) 取 logits
        5. 参考：https://huggingface.co/Qwen/Qwen3-Guard （微调文档见 README）
    """

    name: str = "qwen3guard"

    def load(self) -> None:
        raise NotImplementedError(
            "Qwen3GuardBackend 尚未接入真实权重。"
            "接入步骤：安装 transformers/torch，下载 Qwen/Qwen3-Guard 权重，"
            "在 load() 中初始化 AutoModelForSequenceClassification。"
        )

    def is_ready(self) -> bool:
        # 未加载时永远 False，ModelDetector 会 fail-open 跳过
        return False

    def classify(self, texts, categories=None):
        # is_ready()=False 时 ModelDetector 不会调用 classify；此处仍返回全空保持健壮性
        return [[] for _ in texts]


@register_backend("shieldlm")
class ShieldLMBackend(ModelBackend):
    """占位：ShieldLM 内容安全分类模型后端。

    接入方式：
        1. 安装依赖：pip install transformers torch
        2. 下载权重：modelscope download thu-coai/ShieldLM-7B-internlm2
        3. 在 load() 中加载 AutoModelForCausalLM（ShieldLM 使用生成式框架）
        4. classify() 构造 ShieldLM prompt，解析 safe/unsafe 判断及原因
        5. 参考：https://github.com/thu-coai/ShieldLM （微调文档见 train/README）
    """

    name: str = "shieldlm"

    def load(self) -> None:
        raise NotImplementedError(
            "ShieldLMBackend 尚未接入真实权重。"
            "接入步骤：安装 transformers/torch，下载 thu-coai/ShieldLM-7B 权重，"
            "在 load() 中初始化 AutoModelForCausalLM 并配置 ShieldLM prompt 模板。"
        )

    def is_ready(self) -> bool:
        return False

    def classify(self, texts, categories=None):
        return [[] for _ in texts]


@register_backend("promptguard")
class PromptGuardBackend(ModelBackend):
    """占位：Meta PromptGuard 提示注入检测模型后端。

    接入方式：
        1. 安装依赖：pip install transformers torch
        2. 下载权重：huggingface-cli download meta-llama/Prompt-Guard-86M
        3. 在 load() 中加载 AutoModelForSequenceClassification（BERT 架构）
        4. classify() 输出 INJECTION / JAILBREAK / BENIGN 三类 logits
        5. 参考：https://huggingface.co/meta-llama/Prompt-Guard-86M
    """

    name: str = "promptguard"

    def load(self) -> None:
        raise NotImplementedError(
            "PromptGuardBackend 尚未接入真实权重。"
            "接入步骤：安装 transformers/torch，下载 meta-llama/Prompt-Guard-86M，"
            "在 load() 中初始化 AutoModelForSequenceClassification（BERT 分类头）。"
        )

    def is_ready(self) -> bool:
        return False

    def classify(self, texts, categories=None):
        return [[] for _ in texts]


@register_backend("llamaguard")
class LlamaGuardBackend(ModelBackend):
    """占位：Llama Guard 内容安全模型后端。

    接入方式：
        1. 安装依赖：pip install transformers torch accelerate
        2. 下载权重：huggingface-cli download meta-llama/Llama-Guard-3-8B
        3. 在 load() 中加载 AutoModelForCausalLM（生成式，输出 safe/unsafe + 违规类目）
        4. classify() 构造 Llama Guard 对话格式 prompt，解析输出类目
        5. 参考：https://huggingface.co/meta-llama/Llama-Guard-3-8B （微调见 mlc-llm docs）
    """

    name: str = "llamaguard"

    def load(self) -> None:
        raise NotImplementedError(
            "LlamaGuardBackend 尚未接入真实权重。"
            "接入步骤：安装 transformers/torch/accelerate，下载 meta-llama/Llama-Guard-3-8B，"
            "在 load() 中初始化 AutoModelForCausalLM 并配置对话格式 prompt 模板。"
        )

    def is_ready(self) -> bool:
        return False

    def classify(self, texts, categories=None):
        return [[] for _ in texts]
