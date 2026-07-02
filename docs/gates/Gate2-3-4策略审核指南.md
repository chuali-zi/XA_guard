# Gate2/3/4 策略合规审核指南

> 给组员用的傻瓜版审核手册。主要审核**策略是否合规、依据是否充分、证据是否完整**；代码只作为辅助验证，不是本次审核重点。

## 0. 先记住结论

当前 Gate2/3/4 的策略数量基本够用。审核重点不是“代码写得怎么样”，而是：

1. 每条策略有没有明确法规、标准、文献或项目依据。
2. 风险等级是不是合理，能不能解释为什么是 green / yellow / red。
3. 工具能力声明是否符合真实风险，比如外网、执行、写文件、权限变更有没有标出来。
4. Gate3 规则有没有证明材料：正例、反例、bench case、`policy_refs`。
5. 策略有没有夸大宣传，比如把 demo 口径说成真实模型评测或 L3 政企落地。

不要一上来就加新规则。先判断已有策略是否“合规、可信、能解释”。

## 1. 为什么要审核

比赛看的是“实际效果、技术创新、方案完整性、应用价值”，不是 YAML 数量。策略如果没有合规依据，写再多也很难答辩。

如果只加规则但不做合规审核，会有这些问题：

- 规则写着“符合国标”，但找不到具体标准或条款。
- 风险分级说不清，评委问“为什么这个工具是 red”时答不上来。
- 工具能力漏标，例如插件安装明明可能执行代码，却没有标 `EXEC`。
- 策略只拦截危险样例，没有正常反例，无法证明误报可控。
- bench 没有样例，答辩时说不清“这条策略怎么证明有效”。
- 文档口径过大，把规则链路 + mock executor 说成真实模型或真实政企系统。

审核的目标是让策略变成“有依据、能解释、有样例、可复查”的合规证据链。

## 2. 审核范围

本次只审核 Gate2 / Gate3 / Gate4 的**策略合规性**：

| 关卡 | 干什么 | 主要文件 |
|---|---|---|
| Gate2 | 工具风险分级策略，决定什么工具低危/中危/高危 | `policies/baseline/gate4_capabilities.yaml` 的 `risk_level` |
| Gate3 | 法规、国标、企业规则策略，决定 deny / approval / warn | `policies/baseline/gate3_rules.yaml` |
| Gate4 | 工具能力和数据密级策略，决定数据能不能流向某工具 | `policies/baseline/gate4_capabilities.yaml`、`policies/baseline/gate4_sensitive_patterns.yaml` |

一起看的支撑文件：

| 文件 | 用途 |
|---|---|
| `bench/.log/tool_gate_coverage.md` | 工具 x Gate 覆盖矩阵，先看这里找缺口 |
| `bench/cases/csab-gov-mini-seed.yaml` | bench 样例，总共 290 条 |
| `docs/gates/规则测试样例约定.md` | Gate3 规则正例/反例怎么写 |
| `docs/gates/risk_classification_basis.md` | risk_level 分级依据 |
| `docs/source-of-truth/事实源.md` | 项目事实口径和纠偏依据 |
| `docs/planning/PRD.md` | 验收目标、KPI 和交付标准 |
| `status.md` | 当前仓库状态和已知缺口 |
| `log.md` | 工作日志，记录你实际做了什么 |

代码文件只在需要理解运行语义时看，例如 `src/xa_guard/gates/*.py`。不要把代码 review 当成本次主任务。

## 3. 审核前先看这 5 个文件

按顺序看，不要跳：

1. `docs/planning/PRD.md`
   看比赛验收目标，尤其是 4 个方向、Policy DSL、三色污点、审计证据和 L3 政企目标。

2. `docs/gates/risk_classification_basis.md`
   看工具风险等级为什么这么分。审核 risk_level 时优先参考这里。

3. `status.md`
   看当前仓库真实状态，尤其是“测试状态”“策略目录结构”“逐关卡状态”“下一步优先级”。

4. `bench/.log/tool_gate_coverage.md`
   看当前工具是否缺登记，哪些 Gate3 trigger 没有 bench case。

5. `policies/baseline/gate3_rules.yaml` 和 `policies/baseline/gate4_capabilities.yaml`
   一个看法规策略，一个看工具风险和能力边界。

看完这 5 个文件再开始审核，不然容易只盯代码细节，忽略合规依据。

## 4. 当前已知事实

截至 2026-07-01，本仓库当前口径是：

