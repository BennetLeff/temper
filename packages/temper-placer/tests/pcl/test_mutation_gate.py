"""Tests for the constraint mutation gate (U3).

The gate AST-scans the encoder surfaces and requires a kill-set register
entry per surface: non-empty killed set, no untriaged survivors, and no stale
entries. These tests exercise the gate's check functions against the real
register and synthetic mutations of it (a missing entry, an emptied kill set,
an untriaged survivor, a stale entry), plus the router-V6 family checks.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[4]
_SCRIPTS = _REPO / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import constraint_mutation_gate as gate  # noqa: E402


@pytest.fixture(scope="module")
def register() -> dict:
    import yaml

    return yaml.safe_load(
        (_REPO / "power_pcb_dataset/constraint_kill_sets.yaml").read_text()
    )


class TestHandlerChecks:
    def test_gate_is_green_on_the_fully_populated_register(self, register) -> None:
        assert gate.check_handler_surfaces(register) == []
        assert gate.check_router_v6(register) == []

    def test_new_handler_without_entry_fails_named(self, register) -> None:
        doc = copy.deepcopy(register)
        # drop one surface entirely, as if a new handler shipped without an entry
        doc["families"]["placer-pcl-handlers"]["surfaces"] = [
            s for s in doc["families"]["placer-pcl-handlers"]["surfaces"]
            if s["id"] != "separated"
        ]
        violations = gate.check_handler_surfaces(doc)
        assert any("separated" in v and "no kill-set register entry" in v for v in violations)

    def test_empty_kill_set_fails(self, register) -> None:
        doc = copy.deepcopy(register)
        surface = next(
            s for s in doc["families"]["placer-pcl-handlers"]["surfaces"]
            if s["id"] == "separated"
        )
        for m in surface["mutations"]:
            m["outcome"] = "survived"
            m["triage"] = "benign"
            m["triage_rationale"] = "test rationale for emptied kill set"
        surface["killed"] = []
        surface["survived"] = [m["id"] for m in surface["mutations"]]
        violations = gate.check_handler_surfaces(doc)
        assert any("separated" in v and "empty kill set" in v for v in violations)

    def test_registering_a_non_empty_kill_set_clears_the_failure(self, register) -> None:
        assert gate.check_handler_surfaces(register) == []

    def test_survivor_without_triage_fails(self, register) -> None:
        doc = copy.deepcopy(register)
        surface = next(
            s for s in doc["families"]["placer-pcl-handlers"]["surfaces"]
            if s["id"] == "separated"
        )
        survivor = next(m for m in surface["mutations"] if m["outcome"] == "survived")
        del survivor["triage"]
        violations = gate.check_handler_surfaces(doc)
        assert any("separated" in v and "without a triage status" in v for v in violations)

    def test_survivor_triage_without_rationale_fails(self, register) -> None:
        doc = copy.deepcopy(register)
        surface = next(
            s for s in doc["families"]["placer-pcl-handlers"]["surfaces"]
            if s["id"] == "separated"
        )
        survivor = next(m for m in surface["mutations"] if m["outcome"] == "survived")
        survivor["triage_rationale"] = ""
        violations = gate.check_handler_surfaces(doc)
        assert any("no rationale" in v for v in violations)

    def test_stale_register_entry_fails(self, register) -> None:
        doc = copy.deepcopy(register)
        fake = {
            "id": "no_such_handler",
            "constraint_type": "NOPE",
            "mutations": [],
            "killed": [],
            "survived": [],
        }
        doc["families"]["placer-pcl-handlers"]["surfaces"].append(fake)
        violations = gate.check_handler_surfaces(doc)
        assert any("no_such_handler" in v and "resolves to no handler" in v for v in violations)


class TestRouterV6Checks:
    def test_missing_class_fails(self, register) -> None:
        doc = copy.deepcopy(register)
        doc["families"]["router-v6-topology"]["classes"] = ["CapacityConstraint"]
        violations = gate.check_router_v6(doc)
        assert any("DiffPairConstraint" in v and "missing from the register" in v for v in violations)

    def test_deferred_family_requires_a_reason(self, register) -> None:
        doc = copy.deepcopy(register)
        doc["families"]["router-v6-topology"]["deferred_reason"] = ""
        violations = gate.check_router_v6(doc)
        assert any("missing deferred_reason" in v for v in violations)

    def test_invalid_family_status_fails(self, register) -> None:
        doc = copy.deepcopy(register)
        doc["families"]["router-v6-topology"]["status"] = "banana"
        violations = gate.check_router_v6(doc)
        assert any("status must be 'active' or 'deferred'" in v for v in violations)


class TestExitCodes:
    def test_exit_zero_on_clean_register(self) -> None:
        assert gate.main() is None  # main() prints OK and returns (exit 0)
