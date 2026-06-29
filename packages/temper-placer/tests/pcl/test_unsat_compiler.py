"""TS1: Unit tests for UNSAT core -> PCL upward compiler."""

import pytest

from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.pcl.constraints import (
    CompilationContext,
    ConstraintTier,
    SeparatedConstraint,
)
from temper_placer.pcl.parser import ConstraintCollection
from temper_placer.pcl.sat_bridge import ConstraintOrigin
from temper_placer.pcl.unsat_compiler import (
    InfeasibleConstraintSet,
    _deduplicate_constraints,
    _synthesize_constraint,
    compile_unsat_to_pcl,
    reset_escalation_counts,
)


def _make_netlist(refs: list[str]) -> Netlist:
    comps = [Component(ref=r, footprint="TEST", bounds=(10.0, 10.0)) for r in refs]
    nets = [Net(name=r, pins=[]) for r in refs]
    return Netlist(components=comps, nets=nets)


class TestEmptyCore:
    """Empty UNSAT core raises InfeasibleConstraintSet."""

    def test_empty_core_raises(self):
        netlist = _make_netlist(["Q1", "Q2"])
        origin = ConstraintOrigin()
        ctx = CompilationContext(netlist=netlist)
        collection = ConstraintCollection(constraints=[])

        with pytest.raises(InfeasibleConstraintSet, match="Empty UNSAT core"):
            compile_unsat_to_pcl([], collection, origin, ctx)


class TestEscalation:
    """Known PCL constraints get escalated."""

    def test_soft_escalates_to_strong(self):
        netlist = _make_netlist(["Q1", "Q2"])
        origin = ConstraintOrigin()
        c = SeparatedConstraint(
            a="Q1", b="Q2",
            min_distance_mm=5.0,
            tier=ConstraintTier.SOFT,
            because="Test escalation from soft to strong tier",
        )
        origin.record(c.id, "sat_cap_Q1_Q2")
        collection = ConstraintCollection(constraints=[c])
        ctx = CompilationContext(netlist=netlist)

        reset_escalation_counts()
        diff = compile_unsat_to_pcl(
            ["sat_cap_Q1_Q2"], collection, origin, ctx,
        )
        assert len(diff.constraints) == 1
        assert diff.constraints[0].tier == ConstraintTier.STRONG

    def test_strong_escalates_to_hard(self):
        netlist = _make_netlist(["Q1", "Q2"])
        origin = ConstraintOrigin()
        c = SeparatedConstraint(
            a="Q1", b="Q2",
            min_distance_mm=5.0,
            tier=ConstraintTier.STRONG,
            because="Test escalation from strong to hard tier",
        )
        origin.record(c.id, "sat_cap_Q1_Q2")
        collection = ConstraintCollection(constraints=[c])
        ctx = CompilationContext(netlist=netlist)

        reset_escalation_counts()
        diff = compile_unsat_to_pcl(
            ["sat_cap_Q1_Q2"], collection, origin, ctx,
        )
        assert len(diff.constraints) == 1
        assert diff.constraints[0].tier == ConstraintTier.HARD

    def test_hard_does_not_escalate(self):
        """HARD constraints are already at max tier."""
        netlist = _make_netlist(["Q1", "Q2"])
        origin = ConstraintOrigin()
        c = SeparatedConstraint(
            a="Q1", b="Q2",
            min_distance_mm=5.0,
            tier=ConstraintTier.HARD,
            because="Test hard constraint stays hard",
        )
        origin.record(c.id, "sat_cap_Q1_Q2")
        collection = ConstraintCollection(constraints=[c])
        ctx = CompilationContext(netlist=netlist)

        reset_escalation_counts()
        diff = compile_unsat_to_pcl(
            ["sat_cap_Q1_Q2"], collection, origin, ctx,
        )
        assert len(diff.constraints) == 0  # HARD stays HARD, no escalation needed

    def test_max_escalations_limit(self):
        """Escalation counter prevents infinite loops (R15)."""
        netlist = _make_netlist(["Q1", "Q2"])
        origin = ConstraintOrigin()
        c = SeparatedConstraint(
            a="Q1", b="Q2",
            min_distance_mm=5.0,
            tier=ConstraintTier.SOFT,
            because="Test escalation counter limit enforcement",
        )
        origin.record(c.id, "sat_cap_Q1_Q2")
        collection = ConstraintCollection(constraints=[c])
        ctx = CompilationContext(netlist=netlist)

        reset_escalation_counts()
        # First 2 escalations work (SOFT->STRONG->HARD, only 2 tier transitions)
        for _ in range(2):
            diff = compile_unsat_to_pcl(
                ["sat_cap_Q1_Q2"], collection, origin, ctx, max_escalations=2,
            )
            assert len(diff.constraints) == 1

        # 3rd escalation should be skipped (already at HARD)
        diff = compile_unsat_to_pcl(
            ["sat_cap_Q1_Q2"], collection, origin, ctx, max_escalations=2,
        )
        assert len(diff.constraints) == 0


class TestSynthesis:
    """Unknown SAT constraints trigger synthesis of new PCL constraints."""

    def test_synthesized_constraint(self):
        netlist = _make_netlist(["Q1", "Q2"])
        origin = ConstraintOrigin()
        collection = ConstraintCollection(constraints=[])
        ctx = CompilationContext(netlist=netlist)

        diff = compile_unsat_to_pcl(
            ["unknown_sat_constraint"], collection, origin, ctx,
        )
        assert len(diff.constraints) >= 1
        synthesized = diff.constraints[0]
        assert isinstance(synthesized, SeparatedConstraint)
        assert synthesized.id.startswith("unsat_"), (
            f"ID should start with 'unsat_', got {synthesized.id}"
        )
        assert "Synthesized from SAT UNSAT core" in synthesized.because
        assert synthesized.tier == ConstraintTier.STRONG

    def test_synthesized_constraint_carries_because(self):
        """R16: Synthesized constraints have because and unsat_ prefix."""
        netlist = _make_netlist(["Q1", "Q2"])
        origin = ConstraintOrigin()
        collection = ConstraintCollection(constraints=[])
        ctx = CompilationContext(netlist=netlist)

        diff = compile_unsat_to_pcl(
            ["sat_conflict_cap_L1_E42"], collection, origin, ctx,
        )
        assert len(diff.constraints) >= 1
        c = diff.constraints[0]
        assert c.id.startswith("unsat_")
        assert len(c.because) >= 10


class TestDeduplication:
    """Multiple constraints with identical pairs get merged."""

    def test_dedup_identical_pairs(self):
        netlist = _make_netlist(["Q1", "Q2"])
        c1 = SeparatedConstraint(
            a="Q1", b="Q2",
            min_distance_mm=5.0,
            tier=ConstraintTier.STRONG,
            because="Test dedup first constraint",
        )
        c2 = SeparatedConstraint(
            a="Q1", b="Q2",
            min_distance_mm=10.0,
            tier=ConstraintTier.STRONG,
            because="Test dedup second constraint",
        )
        merged = _deduplicate_constraints([c1, c2])
        assert len(merged) == 1
        assert merged[0].min_distance_mm == 10.0  # Takes max

    def test_dedup_different_tiers_kept_separate(self):
        c1 = SeparatedConstraint(
            a="Q1", b="Q2",
            min_distance_mm=5.0,
            tier=ConstraintTier.STRONG,
            because="Strong tier constraint for dedup test",
        )
        c2 = SeparatedConstraint(
            a="Q1", b="Q2",
            min_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="Hard tier constraint for dedup test",
        )
        merged = _deduplicate_constraints([c1, c2])
        assert len(merged) == 2  # Different tiers, not merged
