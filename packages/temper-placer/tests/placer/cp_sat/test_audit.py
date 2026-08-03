"""Tests for PlacementAuditor — U6: audit checks for all constraint types.

Extended by plan 2026-08-02-016 (post-solve audit for all constraints):
fail-closed on unregistered types (KTD1), UNVERIFIED records with a
documented-exemption registry, missing-ref fail-closed behavior, and the
register totality contract (KTD2 / U2, U4).
"""

from __future__ import annotations

from unittest import mock

import pytest

from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    AlignedConstraint,
    AnchoredConstraint,
    Axis,
    BoardSide,
    ConstraintTier,
    ConstraintType,
    DistanceMetric,
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
    UnregisteredConstraintTypeError,
    audit_register_types,
    encoder_emitted_types,
    validate_audit_register,
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


# ---------------------------------------------------------------------------
# Plan 2026-08-02-016 U1: fail closed on unregistered constraint types (KTD1)
# ---------------------------------------------------------------------------


class _UnregisteredType:
    """A ConstraintType-like object that is NOT a ConstraintType member."""

    value = "unregistered_fake"

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return "<unregistered-fake>"


class _FakeUnregisteredConstraint:
    """Minimal BaseConstraint-shaped object with an unregistered type."""

    constraint_type = _UnregisteredType()
    id = "fake_unregistered_1"


class TestUnregisteredTypeFailsClosed:
    """U1 scenario 1: a constraint type outside _CHECK_MAP raises, naming it."""

    def test_check_raises_with_type_named(self) -> None:
        p = make_placement()
        auditor = PlacementAuditor(p)
        with pytest.raises(UnregisteredConstraintTypeError) as ei:
            auditor._check(_FakeUnregisteredConstraint())
        assert "unregistered_fake" in str(ei.value)
        assert "unregistered" in str(ei.value).lower()

    def test_audit_propagates_fail_closed(self) -> None:
        """audit() must not swallow the fail-closed error into a clean pass."""
        p = make_placement()
        auditor = PlacementAuditor(p)
        with pytest.raises(UnregisteredConstraintTypeError):
            auditor.audit([_FakeUnregisteredConstraint()])


# ---------------------------------------------------------------------------
# Plan 2026-08-02-016 U1: PIN_TO_PIN adjacency audits UNVERIFIED, never a
# silent pass or a false-positive violation.
# ---------------------------------------------------------------------------


class TestPinToPinUnverified:
    """U1 scenario 2: PIN_TO_PIN audits to UNVERIFIED.

    The default auditor carries a documented exemption for PIN_TO_PIN (the
    Placement model has no per-pin geometry), so the UNVERIFIED record is
    visible but does not fail the run.  The mechanism that makes UNVERIFIED
    fail unless exempt is exercised by ``test_pin_to_pin_without_exemption
    _fails`` below.
    """

    def test_pin_to_pin_records_unverified_with_exemption(self) -> None:
        p = make_placement(positions={"A": (5.0, 5.0), "B": (6.0, 5.0)})
        auditor = PlacementAuditor(p)
        c = AdjacentConstraint(
            "A",
            "B",
            max_distance_mm=5.0,
            metric=DistanceMetric.PIN_TO_PIN,
            tier=ConstraintTier.HARD,
            because="Half-bridge pair must be close to minimize loop area ind",
        )
        report = auditor.audit([c])
        # Exempt: does not fail the run ...
        assert report.all_pass
        assert report.failed == 0
        # ... but is recorded, never silently passed.
        assert len(report.unverified) == 1
        assert "UNVERIFIED" in report.unverified[0].description
        assert "PIN_TO_PIN" in report.unverified[0].description
        assert "per-pin geometry" in report.unverified[0].detail

    def test_pin_to_pin_without_exemption_fails(self) -> None:
        """UNVERIFIED with no registered exemption counts as not-passing."""

        class _NoExemptionsAuditor(PlacementAuditor):
            _EXEMPTIONS: dict = {}

        p = make_placement(positions={"A": (5.0, 5.0), "B": (6.0, 5.0)})
        auditor = _NoExemptionsAuditor(p)
        c = AdjacentConstraint(
            "A",
            "B",
            max_distance_mm=5.0,
            metric=DistanceMetric.PIN_TO_PIN,
            tier=ConstraintTier.HARD,
            because="Half-bridge pair must be close to minimize loop area ind",
        )
        report = auditor.audit([c])
        assert not report.all_pass
        assert report.failed == 1
        assert "UNVERIFIED" in report.violations[0].description

    def test_exemption_registry_is_documented(self) -> None:
        """The PIN_TO_PIN exemption must carry a documented reason (NOTE
        convention), never an empty justification."""
        key = (ConstraintType.ADJACENT, DistanceMetric.PIN_TO_PIN.value)
        assert key in PlacementAuditor._EXEMPTIONS
        assert len(PlacementAuditor._EXEMPTIONS[key]) > 100  # real prose, not a stub


# ---------------------------------------------------------------------------
# Plan 2026-08-02-016 U1/U2: a constraint referencing geometry absent from
# the placement is never a clean pass — it is a violation or a named
# UNVERIFIED marker.
# ---------------------------------------------------------------------------


