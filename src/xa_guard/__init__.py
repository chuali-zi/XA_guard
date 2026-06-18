"""XA-Guard MCP Server — 政企智能体安全防护层。

赛题编号：XA-202620（雄安集团数字城市科技有限公司）
当前阶段：L2 工程完成，L3 政企原型推进中。

公共入口：
- xa_guard.server.run_server      启动 MCP server
- xa_guard.pipeline.Pipeline       6 关卡编排
- xa_guard.types                    共享数据结构（Gate*, Decision, TaintLabel ...）
- xa_guard.config                   YAML 配置加载
- xa_guard.protect                  SDK 装饰器（非 MCP / LangChain 场景）
"""

from xa_guard.sdk import XAGuardBlocked, protect
from xa_guard.version import __version__

__all__ = ["__version__", "XAGuardBlocked", "protect"]
