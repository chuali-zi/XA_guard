"""单元测试 — LayeredPolicySource（双层策略 + 单调性 + bundle_sha + 热加载）。

覆盖：
1. baseline-only 加载（manifest 指向 4 个 yaml，统计规则/工具/敏感词 baseline）
2. overlay 命名空间检查（rule.id 必须以 tenant::<id>:: 开头）
3. overlay 不能覆盖 baseline 同名 rule.id
4. overlay 不能弱化 tool_risks（red→green/yellow→green 拒）
5. overlay 不能放宽 tool_capabilities.input_max_taint
6. overlay 可以 ADD 新工具 / 新敏感词 / 新规则
7. predicate_safe overlay AST 白名单拒不安全表达式
8. bundle_sha 变化反映文件内容变化
9. reload() 接受新合法 overlay；拒绝违例 overlay 保留旧 snapshot
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from xa_guard.policy.layered import LayeredPolicySource, set_global_source
from xa_guard.policy.monotonicity import (
    PolicyViolationError,
    check_rules,
    check_sensitive_patterns,
    check_tool_capabilities,
    check_tool_risks,
)
from xa_guard.policy.predicate_safe import UnsafePredicateError, compile_for_tier
from xa_guard.types import PolicyRule, RiskLevel, TaintLabel, ToolCapability, Decision


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GATE3_RULES = PROJECT_ROOT / "policies" / "baseline" / "gate3_rules.yaml"


def _baseline_rule_count() -> int:
    data = yaml.safe_load(GATE3_RULES.read_text(encoding="utf-8")) or {}
    return len(data.get("rules", []) or [])


# ────────────────────────────────────────────────────────────
# fixtures
# ────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _isolate_global_source():
    """每个用例结束清理全局 source，避免跨测试污染。"""
    yield
    set_global_source(None)


@pytest.fixture
def baseline_src() -> LayeredPolicySource:
    return LayeredPolicySource(
        manifest_path="policies/baseline/manifest.yaml",
        overlay_root=None,  # 不要加载 overlay 目录
        project_root=PROJECT_ROOT,
    )


def _write_overlay(root: Path, tenant_id: str, **files: str) -> None:
    d = root / tenant_id
    d.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (d / name).write_text(content, encoding="utf-8")


# ────────────────────────────────────────────────────────────
# 1. baseline-only
# ────────────────────────────────────────────────────────────
def test_baseline_loads_current_rules(baseline_src):
    rules = baseline_src.get_policy_rules()
    assert len(rules) == _baseline_rule_count()
    # baseline 规则 id 与现有测试一致（不带 tenant:: 前缀）
    assert any(r.id == "GBT-22239-8.1.4.5" for r in rules)


def test_baseline_loads_tool_risks(baseline_src):
    risks = baseline_src.get_tool_risks()
    assert risks["exec_command"] == RiskLevel.RED
    assert risks["get_cpu"] == RiskLevel.GREEN


def test_baseline_loads_capabilities(baseline_src):
    caps = baseline_src.get_tool_capabilities()
    assert "send_email" in caps
    assert caps["send_email"].input_max_taint == TaintLabel.INTERNAL


def test_baseline_loads_sensitive_pattern(baseline_src):
    pat = baseline_src.get_sensitive_pattern()
    assert pat is not None
    assert pat.search("user 身份证 = 123") is not None
    assert pat.search("AKIAIOSFODNN7EXAMPLE") is not None


@pytest.mark.parametrize(
    "sample",
    [
        "身份证号 110105199001011234",
        "手机号 13800138000",
        "统一社会信用代码 91350211M000100Y43",
        "Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature",
        "-----BEGIN PRIVATE KEY-----",
        "密级：机密★10年",
        "内部资料，严禁外传",
    ],
)
def test_baseline_sensitive_pattern_matches_structured_samples(baseline_src, sample):
    pat = baseline_src.get_sensitive_pattern()
    assert pat is not None
    assert pat.search(sample) is not None


def test_baseline_gate3_triggers_have_gate2_and_gate4_profiles(baseline_src):
    """Every Gate3 baseline trigger must have a Gate2 risk and Gate4 capability profile."""
    triggers = {trigger for rule in baseline_src.get_policy_rules() for trigger in rule.triggers}
    risks = baseline_src.get_tool_risks()
    caps = baseline_src.get_tool_capabilities()

    missing_risks = sorted(triggers - set(risks))
    missing_caps = sorted(triggers - set(caps))

    assert missing_risks == []
    assert missing_caps == []


def test_baseline_high_risk_tools_are_not_green(baseline_src):
    """政企 baseline 中会改变权限、审计、模型或数据边界的工具不得默认为 green。"""
    risks = baseline_src.get_tool_risks()
    high_risk_tools = {
        "admin_action",
        "delete_file",
        "deploy_model",
        "deploy_system",
        "drop_table",
        "exec_command",
        "export_database",
        "fine_tune_model",
        "grant_permission",
        "import_training_data",
        "ingest_training_data",
        "log_cleanup",
        "publish_system",
        "train_model",
        "update_audit_policy",
        "update_backup_policy",
        "update_encryption_policy",
        "update_model",
        "update_user_role",
    }

    assert all(risks[tool] != RiskLevel.GREEN for tool in high_risk_tools)


def test_baseline_gate2_and_gate4_risk_levels_match(baseline_src):
    risks = baseline_src.get_tool_risks()
    caps = baseline_src.get_tool_capabilities()

    shared = sorted(set(risks) & set(caps))
    mismatched = [
        tool
        for tool in shared
        if caps[tool].risk_level != risks[tool]
    ]

    assert mismatched == []


def test_baseline_external_tools_reject_confidential_input(baseline_src):
    caps = baseline_src.get_tool_capabilities()
    external_tools = [
        name
        for name, cap in caps.items()
        if "NETWORK_EXTERNAL" in cap.capabilities or "NOTIFY" in cap.capabilities
    ]

    assert external_tools
    assert all(caps[name].input_max_taint != TaintLabel.CONFIDENTIAL for name in external_tools)


def test_baseline_model_calls_are_treated_as_external_boundary(baseline_src):
    cap = baseline_src.get_tool_capabilities()["call_model"]
    assert "NETWORK_EXTERNAL" in cap.capabilities
    assert cap.input_max_taint == TaintLabel.INTERNAL


def test_bundle_sha_is_stable_for_same_files(baseline_src):
    s1 = baseline_src.bundle_sha
    # 重新加载（相同文件）→ 同样的 bundle_sha
    baseline_src.reload()
    assert baseline_src.bundle_sha == s1
    assert len(s1) == 64  # sha256 hex


# ────────────────────────────────────────────────────────────
# 2/3. namespace + 覆盖检查
# ────────────────────────────────────────────────────────────
def test_overlay_rule_id_namespace_enforced(tmp_path: Path):
    overlay_root = tmp_path / "overlay"
    _write_overlay(
        overlay_root, "acme",
        **{
            "policy.yaml": """
