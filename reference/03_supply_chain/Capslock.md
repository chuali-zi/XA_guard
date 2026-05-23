# Capslock Go 库能力分析器

## 基本信息
- **类型**: 静态分析工具
- **维护机构**: Google
- **GitHub**: https://github.com/google/capslock
- **支持语言**: Go（主要）
- **是否强制（政企场景）**: 工具借鉴价值高于直接使用

## 一句话总结
扫描 Go 库到底用了哪些"危险能力"（开网络、读文件、起进程），让你按能力授权而非黑名单。

## 这是什么

传统软件审计是看"用了哪些库"（黑名单：这个库有 CVE 就不能用）。
Capslock 反过来：看**"这个库到底要做哪些危险操作"**（白名单：除非这个库需要联网，否则它就不应该联网）。

工具自动分析 Go 包的代码，把它的行为分类到**几类能力**：
- `NETWORK`（联网）
- `FILES`（读写文件）
- `RUNTIME`（启动子进程）
- `READ_SYSTEM_STATE`（读系统状态如环境变量）
- `MODIFY_SYSTEM_STATE`（改系统状态）
- `OPERATING_SYSTEM`（直接 syscall）
- `ARBITRARY_EXECUTION`（任意代码执行，如 reflect / unsafe）

然后开发者就可以做能力级别的策略决定："我这个 web 服务里的日期格式化库为什么需要联网能力？这不对，拒绝引入。"

## 关键能力

1. **细粒度行为标签**：把每个函数标到 7 类能力
2. **静态分析**：不用真跑代码就能分析
3. **能力对比**：升级一个库时能看"新版本和旧版本的能力差异"——这是检测**供应链投毒**的强信号

## 我们项目里的用法

**学习思路**而非直接用（因为 Capslock 仅支持 Go，我们用 Python）。但思想 100% 可以照搬：

我们的 **AIBOM 准入网关**可以做一个简化版的 **Python 能力分析器**：
- 用 Python AST 模块解析插件代码
- 检测 `requests` / `socket`（联网）、`open()` / `os.path`（文件）、`subprocess` / `os.system`（进程）、`exec` / `eval`（动态执行）
- 给每个插件标能力标签
- 与该插件声明的能力比较——不匹配就拒绝

这是个**约 200 行 Python 就能写完**的小工具，但作为创新点很有说服力。

## 学习建议

- **必看**：https://github.com/google/capslock 的 README + 一个 demo（10 分钟）
- **关键概念**：理解"能力清单"（Capability Manifest）的设计思路
- **可借鉴**：Capslock 的 7 类能力分类法可以直接搬到我们的 Python 工具

## 与本目录其他资源的关系

- **OpenSSF-Scorecard**：Scorecard 给整体评分，Capslock 给具体行为分析，两者互补
- **AIRS-Framework**：AIRS 的"行为证据"字段可以用 Capslock 类工具产出
