"""Tests for the voltage-domain clearance constraint generator (R24).

Three groups, mapping to the three R24 gates in
``temper_placer.placer.cp_sat.domain_clearance``:

1. ``TestGeneratorNotVacuous`` -- falsifier-driven tests that the generator
   actually classifies components and emits constraints, not a no-op.
2. ``TestChebyshevSoundnessBMC`` -- the R24 item-2 BMC-exhaustive check:
   sweeps the encoder's own Chebyshev disjunction (reimplemented here to
   match ``handlers/separated.py::encode_separated`` line-for-line) against
   the validator's own Euclidean-distance oracle (``_distance``, imported,
   not reimplemented) over every integer-mm offset in a bounded window.
3. ``TestPostSolveAudit`` -- the R24 item-3 audit function, exercised
   against both a passing and a deliberately-broken resolved placement.
"""

from __future__ import annotations

import itertools

from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint
from temper_placer.placer.cp_sat.domain_clearance import (
    IEC60335_REQUIREMENTS,
    VoltageDomain,
    audit_domain_clearance,
    find_intra_footprint_domain_conflicts,
    generate_domain_clearance_constraints,
    required_margin_mm,
)
from tests.requirements.validators._geometry import _distance

# ---------------------------------------------------------------------------
# Group 1: the generator is not vacuous
# ---------------------------------------------------------------------------


class TestGeneratorNotVacuous:
    """Falsifier: if generate_domain_clearance_constraints() returns [] on a
    placement with a known MAINS/LV_CONTROL pair, the generator inspects
    nothing and is a silent no-op -- exactly the failure mode this project
    keeps rediscovering.
    """

    def _two_domain_placement(self) -> tuple[dict, dict]:
        placement = {
            "components": [
                {"ref": "F1", "position": (10.0, 10.0), "nets": ["ac_l"]},
                {"ref": "J1", "position": (10.8, 10.0), "nets": ["gnd"]},
            ],
            "nets": {},
        }
        voltage_domains = {
            "ac_l": VoltageDomain.MAINS,
            "gnd": VoltageDomain.LV_CONTROL,
        }
        return placement, voltage_domains

    def test_generator_is_not_vacuous(self) -> None:
        placement, voltage_domains = self._two_domain_placement()
        constraints = generate_domain_clearance_constraints(placement, voltage_domains)
        assert len(constraints) >= 1, (
            "Falsifier fired: generator produced 0 constraints for a placement "
            "with a real MAINS<->LV_CONTROL pair -- it is inspecting nothing."
        )

    def test_margin_is_the_stricter_of_basic_and_reinforced(self) -> None:
        placement, voltage_domains = self._two_domain_placement()
        constraints = generate_domain_clearance_constraints(placement, voltage_domains)
        [c] = [c for c in constraints if {c.a, c.b} == {"F1", "J1"}]
        # MAINS<->LV_CONTROL: basic (3.0/6.3) and reinforced (6.0/12.6) both
        # apply; the stricter (max of clearance/creepage across both rows)
        # must win. Creepage figures are the IEC 60335-1 Table 17 400V row
        # (MAINS's own working voltage, 340V peak/transient, is >250V and
        # the table is not interpolated), Pollution Degree 3 (corrected from
        # PD2 2026-07-30) -- see
        # docs/evidence/2026-07-30-pollution-degree-determination.md.
        assert c.min_distance_mm == 12.6
        assert c.tier == ConstraintTier.HARD
        assert c.id == "domain_clearance_F1_J1"

    def test_same_ref_pair_never_self_constrained(self) -> None:
        """A component straddling two domains (an isolation device) must
        never generate a SEPARATED constraint against itself."""
        placement = {
            "components": [
                {"ref": "PS1", "position": (0.0, 0.0), "nets": ["PWR_RTN", "gnd"]},
            ],
            "nets": {},
        }
        voltage_domains = {"PWR_RTN": VoltageDomain.DC_BUS, "gnd": VoltageDomain.LV_CONTROL}
        constraints = generate_domain_clearance_constraints(placement, voltage_domains)
        for c in constraints:
            assert c.a != c.b

    def test_component_refs_filter_restricts_output(self) -> None:
        placement, voltage_domains = self._two_domain_placement()
        constraints = generate_domain_clearance_constraints(
            placement, voltage_domains, component_refs={"F1"}
        )
        assert constraints == []

    def test_no_violation_pair_within_matrix_min_mm(self) -> None:
        """Two components 20mm apart (comfortably beyond every matrix
        requirement) still get a constraint generated -- the generator
        constrains the *pair*, irrespective of current distance; it is a
        placement-time constraint, not a post-hoc violation reporter."""
        placement = {
            "components": [
                {"ref": "A", "position": (0.0, 0.0), "nets": ["ac_l"]},
                {"ref": "B", "position": (20.0, 0.0), "nets": ["gnd"]},
            ],
            "nets": {},
        }
        voltage_domains = {"ac_l": VoltageDomain.MAINS, "gnd": VoltageDomain.LV_CONTROL}
        constraints = generate_domain_clearance_constraints(placement, voltage_domains)
        assert len(constraints) == 1


