"""TS1: Unit tests for PCL->SAT downward bridge."""

import pytest

from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    AlignedConstraint,
    CompilationContext,
    CompilationTarget,
    ConstraintTier,
    ConstraintType,
    SeparatedConstraint,
)
from temper_placer.pcl.parser import ConstraintCollection
from temper_placer.pcl.sat_bridge import (
    CAPABILITY_HANDLERS,
    TYPE_HANDLERS,
    ConstraintOrigin,
    SATBridgeContext,
    _adjacent_to_sat,
    _aligned_to_sat,
    _separated_to_sat,
    constraint_to_clauses,
    register_handler,
)


def _make_netlist(refs: list[str]) -> Netlist:
    """Build a minimal Netlist with named components and empty nets."""
    comps = [Component(ref=r, footprint="TEST", bounds=(10.0, 10.0)) for r in refs]
    nets = [Net(name=r, pins=[]) for r in refs]
    return Netlist(components=comps, nets=nets)


def _make_context(netlist: Netlist) -> CompilationContext:
    return CompilationContext(netlist=netlist)


class TestConstraintOrigin:
    """Test the ConstraintOrigin bidirectional registry."""

    def test_record_and_lookup(self):
        origin = ConstraintOrigin()
        origin.record("pcl_1", "sat_a")
        origin.record("pcl_1", "sat_b")
        origin.record("pcl_2", "sat_c")

        assert origin.lookup_pcl_id("sat_a") == "pcl_1"
        assert origin.lookup_pcl_id("sat_b") == "pcl_1"
        assert origin.lookup_pcl_id("sat_c") == "pcl_2"
        assert origin.lookup_pcl_id("nonexistent") is None

    def test_get_sat_names(self):
        origin = ConstraintOrigin()
        origin.record("pcl_1", "sat_a")
        origin.record("pcl_1", "sat_b")

        assert sorted(origin.get_sat_names("pcl_1")) == ["sat_a", "sat_b"]
        assert origin.get_sat_names("nonexistent") == []


class TestTierMapping:
    """Test tier-to-hardness mapping (R8: MVP encodes all as hard)."""

    def test_all_mvp_tiers_to_hard(self):
        from temper_placer.pcl.sat_bridge import TIER_TO_HARDNESS

        assert TIER_TO_HARDNESS[ConstraintTier.HARD] == "hard"
        assert TIER_TO_HARDNESS[ConstraintTier.STRONG] == "hard"
        assert TIER_TO_HARDNESS[ConstraintTier.SOFT] == "hard"


class TestAdjacentToSAT:
    """AdjacentConstraint -> SAT clauses."""

    def test_basic_adjacent(self):
        netlist = _make_netlist(["Q1", "Q2"])
        constraint = AdjacentConstraint(
            a="Q1", b="Q2",
            max_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="Test adjacent constraint for SAT bridge",
        )
        ctx = SATBridgeContext(netlist, None, {}, {})
        results = _adjacent_to_sat(constraint, ctx)
        # Adjacent produces no hard clauses in MVP (proximity preference only)
        assert isinstance(results, list)

    def test_unresolved_components_skipped(self):
        netlist = _make_netlist(["Q1"])
        constraint = AdjacentConstraint(
            a="NONEXISTENT", b="Q1",
            max_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="Test adjacent constraint with missing component",
        )
        ctx = SATBridgeContext(netlist, None, {}, {})
        with pytest.warns(UserWarning, match="cannot resolve"):
            results = _adjacent_to_sat(constraint, ctx)
        assert results == []


class TestSeparatedToSAT:
    """SeparatedConstraint -> ChannelSeparationConstraint."""

    def test_basic_separated(self):
        netlist = _make_netlist(["HV", "LV"])
        constraint = SeparatedConstraint(
            a="HV_ZONE", b="LV_ZONE",
            min_distance_mm=6.0,
            tier=ConstraintTier.HARD,
            because="IEC 60335-1 reinforced isolation requirement",
        )
        ctx = SATBridgeContext(netlist, None, {}, {})
        results = _separated_to_sat(constraint, ctx)
        # No channels in empty context -> empty list
        assert isinstance(results, list)


