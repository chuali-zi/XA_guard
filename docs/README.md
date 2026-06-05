# 项目文档总目录

> **项目**：XA-202620 · 面向政企场景的大模型智能体安全关键技术研究
> **文档目录版本**：v3（2026-05-31 补充 HACK-BENCH 规则后）
>
> 本目录是项目所有书面资料的**单一入口**。所有教学、参考、调研、历史版本都收纳在此。
>
> **权威顺序**：赛题 PDF > [`事实源.md`](./事实源.md) > [`PRD.md`](./PRD.md) > 产品架构 / 项目总览 > 研究资料。遇到冲突时按此顺序纠偏。

---

## 30 秒理解目录

```
docs/
├── README.md                ← 你在这里
├── 事实源.md                ← 维护口径与纠偏清单
├── PRD.md                   ← 验收目标与 KPI
├── 产品架构.md              ← XA-Guard 三件套设计（产品级核心）
├── 项目总览.md              ← 项目方案 / 时间线 / 风险（项目级核心）
├── HACK-BENCH-组员提交规范.md ← hack 组员必读：怎么提交可复现攻击样例
├── XA-Bench-对抗测试规则.md ← bench 维护者必读：怎么接入、验收和分层报告
├── 规则测试样例约定.md      ← Gate3 规则正/反例、bench 绑定和阳历日期样例约定
├── XA-202620…比赛方案.pdf   ← 赛题原文
│
├── tutorials/               ← 教学文档：上手 / 学习类
│   └── MCP零基础上手.md
│
└── references/              ← 参考资料：方案对比 / 文献 / 历史版本
    ├── product-forms/       ← 产品形态备选方案与调研
    │   ├── 产品形态-对比分析.md
    │   ├── 产品形态-备选-*.md（Skill / CLI / SaaS 三个备选）
    │   └── research-raw/    ← 调研原始报告（约 1.4 万字 + 85 引用）
    ├── literature/          ← 学术文献库（55 PDF + 88 中文导读）
    │   ├── INDEX.md         ← 文献库总索引（必读）
    │   ├── 01_input_attack/   提示注入 / RAG 投毒 / 越狱 / 间接注入
    │   ├── 02_tool_security/  工具调用安全（含基准 / 中间策略 / 异常检测 / 沙盒）
    │   ├── 03_supply_chain/   供应链安全（AIBOM / 签名 / 真实事件）
    │   ├── 04_eval_audit/     评估与审计（CoT 可信 / 溯源 / 水印）
    │   └── 05_standards/      合规与标准（国标 / TC260 / 等保 / OWASP / NIST / EU）
    └── archive/             ← 历史 / 分发版（docx 等）
        ├── 项目总览.docx
        └── 项目总览-v2.docx
```

---

## 各目录用途（1 行版）

| 路径 | 用途 |
|---|---|
| `docs/事实源.md` | 核心事实和纠偏清单，内部衍生文档冲突时优先采用 |
| `docs/PRD.md` | 验收目标、KPI、里程碑和交付物边界 |
| `docs/产品架构.md` | XA-Guard MCP Server + Protocol + SDK + Bench 的产品级技术设计，**新人第二份必读** |
| `docs/项目总览.md` | 5 个月时间表 / 6 关卡方案 / FAQ，**新人第一份必读** |
| `docs/HACK-BENCH-组员提交规范.md` | hack 组员提交攻击、误报和人工探索记录的统一格式 |
| `docs/XA-Bench-对抗测试规则.md` | bench 维护者的接入层、oracle、指标和演进规则 |
| `docs/规则测试样例约定.md` | Gate3 规则逐条正/反例、bench case 绑定和阳历日期样例口径 |
| `docs/XA-202620…比赛方案.pdf` | 赛题原文，遇到分歧以此为准 |
| `docs/tutorials/` | 教学文档。当前只有 MCP 入门指南，未来加入沙盒、审计等手把手教程 |
| `docs/references/product-forms/` | 产品形态可行性评估的 4 篇方案 + 横向对比 |
| `docs/references/product-forms/research-raw/` | 上述方案背后的调研原始报告（外部引用全在这里） |
| `docs/references/literature/` | 项目研究的文献库，按 5 个方向组织，对每篇 PDF 都有中文导读 md |
| `docs/references/archive/` | 历史快照 / 分发版（如 docx 招新版本），用于回溯，**不是当前权威** |

