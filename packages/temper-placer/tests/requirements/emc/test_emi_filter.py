"""
Tests for REQ-EMC-03: EMI Filter Layout Requirements.

These tests verify that EMI filter component placement meets EN 55014-1
requirements for conducted emissions.
"""

import pytest

try:
    from tests.requirements.validators.emi_filter import (
        EMIFilterResult,
        FilterComponent,
        check_cm_choke_placement,
        check_filter_component_order,
        check_filter_signal_flow,
        check_line_neutral_pe_spacing,
        check_mov_placement,
        check_pe_trace_requirements,
        check_x_cap_placement,
        check_y_cap_placement,
    )

    VALIDATORS_AVAILABLE = True
except ImportError:
    VALIDATORS_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not VALIDATORS_AVAILABLE, reason="EMI filter validators not yet implemented"
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def correct_filter_layout():
    """EMI filter with correct component placement.

    MOV is downstream of (after) the fuse, not before it -- corrected
    2026-07-26, see check_mov_placement's docstring and
    docs/evidence/2026-07-26-emc-validators-implemented.md "Addendum": an
    MOV ahead of the fuse fails short with no overcurrent protection.
    """
    return {
        "input_connector": (10.0, 50.0),
        "components": {
            FilterComponent.FUSE: (15.0, 50.0),
            FilterComponent.MOV: (20.0, 50.0),
            FilterComponent.L_DM: (30.0, 50.0),
            FilterComponent.C_X1: (40.0, 50.0),
            FilterComponent.L_CM: (50.0, 50.0),
            FilterComponent.C_Y1: (55.0, 45.0),
            FilterComponent.C_Y2: (55.0, 55.0),
            FilterComponent.C_X2: (60.0, 50.0),
        },
    }


@pytest.fixture
def incorrect_filter_order():
    """EMI filter with incorrect component order."""
    return {
        "input_connector": (10.0, 50.0),
        "components": {
            FilterComponent.FUSE: (20.0, 50.0),
            FilterComponent.C_X1: (30.0, 50.0),  # X-cap before L_CM - wrong
            FilterComponent.L_CM: (40.0, 50.0),
            FilterComponent.MOV: (50.0, 50.0),  # MOV after choke - wrong
        },
    }


# =============================================================================
# Signal Flow Tests
# =============================================================================


class TestFilterSignalFlow:
    """Tests for EMI filter signal flow validation."""

    def test_correct_signal_flow_passes(self, correct_filter_layout):
        """Correct left-to-right signal flow should pass."""
        result = check_filter_signal_flow(
            component_positions=correct_filter_layout["components"],
            input_connector_position=correct_filter_layout["input_connector"],
        )

        assert result.passed
        assert result.error_count == 0

    def test_reversed_flow_fails(self):
        """Reversed signal flow should fail."""
        result = check_filter_signal_flow(
            component_positions={
                FilterComponent.FUSE: (60.0, 50.0),  # Reversed
                FilterComponent.L_CM: (40.0, 50.0),
                FilterComponent.C_X1: (20.0, 50.0),
            },
            input_connector_position=(10.0, 50.0),
        )

        assert not result.passed

    def test_components_not_aligned_warning(self):
        """Components not aligned horizontally should generate warning."""
        result = check_filter_signal_flow(
            component_positions={
                FilterComponent.FUSE: (20.0, 50.0),
                FilterComponent.L_CM: (40.0, 70.0),  # Offset vertically
                FilterComponent.C_X1: (60.0, 30.0),  # Offset vertically
            },
            input_connector_position=(10.0, 50.0),
        )

        # May pass but with warnings about alignment
        assert isinstance(result, EMIFilterResult)


# =============================================================================
# Component Order Tests
# =============================================================================


