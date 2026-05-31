# MCP 零基础上手 · 给团队所有人

> **这份文档的目标**：让团队里**零经验**的组员，在**3 小时内**搞懂 MCP 是什么 + 跑出一个能用的 MCP Server + 接入**国产 AI 工具（Trae / CodeBuddy / 通义灵码等）**实际看到效果。
>
> **配套**：本文是动手指南。`docs/产品架构.md` 是项目设计文档。`docs/references/literature/INDEX.md` 是文献库。

> ⚠ **本文档遵循 [`docs/事实源.md`](../事实源.md) v1.1 作为权威事实源**。上次纠偏：2026-05-24

---

## 目录

1. [MCP 是什么（5 分钟版）](#1-mcp-是什么)
2. [为什么我们项目要学 MCP](#2-为什么我们要学-mcp)
3. [MCP 核心概念（用人话）](#3-mcp-核心概念)
4. [上手第一步：装环境（30 分钟）](#4-上手第一步)
5. [上手第二步：写一个最简 MCP Server（30 分钟）](#5-上手第二步)
6. [上手第三步：接入国产 AI 工具（30 分钟）](#6-上手第三步)
7. [上手第四步：写一个带"安全检查"的 MCP Server（1 小时）](#7-上手第四步)
8. [关键 API 速查](#8-关键-api-速查)
9. [我们项目的 MCP 设计](#9-我们项目的-mcp-设计)
10. [推荐学习资源](#10-推荐学习资源)
11. [FAQ](#11-faq)

---

## 1. MCP 是什么

### 1.1 一句话定义

> **MCP（Model Context Protocol）= LLM 应用的"USB-C 接口"。**

### 1.2 用生活例子讲清楚

想象你买了台新电脑（=ChatGPT 类的 LLM 客户端，如 Trae / CodeBuddy / 通义灵码 / Cursor），你想插各种设备：
- 移动硬盘（=本地文件系统）
- 打印机（=外部服务）
- 网络（=Google 搜索、API）
- 显示器（=数据库视图）

**没有 USB-C 之前**：每种设备一种接口（VGA / HDMI / USB-A / DP / Mini-DP / Thunderbolt / ……），每次买新电脑要换一堆线。

**USB-C 之后**：一种接口走天下，新电脑直接插上就能用。

**MCP 之前**：每个 LLM 应用要自己写代码连每种外部工具——OpenAI 的 plugin、LangChain 的 tool、Cursor 的 extension 都是自己一套。

**MCP 之后**：写一次"MCP Server"，所有 MCP 客户端都能用——国产的 **Trae / CodeBuddy / Qoder CN（原通义灵码 2026-05-20 更名）/ Qoder（阿里 2025-08 独立 IDE） / 智谱清言桌面版**，国际的 Cursor / Claude Desktop / Cline / Continue / Zed 等，全部一份代码搞定。

### 1.3 MCP 出生年月

- **2024 年 11 月**：Anthropic 首次推出 MCP
- **2025 年 1-6 月**：Cursor / Claude Desktop / Cline 等国际主流 LLM 工具支持
- **2025 年下半年**：字节 **Trae**、腾讯云 **CodeBuddy**、阿里 **通义灵码**（2026-05-20 更名 **Qoder CN**）+ 阿里 **Qoder**（独立 Agentic IDE）、智谱 **智谱清言** 等国产 LLM 工具跟进 MCP 支持
- **现在（2026-05）**：MCP 已是业界事实标准之一，**国产 AI 编程工具全面支持**（**MCP 协议当前稳定版 2025-11-25**，主流传输 stdio + Streamable HTTP，SSE 已 deprecated）

---

## 2. 为什么我们要学 MCP

### 2.1 我们的产品形态选择

我们项目的产品形态是 **「XA-Guard MCP Server」**——一个"装在 LLM 客户端和工具之间"的安全代理。详见 [产品架构.md](../产品架构.md)。

```
[国产 AI 工具：Trae / CodeBuddy / 通义灵码 / Qcoder / ...]
[国际 AI 工具：Cursor / Claude Desktop / Cline / ...]
    ↓ MCP 协议（这层是中立的，所有客户端都说一样的协议）
[★ 我们的 XA-Guard MCP Server ★]
    ↓ MCP 协议
[下游工具: filesystem, shell, database, ...]
```

### 2.2 为什么不是别的形态

简单回答：**我们想做"任何人都能用的安全防护"**——而不是"我们的安全 agent"。
- 完整安全 agent → 没人会换框架 → 没人用
- Python SDK → 只覆盖 LangChain 用户
- MCP Server → **覆盖所有用 Trae / CodeBuddy / Qoder CN / Cursor 等 MCP 客户端的开发者和运维**

### 2.3 不学 MCP 行不行

不行。M2-M5 全程都是基于 MCP 开发。不懂 MCP 等于做不了主线工作。

但是别慌——**MCP 比 Docker 简单**。如果你能用 LangChain 写个 chatbot，MCP 你 2 小时就上手。

### 2.4 我们主推国产 AI 工具

**面向政企的产品定位**决定了我们要主推国产：

| 工具 | 厂商 | 我们的优先级 | 备注 |
|---|---|---|---|
| **Trae** | 字节跳动 | ★★★ 推荐 | 类 Cursor 国产代表 / 免费 / MCP 原生支持 / 中文界面 |
| **CodeBuddy** | 腾讯云 | ★★★ 推荐 | 腾讯生态、企业版本对接顺畅 |
| **Qoder CN**（原通义灵码 2026-05-20 更名） | 阿里云 | ★★ 推荐 | 阿里生态、国企/央企已多有采购 |
| **Qoder** | 阿里（2025-08 推出独立 Agentic IDE） | ★★ | 用户/团队点名 |
| **智谱清言桌面版** | 智谱 AI | ★ | 渐进式 MCP 支持 |
| Cursor / Claude Desktop / Cline | 国外 | ◯ 学习参考 | 协议成熟度好，作为参考实现 |

**重点**：MCP 协议本身是中立的，我们写的 MCP Server **同时支持以上所有客户端**——只是不同客户端的"配置文件路径"和"UI 入口"不同。

**新手建议**：M1 阶段（2026-06）大家可以用 **Trae** 学习，原因：
1. **免费**（不像 Cursor 付费版要 20 美元/月）
2. **国产**（与项目"政企落地"叙事一致）
3. **类 Cursor**（UI、操作、MCP 配置高度相似，学完了也能切到 Cursor）
4. **中文支持好**（界面、文档全中文）

---

## 3. MCP 核心概念

### 3.1 三个角色

```
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│              │  调用    │              │  调用    │              │
│  MCP Host    │  ─────▶ │  MCP Server  │  ─────▶ │  外部系统     │
│  (LLM 客户端)  │         │  (你写的代码) │         │  (文件/API)   │
│              │  ◀───── │              │  ◀───── │              │
└──────────────┘  返回    └──────────────┘  返回    └──────────────┘
                  结果                      结果
```

- **MCP Host**：用户用的 LLM 应用（国产的 Trae / CodeBuddy / Qoder CN，或国际的 Cursor / Claude Desktop 等）
- **MCP Server**：你写的代码，提供工具/数据
- **外部系统**：真实的文件系统、API、数据库等

### 3.2 三种"提供物"

一个 MCP Server 可以给客户端提供三种东西：

#### Tools（工具）
**LLM 可调用的函数。**例如：
- `read_file(path)`：读文件内容
- `execute_command(cmd)`：执行 shell 命令
- `search_jira(query)`：搜 Jira 任务

#### Resources（资源）
**LLM 可读取的数据。**例如：
- `file:///docs/manual.pdf`：内部手册
- `db://users/alice`：用户档案

#### Prompts（提示词模板）
**预定义的对话模板。**例如：
- `code_review`：让 LLM 做代码 review 的标准化 prompt
- `incident_response`：故障响应工作流

> **我们项目主要用 Tools**。Resources 和 Prompts 用得少。

### 3.3 通信协议

MCP 用 JSON-RPC 2.0 作为底层消息格式。常见的传输方式：
- **stdio**（标准输入输出）：本地进程间通信，**Trae / CodeBuddy / Cursor / Claude Desktop 等主流客户端都默认这种**
- **Streamable HTTP**：网络传输，生产部署用（旧 HTTP+SSE 已被 MCP spec 标注 deprecated，仅做向后兼容）

> **新手不用管这些细节**，Python `mcp` 库会帮你处理。

---

## 4. 上手第一步：装环境

### 4.1 系统要求

- **Python 3.10+**（推荐 3.11 或 3.12）
- 操作系统：macOS / Linux / Windows（推荐 WSL2）
- 一个 MCP 客户端用于测试（**推荐 Trae**；备选 CodeBuddy / 通义灵码 / Cursor / Claude Desktop 任一个）

### 4.2 装 Python（已装跳过）

```bash
# macOS
brew install python@3.12

# Ubuntu / WSL2
sudo apt install python3.12 python3.12-venv

# Windows
# 去 python.org 下载 3.12 安装包
```

### 4.3 创建项目目录 + 虚拟环境

```bash
mkdir my-mcp-learn
cd my-mcp-learn
python -m venv venv

# 激活虚拟环境
# macOS/Linux:
source venv/bin/activate
# Windows (Git Bash):
source venv/Scripts/activate
```

### 4.4 装 MCP 库

```bash
pip install mcp
```

验证：
```bash
python -c "import mcp; print(mcp.__version__)"
# 应输出版本号，如 1.x.x
```

---

## 5. 上手第二步：写一个最简 MCP Server

### 5.1 目标

写一个能：
- 接受 LLM 的 `echo` 工具调用
- 返回输入字符串的"问候"版本

### 5.2 完整代码

新建文件 `echo_server.py`：

```python
"""
最简 MCP Server 示例
功能：提供一个 echo 工具，返回 "你好，[输入]"
"""
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types


# 创建 server
app = Server("echo-demo")


# 注册一个 tool
@app.list_tools()
async def list_tools() -> list[types.Tool]:
    """告诉 LLM 客户端我们有哪些工具"""
    return [
        types.Tool(
            name="echo",
            description="返回问候语",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "要问候的内容"
                    }
                },
                "required": ["message"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """处理工具调用"""
    if name == "echo":
        message = arguments.get("message", "世界")
        result = f"你好，{message}！"
        return [types.TextContent(type="text", text=result)]
    else:
        raise ValueError(f"未知工具: {name}")


# 启动 server
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
```

### 5.3 测试 server

不需要 LLM 客户端，可以用 MCP Inspector 测：

```bash
# 装 Inspector（一次性）
pip install mcp[cli]

# 跑 Inspector
mcp dev echo_server.py
```

会打开浏览器界面，能看到：
- Tools 列表里有 `echo`
- 可以手动调用 echo，传 `{"message": "项目组"}`
- 返回 `"你好，项目组！"`

**成功的话，恭喜你已经会写 MCP Server 了！**

---

## 6. 上手第三步：接入国产 AI 工具真实体验

> 本节以 **Trae** 为主示例（推荐路径）。其他客户端（CodeBuddy / 通义灵码 / Cursor）配置原理完全一致，差别只在"配置文件路径"和"UI 入口"，文末附其他客户端的等价配置。

### 6.1 主推路径：用 Trae（字节跳动的国产 AI IDE）

#### 6.1.1 装 Trae

到 **https://trae.ai** 下载（中国大陆可访问，无需科学上网）。

支持 macOS / Windows / Linux 全平台。装完后启动，登录字节跳动账号即可。

#### 6.1.2 配置 MCP

Trae 里：
1. 打开**设置**（左下角齿轮 → 或快捷键 `Cmd/Ctrl + ,`）
2. 找到 **MCP** 或 **Model Context Protocol** 项
3. 点 **Add MCP Server** / **添加 MCP 服务器**，或直接编辑配置文件

Trae 的配置文件路径：
- **macOS/Linux**：`~/.trae/mcp.json`
- **Windows**：`%USERPROFILE%\.trae\mcp.json`

配置内容（**所有 MCP 客户端的 JSON 格式是统一的**，标准化由 MCP 协议规定）：

```json
{
  "mcpServers": {
    "my-echo": {
      "command": "/绝对路径/venv/bin/python",
      "args": ["/绝对路径/my-mcp-learn/echo_server.py"]
    }
  }
}
```

> **路径必须是绝对路径**。Windows 注意用 `C:\\Users\\...`（双反斜杠）或 `/c/Users/...`（Git Bash 风格）。

#### 6.1.3 验证接入

1. 重启 Trae
2. 看 MCP 状态指示——应该显示 `my-echo` 已连接（绿色 ✓）
3. 在 Trae 对话框输入：

```
帮我用 my-echo 工具说一声你好
```

4. Trae 会自动调用我们的 echo tool，返回 "你好，[Trae 拟定的参数]！"

**第一次看到 AI 调用你自己写的 MCP tool，感觉很神奇。**

---

### 6.2 备选路径：其他客户端配置

**所有 MCP 客户端的 mcpServers 配置内容是一致的**（这是 MCP 协议标准）。区别只在配置文件位置：

| 客户端 | 配置位置 | 入口 UI |
|---|---|---|
| **Trae** | `~/.trae/mcp.json` | 设置 → MCP |
| **CodeBuddy** | （以最新文档为准，一般是 设置 → MCP） | 设置面板 |
| **Qoder CN**（原通义灵码） | 视版本而定（IDE 插件模式下在 IDE 设置里） | 插件设置 |
| **Qoder** | 设置面板（参考阿里官网文档） | 设置面板 |
| **Cursor** | `~/.cursor/mcp.json` | 设置 → Features → MCP |
| **Claude Desktop** | `~/.config/Claude/claude_desktop_config.json` | 配置文件 |
| **Cline** (VSCode 插件) | VSCode 设置里的 cline.mcp | VSCode Settings |

> **关键**：JSON 内容完全一样，所以你为 Trae 写的 echo server 配置，复制粘贴到 Cursor 也能直接跑。这就是我们项目"协议层产品"的最大杠杆。

### 6.3 如果 Trae 暂时装不上 / 不能用

任何一个 MCP 客户端都行（推荐顺序）：
1. **CodeBuddy**（腾讯云出品，对接腾讯生态）
2. **通义灵码**（阿里云出品，国企央企采购版本）
3. **Cursor**（国际备选，配置最稳）
4. **Claude Desktop**（国际备选，配置略复杂）

后续 M2-M5 的开发，**只要任一 MCP 客户端能跑就够了**——我们的 XA-Guard 是客户端无关的。

---

## 7. 上手第四步：写一个带"安全检查"的 MCP Server

### 7.1 目标

把 echo server 升级——加一个**输入安全检查**：
- 如果输入包含敏感词（如 "rm -rf"），拦截
- 如果是高危操作，请求人工审批
- 所有调用记录到日志

### 7.2 完整代码

新建 `safe_echo_server.py`：

```python
"""
带安全检查的 MCP Server
模拟 XA-Guard MCP Server 的精简版
"""
import asyncio
import json
import datetime
import hashlib
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types


app = Server("safe-echo")


# 简单的"敏感词"清单（实际项目中会用 PromptGuard 模型）
DANGEROUS_PATTERNS = [
    "rm -rf",
    "drop table",
    "delete from",
    "format",
    "shutdown",
    "/etc/passwd",
]


# 简单的"高危操作"清单
HIGH_RISK_TOOLS = ["exec_command", "delete_file"]


# 简单的日志（实际项目中会用国密签名 + 哈希链）
AUDIT_LOG_PATH = Path.home() / "xa_guard_demo.log"


def gate1_input_check(arguments: dict) -> tuple[bool, str]:
    """关卡 1: 门口安检"""
    arg_str = json.dumps(arguments, ensure_ascii=False).lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern in arg_str:
            return False, f"检测到敏感词: {pattern}"
    return True, "OK"


def gate6_audit(event: dict):
    """关卡 6: 黑匣子审计"""
    event["timestamp"] = datetime.datetime.now().isoformat()
    # 简化版：拼上一条日志的哈希做"前向链"
    prev_hash = ""
    if AUDIT_LOG_PATH.exists():
        with open(AUDIT_LOG_PATH, "rb") as f:
            content = f.read()
            if content:
                prev_hash = hashlib.sha256(content).hexdigest()[:16]
    event["prev_hash"] = prev_hash

    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="safe_echo",
            description="带安全检查的问候工具",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"}
                },
                "required": ["message"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    # 关卡 1: 输入安检
    allow, reason = gate1_input_check(arguments)
    if not allow:
        gate6_audit({
            "tool": name,
            "args": arguments,
            "decision": "deny",
            "reason": reason,
        })
        return [types.TextContent(
            type="text",
            text=f"⚠ 已拦截: {reason}\n该请求已记录到审计日志。"
        )]

    # 实际执行
    if name == "safe_echo":
        message = arguments.get("message", "世界")
        result = f"你好，{message}！"

        # 关卡 6: 审计
        gate6_audit({
            "tool": name,
            "args": arguments,
            "decision": "allow",
            "result_preview": result[:50],
        })

        return [types.TextContent(type="text", text=result)]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
```

### 7.3 测试

```bash
mcp dev safe_echo_server.py
```

试两个输入：
- `{"message": "项目组"}` → 应正常返回 "你好，项目组！"
- `{"message": "rm -rf /var/log/"}` → 应被拦截

查看审计日志：
```bash
cat ~/xa_guard_demo.log
```

你会看到一系列 JSON 行，每行有 timestamp / decision / prev_hash。

**这就是我们 XA-Guard MCP Server 的微型版**。完整版要把：
- "敏感词列表" → 替换成 PromptGuard 2 模型
- "审计日志" → 替换成 OpenTelemetry + 国密 SM3/SM2
- 加上 5 个其他关卡

---

## 8. 关键 API 速查

### 8.1 必背 5 个

| API | 用途 | 示例 |
|---|---|---|
| `Server(name)` | 创建 server | `app = Server("xa-guard")` |
| `@app.list_tools()` | 声明工具列表 | 见上 |
| `@app.call_tool()` | 处理工具调用 | 见上 |
| `types.Tool(...)` | 工具定义 | 见上 |
| `types.TextContent(...)` | 文本返回值 | 见上 |

### 8.2 进阶 5 个

| API | 用途 |
|---|---|
| `@app.list_resources()` | 声明资源列表（如可读取的文件） |
| `@app.read_resource()` | 处理资源读取 |
| `@app.list_prompts()` | 声明 prompt 模板 |
| `@app.get_prompt()` | 处理 prompt 模板请求 |
| `ctx.elicit(...)` | 反向问客户端（HITL 审批用） |

### 8.3 我们项目会用到的

| API | 我们的用法 |
|---|---|
| `@app.list_tools()` | 列出下游所有真实工具（透传） |
| `@app.call_tool()` | 关卡 1-6 全部在这里实现 |
| `ctx.elicit()` | 关卡 2 的 HITL 审批弹窗 |
| `ImageContent` | 返回审计可视化图（可选） |
| `EmbeddedResource` | 返回审计日志附件 |

---

## 9. 我们项目的 MCP 设计

### 9.1 双面 MCP

XA-Guard MCP Server 同时是：
- **MCP Server**（对上游 LLM 客户端，如 Trae / CodeBuddy / 通义灵码 / Cursor 等）
- **MCP Client**（对下游真实工具）

```
[LLM 客户端：Trae / CodeBuddy / 通义灵码 / Cursor / ...]
   ↓ 调用 file_read
[XA-Guard MCP Server]
  ① 关卡 1-5 检查
  ② 如通过，作为 MCP Client 调用下游
   ↓ 调用 filesystem.file_read
[filesystem MCP Server]
   ↓ 返回结果
[XA-Guard MCP Server]
  ③ 关卡 4 输出检查 + 关卡 6 审计
   ↓ 返回
[LLM 客户端]
```

### 9.2 关键技术挑战

1. **HITL 通过 MCP 怎么实现？**
   - MCP 自 **protocol revision 2025-06-18** 起标准化 `elicitation`，**2025-11-25 SEP-1036 新增 URL mode**
   - **Cursor v1.5+ / Claude Code / Codex / GitHub Copilot CLI / Goose 等明确支持 elicitation**；**Claude Desktop 不支持 elicitation**；国产 IDE（Trae / CodeBuddy / Qoder / Qoder CN）目前均未声明 elicitation，需实测

2. **下游工具发现？**
   - 启动时遍历配置的下游 MCP Servers
   - 缓存它们的 tools list

3. **性能开销？**
   - 每次调用经过 6 关卡 ≈ 200-500ms（本地模型推理是主要瓶颈）
   - 优化方向：关卡 1 用 cache、关卡 6 异步写日志

### 9.3 配置文件示例

```yaml
# xa-guard.yaml
xa_guard:
  upstream:
    transport: stdio
    
  downstream:
    - name: filesystem
      command: ["mcp-server-filesystem", "/safe_path"]
    - name: shell
      command: ["mcp-server-shell"]
      
  gates:
    gate1:
      enabled: true
      prompt_guard_model: "Meta-Llama-Prompt-Guard-2-86M"
      threshold: 0.7
    gate2:
      enabled: true
      hitl_required_for: ["red"]
    gate3:
      enabled: true
      policy_file: "policies/enterprise-l3.yaml"
    gate4:
      enabled: true
      strict_mode: false
    gate5:
      enabled: true
      docker_image: "xa-guard/sandbox:latest"
    gate6:
      enabled: true
      audit_path: "/var/log/xa-guard/"
      sm2_key_path: "/etc/xa-guard/sm2.pem"
```

---

## 10. 推荐学习资源

### 10.1 官方资源

1. **MCP 官网**：https://modelcontextprotocol.io
2. **MCP Python SDK**：https://github.com/modelcontextprotocol/python-sdk
3. **MCP Inspector**：https://modelcontextprotocol.io/docs/tools/inspector
4. **MCP 服务器示例集**：https://github.com/modelcontextprotocol/servers

### 10.2 中文资源

1. **B 站搜**："MCP 入门"、"Model Context Protocol 教程"
2. **知乎专栏**：搜 "Anthropic MCP"
3. **微信公众号**："AI 编程指南" 系列文章

### 10.3 进阶资源

1. **MCP 协议规范**：https://spec.modelcontextprotocol.io
2. **MCP 安全研究**（这是我们的方向）：
   - 我们 reference 库的 [02_tool_security/](../references/literature/02_tool_security/) 全部
   - GitHub 上搜 "mcp security" / "mcp guardrail"

### 10.4 实战示例

我们 reference 库里：
- [LlamaFirewall](../references/literature/01_input_attack/1.1_prompt_injection/2025-LlamaFirewall.md) — Meta 的入门套件，可以包装成 MCP Server
- [IsolateGPT](../references/literature/02_tool_security/2.2_middle_policy/2025-IsolateGPT.md) — NDSS 2025 的 hub-spoke 架构，与我们的 MCP 代理模式高度相似

---

## 11. FAQ

### Q1：MCP 跟 OpenAI Function Calling、LangChain Tool 有什么区别？

简单回答：
- **OpenAI Function Calling**：单家厂商的标准，只 OpenAI 模型用
- **LangChain Tool**：单个框架的概念，必须在 LangChain 内部使用
- **MCP**：**跨厂商、跨框架、跨客户端**的开放协议

打比方：Function Calling 是某家手机厂的私有充电口，LangChain Tool 是某个充电宝品牌的接口，**MCP 是 USB-C 国际标准**。

### Q2：MCP 比 OpenAPI / gRPC 强在哪？

OpenAPI 和 gRPC 是 RPC 协议——为人写的代码调用设计。MCP 专为 **LLM 调用工具**设计：
- 工具描述自然语言友好（LLM 能读懂）
- 双向通信（LLM 可以反过来问用户）
- 资源 / 提示词等 LLM 特有概念

### Q3：MCP 安全吗？

**MCP 协议本身不提供安全保证**。这正是我们项目的切入点：
- MCP 没有内置的"输入检查"
- MCP 没有内置的"权限审批"
- MCP 没有内置的"审计日志"

所以我们要做 XA-Guard。

### Q4：MCP 在国内能用吗？

**完全能用，且国产生态已经成熟**。
- **国产工具 MCP 支持**（2025-2026 已全面铺开）：
  - **Trae**（字节）：免费、国产、原生支持，强烈推荐
  - **CodeBuddy**（腾讯云）：腾讯生态、企业版本对接
  - **Qoder CN**（原通义灵码 2026-05-20 更名，阿里）：阿里生态、国企央企采购首选
  - **智谱清言桌面版**（智谱）
  - **Qoder**（阿里 2025-08 推出独立 Agentic IDE）
- **国际工具**：Cursor / Claude Desktop / Cline 在国内需要科学上网（仅作学习参考）
- **核心结论**：我们的 XA-Guard 是 LLM 客户端无关的——上述所有客户端都能接入

### Q5：MCP 的未来会不会被废弃？

不太可能。MCP 已经形成强生态：
- Anthropic / OpenAI / Google / Microsoft 都在跟进
- 工具厂商（GitHub、JetBrains、Notion 等）都在出 MCP 集成
- 类比"USB-C"——一旦形成生态就难以替换

### Q6：MCP 学习曲线多陡？

- **会 Python + 用过任何 SDK**：2-3 小时入门
- **从未做过任何后端**：1-2 天
- **想成为专家**：1-2 周

### Q7：如果我搞不定怎么办？

按这个顺序求助：
1. 重读本文档相关章节
2. 在群里问队友（具体问题 + 错误截图 + 已经试过的）
3. 在 GitHub MCP 仓库的 Issues 里搜
4. 问 ChatGPT/Claude（贴上你的代码 + 错误）

**记住**：5 月底前每个组员都要跑通"第 5-7 节"的所有 demo。这是 M1 入门标志。

### Q8：MCP server 跑得动 PromptGuard 模型吗？

可以但要注意：
- PromptGuard 2 大约 22M 参数（小型）
- 在 CPU 上推理约 50-100ms
- 第一次加载约 1-2 秒
- 内存占用约 200MB

> **事实源 v1.1**：22M 版本延迟 19.3ms 但多语言精度下降；86M 版本 92.4ms（A100）/ Recall 97.5% @ 1% FPR

我们项目里**关卡 1 用 PromptGuard 是没问题的**。

### Q9：开发环境推荐配置？

- **CPU**：不挑（Intel/AMD/ARM 都行）
- **内存**：8GB+（16GB 更舒适）
- **磁盘**：10GB+ 可用空间
- **GPU**：不需要（M2/M3 阶段微调时可选用 Colab Pro）

### Q10：什么时候开始学？

**M1 开始（2026-06-01）**。

按本文档 1-7 节顺序，预计：
- 第 1 周末：跑通 echo_server.py
- 第 2 周末：跑通 safe_echo_server.py + 接入 **Trae**（或任一 MCP 客户端）实测
- 第 3 周开始：扩展为多关卡的真实版本

---

## 维护说明

- **版本**：v0.1
- **最后更新**：2026-05-23
- **下次更新**：MCP 协议有大版本变化时；项目实践遇到的新问题
- **维护者**：项目助手 + 全体团队成员
- **v1.1 纠偏**（2026-05-24）：依据事实源 v1.1 修正 Qcoder→Qoder / 通义灵码→Qoder CN / CodeGeeX 移除 / MCP 协议版本 2025-11-25 / Streamable HTTP 取代 SSE / Elicitation 标准化日期

## 相关文档

- [项目总览.md](../项目总览.md) — 项目全局
- [产品架构.md](../产品架构.md) — XA-Guard 三件套设计
- [文献库 INDEX.md](../references/literature/INDEX.md) — 文献库
- [../../status.md](../../status.md) — 当前仓库能力和缺口
- [../../log.md](../../log.md) — 客观工作日志