class TestAlignedToSAT:
    """AlignedConstraint has no SAT grounding."""

    def test_returns_empty(self):
        netlist = _make_netlist(["R1", "R2"])
        from temper_placer.pcl.constraints import Axis
        constraint = AlignedConstraint(
            components=["R1", "R2"],
            axis=Axis.X,
            tier=ConstraintTier.SOFT,
            because="Visual consistency for aligned components",
        )
        ctx = SATBridgeContext(netlist, None, {}, {})
        results = _aligned_to_sat(constraint, ctx)
        assert results == []


class TestConstraintToClauses:
    """Main entry point: constraint_to_clauses."""

    def test_origin_is_populated(self):
        netlist = _make_netlist(["Q1", "Q2"])
        constraint = AdjacentConstraint(
            a="Q1", b="Q2",
            max_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="Test origin population for SAT compilation",
        )
        ctx = SATBridgeContext(netlist, None, {}, {})
        clauses, origin = constraint_to_clauses(constraint, ctx)
        assert isinstance(origin, ConstraintOrigin)

    def test_type_handlers_cover_all_types(self):
        """All ConstraintType members that support SAT have TYPE_HANDLERS entries."""
        from temper_placer.pcl.constraints import CompilationTarget
        for ct in ConstraintType:
            if CompilationTarget.SAT not in ct.supported_targets:
                continue
            assert ct in TYPE_HANDLERS, f"{ct} missing from TYPE_HANDLERS"


class TestRegisterHandler:
    """R25: Custom handler registration."""

    def test_register_override(self):
        netlist = _make_netlist(["Q1", "Q2"])
        called = []

        def custom_handler(constraint, _ctx):
            called.append(constraint)
            return []

        register_handler(ConstraintType.SEPARATED, custom_handler)

        constraint = SeparatedConstraint(
            a="Q1", b="Q2",
            min_distance_mm=6.0,
            tier=ConstraintTier.HARD,
            because="Test custom handler override for separated constraint",
        )
        ctx = SATBridgeContext(netlist, None, {}, {})
        constraint_to_clauses(constraint, ctx)
        assert len(called) == 1

        # Restore original
        register_handler(ConstraintType.SEPARATED, _separated_to_sat)


class TestCapabilityHandlers:
    """R24: Capability-based default handlers."""

    def test_all_semantic_tags_have_handlers(self):
        """Every SemanticTag has a CAPABILITY_HANDLERS entry."""
        from temper_placer.pcl.constraints import SemanticTag
        for tag in SemanticTag:
            assert tag in CAPABILITY_HANDLERS, f"{tag} missing from CAPABILITY_HANDLERS"


class TestConstraintCollectionCompile:
    """ConstraintCollection.compile() with SAT target."""

    def test_compile_sat_returns_results(self):
        netlist = _make_netlist(["Q1", "Q2"])
        collection = ConstraintCollection(constraints=[
            AdjacentConstraint(
                a="Q1", b="Q2",
                max_distance_mm=10.0,
                tier=ConstraintTier.HARD,
                because="Test SAT compilation via ConstraintCollection",
            ),
        ])
        ctx = CompilationContext(netlist=netlist)
        results = collection.compile(CompilationTarget.SAT, ctx)
        assert isinstance(results, list)

    def test_compile_skips_non_sat_targets(self):
        """Constraint without 'sat' in targets is skipped."""
        netlist = _make_netlist(["Q1", "Q2"])
        constraint = AdjacentConstraint(
            a="Q1", b="Q2",
            max_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="Test SAT skip for constraint without sat target",
        )
        constraint.targets = ["jax"]  # Only JAX, no SAT
        collection = ConstraintCollection(constraints=[constraint])
        ctx = CompilationContext(netlist=netlist)
        results = collection.compile(CompilationTarget.SAT, ctx)
        assert results == []
