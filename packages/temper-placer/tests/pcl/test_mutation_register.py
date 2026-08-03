"""Tests for the kill-set register (U2).

The register (``power_pcb_dataset/constraint_kill_sets.yaml``) is the
machine-readable contract the mutation gate enforces: every active encoding
has a non-empty killed set, every survivor is triaged, and every entry
resolves to a real handler or constraint class.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[4]
_SCRIPTS = _REPO / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import constraint_mutation_gate as gate  # noqa: E402
import constraint_mutation_runner as runner  # noqa: E402

REGISTER = _REPO / "power_pcb_dataset/constraint_kill_sets.yaml"


@pytest.fixture(scope="module")
def register() -> dict:
    import yaml

    return yaml.safe_load(REGISTER.read_text())


def _active_surfaces(register: dict):
    return register["families"]["placer-pcl-handlers"]["surfaces"]


class TestRegisterSchema:
    def test_register_exists_and_parses(self, register) -> None:
        assert register["schema_version"] == 1
        assert register["generator"] == "scripts/constraint_mutation_runner.py"

    def test_all_eight_handlers_registered(self, register) -> None:
        ids = {s["id"] for s in _active_surfaces(register)}
        assert ids == {
            "adjacent",
            "aligned",
            "anchored",
            "enclosing",
            "keepout",
            "loop_area",
            "onside",
            "separated",
        }

    def test_every_active_surface_has_a_non_empty_killed_set(self, register) -> None:
        for surface in _active_surfaces(register):
            assert surface["killed"], f"{surface['id']} has an empty kill set"
            killed = [m["id"] for m in surface["mutations"] if m["outcome"] == "killed"]
            assert set(surface["killed"]) == set(killed), surface["id"]

    def test_every_survivor_is_triaged_with_rationale(self, register) -> None:
        for surface in _active_surfaces(register):
            for m in surface["mutations"]:
                if m["outcome"] != "survived":
                    continue
                assert m["triage"] in ("benign", "test-gap"), (
                    f"{surface['id']}:{m['id']} triage {m['triage']!r}"
                )
                assert m["triage_rationale"], (
                    f"{surface['id']}:{m['id']} triaged without a rationale"
                )
                assert len(m["triage_rationale"]) >= 10, (
                    f"{surface['id']}:{m['id']} rationale too short"
                )

    def test_every_entry_resolves_to_a_real_handler(self, register) -> None:
        real = {s.surface_id for s in runner.discover_handler_surfaces()}
        for surface in _active_surfaces(register):
            assert surface["id"] in real, f"{surface['id']} resolves to no handler"

    def test_router_v6_family_is_registered_as_deferred(self, register) -> None:
        family = register["families"]["router-v6-topology"]
        assert family["status"] == "deferred"
        assert family["deferred_reason"]
        real = set(gate.discover_router_v6_classes())
        assert set(family["classes"]) == real


class TestTriagePreservation:
    def test_triage_from_register_reads_back_survivor_verdicts(self, register) -> None:
        triage = runner._triage_from_register(REGISTER)
        for surface in _active_surfaces(register):
            for m in surface["mutations"]:
                if m["outcome"] == "survived":
                    assert (surface["id"], m["id"]) in triage
        assert len(triage) == 15  # all survivors carry a curated verdict (16th was keepout, now non-applicable)


class TestOperatorCoverage:
    def test_every_r4_operator_is_killed_on_at_least_one_encoding(self, register) -> None:
        """Definition of Done: each R4 bug-class operator is demonstrated killed.

        An operator may instead be documented non-applicable on every surface
        where it was registered (with a recorded rationale). Today that is
        double-count: its only registration was on the keepout margin math,
        which the Wave 4 migration moved into the Rust kernel.
        """
        killed_operators: set[str] = set()
        non_applicable: set[str] = set()
        for surface in _active_surfaces(register):
            for m in surface["mutations"]:
                if m["outcome"] == "killed":
                    killed_operators.add(m["operator"])
                elif m["outcome"] == "non-applicable":
                    assert m.get("triage_rationale"), f"{m['id']} lacks a rationale"
                    non_applicable.add(m["operator"])
        assert killed_operators | non_applicable == set(runner.VALID_OPERATORS), (
            f"uncovered operators: {sorted(set(runner.VALID_OPERATORS) - killed_operators - non_applicable)}"
        )
