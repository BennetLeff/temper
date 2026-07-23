"""Tests for PlacementAuditor — U6: audit checks for all constraint types."""

from __future__ import annotations

from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    AlignedConstraint,
    AnchoredConstraint,
    Axis,
    BoardSide,
    ConstraintTier,
    EdgeType,
    EnclosingConstraint,
    KeepoutConstraint,
    LoopAreaConstraint,
    OnSideConstraint,
    SeparatedConstraint,
)
from temper_placer.placer.cp_sat.audit import (
    Placement,
    PlacementAuditor,
)


def make_placement(**overrides: object) -> Placement:
    """Build a Placement with defaults overridden."""
    positions: dict[str, tuple[float, float]] = {"A": (5.0, 5.0), "B": (15.0, 5.0)}
    sizes: dict[str, tuple[float, float]] = {"A": (2.0, 2.0), "B": (2.0, 2.0)}
    zones: dict[str, tuple[float, float, float, float]] = {
        "HV_ZONE": (3.0, 3.0, 17.0, 17.0),
        "NO_FLY": (9.0, 9.0, 11.0, 11.0),
    }
    if "positions" in overrides:
        positions = overrides["positions"]  # type: ignore[assignment]
    if "sizes" in overrides:
        sizes = overrides["sizes"]  # type: ignore[assignment]
    if "zones" in overrides:
        zones = overrides["zones"]  # type: ignore[assignment]
    return Placement(
        positions_mm=positions,
        sizes_mm=sizes,
        rotations={"A": 0, "B": 0},
        board_w_mm=20.0,
        board_h_mm=20.0,
        zones=zones,
    )


class TestSeparatedAudit:
    def test_passes_when_gap_sufficient(self) -> None:
        p = make_placement(positions={"A": (5.0, 5.0), "B": (12.0, 5.0)})
        auditor = PlacementAuditor(p)
        c = SeparatedConstraint(
            "A",
            "B",
            min_distance_mm=3.0,
            tier=ConstraintTier.HARD,
            because="Safety isolation requirement for high voltage paths",
        )
        report = auditor.audit([c])
        assert report.all_pass

    def test_fails_when_gap_too_small(self) -> None:
        p = make_placement(positions={"A": (5.0, 5.0), "B": (5.6, 5.0)})
        auditor = PlacementAuditor(p)
        c = SeparatedConstraint(
            "A",
            "B",
            min_distance_mm=5.0,
            tier=ConstraintTier.HARD,
            because="Safety isolation requirement for high voltage paths",
        )
        report = auditor.audit([c])
        assert not report.all_pass
        assert report.failed == 1


class TestEnclosingAudit:
    def test_passes_within_zone(self) -> None:
        p = make_placement(positions={"A": (8.0, 8.0)})
        auditor = PlacementAuditor(p)
        c = EnclosingConstraint(
            outer="HV_ZONE",
            inner=["A"],
            tier=ConstraintTier.HARD,
            because="All high voltage components must stay in HV safety zone area",
        )
        report = auditor.audit([c])
        assert report.all_pass

    def test_fails_outside_zone(self) -> None:
        p = make_placement(positions={"A": (19.0, 19.0)})
        auditor = PlacementAuditor(p)
        c = EnclosingConstraint(
            outer="HV_ZONE",
            inner=["A"],
            tier=ConstraintTier.HARD,
            because="All high voltage components must stay in HV safety zone area",
        )
        report = auditor.audit([c])
        assert not report.all_pass


class TestAdjacentAudit:
    def test_passes_within_distance(self) -> None:
        p = make_placement(positions={"A": (5.0, 5.0), "B": (6.0, 5.0)})
        auditor = PlacementAuditor(p)
        c = AdjacentConstraint(
            "A",
            "B",
            max_distance_mm=5.0,
            tier=ConstraintTier.HARD,
            because="Half-bridge pair must be close to minimize loop area ind",
        )
        report = auditor.audit([c])
        assert report.all_pass

    def test_fails_far_apart(self) -> None:
        p = make_placement(positions={"A": (1.0, 1.0), "B": (19.0, 19.0)})
        auditor = PlacementAuditor(p)
        c = AdjacentConstraint(
            "A",
            "B",
            max_distance_mm=2.0,
            tier=ConstraintTier.HARD,
            because="Half-bridge pair must be close to minimize loop area ind",
        )
        report = auditor.audit([c])
        assert not report.all_pass