class TestFilterComponentOrder:
    """Tests for EMI filter component topology order."""

    def test_correct_order_passes(self, correct_filter_layout):
        """Correct component order should pass."""
        result = check_filter_component_order(
            component_positions=correct_filter_layout["components"]
        )

        assert result.passed

    def test_incorrect_order_fails(self, incorrect_filter_order):
        """Incorrect component order should fail."""
        result = check_filter_component_order(
            component_positions=incorrect_filter_order["components"]
        )

        assert not result.passed
        assert result.error_count >= 1

    def test_x_cap_before_cm_choke(self):
        """X-caps must be before CM choke.

        Fixed 2026-07-26: the original fixture placed the *second* X-cap
        (C_X2) after the choke and labeled that "wrong" -- but the
        canonical topology this same module's docstring defines
        (MOV, FUSE, L_DM, C_X1, L_CM, C_Y1, C_Y2, C_X2) puts C_X2 *after*
        the choke by design (it is the output-stage cap of a two-stage
        Pi filter). That fixture was internally inconsistent with its own
        stated intent ("X-caps must be before CM choke" is true of C_X1,
        not C_X2). Corrected to actually test C_X1 placed after the choke.
        """
        result = check_filter_component_order(
            component_positions={
                FilterComponent.L_CM: (40.0, 50.0),
                FilterComponent.C_X1: (50.0, 50.0),  # After choke - wrong (C_X1 must precede it)
            }
        )

        assert not result.passed

    def test_y_caps_after_cm_choke(self):
        """Y-caps must be after CM choke."""
        result = check_filter_component_order(
            component_positions={
                FilterComponent.C_Y1: (30.0, 45.0),  # Before choke - wrong
                FilterComponent.L_CM: (40.0, 50.0),
                FilterComponent.C_Y2: (50.0, 55.0),  # After choke - correct
            }
        )

        assert not result.passed


# =============================================================================
# X-Capacitor Placement Tests
# =============================================================================


class TestXCapPlacement:
    """Tests for X-capacitor placement requirements."""

    def test_x_caps_line_to_neutral_only(self):
        """X-caps should connect line to neutral, not to PE."""
        result = check_x_cap_placement(
            x_cap_positions={"C_X1": (40.0, 50.0)},
            line_trace=[(35.0, 52.0), (40.0, 52.0), (45.0, 52.0)],
            neutral_trace=[(35.0, 48.0), (40.0, 48.0), (45.0, 48.0)],
            pe_trace=[(35.0, 40.0), (45.0, 40.0)],  # No connection to PE
        )

        assert result.passed

    def test_x_cap_connected_to_pe_fails(self):
        """X-cap connected to PE should fail."""
        result = check_x_cap_placement(
            x_cap_positions={"C_X1": (40.0, 50.0)},
            line_trace=[(35.0, 52.0), (40.0, 52.0), (45.0, 52.0)],
            neutral_trace=[(35.0, 48.0), (40.0, 48.0), (45.0, 48.0)],
            pe_trace=[(35.0, 40.0), (40.0, 45.0), (45.0, 40.0)],  # Connected!
        )

        assert not result.passed

    def test_x_cap_trace_length(self):
        """X-cap traces should be short and fat."""
        # TODO: Implement trace length/width checking
        pytest.skip("Trace geometry checking not yet implemented")


# =============================================================================
# Y-Capacitor Placement Tests
# =============================================================================


class TestYCapPlacement:
    """Tests for Y-capacitor placement requirements."""

    def test_y_caps_within_leakage_limit(self):
        """Total Y-cap capacitance should be ≤4.4nF."""
        result = check_y_cap_placement(
            y_cap_positions={"C_Y1": (55.0, 45.0), "C_Y2": (55.0, 55.0)},
            y_cap_values={"C_Y1": 2.2, "C_Y2": 2.2},  # Total 4.4nF
            pe_connection=(60.0, 50.0),
            max_total_capacitance_nf=4.4,
        )

        assert result.passed

    def test_y_caps_exceed_leakage_limit_fails(self):
        """Total Y-cap capacitance >4.4nF should fail."""
        result = check_y_cap_placement(
            y_cap_positions={"C_Y1": (55.0, 45.0), "C_Y2": (55.0, 55.0)},
            y_cap_values={"C_Y1": 3.3, "C_Y2": 3.3},  # Total 6.6nF - too much
            pe_connection=(60.0, 50.0),
            max_total_capacitance_nf=4.4,
        )

        assert not result.passed

    def test_y_caps_close_to_pe(self):
        """Y-caps should have short traces to PE."""
        result = check_y_cap_placement(
            y_cap_positions={"C_Y1": (55.0, 45.0)},
            y_cap_values={"C_Y1": 2.2},
            pe_connection=(56.0, 45.0),  # 1mm away - good
            max_total_capacitance_nf=4.4,
        )

        assert result.passed


