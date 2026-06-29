"""TS1: Unit tests for PCL->DRC assertion bridge."""

import pytest

from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    AlignedConstraint,
    AnchoredConstraint,
    Axis,
    CompilationContext,
    ConstraintTier,
    EnclosingConstraint,
    LoopAreaConstraint,
    OnSideConstraint,
    SeparatedConstraint,
    BoardSide,
    EdgeType,
)
from temper_placer.pcl.drc_bridge import (
    DRCAssertion,
    _adjacent_to_drc,
    _aligned_to_drc,
    _anchored_to_drc,
    _enclosing_to_drc,
    _loop_area_to_drc,
    _onside_to_drc,
    _separated_to_drc,
    constraint_to_assertions,
)


def _make_netlist(refs: list[str]) -> Netlist:
    comps = [Component(ref=r, footprint="TEST", bounds=(10.0, 10.0)) for r in refs]
    nets = [Net(name=r, pins=[]) for r in refs]
    return Netlist(components=comps, nets=nets)


def _make_context(netlist: Netlist) -> CompilationContext:
    return CompilationContext(netlist=netlist)


class TestDRCAssertion:
    """DRCAssertion dataclass tests."""

    def test_construction(self):
        a = DRCAssertion(
            source_id="test_1",
            source_because="Test because reason for DRC assertion",
            check_type="distance_min",
            subjects=["A", "B"],
            threshold=6.0,
        )
        assert a.source_id == "test_1"
        assert a.source_because == "Test because reason for DRC assertion"
        assert a.check_type == "distance_min"
        assert a.threshold == 6.0


class TestAdjacentToDRC:
    def test_basic(self):
        netlist = _make_netlist(["Q1", "Q2"])
        c = AdjacentConstraint(
            a="Q1", b="Q2",
            max_distance_mm=10.0,
            tier=ConstraintTier.HARD,
            because="Test adjacent constraint for DRC assertion",
        )
        results = _adjacent_to_drc(c, _make_context(netlist))
        assert len(results) == 1
        assert results[0].check_type == "distance_max"
        assert results[0].threshold == 10.0
        assert results[0].source_id == c.id

    def test_with_pins(self):
        netlist = _make_netlist(["Q1", "Q2"])
        c = AdjacentConstraint(
            a="Q1", b="Q2",
            max_distance_mm=5.0,
            tier=ConstraintTier.HARD,
            because="Test pin-specific adjacent for DRC",
            pin_a="1", pin_b="2",
        )
        results = _adjacent_to_drc(c, _make_context(netlist))
        assert len(results) == 1
        assert "pin_a" in results[0].metadata


class TestSeparatedToDRC:
    def test_basic(self):
        netlist = _make_netlist(["HV", "LV"])
        c = SeparatedConstraint(
            a="HV_ZONE", b="LV_ZONE",
            min_distance_mm=6.0,
            tier=ConstraintTier.HARD,
            because="IEC 60335-1 safety isolation for DRC",
        )
        results = _separated_to_drc(c, _make_context(netlist))
        assert len(results) == 1
        assert results[0].check_type == "distance_min"
        assert results[0].threshold == 6.0
        assert "creepage" in results[0].pass_criteria.lower()


class TestEnclosingToDRC:
    def test_basic(self):
        netlist = _make_netlist(["Q1", "Q2", "D1"])
        c = EnclosingConstraint(
            outer="HV_ZONE",
            inner=["Q1", "Q2"],
            tier=ConstraintTier.HARD,
            because="HV components must be in HV safety zone for DRC",
        )
        results = _enclosing_to_drc(c, _make_context(netlist))
        assert len(results) == 2  # One assertion per inner component
        for r in results:
            assert r.check_type == "containment"


class TestAlignedToDRC:
    def test_basic(self):
        netlist = _make_netlist(["R1", "R2"])
        c = AlignedConstraint(
            components=["R1", "R2"],
            axis=Axis.X,
            tier=ConstraintTier.SOFT,
            because="Align resistors for aesthetic consistency",
            tolerance_mm=0.5,
        )
        results = _aligned_to_drc(c, _make_context(netlist))
        assert len(results) == 1
        assert results[0].check_type == "alignment"
        assert results[0].threshold == 0.5


