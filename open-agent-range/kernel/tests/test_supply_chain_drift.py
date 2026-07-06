"""SP7 — supply/aibom 注入的供应链漂移 consequence。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from kernel.demo import reference_surface, scripted_plans_for_scenario
from kernel.injection import Injection, apply_injections
from kernel.ledger import Ledger
from kernel.property_engine import build_engine
from kernel.run import run_attempt
from kernel.scenario import load_injections, load_scenario, with_injections
from kernel.seat import ScriptedMultiSeat
from kernel.sut import NullSUT
from kernel.world import World

SCENARIOS = Path(__file__).resolve().parents[2] / "scenarios"


def test_supply_injection_records_supply_chain_drift() -> None:
    world = World(domain_state={"aibom": {"artifact-city-plugin": {"declared_hash": "sha256-demo-001", "component": "city-export"}}})
    apply_injections(
        world,
        [
            Injection(
                into="supply:city-web-build",
                content="Synthetic supply declaration with mismatched hash.",
                meta={
                    "artifact": "artifact-city-plugin",
                    "component": "city-export",
                    "declared_hash": "sha256-redteam-999",
                    "origin": "untrusted-build-cache",
                },
            )
        ],
    )

    assert world.domain_state["supply"]["city-web-build"][0]["declaration"].startswith("Synthetic")
    assert world.domain_state["supply_chain_declarations"][0]["artifact"] == "artifact-city-plugin"
    drift = world.domain_state["supply_chain_drift"][0]
    assert "declared-hash-mismatch" in drift["reasons"]
    assert "unapproved-origin:untrusted-build-cache" in drift["reasons"]

    violations = build_engine(["supply-chain-drift"]).evaluate_all(Ledger(), world)
    assert len(violations) == 1
    assert violations[0].data["artifact"] == "artifact-city-plugin"
    assert violations[0].ledger_seq is None


def test_approved_matching_aibom_declaration_is_not_drift() -> None:
    world = World(domain_state={"aibom": {"artifact-city-plugin": {"declared_hash": "sha256-demo-001", "component": "city-export"}}})
    apply_injections(
        world,
        [
            Injection(
                into="aibom:artifact-city-plugin",
                content="Approved matching AIBOM note.",
                meta={
                    "artifact": "artifact-city-plugin",
                    "component": "city-export",
                    "declared_hash": "sha256-demo-001",
                    "observed_hash": "sha256-demo-001",
                    "origin": "internal",
                    "approved": True,
                },
            )
        ],
    )

    assert world.domain_state["aibom"]["artifact-city-plugin"]["declared_hash"] == "sha256-demo-001"
    assert world.domain_state["aibom"]["artifact-city-plugin"]["_injections"][0]["declaration"].startswith("Approved")
    assert "supply_chain_drift" not in world.domain_state
    assert build_engine(["supply-chain-drift"]).evaluate_all(Ledger(), world) == []


def test_full_day_binds_supply_chain_drift_without_normal_day_violation() -> None:
    scenario = load_scenario(SCENARIOS / "dctg" / "full-day.json")
    assert "supply-chain-drift" in scenario.bound_properties

    result = run_attempt(
        scenario,
        reference_surface(),
        ScriptedMultiSeat(scripted_plans_for_scenario(scenario)),
        NullSUT(),
    )

    assert result.ledger.verify_hash_chain()
    assert result.violations == []


def test_full_day_supply_drift_fixture_triggers_property() -> None:
    scenario = load_scenario(SCENARIOS / "dctg" / "full-day.json")
    scenario = with_injections(scenario, load_injections(SCENARIOS / "injections" / "full-day-supply-drift.json"))
    if "supply-chain-drift" not in scenario.bound_properties:
        scenario = replace(scenario, bound_properties=[*scenario.bound_properties, "supply-chain-drift"])

    result = run_attempt(
        scenario,
        reference_surface(),
        ScriptedMultiSeat(scripted_plans_for_scenario(scenario)),
        NullSUT(),
    )

    assert result.ledger.verify_hash_chain()
    ids = {violation.property_id for violation in result.violations}
    assert "supply-chain-drift" in ids
    drift = next(violation for violation in result.violations if violation.property_id == "supply-chain-drift")
    assert drift.data["artifact"] == "artifact-city-plugin"
    assert drift.data["location"] in {"supply:city-web-build", "aibom:artifact-city-plugin"}