# =============================================================================
# MOV Placement Tests
# =============================================================================


class TestMOVPlacement:
    """Tests for MOV (surge suppressor) placement.

    Corrected 2026-07-26: the requirement is MOV *downstream of* (after)
    the fuse, not before it -- see check_mov_placement's docstring and
    docs/evidence/2026-07-26-emc-validators-implemented.md "Addendum" for
    why the original "before or parallel to fuse" requirement was backwards
    for a safety-certified mains appliance (an MOV ahead of the fuse fails
    short with no overcurrent protection).
    """

    def test_mov_at_input(self):
        """MOV should be at the AC input, downstream of the fuse."""
        result = check_mov_placement(
            mov_position=(20.0, 50.0),
            fuse_position=(15.0, 50.0),
            input_connector=(10.0, 50.0),
            line_trace=[(10.0, 52.0), (15.0, 52.0), (20.0, 52.0)],
            neutral_trace=[(10.0, 48.0), (15.0, 48.0), (20.0, 48.0)],
        )

        assert result.passed

    def test_mov_before_fuse_fails(self):
        """MOV upstream of (before) the fuse should fail -- an end-of-life
        MOV short would then have no overcurrent protection."""
        result = check_mov_placement(
            mov_position=(10.0, 50.0),  # Before fuse -- unprotected if it shorts
            fuse_position=(20.0, 50.0),
            input_connector=(5.0, 50.0),
            line_trace=[(5.0, 52.0), (10.0, 52.0), (20.0, 52.0)],
            neutral_trace=[(5.0, 48.0), (10.0, 48.0), (20.0, 48.0)],
        )

        assert not result.passed
        assert any(v.code == "MOV-001" for v in result.violations)


# =============================================================================
# Common-Mode Choke Tests
# =============================================================================


class TestCMChokePlacement:
    """Tests for common-mode choke placement."""

    def test_cm_choke_after_x_caps(self):
        """CM choke should be after X-caps."""
        result = check_cm_choke_placement(
            cm_choke_position=(50.0, 50.0),
            x_cap_positions={"C_X1": (40.0, 50.0)},  # Before choke
            y_cap_positions={"C_Y1": (55.0, 45.0)},  # After choke
        )

        assert result.passed

    def test_cm_choke_before_x_caps_fails(self):
        """CM choke before X-caps should fail."""
        result = check_cm_choke_placement(
            cm_choke_position=(35.0, 50.0),
            x_cap_positions={"C_X1": (40.0, 50.0)},  # After choke - wrong
            y_cap_positions={"C_Y1": (55.0, 45.0)},
        )

        assert not result.passed

    def test_cm_choke_after_y_caps_fails(self):
        """CM choke after Y-caps should fail (falsifier for CMC-002)."""
        result = check_cm_choke_placement(
            cm_choke_position=(60.0, 50.0),
            x_cap_positions={"C_X1": (40.0, 50.0)},  # Before choke - correct
            y_cap_positions={"C_Y1": (55.0, 45.0)},  # Before choke - wrong
        )

        assert not result.passed
        assert result.error_count >= 1


# =============================================================================
# PE Trace Tests
# =============================================================================


class TestPETraceRequirements:
    """Tests for protective earth trace requirements."""

    def test_pe_trace_width(self):
        """PE trace should be ≥2mm wide."""
        result = check_pe_trace_requirements(
            pe_trace=[(10.0, 40.0), (60.0, 40.0)],
            pe_connection=(60.0, 40.0),
            earth_stud=(70.0, 40.0),
            min_width_mm=2.0,
        )

        # Should check trace width
        assert isinstance(result, EMIFilterResult)

    def test_pe_trace_direct_path(self):
        """PE trace should be direct path to earth stud."""
        # Straight trace - good
        result = check_pe_trace_requirements(
            pe_trace=[(60.0, 40.0), (70.0, 40.0)],
            pe_connection=(60.0, 40.0),
            earth_stud=(70.0, 40.0),
            min_width_mm=2.0,
        )

        assert result.passed

    def test_pe_trace_width_below_minimum_fails(self):
        """PE trace narrower than min_width_mm should fail (falsifier for PE-001).

        Width can only be checked when the trace's points carry a width as a
        3rd tuple element (see check_pe_trace_requirements docstring note) --
        the plain 2-tuple contract every other fixture in this suite uses
        has no width channel at all.
        """
        result = check_pe_trace_requirements(
            pe_trace=[(60.0, 40.0, 1.0), (70.0, 40.0, 1.0)],  # 1mm wide < 2mm minimum
            pe_connection=(60.0, 40.0),
            earth_stud=(70.0, 40.0),
            min_width_mm=2.0,
        )

        assert not result.passed
        assert result.error_count >= 1

    def test_pe_trace_zigzag_not_direct_fails(self):
        """A PE trace that meanders well beyond the straight-line distance should fail
        (falsifier for PE-002)."""
        result = check_pe_trace_requirements(
            pe_trace=[(60.0, 40.0), (62.0, 60.0), (64.0, 20.0), (66.0, 55.0), (70.0, 40.0)],
            pe_connection=(60.0, 40.0),
            earth_stud=(70.0, 40.0),
            min_width_mm=2.0,
        )

        assert not result.passed
        assert result.error_count >= 1


