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


class TestRouterV6Discovery:
    """2026-08-11 gate-vacuity audit, finding 8's second defect: the router-V6
    classes are PyO3 re-exports (``X = _mb.X``) since the Wave 4 migration
    (commit 8dce8f8ae), not ``class X(Constraint):`` definitions -- an
    ``ast.ClassDef`` scan for a ``Constraint`` base finds none of them.
    ``discover_router_v6_classes`` must resolve them by importing the module,
    not by parsing its source.
    """

    def test_discovers_all_four_post_migration_reexports(self) -> None:
        classes = gate.discover_router_v6_classes()
        assert classes == [
            "CapacityConstraint",
            "ChannelSeparationConstraint",
            "DiffPairConstraint",
            "LayerConstraint",
        ]


class TestLiveKillSetVerification:
    """2026-08-11 gate-vacuity audit, finding 8: a scratch-tree repro proved
    that gutting ``handlers/keepout.py``'s ``encode_keepout`` (deleting every
    enforcement statement, including the ``AddNoOverlap2D`` call that is the
    sole mechanism keeping components out of the mains<->SELV isolation
    keepout) left the gate's exit code and output byte-identical to the
    unmutated baseline, because the gate only ever read a frozen register
    snapshot and never re-derived its claims from current encoder source.

    These tests exercise ``check_live_kill_sets`` -- the fix -- directly
    against the real register and a live-mutated ``HANDLER_REGISTRY`` entry,
    without touching any file on disk.
    """

    def test_clean_register_has_no_live_mismatches(self, register) -> None:
        assert gate.check_live_kill_sets(register) == []

    def test_gutted_keepout_encoder_is_caught(self, register, monkeypatch) -> None:
        """Reproduction of the audit's finding 8: a KEEPOUT handler reduced
        to a no-op (mirroring ``encode_keepout`` gutted down to a bare
        ``return []``) must fail live verification, even though the register
        still claims ``keepout_drop_no_overlap`` is ``killed``.
        """
        from temper_placer.pcl.constraints import ConstraintType
        from temper_placer.placer.cp_sat.handlers import HANDLER_REGISTRY

        def _gutted_encode_keepout(constraint, components, model, ctx):
            return []

        monkeypatch.setitem(HANDLER_REGISTRY, ConstraintType.KEEPOUT, _gutted_encode_keepout)

        violations = gate.check_live_kill_sets(register)
        assert violations, (
            "gutting the keepout encoder's enforcement must produce a live "
            "verification violation, not pass silently"
        )
        assert any("keepout" in v for v in violations)

    def test_gutted_keepout_encoder_fails_the_whole_gate(self, monkeypatch) -> None:
        """End-to-end: the top-level ``main()`` entrypoint (what CI actually
        runs) must exit non-zero, not just the isolated check function.
        """
        from temper_placer.pcl.constraints import ConstraintType
        from temper_placer.placer.cp_sat.handlers import HANDLER_REGISTRY

        def _gutted_encode_keepout(constraint, components, model, ctx):
            return []

        monkeypatch.setitem(HANDLER_REGISTRY, ConstraintType.KEEPOUT, _gutted_encode_keepout)

        with pytest.raises(SystemExit) as exc_info:
            gate.main()
        assert exc_info.value.code == gate.EXIT_MISSING

    def test_stale_killed_claim_is_caught_without_touching_source(
        self, register, monkeypatch
    ) -> None:
        """A register that claims a mutation is killed when a live re-run
        actually classifies it as survived must fail -- the general case of
        which the gutted-encoder scenario above is one instance."""
        import constraint_mutation_gate

        class _FakeResult:
            def __init__(self, surface_id, mutation_id, outcome):
                self.surface_id = surface_id
                self.mutation_id = mutation_id
                self.outcome = outcome

        def _fake_run_suite():
            return [_FakeResult("separated", "sep_sign_flip_x_margin", "survived")]

        import constraint_mutation_runner as runner

        monkeypatch.setattr(runner, "run_suite", _fake_run_suite)

        violations = constraint_mutation_gate.check_live_kill_sets(register)
        assert any(
            "sep_sign_flip_x_margin" in v
            and "killed" in v
            and "survived" in v
            for v in violations
        )
