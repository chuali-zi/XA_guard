# 方向 3 · 第三方组件可信审计 — 文献库

## 这个方向研究什么

**通俗解释**：智能体除了"大脑"（LLM）以外，会调用很多第三方"工具"——插件、Skill 包、Python 库、模型权重、知识库索引、远程 API ……这些**第三方组件**就像家里请的家政、维修工、外卖员。家里来的人多了，谁是好人、谁是坏人就要管起来：

- 这个人是谁介绍来的？（**溯源**）
- 他过往口碑怎么样？（**信誉**）
- 他要做什么？（**能力声明**）
- 他做的是否和声明的一致？（**行为验证**）
- 万一出事能不能找到他？（**可问责**）

这就是"第三方组件可信审计"在做的事。

## 智能体场景的独特挑战

| 传统软件 | LLM 智能体 |
|---|---|
| 一次安装，长期固定 | 动态加载、运行时拉取 |
| 代码可静态审计 | 自然语言工具描述可被注入 |
| 依赖关系清晰 | 模型权重、提示词、知识库都是依赖 |
| 攻击面有限 | 自然语言 + 代码 + 数据三重攻击面 |

## 本目录文件清单

### 学术论文（2 篇 PDF + md）
- [2026-Agentic-AIBOM.md](./2026-Agentic-AIBOM.md) ★★★ — Oxford / 艾伦图灵研究所，2026 年最新研究，**必读**
- [2025-AIRS-Framework.md](./2025-AIRS-Framework.md) ★★★ — JHU APL 出品，威胁建模驱动的评估框架，**必读**

### 行业规范与开源工具（介绍 md）
- [OWASP-AIBOM-Generator.md](./OWASP-AIBOM-Generator.md) ★★★ — **必读 + 必跑** OWASP 官方开源工具
- [CycloneDX-1.6.md](./CycloneDX-1.6.md) — 我们的 AIBOM 输出格式默认选项
- [SPDX-3.0.md](./SPDX-3.0.md) — 国际标准 SBOM 格式
- [SLSA-Framework.md](./SLSA-Framework.md) — 供应链可信级别
- [Sigstore.md](./Sigstore.md) — 软件签名透明化
- [OpenSSF-Scorecard.md](./OpenSSF-Scorecard.md) ★★ — **强烈建议跑一遍 demo**，可直接集成到我们网关
- [Capslock.md](./Capslock.md) — Google 能力分析器，思想可借鉴

### 真实案例
- [LiteLLM-Incident-2026.md](./LiteLLM-Incident-2026.md) ★★★ — **必读** 写报告必引

## 必读路径（按时间预算）

**1 小时入门**：
1. 读 [OWASP-AIBOM-Generator.md](./OWASP-AIBOM-Generator.md)（15 min）
2. 读 [LiteLLM-Incident-2026.md](./LiteLLM-Incident-2026.md)（15 min）
3. 读 [2026-Agentic-AIBOM.md](./2026-Agentic-AIBOM.md)（30 min，重点是 Abstract + Section 1）

**1 天深入**：在 1 小时基础上加：
4. [2025-AIRS-Framework.md](./2025-AIRS-Framework.md)（2 小时）
5. [CycloneDX-1.6.md](./CycloneDX-1.6.md) + [OpenSSF-Scorecard.md](./OpenSSF-Scorecard.md)（1 小时跑 demo）
6. 浏览其余 md（每个 5-10 min）

## 与我们项目 6 关卡的对应关系

本目录的核心对应到我们项目的**加分项"AIBOM 准入网关"**：

```
插件 / 工具 / 模型权重 提交
    ↓
1. AIBOM 自动生成     ← 借鉴 OWASP-AIBOM-Generator + CycloneDX 1.6
2. 自动评级           ← 借鉴 OpenSSF-Scorecard + Capslock 思想
    ↓
评级 < 5 → 自动拒绝
评级 5-7 → 人工复核（HITL）
评级 > 7 → 自动通过
    ↓
3. 上线后行为漂移监测  ← 借鉴 Agentic-AIBOM 的运行时监控思想
    ↓
存入关卡 6 黑匣子审计日志（国密哈希链）
```

## 设计建议

1. **MVP 范围**：输出 CycloneDX 1.6 JSON 即可，工具直接用 OWASP AIBOM Generator
2. **差异化创新**：在 OWASP 工具上加一层"政企合规过滤"（国密签名、备案镜像源等）
3. **演示亮点**：演示视频展示一个"假设被污染的插件"被网关识别并拒绝的全过程（参考 LiteLLM 事件场景）

## 相关方向

- 方向 4（评测审计）：本方向产出的 AIBOM 进入审计日志体系
- 方向 5（标准与法规）：本方向的合规支撑文档