class TestIntraFootprintDomainConflicts:
    """R24-follow-up (2026-07-30): self-pairs are excluded from
    ``generate_domain_clearance_constraints``'s output for a real, provable
    reason (see module docstring), but that exclusion used to be silent --
    no log, no queryable signal, nothing distinguishing "no isolator on
    this board" from "an isolator exists and nothing is protecting it".
    These tests pin the new, loud alternative.
    """

    def test_straddling_component_is_flagged(self) -> None:
        placement = {
            "components": [
                {"ref": "PS1", "position": (0.0, 0.0), "nets": ["ac_l", "gnd"]},
            ],
            "nets": {},
        }
        voltage_domains = {"ac_l": VoltageDomain.MAINS, "gnd": VoltageDomain.LV_CONTROL}
        conflicts = find_intra_footprint_domain_conflicts(placement, voltage_domains)
        assert len(conflicts) == 1
        c = conflicts[0]
        assert c.ref == "PS1"
        assert {c.domain_a, c.domain_b} == {VoltageDomain.MAINS, VoltageDomain.LV_CONTROL}
        assert c.margin_mm == 12.6  # PD3 reinforced creepage requirement

    def test_non_straddling_components_not_flagged(self) -> None:
        placement, voltage_domains = TestGeneratorNotVacuous()._two_domain_placement()
        conflicts = find_intra_footprint_domain_conflicts(placement, voltage_domains)
        assert conflicts == []

    def test_same_domain_row_never_flags_a_straddle(self) -> None:
        """A component entirely within LV_CONTROL cannot "straddle"
        LV_CONTROL<->LV_CONTROL (domain_a == domain_b) -- that row governs
        pairs of *different* LV_CONTROL components, not a single one."""
        placement = {
            "components": [
                {"ref": "R1", "position": (0.0, 0.0), "nets": ["gnd", "+3V3"]},
            ],
            "nets": {},
        }
        voltage_domains = {"gnd": VoltageDomain.LV_CONTROL, "+3V3": VoltageDomain.LV_CONTROL}
        assert find_intra_footprint_domain_conflicts(placement, voltage_domains) == []

    def test_component_refs_filter_applies(self) -> None:
        placement = {
            "components": [
                {"ref": "PS1", "position": (0.0, 0.0), "nets": ["ac_l", "gnd"]},
            ],
            "nets": {},
        }
        voltage_domains = {"ac_l": VoltageDomain.MAINS, "gnd": VoltageDomain.LV_CONTROL}
        assert (
            find_intra_footprint_domain_conflicts(
                placement, voltage_domains, component_refs={"OTHER"}
            )
            == []
        )

    def test_generator_warns_when_conflicts_present(self, caplog) -> None:
        """The generator itself must surface this, not just the standalone
        finder function -- a caller that only calls
        generate_domain_clearance_constraints (the common case) must still
        see the signal."""
        import logging

        placement = {
            "components": [
                {"ref": "PS1", "position": (0.0, 0.0), "nets": ["ac_l", "gnd"]},
            ],
            "nets": {},
        }
        voltage_domains = {"ac_l": VoltageDomain.MAINS, "gnd": VoltageDomain.LV_CONTROL}
        with caplog.at_level(logging.WARNING):
            generate_domain_clearance_constraints(placement, voltage_domains)
        assert any("PS1" in rec.message for rec in caplog.records), (
            "generator produced no warning naming the intra-footprint ref -- "
            "the exclusion is silent again"
        )

    def test_real_board_finds_known_isolators(self) -> None:
        """Cross-check against the validator's own real-board finding
        (test_clearance.py::TestClearanceIntegration, 13 intra-footprint
        records across {C6, K1, K2, K3, T1, U3, U7} at the current 10.0mm
        reinforced bar): every one of those refs must appear here too, since
        this is deliberately the coarser, component-level superset check
        (see docstring) -- a false negative here would mean a real
        REQ-SAFE-01 intra-footprint violation that this early-warning
        mechanism failed to flag at all."""
        import pytest

        from tests.requirements.safety._real_board_fixture import (
            RealBoardUnavailable,
            load_real_board_placement,
        )

        try:
            placement, voltage_domains, _stats = load_real_board_placement()
        except RealBoardUnavailable as exc:
            pytest.skip(f"{exc} (run `make netlist` first)")

        conflicts = find_intra_footprint_domain_conflicts(placement, voltage_domains)
        flagged_refs = {c.ref for c in conflicts}
        known_validator_intra_refs = {"C6", "K1", "K2", "K3", "T1", "U3", "U7"}
        missing = known_validator_intra_refs - flagged_refs
        assert not missing, (
            f"{missing} have a REAL pad-level intra-footprint REQ-SAFE-01 "
            f"violation (per the validator) but this component-level "
            f"early-warning check missed them -- it should be a superset, "
            f"never a subset, of the validator's own finding."
        )


