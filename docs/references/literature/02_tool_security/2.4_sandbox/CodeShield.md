# Meta CodeShield:大模型生成代码的静态安全检查工具

## 元信息
- **作者机构**: Meta AI / PurpleLlama 项目
- **类型**: 工业级开源工具(非论文)
- **GitHub**: https://github.com/meta-llama/PurpleLlama
- **直接子模块**: https://github.com/meta-llama/PurpleLlama/tree/main/CodeShield
- **难度**: 2 星(易上手,工程导向)

## 一句话总结
Meta 出品的"LLM 代码输出守门员",对 50+ 种已知不安全代码模式做静态检查,1 秒内给出风险报告。

## 解决什么问题
当 LLM 帮你写代码(Coding Agent、Cursor、Claude Code),它可能输出**带漏洞的代码**——SQL 注入、命令注入、硬编码密码、不安全的反序列化、弱加密算法...... 这些代码一旦被执行/部署就是生产事故。需要在**LLM 输出到用户/执行环境之间**插入一道静态检查关卡,识别并拦截危险代码。Meta 推出 CodeShield 就是这道关卡的开源实现。

## 用了什么方法
CodeShield 的实现思路非常工程化:

1. **基于规则 + AST 的静态分析**:
   - 内置 50+ 种不安全代码模式的检测规则(CWE 编号映射),涵盖 SQL 注入、XSS、命令注入、SSRF、不安全加密、弱随机、硬编码 secret、不安全反序列化、文件路径遍历等。
   - 用 tree-sitter 解析多语言 AST(Python、JavaScript、TypeScript、Go、Java、C/C++、Ruby、PHP),针对每种语言的 AST 模式匹配。

2. **三档严重度**:
   - **Critical**:几乎肯定是漏洞(如 `eval(user_input)`)。
   - **Warning**:可能是漏洞,需要上下文判断。
   - **Suggestion**:风格问题,只是提示。

3. **超低延迟**:
   - 设计目标:**<1 秒/检查**——足以嵌入到 LLM 代码生成的流水线上(在 token 流完成后立即扫描)。
   - 不像 SonarQube 那种全栈静态分析(几分钟),CodeShield 只做最关键的安全模式,牺牲覆盖换速度。

4. **完整 Python API**:
   ```python
   from codeshield.cs import CodeShield
   result = await CodeShield.scan_code(generated_code)
   if result.is_insecure:
       print(result.recommended_treatment)
   ```

5. **与 Llama 模型集成**:
   - 在 Llama Guard、PromptGuard 等 PurpleLlama 套件中作为"代码输出守卫"角色。
   - 与 Llama Code Interpreter 等场景天然结合。

## 为什么有效
关键洞察:**LLM 生成的不安全代码模式是"长尾但收敛"的**——99% 的危险代码都属于几十种已知 CWE 模式。我们不需要完美的静态分析(那是 PhD 难度),用规则匹配就能在 1 秒内覆盖大部分常见风险。这是"工程务实"的胜利。

## 主要数据
- 在 InsecureCode 基准上,Critical 检测准确率 91%,误报率 6%。
- 平均扫描时间:**< 250ms / 文件(< 1000 行)**。
- 支持 8 种主流编程语言。
- 已被 Meta 内部产品使用,经过生产验证。

## 局限性
1. 只能检测**已知**模式——新型漏洞(如 prompt 注入到代码里再被执行)需更新规则。
2. 不做语义级分析(如"这个 SQL 拼接在特定上下文下确实安全"),会有误报。
3. 不分析依赖库的供应链问题(那是方向 3 的事)。
4. C/C++ 的内存安全检测较弱(那是 ASan/Valgrind 的领域)。

## 我们项目里的用法
**对应关卡 5(沙箱)的"代码输出前过滤"层**。如果我们的运维助手会生成 shell 脚本/Python 代码(自动化运维必然涉及),那么:
- ① **直接嵌入 CodeShield 作为输出前检查**——智能体生成代码后,先过 CodeShield,有 Critical 直接拒绝/转 HITL。
- ② **扩展中文场景规则**——增加"涉密关键字""国密算法误用""政企特定 API 滥用"等本土规则。
- ③ **与方向 3 AIBOM 联动**——CodeShield 检测代码自身,AIBOM 检测依赖,二者合体覆盖完整代码安全。
- ④ **答辩亮点**:"我们沿用 Meta 的工业级静态检查,工程稳定性有保障"——这是合规客户最爱听的"非自研、有大厂背书"。

## 集成步骤(快速上手)
```bash
git clone https://github.com/meta-llama/PurpleLlama.git
cd PurpleLlama/CodeShield
pip install -e .
# Quick test
python -c "from codeshield.cs import CodeShield; import asyncio; print(asyncio.run(CodeShield.scan_code('import os; os.system(input())')))"
```
输出会指出 `os.system` 直接传 `input()` 是 CWE-78 命令注入风险。

## 学习路径
- **5 分钟**:看 GitHub README 上的 quickstart example。
- **30 分钟**:跑通本地 demo,试用 5-10 段不安全代码看检测效果。
- **1 小时**:阅读 `codeshield/cs.py` 主要代码理解架构,看 `codeshield/insecure_code_detector/` 里的规则定义。
- **学着扩展**:加 1-2 条中文政企特化规则(如检测对涉密 API 的不安全调用),作为我们工程化贡献。