# =============================================================================
# L/N/PE Spacing Tests
# =============================================================================


class TestLineNeutralPESpacing:
    """Tests for spacing between L/N and PE traces."""

    def test_adequate_spacing_passes(self):
        """L/N and PE with >6mm spacing should pass."""
        result = check_line_neutral_pe_spacing(
            line_trace=[(10.0, 52.0), (60.0, 52.0)],
            neutral_trace=[(10.0, 48.0), (60.0, 48.0)],
            pe_trace=[(10.0, 40.0), (60.0, 40.0)],  # 8mm from neutral
            min_spacing_mm=6.0,
        )

        assert result.passed

    def test_line_too_close_to_pe_fails(self):
        """Line trace <6mm from PE should fail (falsifier for LNPE-001)."""
        result = check_line_neutral_pe_spacing(
            line_trace=[(10.0, 44.0), (60.0, 44.0)],  # 4mm from PE - too close
            neutral_trace=[(10.0, 30.0), (60.0, 30.0)],
            pe_trace=[(10.0, 40.0), (60.0, 40.0)],
            min_spacing_mm=6.0,
        )

        assert not result.passed
        assert result.error_count >= 1

    def test_insufficient_spacing_fails(self):
        """L/N and PE with <6mm spacing should fail."""
        result = check_line_neutral_pe_spacing(
            line_trace=[(10.0, 52.0), (60.0, 52.0)],
            neutral_trace=[(10.0, 48.0), (60.0, 48.0)],
            pe_trace=[(10.0, 44.0), (60.0, 44.0)],  # 4mm from neutral - too close
            min_spacing_mm=6.0,
        )

        assert not result.passed


# =============================================================================
# Integration Tests
# =============================================================================


def _repo_root():
    from pathlib import Path

    # tests/requirements/emc/test_emi_filter.py -> repo root is 5 parents up
    # (emc -> requirements -> tests -> temper-placer -> packages -> root).
    return Path(__file__).resolve().parents[5]


def _load_real_emi_filter_positions() -> dict[str, tuple[float, float]]:
    """Load real component positions from the committed board.

    Reference designators are resolved from ``elec/build/default.csv`` (BOM,
    keyed by MPN -- default.net aliases part *identity* by footprint, per
    the task brief, so .csv is the reliable identity source), not hardcoded:
    F1=fuse, RV1=MOV (V150LA10AP varistor), L1=CM choke (B82726S2163N030),
    C1=the design's one X-cap (B32922C3224M289, source name ``c_x2`` --
    see the docstring on ``test_temper_board_emi_filter_compliance`` for why
    it plays the C_X1 role here), C6=the Y1 PE-bonding cap
    (DE1E3KX222MA4BA01, ``y_cap_pe`` in modules.ato).
    """
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    root = _repo_root()
    res = parse_kicad_pcb(root / "pcb" / "temper.kicad_pcb")
    comps = {c.ref: c for c in res.netlist.components}
    refs = {"F1": "fuse", "RV1": "mov", "L1": "cmc", "C1": "c_x", "C6": "c_y"}
    missing = [r for r in refs if r not in comps]
    if missing:
        pytest.skip(f"Real board is missing expected refs {missing} -- BOM/PCB may have changed")
    return {refs[r]: comps[r].initial_position for r in refs}


