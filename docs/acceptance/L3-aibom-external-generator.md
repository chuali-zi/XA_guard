# AIBOM 外部生成器静态交换适配

## 范围

`xa_guard.aibom.external_generator` 接收已经生成的 CycloneDX JSON，不发现、下载或执行任何外部生成器。该边界用于离线 fixture、受控流水线产物和人工提供的产物交换；它不是外部工具运行器。

R8 后续接手入口见 [`r8-aibom-external/README.md`](./r8-aibom-external/README.md)。该目录已准备 `@cyclonedx/cdxgen` 作为合法外部 AIBOM/CycloneDX 生成器候选、最小样本目录和候选命令；当前仍是 `TODO/BLOCKED`，尚未实跑，不构成 R8 PASS。

本仓库不内置任何第三方命令，也不由 XA-Guard 自动执行外部生成器。调用方必须记录自己实际使用并已核验的命令参数、版本、许可证和产物哈希。

## 必填来源记录

每次导入必须构造 `ExternalGeneratorSpec`，显式填写生成器名称、来源、固定版本、许可证表达式和实际命令清单。每条命令按参数数组保存，不使用 shell 字符串。

适配器保存这些声明，但不替调用方验证来源真实性、许可证合规性或命令语义。依赖和工具的采用仍需项目合规审核。

## 校验顺序

1. 读取 `bytes` 或本地 `pathlib.Path`，默认拒绝超过 16 MiB 的产物；
2. 对原始字节计算 SHA-256，与调用方提供的 64 位十六进制摘要进行恒定时间比较；
3. 严格按 UTF-8 JSON 解析，并拒绝重复对象键；
4. 要求 `specVersion` 精确为 `1.6`；
5. 调用现有 `validate_cyclonedx`，复用仓库 schema 与引用完整性检查。

任何一步失败都会抛出 `ExternalGeneratorError`，不返回部分可信结果。

## 静态 fixture

测试中的 `fixture-generator`、`example.invalid` 来源及其参数仅为不可访问的 fixture 数据，不代表真实产品或官方 CLI。单元测试只构造本地字节和临时文件，不访问网络，也不启动外部进程。

## R8 候选准备状态

- 候选工具：`@cyclonedx/cdxgen` / `cdxgen` / `aibom`。
- 样本目录：`docs/acceptance/r8-aibom-external/samples/python-ai-plugin/`。
- 命令与证据清单：[`r8-aibom-external/README.md`](./r8-aibom-external/README.md)。
- 仍缺：固定版本实跑、真实 CycloneDX 1.6 产物、XA-Guard 导入校验输出、artifact hash manifest、真实安装链证据。