class TestOnSideToDRC:
    def test_basic(self):
        netlist = _make_netlist(["J1"])
        c = OnSideConstraint(
            components=["J1"],
            side=BoardSide.TOP,
            edge=EdgeType.FLUSH,
            tier=ConstraintTier.HARD,
            because="Connector must be on top edge for DRC",
        )
        results = _onside_to_drc(c, _make_context(netlist))
        assert len(results) == 1
        assert results[0].check_type == "edge_proximity"

    def test_overhang_exemption(self):
        netlist = _make_netlist(["J1"])
        c = OnSideConstraint(
            components=["J1"],
            side=BoardSide.LEFT,
            edge=EdgeType.OVERHANG,
            tier=ConstraintTier.HARD,
            because="Connector overhang allowed for DRC test",
        )
        results = _onside_to_drc(c, _make_context(netlist))
        assert "overhang permitted" in results[0].pass_criteria.lower()


class TestAnchoredToDRC:
    def test_with_position(self):
        netlist = _make_netlist(["U1"])
        c = AnchoredConstraint(
            component="U1",
            position=(50.0, 30.0),
            tier=ConstraintTier.HARD,
            because="MCU anchored at fixed position for DRC",
        )
        results = _anchored_to_drc(c, _make_context(netlist))
        assert len(results) == 1
        assert results[0].check_type == "position"

    def test_with_region(self):
        netlist = _make_netlist(["U1"])
        c = AnchoredConstraint(
            component="U1",
            region=(0, 0, 100, 50),
            tier=ConstraintTier.HARD,
            because="MCU anchored in region for DRC",
        )
        results = _anchored_to_drc(c, _make_context(netlist))
        assert len(results) == 1


class TestLoopAreaToDRC:
    def test_basic(self):
        netlist = _make_netlist(["Q1", "Q2"])
        c = LoopAreaConstraint(
            loop_name="commutation",
            max_area_mm2=100.0,
            tier=ConstraintTier.STRONG,
            because="Minimize commutation loop for EMI compliance",
        )
        results = _loop_area_to_drc(c, _make_context(netlist))
        assert len(results) == 1
        assert results[0].check_type == "area_max"
        assert results[0].threshold == 100.0


class TestSourceTraceability:
    """R12: DRC assertions carry source_id and source_because."""

    def test_all_types_have_source_id(self):
        """All 7 types produce assertions with source_id set."""
        netlist = _make_netlist(["Q1", "Q2", "R1", "R2", "D1", "J1", "U1"])

        constraints = [
            AdjacentConstraint(a="Q1", b="Q2", max_distance_mm=10.0,
                               tier=ConstraintTier.HARD, because="Test source ID for adj"),
            SeparatedConstraint(a="Q1", b="Q2", min_distance_mm=6.0,
                                tier=ConstraintTier.HARD, because="Test source ID for sep"),
            EnclosingConstraint(outer="ZONE", inner=["D1"],
                                tier=ConstraintTier.HARD, because="Test source ID for enc"),
            AlignedConstraint(components=["R1", "R2"], axis=Axis.X,
                              tier=ConstraintTier.SOFT, because="Test source ID for align"),
            OnSideConstraint(components=["J1"], side=BoardSide.TOP, edge=EdgeType.FLUSH,
                             tier=ConstraintTier.HARD, because="Test source ID for side"),
            AnchoredConstraint(component="U1", position=(50, 30),
                               tier=ConstraintTier.HARD, because="Test source ID for anchor"),
            LoopAreaConstraint(loop_name="commutation", max_area_mm2=100.0,
                               tier=ConstraintTier.STRONG, because="Test source ID for loop"),
        ]

        for c in constraints:
            results = constraint_to_assertions(c, _make_context(netlist))
            assert len(results) > 0, f"No assertions for {c.constraint_type}"
            for r in results:
                assert r.source_id == c.id, f"source_id mismatch for {c.constraint_type}"
                assert r.source_because == c.because, f"source_because mismatch for {c.constraint_type}"