class TestEMIFilterIntegration:
    """Integration tests for complete EMI filter validation."""

    @pytest.mark.slow
    def test_temper_board_emi_filter_compliance(self):
        """Temper board EMI filter should meet all REQ-EMC-03 requirements.

        Implemented 2026-07-26, replacing "Temper board fixture not yet
        available"; **corrected the same day** after coordinator review
        overturned the original MOV finding -- see
        docs/evidence/2026-07-26-emc-validators-implemented.md "Addendum"
        for the full research and reasoning. Summary: the first pass of
        this test asserted `check_mov_placement` should FAIL on the real
        board (MOV placed after the fuse). That was backwards --
        `check_mov_placement`'s original "before or parallel to fuse"
        requirement was itself the bug, not this board's wiring. An MOV's
        dominant failure mode is a low-resistance short; placing it
        upstream of the fuse means a shorted MOV has no overcurrent
        protection at all -- a fire mechanism. The real design
        (`elec/src/modules.ato:658-659`: `fuse.p2 ~ mov.p1`) has the MOV
        correctly downstream of the fuse. The requirement was corrected
        (see `_CANONICAL_ORDER`'s comment in emi_filter.py and
        `check_mov_placement`'s docstring), and this test now asserts the
        real board PASSES.

        Two other real limitations remain, reported rather than papered
        over (see the evidence doc for the full writeup):

        1. ``pcb/temper.kicad_pcb`` has zero routed copper segments and
           zero vias (verified: ``grep -c '(segment'`` / ``'(via'`` both
           return 0). Every trace-geometry check (check_x_cap_placement's
           PE-proximity leg, check_pe_trace_requirements,
           check_line_neutral_pe_spacing) has nothing to measure and is
           skipped here rather than fed empty lists and reported as a
           fabricated "0 violations" pass.
        2. This board's EMI-filter parts are not laid out on a common axis
           (F1, RV1, L1, C1 span both X and Y widely), so the x-only
           "left-to-right flow" ordering check_filter_signal_flow /
           check_filter_component_order / check_cm_choke_placement assume
           is not a reliable proxy for true physical signal-path order on
           this specific layout -- these checks infer topology from
           geometry, which is unsound in general whenever a layout isn't
           collinear. Their raw output is reported in the evidence doc for
           completeness but is *not* asserted on here.
        """
        positions = _load_real_emi_filter_positions()

        # No AC input connector part exists in this design (ac_l/ac_n are
        # bare PowerInput-module-boundary signals -- confirmed:
        # `grep -c Connector elec/build/default.csv` finds only J1, a 2-pin
        # header unrelated to the mains input). There is nothing upstream
        # of the fuse to use as "input_connector_position"; using the
        # fuse's own position (fuse is the very first component ac_l
        # reaches) as an explicit, documented proxy rather than fabricating
        # a connector location.
        input_proxy = (positions["fuse"][0] - 0.01, positions["fuse"][1])

        result = check_mov_placement(
            mov_position=positions["mov"],
            fuse_position=positions["fuse"],
            input_connector=input_proxy,
            line_trace=[],  # not routed yet (0 segments in pcb/temper.kicad_pcb)
            neutral_trace=[],
        )

        assert result.passed, (
            "check_mov_placement should now PASS on the real board: MOV (RV1) is "
            "wired and placed downstream of the fuse (F1), which is the correct, "
            "safety-relevant requirement (see docstring above) -- a failure here "
            "would mean the fix regressed"
        )
        assert not any(v.code == "MOV-001" for v in result.violations)

    def test_complete_filter_validation(self, correct_filter_layout):
        """Complete EMI filter should pass all checks.

        Fixed 2026-07-26: this fixture parameter was named
        ``_correct_filter_layout`` (leading underscore), which does not
        match the ``correct_filter_layout`` fixture defined above -- a
        latent collection-time error masked for as long as this whole
        module was skipped via ``VALIDATORS_AVAILABLE = False``. Now that
        the validators exist, pytest raised "fixture not found" instead of
        silently skipping. Corrected the name; still intentionally skipped
        below pending a real aggregation helper (out of scope for this
        pass -- REQ-EMC-03's individual checks are implemented and tested
        independently).
        """
        # TODO: Run all validation functions
        # TODO: Aggregate results
        pytest.skip("Complete validation not yet implemented")