rules:
  - id: "no-prefix-rule"
    name: bad
    source: x
    triggers: []
    predicate: "tool == 'noop'"
    enforce: warn
""",
        },
    )
    src = LayeredPolicySource(
        manifest_path="policies/baseline/manifest.yaml",
        overlay_root=str(overlay_root),
        project_root=PROJECT_ROOT,
    )
    # 'acme' 因为命名空间未对齐被拒绝
    assert "acme" in src.overlay_rejections
    assert "tenant::acme::" in src.overlay_rejections["acme"]
    # baseline 仍正常加载
    assert len(src.get_policy_rules()) == _baseline_rule_count()


def test_overlay_cannot_override_baseline_rule_id(tmp_path: Path):
    overlay_root = tmp_path / "overlay"
    # 故意撞 baseline 的 rule.id
    _write_overlay(
        overlay_root, "acme",
        **{
            "policy.yaml": """
rules:
  - id: "GBT-22239-8.1.4.5"
    name: hijack
    source: bad
    triggers: [exec_command]
    predicate: "False"
    enforce: allow
""",
        },
    )
    src = LayeredPolicySource(
        manifest_path="policies/baseline/manifest.yaml",
        overlay_root=str(overlay_root),
        project_root=PROJECT_ROOT,
    )
    assert "acme" in src.overlay_rejections
    assert "GBT-22239-8.1.4.5" in src.overlay_rejections["acme"]


# ────────────────────────────────────────────────────────────
# 4. tool_risks 弱化
# ────────────────────────────────────────────────────────────
def test_overlay_cannot_weaken_tool_risk():
    base = {"exec_command": RiskLevel.RED, "send_email": RiskLevel.YELLOW}
    overlay = {"exec_command": RiskLevel.GREEN}  # 红 → 绿
    rep = check_tool_risks(base, overlay)
    assert not rep.ok
    assert any("exec_command" in v and "weakened" in v for v in rep.violations)


def test_overlay_can_keep_or_raise_tool_risk():
    base = {"exec_command": RiskLevel.RED}
    overlay = {"exec_command": RiskLevel.RED, "new_tool": RiskLevel.YELLOW}
    assert check_tool_risks(base, overlay).ok


# ────────────────────────────────────────────────────────────
# 5. tool_capabilities 放宽
# ────────────────────────────────────────────────────────────
def test_overlay_cannot_relax_input_max_taint():
    base = {
        "post_url": ToolCapability(
            tool_name="post_url",
            capabilities=["NETWORK_EXTERNAL"],
            input_max_taint=TaintLabel.PUBLIC,
            output_taint=TaintLabel.PUBLIC,
            risk_level=RiskLevel.YELLOW,
        )
    }
    overlay = {
        "post_url": ToolCapability(
            tool_name="post_url",
            capabilities=["NETWORK_EXTERNAL"],
            input_max_taint=TaintLabel.CONFIDENTIAL,  # 故意放宽
            output_taint=TaintLabel.PUBLIC,
            risk_level=RiskLevel.YELLOW,
        )
    }
    rep = check_tool_capabilities(base, overlay)
    assert not rep.ok
    assert any("input_max_taint relaxed" in v for v in rep.violations)


# ────────────────────────────────────────────────────────────
# 6. overlay ADD 路径
# ────────────────────────────────────────────────────────────
def test_overlay_can_add_new_rules_and_tools(tmp_path: Path):
    overlay_root = tmp_path / "overlay"
    _write_overlay(
        overlay_root, "acme",
        **{
            "policy.yaml": """