| 项 | 当前值 |
|---|---:|
| Gate3 规则 | 32 条 |
| Gate3 trigger | 45 个 |
| Gate4 工具能力登记 | 52 个 |
| Gate2 layered 派生工具风险 | 52 个 |
| bench-only 工具 | 0 个 |
| Gate3 trigger 无 bench case | 24 个 |

当前审核提醒：

- Gate3 32 条 baseline 规则已有正例/反例 fixtures 强约束。
- 覆盖矩阵仍显示 24 个 Gate3 trigger 没有进入 `csab-gov-mini-seed.yaml` bench case。
- 这 24 个不是“规则没写”，而是“答辩/评测证据还不够完整”。
- 本轮审核要重点判断这些缺口是否影响合规叙事，哪些需要优先补 bench case。

## 5. 怎么审核 Gate2 风险分级是否合规

Gate2 审核目标：确认每个工具的风险等级有依据、能解释、和工具能力匹配。

### 5.1 看哪里

主要看策略文件：

- `policies/baseline/gate4_capabilities.yaml`
- `bench/.log/tool_gate_coverage.md`
- `docs/gates/risk_classification_basis.md`

注意：`policies/baseline/gate2_tool_risks.yaml` 已废弃，只保留给 legacy 测试兼容。不要把它当新的事实源。

### 5.2 查什么

逐项检查：

1. 工具是否在 `gate4_capabilities.yaml` 登记。
2. `risk_level` 是否只能是 `green`、`yellow`、`red`。
3. 这个等级是否符合工具真实能力。
4. 这个等级是否能用 `docs/gates/risk_classification_basis.md` 或同类工具解释。
5. red 工具是否确实属于高危动作，例如执行命令、删数据、改权限、插件安装、模型训练/部署。
6. yellow 工具是否只是中等风险，例如外发通知、写文件、跨域调用，但不是直接破坏核心系统。
7. green 工具是否基本只读、低风险。

### 5.3 怎么判断风险等级

傻瓜判断：

| risk_level | 适合什么工具 | 例子 |
|---|---|---|
| green | 只读、内部查询、不会改状态 | `get_cpu`、`list_servers` |
| yellow | 会写文件、外发通知、跨域但不是核心破坏 | `send_email`、`write_file` |
| red | 命令执行、删数据、改权限、训练/部署模型、插件安装 | `exec_command`、`delete_file`、`install_plugin` |

审核时要写出一句解释，例如：

```text
install_plugin = red，因为它会引入外部代码和依赖，并可能具备网络、写文件、执行能力，属于供应链入口。
```

参考依据：

- `docs/gates/risk_classification_basis.md`
- `policies/baseline/gate4_capabilities.yaml` 里同类工具的现有分级。

## 6. 怎么审核 Gate3 规则是否合规

Gate3 审核目标：确认每条规则不是“拍脑袋写的”，而是有标准来源、有清楚边界、有证据样例。

### 6.1 看哪里

主要看策略和证据：

- `policies/baseline/gate3_rules.yaml`
- `bench/cases/csab-gov-mini-seed.yaml`
- `docs/gates/规则测试样例约定.md`
- `docs/planning/PRD.md`
- `docs/source-of-truth/事实源.md`

辅助看：

- `tests/unit/test_gate3.py`

### 6.2 每条规则查什么

对每条规则照这个表检查：

| 检查项 | 必须有吗 | 怎么看 |
|---|---|---|
| `id` | 必须 | 规则唯一 ID，不能重复 |
| `name` | 必须 | 人能看懂这条规则干什么 |
| `source` | 必须 | 来自哪个标准、法规、文献或安全依据 |
| `triggers` | 必须 | 规则会检查哪些工具 |
| `predicate` | 必须 | 命中条件，不能太泛 |
| `enforce` | 必须 | `allow` / `warn` / `deny` / `require_approval` |
| `severity` | 必须 | `low` / `medium` / `high` / `critical` |
| 合规解释 | 必须 | 能用一句话说明为什么要有这条规则 |
| 正例 | 必须补 | 危险场景能命中 |
| 反例 | 必须补 | 正常相邻场景不误伤 |
| bench case | 高价值规则必须补 | 用于答辩和指标证明 |

审核时最重要的是 `source` 和合规解释。没有来源的规则，不要算合规。

### 6.3 正例怎么审

正例要证明“该拦的能拦住”，并且要能对应合规要求。

例子：

