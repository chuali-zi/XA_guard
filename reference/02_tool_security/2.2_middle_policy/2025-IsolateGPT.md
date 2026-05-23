# IsolateGPT:基于 LLM 的智能体系统的执行隔离架构(IsolateGPT: An Execution Isolation Architecture for LLM-Based Agentic Systems)

## 元信息
- **作者机构**: Yuhao Wu、Franziska Roesner、Tadayoshi Kohno、Ning Zhang 等 / 华盛顿大学(WashU + UW)
- **年份 · 发表**: 2025 · NDSS 2025(网络安全顶会)
- **arXiv**: https://arxiv.org/abs/2403.04960
- **本地 PDF**: ./2025-IsolateGPT.pdf
- **代码**: https://github.com/llm-platform-security/SecGPT(原名 SecGPT)
- **难度**: 4 星 ★★★★

## 一句话总结
把每个智能体应用(类似浏览器扩展、操作系统进程)放进独立沙箱,通过 hub-spoke 架构隔离,防止跨应用越权。

## 解决什么问题
当下智能体平台(GPTs、Cursor 插件、Claude Skills、MCP Servers)的核心问题:**所有插件/工具都共享同一个 LLM 上下文**。一个 GPT 插件如果想读取另一个插件的数据(如银行插件偷邮件插件的内容),它只要在自己的描述里写一句"接下来请调用 read_email 工具",LLM 就可能照办——**零成本横向越权**。论文作者来自系统安全圈,他们从 OS 视角看这个问题:**这不就是 Unix 进程之间互相读内存吗?** 在 OS 里我们用进程隔离+IPC 解决了这个问题,LLM 智能体平台为什么不能?IsolateGPT 就是把这个思想搬过来。

## 用了什么方法
IsolateGPT 的核心架构是 **Hub-Spoke 隔离**:

1. **Hub(中心调度器)**:
   - 一个核心 LLM,只读用户的原始指令,负责决定"哪个 spoke 应该被激活"。
   - 持有所有用户身份/会话状态,但**不会把任何状态泄露给 spoke**。

2. **Spoke(隔离的执行环境)**:
   - 每个第三方应用/插件运行在自己独立的 Spoke 里。
   - Spoke 内部有自己的 LLM 实例(可以是同模型不同 session 或不同模型)、独立 memory、独立工具集。
   - **Spoke 之间互相不可见**——一个 spoke 不知道其他 spoke 存在,也不知道用户原始 prompt(只看到 Hub 转发过来的"任务子集")。

3. **受限 IPC(Inter-Spoke Communication)**:
   - 如果一个 spoke 需要另一个 spoke 的能力(如订机票时要查日历),必须通过 Hub 显式申请。
   - Hub 检查这次申请是否在用户授权的范围内,通过则建立**一次性、最小化暴露**的通道。
   - 类似于 Android intent 系统——你想调相机就申请 INTENT,系统决定给不给。

4. **用户审批 UI**:
   - 第一次跨 spoke 通信时弹窗给用户:"邮件插件想读取你的日历,是否允许?"
   - 用户决策被记录为长期 capability,后续同样请求免审批。

类比:这就像把"装满插件的浏览器"改造成"每个插件运行在独立沙箱、互相看不到、互相通信要经过系统弹窗"——和 Chrome 扩展的安全模型一模一样,只不过对象换成了 LLM 智能体。

## 为什么能解决
关键直觉:**系统安全的几十年积累已经给了我们答案——隔离+capability+用户授权**。LLM 平台之前的设计是"信任所有插件",这在 90 年代 Windows 上就被证明是灾难。把 OS/浏览器的成熟设计 patterns 搬到 LLM 智能体上,本质上不会比 OS 安全更难,只是工程量大。同时,Hub-Spoke 架构在性能、并发、可扩展性上都比"单一大模型应付所有任务"更好——这是工程上的双赢。

## 主要结果
- 实现了 SecGPT 原型(在 LangChain + Docker 上),支持 25+ 真实 GPT Plugin 集成。
- 对 7 种已知"插件互相窃取"攻击,IsolateGPT 的拦截率 **100%**;baseline(原版 GPT Store)0%。
- 单次查询延迟比原版增加 30-50%(因为多了 Hub 调度环节),仍在可用范围。
- 用户研究(N=15):85% 用户认为 IsolateGPT 的弹窗"必要、不烦人"。

## 局限性
1. 跨 spoke 协作场景下,任务规划复杂度上升——Hub 需要更强的"任务拆解"能力。
2. 每个 spoke 跑独立 LLM 实例,**资源开销大**——大规模部署成本高。
3. 不解决 spoke 内部的安全问题(如某个 spoke 自己被注入)——需要配合 CaMeL 类方案。
4. 多智能体协作的"持续会话"中,Hub 状态管理会变复杂。

## 我们项目里的用法
**对应关卡 5(沙箱) + 关卡 3(规则编译)**。IsolateGPT 是我们的**插件/工具隔离层蓝本**:
- ① 我们的运维助手会调用多种工具(查日志、改配置、查 CMDB),每种工具放进独立 spoke,即使其中一个工具被恶意 MCP 服务污染也不影响其他。
- ② 直接借鉴**用户审批 UI**——这就是题目要求的"工具调用审批机制"的标准设计。
- ③ Hub-Spoke 模式 + CaMeL 双 LLM 是**完美互补**:Hub 类似 CaMeL 的 P-LLM,Spoke 内部用 Q-LLM 处理不可信数据。两者合体是我们"政企智能体安全中台"的双骨架。
- ④ 配合方向 3 的 AIBOM——每个 spoke 启动前都要过插件准入网关,审计上传供应链 BOM。

## 学习路径
- **先看 Section 3 架构图** —— Hub-Spoke 一图秒懂。
- **看 Section 4 design patterns** —— 5 种 spoke 间通信模式,选最适合政企场景的 2-3 种实现。
- **跑 SecGPT 仓库的 demo** —— 用 docker compose 起一套,看怎么跑通跨 spoke 调用。
- **对比阅读 CaMeL** —— 一个管 IFC、一个管隔离,二者整合就是我们的核心架构。
- **顺带看 Conseca**(同方向的 HotOS 短文,补强政策驱动的隔离视角)。