rules:
  - id: "tenant::acme::COMPETITOR-DENY"
    name: 禁访竞品
    source: acme-sec
    triggers: [post_url]
    predicate: "tool == 'post_url' and contains('url', 'evil.com')"
    enforce: deny
    severity: high
""",
            "tool_risks.yaml": """
tool_risks:
  acme_internal_hr: yellow
""",
            "sensitive_patterns.yaml": """
patterns:
  - "ACME-机密"
""",
        },
    )
    src = LayeredPolicySource(
        manifest_path="policies/baseline/manifest.yaml",
        overlay_root=str(overlay_root),
        project_root=PROJECT_ROOT,
    )
    assert "acme" not in src.overlay_rejections
    rules = src.get_policy_rules()
    assert len(rules) == _baseline_rule_count() + 1
    assert any(r.id == "tenant::acme::COMPETITOR-DENY" for r in rules)

    risks = src.get_tool_risks()
    assert risks["acme_internal_hr"] == RiskLevel.YELLOW

    pat = src.get_sensitive_pattern()
    assert pat.search("这条含 ACME-机密 字样")


# ────────────────────────────────────────────────────────────
# 7. predicate_safe AST 白名单
# ────────────────────────────────────────────────────────────
def test_overlay_predicate_rejects_unsafe_ast():
    # 试图 import 或 __import__ 都应被拒
    with pytest.raises(UnsafePredicateError):
        compile_for_tier("__import__('os').system('ls')", tier="overlay")


def test_overlay_predicate_rejects_lambda():
    with pytest.raises(UnsafePredicateError):
        compile_for_tier("(lambda x: x)(1) == 1", tier="overlay")


def test_overlay_predicate_accepts_safe_expr():
    fn = compile_for_tier("tool == 'noop' and contains('msg', 'x')", tier="overlay")
    # 给个空 ctx 也不该崩
    from xa_guard.types import GateContext

    assert fn(GateContext(tool_name="noop", arguments={"msg": "x"})) is True
    assert fn(GateContext(tool_name="other", arguments={"msg": "x"})) is False


def test_baseline_predicate_still_uses_legacy_eval():
    # baseline tier 路径不走 AST 白名单（项目自身可信），保持向后兼容
    fn = compile_for_tier("tool == 'a' or tool == 'b'", tier="baseline")
    from xa_guard.types import GateContext

    assert fn(GateContext(tool_name="a"))
    assert not fn(GateContext(tool_name="c"))


# ────────────────────────────────────────────────────────────
# 8. bundle_sha 变化
# ────────────────────────────────────────────────────────────
def test_bundle_sha_changes_when_overlay_added(tmp_path: Path):
    overlay_root = tmp_path / "overlay"
    overlay_root.mkdir()
    src = LayeredPolicySource(
        manifest_path="policies/baseline/manifest.yaml",
        overlay_root=str(overlay_root),
        project_root=PROJECT_ROOT,
    )
    sha_before = src.bundle_sha

    _write_overlay(
        overlay_root, "newtenant",
        **{
            "policy.yaml": """