---

## 推荐阅读顺序

### 我是新加入的队员
1. 先读 [项目总览.md](./项目总览.md) —— 理解我们在做什么、为什么、什么时候交付（约 45 分钟）
2. 再读 [产品架构.md](./产品架构.md) —— 理解 XA-Guard 三件套的设计（约 30 分钟）
3. 看 [tutorials/MCP零基础上手.md](./tutorials/MCP零基础上手.md) —— 跑通第一个 MCP Server（约 2-3 小时实操）
4. 浏览 [references/literature/INDEX.md](./references/literature/INDEX.md) —— 文献库地图，知道遇到问题去哪查

### 我是产品形态决策者 / 答辩准备
1. [references/product-forms/产品形态-对比分析.md](./references/product-forms/产品形态-对比分析.md) —— 4 形态横向对比 + 最终推荐
2. 按需深入 [references/product-forms/产品形态-备选-*.md](./references/product-forms/) 任一备选
3. 引用细节去 [references/product-forms/research-raw/](./references/product-forms/research-raw/) 找原始报告

### 我要做某个方向的技术调研
- 方向 1 输入攻击 / 提示注入 → `references/literature/01_input_attack/`
- 方向 2 工具调用安全 → `references/literature/02_tool_security/`
- 方向 3 供应链安全 → `references/literature/03_supply_chain/`
- 方向 4 评估与审计 → `references/literature/04_eval_audit/`
- 方向 5 标准合规 → `references/literature/05_standards/`

每个方向都有 `README.md` 介绍重点论文与阅读顺序，详见 [references/literature/INDEX.md](./references/literature/INDEX.md)。

### 我要负责 hack / red-team

1. 先读 [HACK-BENCH-组员提交规范.md](./HACK-BENCH-组员提交规范.md)。
2. 从 [`../bench/cases/hack-submission-template.yaml`](../bench/cases/hack-submission-template.yaml) 复制提交模板。
3. 用 [XA-Bench-对抗测试规则.md](./XA-Bench-对抗测试规则.md) 核对接入层和 oracle。

### 我在准备答辩
跨方向必读 Top 10、常见评委问题应答清单都在 [references/literature/INDEX.md](./references/literature/INDEX.md) 第 35-165 行。

---

## 文档维护说明

### 文档归属约定

- **教学性文档**（"怎么做"，让人学会）→ `tutorials/`
- **方案 / 备选 / 对比类**（决策依据）→ `references/product-forms/`
- **学术 / 标准 / 引用**（"业界怎么做"）→ `references/literature/`
- **历史 / 分发版**（不再权威，仅备查）→ `references/archive/`
- **产品级 / 项目级核心**（顶层权威）→ `docs/` 根目录

### 新增文档时

1. 判断它属于上面哪类
2. 放进对应目录
3. **更新本 README 的目录树**（如果是新增子目录）
4. 在 [`../log.md`](../log.md) 顶部记录本次具体改动；若仓库能力边界变化，同时更新 [`../status.md`](../status.md)

### 链接维护

所有 `.md` 文档之间使用**相对路径链接**。如果你移动文件，记得：
1. 修改被移动文件中的所有相对链接
2. 用 grep 搜其他引用了它的文件，一并修复
3. 移动后跑一遍链接检查（建议用 markdown-link-check 工具，未来集成到 CI）

### 当前顶层文档（2026-05-31）

顶层包含：赛题 PDF、事实源、PRD、产品架构、项目总览、Gate1 接入说明、HACK-BENCH 提交规范、XA-Bench 对抗测试规则和规则测试样例约定。研究资料和历史快照继续放在 `references/`。

---

## 关联文件（项目根级，不在 docs/ 内）

- [../status.md](../status.md) —— 当前仓库能力、缺口和 PRD 距离
- [../log.md](../log.md) —— 按时间倒序记录客观工作日志
- [../README.md](../README.md) —— 项目根 README（代码级介绍）
- [../scripts/](../scripts/) —— 项目脚本

---

> 维护者：项目负责人
> 上次更新：2026-05-31（补充 HACK-BENCH 规范，改用 `log.md` / `status.md` 留痕）