class TestRequiredMarginMm:
    def test_max_of_clearance_and_creepage(self) -> None:
        assert required_margin_mm({"min_clearance_mm": 6.0, "min_creepage_mm": 8.0}) == 8.0

    def test_every_matrix_row_creepage_dominates_today(self) -> None:
        """Documents the current matrix property this module's docstring
        relies on (creepage >= clearance in every row today) without
        assuming it silently -- if this ever flips, this test fails loudly
        rather than the margin computation silently using the wrong value."""
        for requirements in IEC60335_REQUIREMENTS.values():
            assert requirements["min_creepage_mm"] >= requirements["min_clearance_mm"]


# ---------------------------------------------------------------------------
# Group 2: R24 item 2 -- BMC-exhaustive Chebyshev soundness sweep
# ---------------------------------------------------------------------------


def _chebyshev_box_separated(
    center_a: tuple[float, float],
    half_a: tuple[float, float],
    center_b: tuple[float, float],
    half_b: tuple[float, float],
    margin: float,
) -> bool:
    """Reimplements handlers/separated.py::encode_separated's disjunction
    directly on rectangles (not as a CP-SAT model) so it can be swept
    exhaustively without invoking the solver per point.

    left  = a.x_end + margin <= b.x_start
    right = b.x_end + margin <= a.x_start
    below = a.y_end + margin <= b.y_start
    above = b.y_end + margin <= a.y_start
    return (left or right) or (below or above)
    """
    ax, ay = center_a
    hax, hay = half_a
    bx, by = center_b
    hbx, hby = half_b

    a_x_start, a_x_end = ax - hax, ax + hax
    a_y_start, a_y_end = ay - hay, ay + hay
    b_x_start, b_x_end = bx - hbx, bx + hbx
    b_y_start, b_y_end = by - hby, by + hby

    left = a_x_end + margin <= b_x_start
    right = b_x_end + margin <= a_x_start
    below = a_y_end + margin <= b_y_start
    above = b_y_end + margin <= a_y_start
    return left or right or below or above


class TestChebyshevSoundnessBMC:
    """BMC-exhaustive validation (R24 item 2).

    Falsifier: if this sweep finds ANY (offset, size, margin) combination
    where the Chebyshev encoding reports "separated" (would be SAT) but the
    validator's own Euclidean-distance oracle (``_distance``, the exact
    function ``clearance.py::_check_distance`` calls) reports a distance
    below the margin, the soundness proof in
    ``domain_clearance.py``'s module docstring is false and this test must
    fail. It does not fire below.
    """

    def test_exhaustive_offsets_bounded_grid(self) -> None:
        # Bounded N: three courtyard half-size pairs (covering degenerate
        # 0-size point components, small, and asymmetric footprints), full
        # integer-mm offset sweep over a window comfortably larger than
        # every IEC60335_REQUIREMENTS margin (up to 12.6mm -- corrected from
        # 10.0mm 2026-07-30, see
        # docs/evidence/2026-07-30-pollution-degree-determination.md), at
        # margins spanning the matrix's actual values.
        half_size_pairs = [
            ((0.0, 0.0), (0.0, 0.0)),
            ((0.5, 0.5), (1.0, 0.5)),
            ((1.5, 2.0), (0.75, 0.75)),
        ]
        margins = [1.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.6]
        offsets = range(-14, 15)  # -14mm..+14mm inclusive, 1mm steps

        checked = 0
        counterexamples = []
        center_a = (0.0, 0.0)
        for (half_a, half_b), margin, dx, dy in itertools.product(
            half_size_pairs, margins, offsets, offsets
        ):
            center_b = (float(dx), float(dy))
            encoded_ok = _chebyshev_box_separated(center_a, half_a, center_b, half_b, margin)
            checked += 1
            if encoded_ok:
                oracle_distance = _distance(center_a, center_b)
                if oracle_distance < margin:
                    counterexamples.append((half_a, half_b, margin, dx, dy, oracle_distance))

        assert checked > 9_000, "sweep collapsed to a trivial size -- not exhaustive enough"
        assert counterexamples == [], (
            f"Soundness FALSIFIED: {len(counterexamples)} case(s) where the Chebyshev "
            f"box encoding claimed separation but the oracle Euclidean center distance "
            f"was below the margin. First: {counterexamples[:3]}"
        )

    def test_sweep_is_not_trivially_all_true_or_all_false(self) -> None:
        """Falsifier for the BMC test itself: if encoded_ok were always True
        (or always False) across the sweep, the implication being checked
        would be vacuous. Confirm both outcomes actually occur."""
        half = ((0.5, 0.5), (0.5, 0.5))
        margin = 4.0
        results = {
            _chebyshev_box_separated((0.0, 0.0), half[0], (float(dx), 0.0), half[1], margin)
            for dx in range(-10, 11)
        }
        assert results == {True, False}, (
            "BMC sweep is vacuous -- encoded_ok never varies across the offset range"
        )