rules:
  - id: "tenant::newtenant::LOG-AUDIT"
    name: audit
    source: newtenant
    triggers: []
    predicate: "False"
    enforce: warn
"""
        },
    )
    assert src.reload()
    assert src.bundle_sha != sha_before


# ────────────────────────────────────────────────────────────
# 9. reload fail-safe
# ────────────────────────────────────────────────────────────
def test_reload_keeps_old_snapshot_on_bad_overlay(tmp_path: Path):
    overlay_root = tmp_path / "overlay"
    overlay_root.mkdir()
    src = LayeredPolicySource(
        manifest_path="policies/baseline/manifest.yaml",
        overlay_root=str(overlay_root),
        project_root=PROJECT_ROOT,
    )
    rules_before = len(src.get_policy_rules())

    # 写一个会触发 monotonicity 违例的 overlay
    _write_overlay(
        overlay_root, "evil",
        **{
            "policy.yaml": """
rules:
  - id: "GBT-22239-8.1.4.5"
    name: hijack baseline
    source: x
    triggers: []
    predicate: "False"
    enforce: allow
"""
        },
    )
    ok = src.reload()
    # reload 本身成功（个别 overlay 被拒不导致整批 reload 失败）；但 evil 进 rejections
    assert ok
    assert "evil" in src.overlay_rejections
    # baseline 仍在
    assert len(src.get_policy_rules()) == rules_before


# ────────────────────────────────────────────────────────────
# 10. monotonicity 单元
# ────────────────────────────────────────────────────────────
def test_sensitive_patterns_overlay_rejects_duplicates():
    rep = check_sensitive_patterns(["密码"], ["密码", "新词"])
    assert not rep.ok
    assert any("密码" in v for v in rep.violations)


def test_sensitive_patterns_overlay_accepts_pure_additions():
    assert check_sensitive_patterns(["密码"], ["新词1", "新词2"]).ok


def test_rule_check_rejects_baseline_id_in_overlay():
    base_rule = PolicyRule(
        id="base-r1", name="b", source="x", triggers=[],
        predicate="False", enforce=Decision.ALLOW,
    )
    bad_overlay = PolicyRule(
        id="base-r1", name="bad", source="x", triggers=[],
        predicate="False", enforce=Decision.ALLOW,
    )
    rep = check_rules([base_rule], [bad_overlay], tenant_id="acme")
    assert not rep.ok


def test_policy_violation_error_raised_on_request():
    bad_rule = PolicyRule(
        id="x", name="x", source="x", triggers=[],
        predicate="False", enforce=Decision.ALLOW,
    )
    rep = check_rules([], [bad_rule], tenant_id="acme")
    with pytest.raises(PolicyViolationError):
        rep.raise_if_violated()
