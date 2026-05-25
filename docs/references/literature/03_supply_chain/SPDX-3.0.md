# SPDX 3.0 物料清单标准

## 基本信息
- **类型**: 业界主流 SBOM 标准之一
- **维护机构**: Linux Foundation（开放源代码软件基金会）
- **最新版本**: 3.0（2024 年发布）
- **官方链接**: https://spdx.dev
- **ISO 标准**: SPDX 是 ISO/IEC 5962:2021 国际标准
- **是否强制（政企场景）**: 推荐

## 一句话总结
偏许可证合规和法律层面的"软件成分表"，是 ISO 国际标准。

## 这是什么

与 CycloneDX 是两大主流 SBOM 标准之一。区别：
- **SPDX**：起源于许可证合规问题。比如你用了 GPL 的库会传染你的整个产品 → 法务部门需要扫描所有依赖判定许可证兼容性
- **CycloneDX**：起源于应用安全问题。比如你用了有 CVE 的库 → 安全团队需要知道哪里受影响

SPDX 3.0 是一次大重构，**首次加入 AI Profile** 和 **Dataset Profile**，能描述 AI 模型和训练数据集。

## 关键能力

1. **完整的许可证表达**：支持 SPDX License Expression 语法
2. **AI Profile**：描述 AI 模型的元数据
3. **Dataset Profile**：描述数据集来源、采样方法、许可证
4. **关系建模**：能描述组件间的复杂依赖关系（CONTAINS / DEPENDS_ON / GENERATED_FROM 等）
5. **多格式**：tag-value、RDF、JSON、JSON-LD、YAML、XML

## 与 CycloneDX 怎么选

| 维度 | CycloneDX | SPDX |
|---|---|---|
| 学习成本 | 低 | 高 |
| AI 扩展成熟度 | 较成熟 | 刚起步（3.0） |
| 法律合规 | 一般 | 强 |
| 国际标准 | 否 | 是（ISO） |
| 工具支持 | 多 | 多 |

**我们项目优先选 CycloneDX 1.6**，但报告里可以提一句"也支持导出为 SPDX 3.0 格式以满足跨国合规"作为加分点。

## 我们项目里的用法

作为**备选输出格式**。主要在方案报告里展示我们对"两大主流标准"都支持。

## 学习建议

- **必看**：https://spdx.dev 主页
- **跳过**：完整 spec（500+ 页，没人能看完）
- **关键概念**：SPDX Document → SPDX Element → Relationship 三层结构

## 与本目录其他资源的关系

- **CycloneDX-1.6**：竞品/同类标准
- **OWASP-AIBOM-Generator**：同样可输出 SPDX 格式