```yaml
tool_name: update_audit_policy
arguments:
  retention_days: 30
expected_decision: deny
policy_refs:
  - CSL-LOG-RETENTION-6M
```

这个正例证明：日志留存少于 180 天时，应命中 `CSL-LOG-RETENTION-6M` 并 deny。审核时还要看它的 `source_documents` 或 `source` 是否能解释“为什么是六个月”。

### 6.4 反例怎么审

反例要证明“正常合规的不要误伤”。

例子：

```yaml
tool_name: update_audit_policy
arguments:
  retention_days: 365
expected_decision: allow
policy_refs:
  - CSL-LOG-RETENTION-6M
```

这个反例证明：日志留存 365 天时，不应该命中“少于六个月”的阻断规则。

### 6.5 不合格规则长什么样

看到这些情况要标红：

- `predicate` 只写了很宽泛的关键词，容易误伤。
- `source` 写得很虚，例如“安全要求”，没有具体标准或依据。
- 规则名很像合规要求，但找不到标准、PRD 或事实源支撑。
- 只有正例，没有反例。
- `triggers` 里的工具不在 Gate4 总账。
- `enforce` 和风险严重度不匹配，例如高危命令只 warn。
- bench case 里 `policy_refs` 没写规则 ID。
- 规则实际是 Gate1 输入攻击检测，但硬塞进 Gate3，关卡职责混乱。

## 7. 怎么审核 Gate4 工具能力和数据流是否合规

Gate4 审核目标：确认工具能力声明和数据密级边界符合政企安全要求，不让内部/机密数据随便流出。

### 7.1 看哪里

主要看策略文件：

- `policies/baseline/gate4_capabilities.yaml`
- `policies/baseline/gate4_sensitive_patterns.yaml`

### 7.2 每个工具查什么

每个工具必须有：

```yaml
tool_name: xxx
capabilities: [...]
input_max_taint: PUBLIC | INTERNAL | CONFIDENTIAL
output_taint: PUBLIC | INTERNAL | CONFIDENTIAL
risk_level: green | yellow | red
```

逐项解释：

| 字段 | 意思 | 审核重点 |
|---|---|---|
| `tool_name` | 工具名 | 必须和 Gate3 trigger、bench tool_name 一致 |
| `capabilities` | 工具能力 | 外网、执行、写文件、权限管理等必须写清 |
| `input_max_taint` | 最高允许输入密级 | 外网工具通常不能接 CONFIDENTIAL |
| `output_taint` | 工具输出密级 | 数据导出、训练、内部查询通常不是 PUBLIC |
| `risk_level` | 风险等级 | 这是 Gate2 派生来源 |

审核时要特别看“能力有没有漏标”。例如：

| 工具类型 | 必须重点检查 |
|---|---|
| 外发工具 | 是否有 `NETWORK_EXTERNAL` 或 `NOTIFY` |
| 命令执行工具 | 是否有 `EXEC`，risk 是否为 red |
| 文件写入工具 | 是否有 `FS_WRITE` |
| 数据导出工具 | 是否有 `DATA_EXPORT`，输出是否可能是 CONFIDENTIAL |
| 插件安装工具 | 是否有外网、写文件、执行或数据采集能力 |
| 权限管理工具 | 是否有 `AUTHZ_ADMIN`，risk 是否为 red |

### 7.3 污点等级怎么理解

| taint | 人话解释 | 例子 |
|---|---|---|
| PUBLIC | 公开信息 | 普通用户输入、公开网页 |
| INTERNAL | 内部信息 | 内部知识库、运维日志 |
| CONFIDENTIAL | 机密信息 | 密码、密钥、手机号、银行卡、医疗健康、金融账户 |

合规审核原则：

- 机密数据不能流向外网工具。
- 未登记工具按 fail-closed 处理。
- 有 `NETWORK_EXTERNAL` 或 `NOTIFY` 的工具要格外小心。
- `install_plugin` 这类会引入外部代码和执行权限的工具应保持 red。
- 能力声明要宁可保守，不要为了好看而低估风险。

## 8. 覆盖矩阵怎么用于合规审核

先运行：

```powershell
python scripts/generate_tool_gate_coverage_matrix.py --strict
```

然后打开：

```text
bench/.log/tool_gate_coverage.md
```

重点看 Summary，它回答的是“策略有没有漏登记、有没有不一致”：

