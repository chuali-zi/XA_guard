# CycloneDX 1.6 物料清单标准

## 基本信息
- **类型**: 业界主流 SBOM 标准之一
- **维护机构**: OWASP（CycloneDX 是 OWASP 旗舰项目）
- **最新版本**: 1.6（2024 年发布）
- **官方链接**: https://cyclonedx.org/specification
- **是否强制（政企场景）**: 推荐（与 SPDX 并列两大主流，可选其一）

## 一句话总结
轻量、面向应用安全场景的"软件成分表"标准，AI 时代有专门扩展。

## 这是什么

SBOM（Software Bill of Materials, 软件物料清单）相当于药品的"成分表"——产品里用了什么、版本是多少、来源是哪里。

业界有两大主流 SBOM 标准：**CycloneDX** 和 **SPDX**。两者主要区别：
- **CycloneDX**：OWASP 维护，更偏**应用安全/漏洞管理**视角，schema 相对简单，扩展灵活
- **SPDX**：Linux Foundation 维护，更偏**许可证合规**视角，schema 严谨复杂

CycloneDX 1.6 是 2024 年的最新版，引入了**对 AI / ML 资产的支持**——可以描述模型、数据集、训练 pipeline 等 AI 特有组件。

## 关键能力

1. **组件描述**：library / framework / application / container / file / firmware / data / **machine-learning-model**（这个是 AI 关键）
2. **机器学习模型字段**：训练数据集、性能指标、模型卡（Model Card）、用途限制等
3. **服务依赖**：可描述远程 API 服务（如调用 OpenAI API）
4. **VEX（漏洞利用性交换）**：可附带"虽然我用了有漏洞的库，但这个漏洞在我的场景不可利用"的说明
5. **JSON / XML / Protobuf 格式**：JSON 最常用

## 与 SPDX 怎么选

- **学生项目推荐 CycloneDX**：schema 简单、上手快、AI 扩展更成熟
- **大企业合规推荐 SPDX**：覆盖法律许可证场景更完整

## 我们项目里的用法

我们的 AIBOM 准入网关**默认输出 CycloneDX 1.6 JSON 格式**。原因：
1. OWASP AIBOM Generator 默认支持
2. 字段较少、便于演示视频展示（一屏可以看完关键字段）
3. 与方向 3 论文（Agentic-AIBOM）使用的扩展基础一致

## 学习建议

- **必看**：https://cyclonedx.org/specification 主页的 "What is CycloneDX" 部分
- **跳过**：完整 schema 字段表（用到时再查）
- **关键字段记住**：`components[*].type`、`components[*].purl`（包统一定位符）、`vulnerabilities`、`compositions`

## 与本目录其他资源的关系

- **SPDX-3.0**：另一个主流 SBOM 标准
- **OWASP-AIBOM-Generator**：直接输出 CycloneDX 格式的工具
- **Agentic-AIBOM** / **AIRS-Framework**：基于 CycloneDX 做的 AI 扩展研究
