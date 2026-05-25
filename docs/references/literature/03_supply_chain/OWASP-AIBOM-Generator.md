# OWASP AI SBOM Initiative / AIBOM Generator

## 基本信息
- **类型**: OWASP 开源项目（属于 OWASP GenAI Security Project）
- **发布时间**: 2025 年 RSAC 会议首次开源
- **官方链接**: https://genai.owasp.org/ai-sbom-initiative/
- **GitHub**: 见官网入口
- **许可证**: Apache 2.0（典型 OWASP 项目）
- **是否强制（政企场景）**: 推荐（非强制，但 OWASP 是业界事实标准制定方）

## 一句话总结
OWASP 官方的"AI 物料清单"开源生成器，社区版即装即用。

## 这是什么

OWASP（开放 Web 应用安全项目）是软件安全领域最权威的非营利组织之一，他们 2023 年发布了 **OWASP Top 10 for LLM Applications**（大模型应用十大风险），现在每年更新一次。

在这个项目下，他们 2025 年专门启动了 **AI SBOM Initiative**——目的是把传统 SBOM 工具扩展到 AI 场景。**AIBOM Generator** 是该项目的核心交付物：一个开源工具，能自动扫描你的 AI 项目（Python 代码 + 模型权重文件 + 提示词模板 + 知识库索引），产出标准格式的 AIBOM（CycloneDX 或 SPDX 格式）。

## 关键能力

1. **自动扫描代码依赖**：解析 `requirements.txt` / `pyproject.toml` / `package.json`，识别所有第三方包
2. **识别模型与权重**：扫描本地 `.bin` / `.safetensors` / `.gguf` 等模型文件，提取元数据（hash、来源 HuggingFace 仓库、license）
3. **识别提示词模板**：扫描 prompt 文件，记录模板版本、依赖的变量
4. **识别 RAG 知识库**：扫描向量数据库索引（Faiss/Chroma），记录知识库快照
5. **输出标准格式**：CycloneDX 1.6 JSON / SPDX 3.0 JSON，可直接对接现有 SBOM 工具链
6. **VEX 集成**：可关联 CVE 数据库自动判定漏洞影响

## 我们项目里的用法

直接对应到我们项目的**加分项 AIBOM 准入网关**：

- **不需要造轮子**：OWASP AIBOM Generator 就是基础工具，pip 装上即可
- **我们的差异化**：在 OWASP 工具基础上加一层"政企合规过滤"——例如自动检查依赖项是否来自国内备案过的镜像源、模型权重是否有国密签名等
- **报告价值**：「我们对接了 OWASP 官方 AIBOM 标准」这句话在评委眼里就是合规分加 5 分
- **演示价值**：在演示视频里展示 AIBOM JSON 输出 → 评委会觉得"这队人懂工业落地"

## 学习建议

- **看主页**：先到 https://genai.owasp.org/ai-sbom-initiative/ 看 2-3 分钟介绍视频
- **跑一遍 demo**：用 pip 装上工具，对我们的 LangGraph 项目跑一次，看看产出长什么样（这一步建议 M2 阶段做）
- **重点关注**：输出的 JSON schema 字段名——我们要在自己的"准入网关"里复用这些字段

## 与本目录其他资源的关系

- **CycloneDX-1.6** / **SPDX-3.0**：AIBOM Generator 的两种输出格式
- **Agentic-AIBOM** (./2026-Agentic-AIBOM.md)：学术界对 AIBOM 的扩展研究，可作为我们差异化创新点的参考
- **OWASP-LLM-Top10-2025** (../05_standards/OWASP-LLM-Top10-2025.md)：AI SBOM Initiative 项目的"母项目"