# ---------------------------------------------------------------------------
# Group 3: R24 item 3 -- post-solve audit
# ---------------------------------------------------------------------------


class TestPostSolveAudit:
    def test_clean_placement_has_no_audit_violations(self) -> None:
        c = SeparatedConstraint(
            a="F1",
            b="J1",
            min_distance_mm=8.0,
            tier=ConstraintTier.HARD,
            because="test placeholder rationale",
            id="domain_clearance_F1_J1",
        )
        # 8mm apart on x-axis -- exactly meets the requirement.
        resolved = {"F1": (0.0, 0.0), "J1": (8.0, 0.0)}
        violations = audit_domain_clearance([c], resolved)
        assert violations == []

    def test_broken_placement_is_caught(self) -> None:
        """The audit must not trust the solver: even if a constraint claims
        to require 8mm, a resolved placement that actually violates it
        (e.g. from a bug in the handler or a units error) must be flagged."""
        c = SeparatedConstraint(
            a="F1",
            b="J1",
            min_distance_mm=8.0,
            tier=ConstraintTier.HARD,
            because="test placeholder rationale",
            id="domain_clearance_F1_J1",
        )
        resolved = {"F1": (0.0, 0.0), "J1": (0.836, 0.0)}  # the real pre-fix distance
        violations = audit_domain_clearance([c], resolved)
        assert len(violations) == 1
        v = violations[0]
        assert v.ref_a == "F1"
        assert v.ref_b == "J1"
        assert v.required_mm == 8.0
        assert abs(v.actual_mm - 0.836) < 1e-9

    def test_missing_resolved_position_is_flagged_not_silently_skipped(self) -> None:
        c = SeparatedConstraint(
            a="F1",
            b="MISSING",
            min_distance_mm=8.0,
            tier=ConstraintTier.HARD,
            because="test placeholder rationale",
            id="domain_clearance_F1_MISSING",
        )
        violations = audit_domain_clearance([c], {"F1": (0.0, 0.0)})
        assert len(violations) == 1
        assert "missing resolved position" in violations[0].reason

    def test_non_domain_clearance_constraints_are_ignored(self) -> None:
        """Courtyard/netclass SEPARATED constraints (different id prefix)
        are not this audit's concern -- confirm it does not misfire on
        them."""
        c = SeparatedConstraint(
            a="A",
            b="B",
            min_distance_mm=100.0,
            tier=ConstraintTier.HARD,
            because="courtyard clearance",
            id="courtyard_A_B",
        )
        # Would violate if audited -- must be skipped entirely.
        violations = audit_domain_clearance([c], {"A": (0.0, 0.0), "B": (0.1, 0.0)})
        assert violations == []


# ---------------------------------------------------------------------------
# Group 4: real-board regression -- TP3's net must be classified
# ---------------------------------------------------------------------------