class TestOnSideAudit:
    def test_passes_on_left_edge(self) -> None:
        p = make_placement(positions={"J1": (0.0, 5.0)}, sizes={"J1": (2.0, 2.0)})
        auditor = PlacementAuditor(p)
        c = OnSideConstraint(
            components=["J1"],
            side=BoardSide.LEFT,
            edge=EdgeType.FLUSH,
            max_distance_mm=2.0,
            tier=ConstraintTier.HARD,
            because="Connector must be on left edge for external access housing",
        )
        report = auditor.audit([c])
        assert report.all_pass

    def test_fails_not_on_edge(self) -> None:
        p = make_placement(positions={"J1": (10.0, 5.0)}, sizes={"J1": (2.0, 2.0)})
        auditor = PlacementAuditor(p)
        c = OnSideConstraint(
            components=["J1"],
            side=BoardSide.LEFT,
            edge=EdgeType.FLUSH,
            max_distance_mm=2.0,
            tier=ConstraintTier.HARD,
            because="Connector must be on left edge for external access housing",
        )
        report = auditor.audit([c])
        assert not report.all_pass


class TestAnchoredAudit:
    def test_passes_at_position(self) -> None:
        p = make_placement(positions={"U1": (10.0, 10.0)})
        auditor = PlacementAuditor(p)
        c = AnchoredConstraint(
            component="U1",
            tier=ConstraintTier.HARD,
            position=(10.0, 10.0),
            because="MCU centered in MCU zone for antenna clearance in design",
        )
        report = auditor.audit([c])
        assert report.all_pass

    def test_fails_wrong_position(self) -> None:
        p = make_placement(positions={"U1": (5.0, 5.0)})
        auditor = PlacementAuditor(p)
        c = AnchoredConstraint(
            component="U1",
            tier=ConstraintTier.HARD,
            position=(15.0, 15.0),
            because="MCU centered in MCU zone for antenna clearance in design",
        )
        report = auditor.audit([c])
        assert not report.all_pass


class TestKeepoutAudit:
    def test_passes_outside_keepout(self) -> None:
        p = make_placement(positions={"A": (5.0, 5.0)})
        auditor = PlacementAuditor(p)
        c = KeepoutConstraint(
            zone_name="NO_FLY",
            tier=ConstraintTier.HARD,
            because="No components allowed in keepout for safety isolation zone",
        )
        report = auditor.audit([c])
        assert report.all_pass

    def test_fails_inside_keepout(self) -> None:
        p = make_placement(positions={"A": (10.0, 10.0)})
        auditor = PlacementAuditor(p)
        c = KeepoutConstraint(
            zone_name="NO_FLY",
            tier=ConstraintTier.HARD,
            because="No components allowed in keepout for safety isolation zone",
        )
        report = auditor.audit([c])
        assert not report.all_pass


class TestAlignedAudit:
    def test_passes_x_aligned(self) -> None:
        p = make_placement(positions={"C1": (5.0, 3.0), "C2": (5.2, 5.0)})
        auditor = PlacementAuditor(p)
        c = AlignedConstraint(
            components=["C1", "C2"],
            axis=Axis.X,
            tolerance_mm=0.5,
            tier=ConstraintTier.HARD,
            because="Align decoupling capacitors for visual consistency and routing",
        )
        report = auditor.audit([c])
        assert report.all_pass

    def test_fails_misaligned(self) -> None:
        p = make_placement(positions={"C1": (5.0, 3.0), "C2": (8.0, 5.0)})
        auditor = PlacementAuditor(p)
        c = AlignedConstraint(
            components=["C1", "C2"],
            axis=Axis.X,
            tolerance_mm=0.5,
            tier=ConstraintTier.HARD,
            because="Align decoupling capacitors for visual consistency and routing",
        )
        report = auditor.audit([c])
        assert not report.all_pass


class TestLoopAreaAudit:
    def test_passes_within_ceiling(self) -> None:
        p = make_placement(
            positions={"C1": (5.0, 5.0), "C2": (10.0, 10.0)},
            sizes={"C1": (2.0, 2.0), "C2": (2.0, 2.0)},
        )
        auditor = PlacementAuditor(p)
        c = LoopAreaConstraint(
            loop_name="commutation",
            max_area_mm2=500.0,
            tier=ConstraintTier.HARD,
            because="Minimize commutation loop to reduce voltage overshoot and EMI emission",
        )
        report = auditor.audit([c], loop_components={"commutation": ["C1", "C2"]})
        assert report.all_pass

    def test_fails_exceeds_ceiling(self) -> None:
        p = make_placement(
            positions={"C1": (5.0, 5.0), "C2": (30.0, 30.0)},
            sizes={"C1": (1.0, 1.0), "C2": (1.0, 1.0)},
        )
        auditor = PlacementAuditor(p)
        c = LoopAreaConstraint(
            loop_name="commutation",
            max_area_mm2=10.0,
            tier=ConstraintTier.HARD,
            because="Minimize commutation loop to reduce voltage overshoot and EMI emission",
        )
        report = auditor.audit([c], loop_components={"commutation": ["C1", "C2"]})
        assert not report.all_pass
