# 多智能体安全的开放挑战：迈向可信的交互式 AI 智能体系统(Open Challenges in Multi-Agent Security: Towards Secure Systems of Interacting AI Agents)

## 元信息
- **作者机构**: (2025) / 多机构
- **年份 · 发表**: 2025 · arXiv 预印本
- **arXiv**: https://arxiv.org/abs/2505.02077
- **本地 PDF**: 无
- **难度**: 3 星

## 一句话总结
把安全边界从"单个 agent"扩展到"多个 agent 相互通信/委派"的系统级，指出多数现有分类学只沿单 agent 的感知-推理-行动流水线组织威胁，忽略了 agent 间交互带来的新攻击面。

## 解决什么问题
真实政企场景不是一个 agent 单打独斗，而是多席位协作、任务委派、跨 agent 消息传递。一个被攻陷的 agent 可以污染发给同伴的消息、伪造委派、借信任链横向移动。单 agent 威胁模型完全覆盖不了这些。

## 用了什么方法
1. **系统级威胁梳理**：识别 agent 间通信、委派、信任传递中的攻击面。
2. **对现有分类学的批判**：指出它们把威胁绑在单 agent 流水线上，漏掉了"交互"这一维。
3. **开放挑战清单**：列出多 agent 安全尚未解决的根本问题。

## 为什么能解决
把"信任如何在 agent 之间传递"显式化后，就能看到横向移动、委派伪造、消息投毒等单 agent 视角看不见的攻击，从而指导针对多 agent 系统的红队设计。

## 主要结果
- 明确多 agent 特有攻击面：inter-agent 消息注入、委派链滥用、信任传递漏洞。
- 指出这是相对单 agent 安全更不成熟的领域。

## 局限性
1. 以问题梳理为主，具体防御方案尚少。
2. 缺少统一的多 agent 安全评估基准。

## 我们项目里的用法
**分类 4（多智能体攻击）的直接依据。** ① OAR 的 `full-day.json`（16 席位企业一天）与 `accountability-delegation.json`（委派场景）正是多 agent 攻击面——`THREAT-MODEL.md` 据此设计"污染一个席位发给另一席位的消息""伪造委派让工具调用绕过审批"等 payload；② 检验 XA-Guard 的问责（accountability）能否在跨席位委派中保持"谁该负责"可追溯——这正好对上 OAR 的 accountability-report 判定；③ 答辩时用本文说明我们覆盖了"比单 agent 更前沿"的多 agent 攻击面。

## 学习路径
- 看 inter-agent 攻击面清单 —— 对照 OAR 席位/委派场景设计 payload。
- 看委派/信任传递部分 —— 理解 accountability 判定的攻击价值。

→ **映射到本工作流**：`THREAT-MODEL.md` 分类 4，在 full-day / accountability-delegation 场景落地。
