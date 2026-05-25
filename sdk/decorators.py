"""@protect 装饰器 — 给 LangChain agent 包安全壳。

用法：
    from xa_guard_sdk import protect

    @protect(policy="enterprise-l3")
    def my_agent(query: str) -> str:
        ...

子 agent 实施职责（M2+）：
- 装饰器内部构造 mini-pipeline（gate1 + gate3 + gate6）
- 用 langchain CallbackHandler 接住 tool 调用
"""
from __future__ import annotations

from functools import wraps


def protect(policy: str = "enterprise-l3"):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # TODO(agent-SDK): mini-pipeline
            return fn(*args, **kwargs)

        return wrapper

    return deco
