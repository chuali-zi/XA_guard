# OpenSSF Scorecard 开源项目可信度自动评分

## 基本信息
- **类型**: 开源项目可信度自动评分工具
- **维护机构**: Open Source Security Foundation（OpenSSF）
- **GitHub**: https://github.com/ossf/scorecard
- **官方链接**: https://securityscorecards.dev
- **是否强制（政企场景）**: 推荐

## 一句话总结
给 GitHub 上每个开源仓库自动打 0-10 分"安全分"，告诉你这个项目值不值得用。

## 这是什么

OpenSSF Scorecard 是个自动化工具：给一个 GitHub 仓库 URL，它扫描这个仓库的各种特征（有没有 CI、有没有签名、有没有及时合并安全 PR、维护者活跃度、二进制是否签名……），最后给出一个 **0-10 分的综合评分**。

被 Google、Microsoft、AWS 等大厂用来筛选第三方依赖。

## 关键检测项

Scorecard 检测 **18 类**指标，部分示例：
- Binary-Artifacts（是否有未签名二进制）
- Branch-Protection（主分支是否有保护）
- CI-Tests（是否有自动测试）
- Code-Review（PR 是否有 review）
- Dangerous-Workflow（GitHub Actions 是否有危险工作流）
- Maintained（项目是否还在维护）
- Pinned-Dependencies（依赖是否锁版本）
- Token-Permissions（CI token 权限是否最小化）
- Vulnerabilities（已知 CVE 数量）

## 我们项目里的用法

直接对应到我们**AIBOM 准入网关**的"自动评级"环节：

```
插件提交 → OpenSSF Scorecard 扫描 → 评分 < 5 自动拒绝
                                   → 评分 5-7 进入人工复核
                                   → 评分 > 7 自动通过 + 上线后行为漂移监测
```

这是个**几乎零开发成本**的强落地点——直接调用 Scorecard CLI 即可。

## 学习建议

- **必看**：https://securityscorecards.dev 主页（5 分钟看完）
- **必跑**：用 Scorecard 扫一下 LangChain 仓库，看看分数和具体问题
- **CLI 用法**：`scorecard --repo=github.com/langchain-ai/langchain`

## 与本目录其他资源的关系

- **Capslock**：Google 另一个开源项目可信度工具
- **SLSA-Framework**：Scorecard 部分指标对应 SLSA 等级
