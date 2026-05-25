# 你以为你在用助手，其实助手在用你: 间接 prompt 注入开山之作 (Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection)

## 元信息
- **作者机构**: CISPA Helmholtz + Saarland + Sequire (Kai Greshake 等)
- **年份 · 发表**: 2023-02 · AISec 2023 (ACM Workshop)
- **arXiv**: https://arxiv.org/abs/2302.12173
- **本地 PDF**: ./2023-NotWhatYouSignedUp.pdf
- **代码**: https://github.com/greshake/llm-security
- **难度**: 2/5

## 一句话总结
**首次系统化提出"间接 prompt 注入"概念**——攻击者不直接发消息给 LLM，而是把恶意 prompt 藏到 LLM 会读到的网页/邮件/文档里，让助手被远程劫持。

## 解决什么问题
2022 年底 ChatGPT 火爆后，业界开始把 LLM 集成进各种"读外部内容"的应用：
- Bing Chat 能读网页
- Office Copilot 能读邮件/文档
- ChatGPT plugins 能调外部 API

之前的注入研究都关注**直接注入**：攻击者就是当前用户，直接发消息。但 LLM 集成应用引入了一个新维度：**LLM 会读到大量"非当前用户"产生的内容**——网页、邮件、PDF、搜索结果。如果这些内容里藏着 prompt，会发生什么？

这篇论文是**最早系统化指出这个问题**的工作。在它之前没人意识到"网页里塞 prompt 也