def _make_constraint_with_missing_ref() -> list:
    """One constraint per type, each referencing a ref absent from a
    placement that contains only A/C1/J1."""

    def because() -> str:
        return "Safety isolation requirement for high voltage paths in design"

    return [
        SeparatedConstraint("A", "GHOST", min_distance_mm=3.0, tier=ConstraintTier.HARD, because=because()),
        EnclosingConstraint(outer="GHOST_ZONE", inner=["A"], tier=ConstraintTier.HARD, because=because()),
        AdjacentConstraint("A", "GHOST", max_distance_mm=5.0, tier=ConstraintTier.HARD, because=because()),
        OnSideConstraint(
            ["GHOST"], side=BoardSide.LEFT, edge=EdgeType.FLUSH, tier=ConstraintTier.HARD, because=because()
        ),
        AnchoredConstraint("GHOST", tier=ConstraintTier.HARD, position=(5.0, 5.0), because=because()),
        KeepoutConstraint(zone_name="GHOST_ZONE", tier=ConstraintTier.HARD, because=because()),
        AlignedConstraint(["A", "GHOST"], axis=Axis.X, tier=ConstraintTier.HARD, because=because()),
    ]


class TestMissingRefsFailClosed:
    """U1 scenario 4 / U2 edge case: absent refs never yield a clean pass."""

    @pytest.mark.parametrize("constraint", _make_constraint_with_missing_ref())
    def test_missing_ref_never_clean_pass(self, constraint) -> None:
        p = make_placement(positions={"A": (5.0, 5.0), "J1": (0.0, 5.0), "C1": (5.0, 5.0)})
        # GHOST_ZONE must not exist as a zone in this placement.
        auditor = PlacementAuditor(p)
        report = auditor.audit([constraint])
        assert not report.all_pass, f"{constraint.constraint_type.value} passed with a missing ref"
        assert report.failed == 1
        assert "UNVERIFIED" in report.violations[0].description
        assert "GHOST" in report.violations[0].detail

    def test_missing_loop_never_clean_pass(self) -> None:
        p = make_placement(positions={"C1": (5.0, 5.0), "C2": (10.0, 10.0)})
        auditor = PlacementAuditor(p)
        c = LoopAreaConstraint(
            loop_name="GHOST_LOOP",
            max_area_mm2=500.0,
            tier=ConstraintTier.HARD,
            because="Minimize commutation loop to reduce voltage overshoot in the design",
        )
        report = auditor.audit([c], loop_components={"commutation": ["C1", "C2"]})
        assert not report.all_pass
        assert "UNVERIFIED" in report.violations[0].description
        assert "GHOST_LOOP" in report.violations[0].detail

    def test_missing_enclosing_component_never_clean_pass(self) -> None:
        p = make_placement(positions={"A": (8.0, 8.0)})
        auditor = PlacementAuditor(p)
        c = EnclosingConstraint(
            outer="HV_ZONE",
            inner=["A", "GHOST"],
            tier=ConstraintTier.HARD,
            because="All high voltage components must stay in the HV safety zone area",
        )
        report = auditor.audit([c])
        assert not report.all_pass
        assert "GHOST" in report.violations[0].detail

    def test_missing_zone_for_enclosing_never_clean_pass(self) -> None:
        p = make_placement(positions={"A": (8.0, 8.0)}, zones={})
        auditor = PlacementAuditor(p)
        c = EnclosingConstraint(
            outer="HV_ZONE",
            inner=["A"],
            tier=ConstraintTier.HARD,
            because="All high voltage components must stay in the HV safety zone area",
        )
        report = auditor.audit([c])
        assert not report.all_pass
        assert "HV_ZONE" in report.violations[0].detail


# ---------------------------------------------------------------------------
# Plan 2026-08-02-016 U2/U4: register totality contract (KTD2).
# ---------------------------------------------------------------------------


class TestAuditRegisterCompleteness:
    """U2 scenario 3 / U4: the register covers exactly the encoder surface."""

    def test_register_covers_every_constraint_type(self) -> None:
        assert set(PlacementAuditor._CHECK_MAP) == set(ConstraintType)

    def test_register_covers_exactly_encoder_emitted_types(self) -> None:
        assert set(PlacementAuditor._CHECK_MAP) == set(encoder_emitted_types())

    def test_validate_audit_register_passes(self) -> None:
        assert validate_audit_register() == frozenset(ConstraintType)
        assert validate_audit_register() == audit_register_types()

    def test_dropped_check_fails_validation(self) -> None:
        """A new encoder type without an audit entry (simulated by dropping
        one) fails the register validation test."""
        reduced = dict(PlacementAuditor._CHECK_MAP)
        reduced.pop(ConstraintType.ALIGNED)
        with (
            mock.patch.object(PlacementAuditor, "_CHECK_MAP", reduced),
            pytest.raises(AssertionError) as ei,
        ):
            validate_audit_register()
        assert "aligned" in str(ei.value)

    def test_broken_method_name_fails_validation(self) -> None:
        broken = dict(PlacementAuditor._CHECK_MAP)
        broken[ConstraintType.ALIGNED] = "_check_no_such_method"
        with (
            mock.patch.object(PlacementAuditor, "_CHECK_MAP", broken),
            pytest.raises(AssertionError) as ei,
        ):
            validate_audit_register()
        assert "_check_no_such_method" in str(ei.value)

    def test_register_docstring_agrees_with_check_map(self) -> None:
        """U4 scenario 3: drift between the register docstring table and the
        code fails this test."""
        import temper_placer.placer.cp_sat.audit as audit_module

        doc = audit_module.__doc__ or ""
        for ct, method in PlacementAuditor._CHECK_MAP.items():
            assert ct.value in doc, f"{ct.value} missing from register docstring"
            assert method in doc, f"{method} missing from register docstring"
        for key in PlacementAuditor._EXEMPTIONS:
            assert key[1] in doc, f"exemption discriminator {key[1]} missing from docstring"
