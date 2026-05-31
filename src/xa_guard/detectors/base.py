"""检测框架统一契约 —— 子 agent 之间的接口边界。

四个核心抽象：
- DetectionInput  : 喂给检测器的归一化输入（文本 + 来源 + 上下文）。
- DetectionLabel  : 一条命中标签（类目 + 置信度 + 出处）。
- DetectionResult : 单个检测器的产出（一组 label + 可用性 + 元数据）。
- Detector        : 检测器抽象基类（RuleDetector / ModelDetector 实现它）。
- ModelBackend    : ★通用模型壳子★。任何护栏/分类模型实现此接口即可被 ModelDetector 调用。

设计原则：
1. Detector / ModelBackend 不 import gate1/pipeline，避免环依赖；GateContext 仅在
   TYPE_CHECKING 下引用。
2. ModelBackend 支持 **惰性加载**（load/is_ready/unload），所以"没拉真实模型"时
   stub 后端 is_ready()=False，ModelDetector fail-open 跳过，不阻塞 pipeline。
3. classify 批量接口，便于未来 batch 推理；返回与输入等长的 label 列表。
4. 所有"分数"统一 0..1，语义为"该类目命中的置信度/严重度"，由 fusion 统一解释。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Sequence

if TYPE_CHECKING:  # 仅类型检查期引用，运行时不耦合
    from xa_guard.types import GateContext, InputSource


# ============================================================
# 1. 归一化输入
# ============================================================
@dataclass
class DetectionInput:
    """喂给检测器的归一化输入。

    Gate1 把 GateContext（tool_name / arguments / session_history / input_sources）
    拍平成若干 segment，每个 segment 标注其来源与角色，便于：
    - Spotlighting：对非 user 来源的 segment 加 <untrusted_source> 包裹。
    - 模型/规则：知道命中发生在 user 输入还是工具结果里（影响判罚降级）。
    """

    text: str = ""                       # 已拼接 / 已 Spotlighting 处理的全文（小写化与否由检测器决定）
    raw_text: str = ""                   # 未经预处理的原文（模型通常喂原文）
    source: "str" = "user"               # 主来源（InputSource.value）；多源时取最不可信的
    origin: str = "tool"                 # 文本片段角色：tool/user/assistant/history/...
    sources: list[str] = field(default_factory=lambda: ["user"])  # 全部来源
    meta: dict[str, Any] = field(default_factory=dict)            # spotlight 标记、片段切分等


# ============================================================
# 2. 单条命中标签
# ============================================================
@dataclass
class DetectionLabel:
    """一条检测命中。

    category : 风险类目，跨检测器统一命名空间。规则类目沿用 dangerous_patterns.yaml
               的 key（shell_dangerous / jailbreak_zh / pii_leak / indirect_injection ...）；
               模型类目用 backend 自己的 taxonomy（如 Qwen3Guard 的 "jailbreak" /
               "political_sensitive"），由配置的 category_map 归一到统一类目。
    score    : 0..1 置信度 / 严重度。规则命中默认 1.0；模型给概率。
    detector : 产出者名（"rule" / "qwen3guard" / "shieldlm" / "stub" / ...）。
    term     : 规则命中的具体词；模型可空。
    origin   : 命中所在片段角色（tool/user/assistant/...），影响 fusion 的判罚降级。
    meta     : 原始模型输出 / 规则上下文等，仅供审计与调试。
    """

    category: str
    score: float = 1.0
    detector: str = ""
    term: str = ""
    origin: str = "tool"
    meta: dict[str, Any] = field(default_factory=dict)


# ============================================================
# 3. 单个检测器产出
# ============================================================
@dataclass
class DetectionResult:
    """单个检测器的完整产出。

    available=False 表示该检测器本次未能给出有效判断（如模型未加载 / 推理超时 /
    后端异常）。fusion 对 available=False 的检测器执行 **fail-open**：不因它的缺席
    而放行，也不因它的缺席而误杀——即忽略其票，由其余检测器决定。
    """

    labels: list[DetectionLabel] = field(default_factory=list)
    detector_name: str = ""
    available: bool = True
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def categories(self) -> list[str]:
        return [lbl.category for lbl in self.labels]

    @property
    def hit(self) -> bool:
        return bool(self.labels)


# ============================================================
# 4. 检测器抽象基类
# ============================================================
class Detector(ABC):
    """检测器统一接口。RuleDetector / ModelDetector 子类化并实现 detect()。

    约束：
    - detect 必须捕获自身内部异常并以 available=False 的 DetectionResult 返回，
      不得向上抛——保证单个检测器故障不拖垮 Gate1。
    - detect 不得 mutate 传入的 DetectionInput / GateContext。
    """

    name: str = "detector"

    @abstractmethod
    def detect(
        self,
        inp: DetectionInput,
        ctx: "GateContext | None" = None,
    ) -> DetectionResult:
        """对归一化输入打标，返回 DetectionResult。"""

    # 可选：检测器初始化/资源加载（ModelDetector 用于触发 backend.load）。
    def warmup(self) -> None:
        return None


# ============================================================
# 5. ★通用模型壳子★
# ============================================================
class ModelBackend(ABC):
    """护栏/分类模型的通用后端契约。

    ★ 这是"模型壳子"的核心抽象。后续接入任何真实模型，只需新增一个实现：
        class Qwen3GuardBackend(ModelBackend): ...
        class ShieldLMBackend(ModelBackend): ...
        class PromptGuardBackend(ModelBackend): ...
      并在 backends 注册表登记名字即可，Gate1 / ModelDetector 零改动。

    生命周期：
        __init__(options)         读配置，**不加载权重**（构造必须轻量、可在无模型环境实例化）
        load()                    真正加载权重 / 起推理进程；可能耗时；幂等
        is_ready() -> bool        权重是否就绪；stub / 未 load / 加载失败时返回 False
        classify(texts, cats)     批量分类（核心方法）
        unload()                  释放资源（可选）

    classify 契约：
        入参 texts      : 待分类文本列表。
        入参 categories : 关心的类目白名单（None=后端返回其全部类目）。
        返回            : 与 texts 等长的列表；第 i 项是 texts[i] 命中的 DetectionLabel 列表（可空）。
                          label.detector 应填后端 name；label.score 为 0..1。
        失败语义        : 若模型不可用，classify 不应抛异常导致 pipeline 崩溃——
                          实现可返回全空（[[ ] for _ in texts]）；ModelDetector 会结合
                          is_ready() 决定 available 标志。
    """

    name: str = "model_backend"

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self.options: dict[str, Any] = options or {}

    @abstractmethod
    def load(self) -> None:
        """加载模型权重 / 建立推理通道。幂等。无真实模型时可为 no-op。"""

    @abstractmethod
    def is_ready(self) -> bool:
        """模型是否就绪可推理。"""

    @abstractmethod
    def classify(
        self,
        texts: Sequence[str],
        categories: Sequence[str] | None = None,
    ) -> list[list[DetectionLabel]]:
        """批量分类。返回与 texts 等长的 label 列表（见类 docstring 契约）。"""

    def unload(self) -> None:
        return None