class TestRealBoardTP3Coverage:
    """Falsifier for a specific DRC finding: kicad-cli reports a
    HighVoltage-netclass clearance violation between `TP3` (a UVL-02 test
    point on `safety.uvlo_logic-line`) and `U7` (DC_BUS_RTN). Root cause:
    `TP3`'s net was entirely absent from
    `tests.requirements.safety._real_board_fixture._NET_DOMAINS`, so this
    generator -- which pairs components purely off that classification --
    silently produced zero `SeparatedConstraint`s for any pair involving
    `TP3`. This class checks the generator's real-board behavior directly
    (not just the fixture's own classification, covered separately in
    `tests/requirements/safety/test_clearance.py::
    TestClearanceIntegration::test_tp3_uvlo_line_is_classified`) so a
    regression in either the fixture *or* the generator's own pairing logic
    is caught here.
    """

    def _load(self):
        import pytest

        from tests.requirements.safety._real_board_fixture import (
            RealBoardUnavailable,
            load_real_board_placement,
        )

        try:
            return load_real_board_placement()
        except RealBoardUnavailable as exc:
            pytest.skip(f"{exc} (run `make netlist` first)")

    def test_generator_emits_at_least_one_constraint_for_tp3(self) -> None:
        placement, voltage_domains, _stats = self._load()
        constraints = generate_domain_clearance_constraints(placement, voltage_domains)
        tp3_constraints = [c for c in constraints if c.a == "TP3" or c.b == "TP3"]
        assert tp3_constraints, (
            "generate_domain_clearance_constraints() produced 0 constraints "
            "involving TP3 against the real board -- TP3's net "
            "(safety.uvlo_logic-line) is unclassified again, so the "
            "generator is silently skipping every pair that touches it "
            "(the exact R24-follow-up gap this test guards)."
        )

    def test_generator_covers_the_tp3_u7_pair_specifically(self) -> None:
        """The DRC finding this session investigated was specifically
        TP3<->U7 (kicad-cli: HighVoltage netclass, 2.0mm required, 0.336mm
        actual). Confirm the generator emits a constraint for this pair at
        the DC_BUS<->LV_CONTROL margin (12.6mm -- corrected from 10.0mm
        2026-07-30, see
        docs/evidence/2026-07-30-pollution-degree-determination.md:
        IEC 60335-2-6 cl. 29.2 Addition makes Pollution Degree 3 the
        default for this appliance class and no enclosure/sealing argument
        earns the PD2 exception on this design's own mechanical documents.
        DC_BUS's working voltage, peak/transient 400V, is >250V and <=400V
        -- IEC 60335-1 Table 17 row iv, Material Group IIIa/IIIb, PD3 --
        giving reinforced creepage 12.6mm, not the PD2 figure this test
        previously checked against).

        U7 genuinely straddles domains (it carries `gnd`/`+3V3` -- both
        LV_CONTROL -- *and* `DC_BUS_RTN`, i.e. it is a level-shifting gate
        driver, confirmed directly: ``[c['nets'] for c in placement if
        c['ref']=='U7'] == ['gnd', '+3V3', 'DC_BUS_RTN']``). Because the
        generator's pair-dict key is the *ordered* tuple ``(ref_a, ref_b)``
        rather than a canonicalized/unordered one, the same physical
        TP3/U7 pair can be emitted under two different keys when it
        matches rows from different domain groupings with reversed
        ref order -- here, ``domain_clearance_U7_TP3`` (12.6mm, from the
        DC_BUS<->LV_CONTROL cross-domain rows, where U7 is drawn from the
        DC_BUS group) *and* ``domain_clearance_TP3_U7`` (1.0mm, from the
        LV_CONTROL<->LV_CONTROL functional same-domain row, where both are
        drawn from the LV_CONTROL group and happen to be visited in that
        order). This does not lose safety margin -- the stricter 12.6mm
        constraint is still emitted and still audited under its own id --
        so this test checks that the *strictest* margin among any
        constraint touching this unordered pair is the expected 12.6mm,
        rather than assuming a single key.
        """
        placement, voltage_domains, _stats = self._load()
        constraints = generate_domain_clearance_constraints(placement, voltage_domains)
        matches = [c for c in constraints if {c.a, c.b} == {"TP3", "U7"}]
        assert matches, (
            "No SeparatedConstraint generated for the TP3<->U7 pair -- "
            "either TP3's net is unclassified again, or U7 no longer "
            "carries a DC_BUS-domain net (DC_BUS_RTN)."
        )
        # DC_BUS<->LV_CONTROL: max across basic (3.0/6.3) and reinforced
        # (6.0/12.6) rows is 12.6mm. This must appear among the (possibly
        # multiple, see docstring) constraints for this pair.
        assert max(c.min_distance_mm for c in matches) == 12.6
