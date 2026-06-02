"""Policy DSL：YAML → 可执行 predicate。

模块划分：
- loader / compiler           — 旧单文件路径（向后兼容，Gate3 默认仍可用）
- layered.LayeredPolicySource — 双层（baseline + overlay）+ 单调性 + bundle_sha
- monotonicity                — overlay 不得弱化 baseline 的红线校验
- predicate_safe              — overlay predicate 走 AST 白名单（evalidate 优先）
- hot_reload.OverlayWatcher   — watchfiles 监听 overlay 目录，自动 reload
"""

from xa_guard.policy.layered import (
    LayeredPolicySource,
    get_global_source,
    set_global_source,
)
from xa_guard.policy.monotonicity import PolicyViolationError

__all__ = [
    "LayeredPolicySource",
    "get_global_source",
    "set_global_source",
    "PolicyViolationError",
]