| 指标 | 合格目标 |
|---|---|
| `Gate3 triggers missing Gate2 registration` | 必须是 0 |
| `Gate3 triggers missing Gate4 registration` | 必须是 0 |
| `Gate2/Gate4 risk mismatches` | 必须是 0 |
| `Bench-only tools` | 最好是 0 |
| `Gate3 trigger tools without bench case` | 当前不是 0，要逐步补 |

当前可以接受的状态：

- missing Gate2/Gate4 是 0。
- risk mismatch 是 0。
- bench-only 是 0。
- 还有 23 个 `NO_BENCH_CASE`，这是后续补合规证据任务。

## 9. 命令怎么跑

命令不是本次主任务，但可以帮你确认策略文件没有明显断裂。

### 9.1 先跑覆盖矩阵

```powershell
python scripts/generate_tool_gate_coverage_matrix.py --strict
```

通过才继续。

### 9.2 可选：跑 Gate2/3/4 相关测试

```powershell
$env:PYTHONPATH='src'
python -m pytest -q --basetemp pytest_tmp_gate234_review -p no:cacheprovider tests\unit\test_gate2.py tests\unit\test_gate3.py tests\unit\test_gate4.py tests\test_tool_gate_coverage_matrix.py -x --tb=short
```

如果测试失败，不要直接改测试。先判断失败是策略问题、样例问题还是测试口径问题，并写进审核结果。只有负责人确认“测试本身过时”后，才能修改测试。

### 9.3 跑 bench 资产校验

```powershell
python scripts/validate_csab_gov_mini.py --strict
```

如果这个失败，先看报错字段。不要为了通过校验删除 case 或删规则。

## 10. 审核结果怎么写

每次审核交一个小结，按这个模板写：

````markdown
## Gate2/3/4 审核结果

审核人：
日期：YYYY-MM-DD

### 1. 本次看了哪些策略文件和依据文件
- status.md
- bench/.log/tool_gate_coverage.md
- policies/baseline/gate3_rules.yaml
- policies/baseline/gate4_capabilities.yaml
- docs/gates/risk_classification_basis.md
- docs/planning/PRD.md

### 2. 覆盖矩阵结果
- total_tools:
- gate2:
- gate3_triggers:
- gate4:
- bench_only:
- gate3_no_bench:

### 3. 合规审核结论
- Gate2 风险分级是否合理：
- Gate3 规则来源是否充分：
- Gate4 工具能力和污点边界是否合理：
- bench 证据是否足够：

### 4. 发现的问题
1. ...
2. ...

### 5. 不建议现在做的事
- 不建议继续横向加规则，除非有明确标准来源、正例、反例和 bench case。

### 6. 建议下一步
1. ...
2. ...

### 7. 跑过的命令和结果
```text
命令：
结果：
```
````

## 11. 完成目标

本轮审核完成的标准：

1. 你能说清楚 Gate2/3/4 每一类策略的合规作用。
2. 你能解释风险等级唯一事实源在 `gate4_capabilities.yaml`，并能说明主要 red/yellow/green 工具为什么这么分。
3. 你能指出每条 Gate3 规则有没有明确 `source`，哪些规则证据不足。
4. 你能指出当前覆盖矩阵里的主要缺口是 23 个 `NO_BENCH_CASE`。
5. 你能把每条新增/修改规则对应到合规来源、正例、反例、bench case 和 `policy_refs`。
6. 你能写出一份审核小结，里面有合规结论、问题、风险、下一步，不只是命令结果。

如果这些都做到了，就算完成审核。

## 12. 审核时的红线

- 不要为了测试通过而随便改测试。
- 不要删除 bench case 来减少失败。
- 不要把 `risk_level` 同时写在多个事实源里。
- 不要新增没有 source 的规则。
- 不要新增没有正例/反例的规则。
- 不要把“看起来合理”的规则当成合规规则，必须能说出依据。
- 不要把 mock bench 指标说成真实模型指标。
- 不要把当前 demo MVP 说成已经达到 PRD L3 政企原型。

## 13. 参考文档

优先级从高到低：

1. `docs/source-of-truth/XA-202620中国雄安集团数字城市科技有限公司-面向政企场景的大模型智能体安全关键技术研究比赛方案.pdf`
2. `docs/source-of-truth/事实源.md`
3. `docs/planning/PRD.md`
4. `status.md`
5. `docs/gates/规则测试样例约定.md`
6. `docs/gates/risk_classification_basis.md`
7. `bench/.log/tool_gate_coverage.md`
