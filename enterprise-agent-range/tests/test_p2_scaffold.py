from __future__ import annotations

import contextlib
import importlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "range_src"))

from enterprise_agent_range import p2
from enterprise_agent_range.cli import main
from enterprise_agent_range.p2 import (
    benchmark,
    dashboard,
    discovery,
    evidence,
    identity,
    permissions,
    registry,
    remediation,
    risk,
    scale,
    schema,
    tenancy,
)
from enterprise_agent_range.p2.base import CapabilityStatus

EXPECTED_KEYS = (
    "tenancy",
    "discovery",
    "identity",
    "permissions",
    "risk",
    "remediation",
    "scale",
    "benchmark",
    "evidence",
    "dashboard",
)

CAPABILITY_MODULES = (
    tenancy,
    discovery,
    identity,
    permissions,
    risk,
    remediation,
    scale,
    benchmark,
    evidence,
    dashboard,
)


class P2RegistryTest(unittest.TestCase):
    def test_registry_covers_exactly_the_ten_capabilities(self) -> None:
        self.assertEqual(len(registry.CAPABILITIES), 10)
        self.assertEqual(registry.capability_keys(), EXPECTED_KEYS)

    def test_all_capabilities_have_valid_status(self) -> None:
        for spec in registry.CAPABILITIES:
            self.assertIn(spec.status, CapabilityStatus.ALL, spec.key)

    def test_each_module_spec_is_self_consistent_and_registered(self) -> None:
        for module in CAPABILITY_MODULES:
            spec = module.SPEC
            self.assertEqual(spec.module, module.__name__)
            self.assertIs(registry.get_capability(spec.key), spec)
            self.assertTrue(spec.title)
            self.assertTrue(spec.summary)
            self.assertTrue(spec.roadmap_refs)

    def test_package_reexports_registry(self) -> None:
        self.assertEqual(p2.CAPABILITIES, registry.CAPABILITIES)
        self.assertEqual(p2.capability_keys(), EXPECTED_KEYS)


class P2SchemaTest(unittest.TestCase):
    def test_planned_fields_match_specs(self) -> None:
        expected = {spec.key: spec.planned_expected_fields for spec in registry.CAPABILITIES}
        self.assertEqual(schema.planned_expected_fields(), expected)
        metrics = {spec.key: spec.planned_metrics for spec in registry.CAPABILITIES}
        self.assertEqual(schema.planned_metrics(), metrics)

    def test_planned_fields_not_wired_into_oracle(self) -> None:
        # Scaffold contract: P2 oracle fields must NOT leak into the live oracle.
        from enterprise_agent_range.oracles import SUPPORTED_EXPECTED_FIELDS

        for name in schema.all_planned_expected_fields():
            self.assertNotIn(name, SUPPORTED_EXPECTED_FIELDS, name)


class P2DecouplingTest(unittest.TestCase):
    def test_no_xa_guard_reference_in_p2_sources(self) -> None:
        p2_dir = Path(p2.__file__).resolve().parent
        for path in sorted(p2_dir.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("xa_guard", text, f"{path.name} must not reference xa_guard")


class P2CliTest(unittest.TestCase):
    def test_p2_status_text_prints_ten_rows(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["p2-status"])
        self.assertEqual(code, 0)
        lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(lines), 10)

    def test_p2_status_json_parses_to_ten_entries(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["p2-status", "--json"])
        self.assertEqual(code, 0)
        rows = json.loads(buffer.getvalue())
        self.assertEqual([row["key"] for row in rows], list(EXPECTED_KEYS))

    def test_p2_package_imports_cleanly(self) -> None:
        # Re-import to confirm the scaffold has no import-time side effects.
        importlib.reload(registry)
        self.assertEqual(len(registry.CAPABILITIES), 10)


if __name__ == "__main__":
    unittest.main()
