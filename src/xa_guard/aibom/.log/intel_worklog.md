# intel.py 工作日志

## 2026-06-05

**任务**: 实现离线漏洞+信誉情报模块 `intel.py`

**完成内容**:
- 创建 `src/xa_guard/aibom/intel.py`：`ThreatIntel` 类，提供 `lookup(name, version)` 和 `scan_dependencies(deps)` 接口
- 创建 `data/vulndb.json`：OSV 风格种子库，7个包，10条 CVE（urllib3×3, requests×2, pyyaml×2, pillow×1, cryptography×1, setuptools×1, aiohttp×1）
- 创建 `data/reputation.json`：18个包信誉条目 + default 兜底
- 创建 `tests/unit/test_aibom_intel.py`：26个测试，全绿

**核心逻辑**:
- PEP440 版本比较：纯 stdlib，parse → int tuple，`introduced<=v<fixed`
- 未固定版本（非 ==）: status="potentially_affected"
- max_severity 按 critical>high>medium>low>info>unknown>none 排序

**结果**: 26 passed in 0.07s，零网络调用
