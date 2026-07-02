from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "range_src"))

from enterprise_agent_range.p2 import tenancy
from enterprise_agent_range.p2.base import CapabilityStatus


class TenantRegistryRegisterTest(unittest.TestCase):
    def test_register_then_get_round_trips(self) -> None:
        registry = tenancy.TenantRegistry()
        tenant = tenancy.Tenant(tenant_id="t1", display_name="Acme")
        registry.register(tenant)
        self.assertIs(registry.get("t1"), tenant)

    def test_duplicate_register_raises_value_error(self) -> None:
        registry = tenancy.TenantRegistry()
        registry.register(tenancy.Tenant(tenant_id="t1", display_name="Acme"))
        with self.assertRaises(ValueError):
            registry.register(tenancy.Tenant(tenant_id="t1", display_name="Acme Duplicate"))

    def test_get_missing_tenant_raises_key_error(self) -> None:
        registry = tenancy.TenantRegistry()
        with self.assertRaises(KeyError):
            registry.get("missing")

    def test_list_tenants_sorted_by_tenant_id(self) -> None:
        registry = tenancy.TenantRegistry()
        registry.register(tenancy.Tenant(tenant_id="zeta", display_name="Zeta"))
        registry.register(tenancy.Tenant(tenant_id="alpha", display_name="Alpha"))
        registry.register(tenancy.Tenant(tenant_id="mid", display_name="Mid"))
        ids = [t.tenant_id for t in registry.list_tenants()]
        self.assertEqual(ids, ["alpha", "mid", "zeta"])

    def test_list_tenants_empty_registry(self) -> None:
        registry = tenancy.TenantRegistry()
        self.assertEqual(registry.list_tenants(), [])


class IsolateTest(unittest.TestCase):
    def test_isolate_filters_to_single_tenant_preserving_order(self) -> None:
        rows = [
            {"tenant_id": "t1", "value": 1},
            {"tenant_id": "t2", "value": 2},
            {"tenant_id": "t1", "value": 3},
        ]
        result = tenancy.TenantRegistry.isolate("t1", rows)
        self.assertEqual(result, [{"tenant_id": "t1", "value": 1}, {"tenant_id": "t1", "value": 3}])

    def test_isolate_excludes_rows_missing_tenant_id(self) -> None:
        rows = [{"tenant_id": "t1", "value": 1}, {"value": 2}]
        result = tenancy.TenantRegistry.isolate("t1", rows)
        self.assertEqual(result, [{"tenant_id": "t1", "value": 1}])

    def test_isolate_empty_rows(self) -> None:
        self.assertEqual(tenancy.TenantRegistry.isolate("t1", []), [])

    def test_isolate_no_matches_returns_empty(self) -> None:
        rows = [{"tenant_id": "t2", "value": 1}]
        self.assertEqual(tenancy.TenantRegistry.isolate("t1", rows), [])


class CrossTenantViolationsTest(unittest.TestCase):
    def test_flags_foreign_tenant_rows(self) -> None:
        rows = [
            {"tenant_id": "t1", "value": 1},
            {"tenant_id": "t2", "value": 2},
        ]
        result = tenancy.TenantRegistry.cross_tenant_violations("t1", rows)
        self.assertEqual(result, [{"tenant_id": "t2", "value": 2}])

    def test_flags_rows_missing_tenant_id(self) -> None:
        rows = [{"tenant_id": "t1", "value": 1}, {"value": 2}]
        result = tenancy.TenantRegistry.cross_tenant_violations("t1", rows)
        self.assertEqual(result, [{"value": 2}])

    def test_no_violations_when_all_rows_belong_to_tenant(self) -> None:
        rows = [{"tenant_id": "t1", "value": 1}, {"tenant_id": "t1", "value": 2}]
        self.assertEqual(tenancy.TenantRegistry.cross_tenant_violations("t1", rows), [])

    def test_empty_rows_no_violations(self) -> None:
        self.assertEqual(tenancy.TenantRegistry.cross_tenant_violations("t1", []), [])

    def test_isolate_and_violations_partition_all_rows(self) -> None:
        rows = [
            {"tenant_id": "t1", "value": 1},
            {"tenant_id": "t2", "value": 2},
            {"value": 3},
            {"tenant_id": "t1", "value": 4},
        ]
        isolated = tenancy.TenantRegistry.isolate("t1", rows)
        violations = tenancy.TenantRegistry.cross_tenant_violations("t1", rows)
        self.assertEqual(len(isolated) + len(violations), len(rows))


class TenancySpecTest(unittest.TestCase):
    def test_spec_marked_implemented(self) -> None:
        self.assertEqual(tenancy.SPEC.status, CapabilityStatus.IMPLEMENTED)
        self.assertEqual(tenancy.SPEC.key, "tenancy")
        self.assertEqual(tenancy.SPEC.module, tenancy.__name__)


if __name__ == "__main__":
    unittest.main()
