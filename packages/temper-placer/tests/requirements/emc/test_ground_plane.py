"""
Tests for REQ-EMC-01: Ground Plane Continuity and Slot Avoidance.

These tests verify that ground plane continuity validation functions work correctly
and that placements meet EMC/EMI requirements.
"""

import pytest

# Import validators (will fail until implemented)
VALIDATORS_AVAILABLE = False
try:
    from tests.requirements.validators.ground_plane import (
        GroundPlaneResult,
        GroundPlaneViolation,
        check_signal_ground_reference,
        check_slot_lengths,
        check_star_ground_point,
        check_via_stitching,
    )

    # Check if validators are actually implemented (not just stubs)
    try:
        check_slot_lengths({}, max_slot_mm=30.0)
        VALIDATORS_AVAILABLE = True
    except NotImplementedError:
        VALIDATORS_AVAILABLE = False

except ImportError:
    # Define placeholder classes for TDD - tests will be skipped
    class GroundPlaneViolation:
        def __init__(self, code, message, location=None, severity="error"):
            self.code = code
            self.message = message
            self.location = location
            self.severity = severity

    class GroundPlaneResult:
        def __init__(self, passed, violations):
            self.passed = passed
            self.violations = violations

        @property
        def error_count(self):
            return sum(1 for v in self.violations if v.severity == "error")

        @property
        def warning_count(self):
            return sum(1 for v in self.violations if v.severity == "warning")

    def check_slot_lengths(*_args, **_kwargs):
        # Return empty result for TDD - tests will be skipped anyway
        return GroundPlaneResult(passed=True, violations=[])

    def check_signal_ground_reference(*_args, **_kwargs):
        # Return empty result for TDD - tests will be skipped anyway
        return GroundPlaneResult(passed=True, violations=[])

    def check_star_ground_point(*_args, **_kwargs):
        # Return empty result for TDD - tests will be skipped anyway
        return GroundPlaneResult(passed=True, violations=[])

    def check_via_stitching(*_args, **_kwargs):
        # Return empty result for TDD - tests will be skipped anyway
        return GroundPlaneResult(passed=True, violations=[])


pytestmark = pytest.mark.skipif(
    not VALIDATORS_AVAILABLE, reason="Ground plane validators not yet implemented"
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def simple_ground_plane():
    """Simple ground plane with no slots."""
    # TODO: Define ground plane geometry
    return {"slots": [], "cutouts": []}


@pytest.fixture
def ground_plane_with_long_slot():
    """Ground plane with slot exceeding 30mm."""
    return {
        "slots": [
            {"start": (10, 10), "end": (50, 10), "width": 2.0}  # 40mm slot
        ],
        "cutouts": [],
    }


@pytest.fixture
def ground_plane_with_short_slots():
    """Ground plane with acceptable short slots."""
    return {
        "slots": [
            {"start": (10, 10), "end": (30, 10), "width": 2.0},  # 20mm - OK
            {"start": (40, 10), "end": (65, 10), "width": 2.0},  # 25mm - OK
        ],
        "cutouts": [],
    }


# =============================================================================
# Slot Length Tests
# =============================================================================


class TestSlotLengths:
    """Tests for slot length validation."""

    def test_no_slots_passes(self, simple_ground_plane):
        """Ground plane with no slots should pass."""
        result = check_slot_lengths(simple_ground_plane, max_slot_mm=30.0)

        assert result.passed
        assert result.error_count == 0

    def test_long_slot_fails(self, ground_plane_with_long_slot):
        """Ground plane with slot >30mm should fail."""
        result = check_slot_lengths(ground_plane_with_long_slot, max_slot_mm=30.0)

        assert not result.passed
        assert result.error_count >= 1
        assert any("30mm" in v.message or "slot" in v.message.lower() for v in result.violations)

    def test_short_slots_pass(self, ground_plane_with_short_slots):
        """Ground plane with slots <30mm should pass."""
        result = check_slot_lengths(ground_plane_with_short_slots, max_slot_mm=30.0)

        assert result.passed
        assert result.error_count == 0

    def test_custom_threshold(self, ground_plane_with_short_slots):
        """Should respect custom slot length threshold."""
        # 25mm slot should fail with 20mm threshold
        result = check_slot_lengths(ground_plane_with_short_slots, max_slot_mm=20.0)

        assert not result.passed
        assert result.error_count >= 1


# =============================================================================
# Signal Ground Reference Tests
# =============================================================================


class TestSignalGroundReference:
    """Tests for signal trace ground reference validation."""

    def test_trace_over_solid_ground_passes(self):
        """Signal trace over continuous ground should pass."""
        traces = [{"net": "SPI_CLK", "path": [(10, 10), (50, 10)], "layer": "F.Cu"}]
        ground_plane = {
            "layer": "In1.Cu",
            "geometry": [(0, 0, 100, 100)],  # Solid ground under trace
        }

        result = check_signal_ground_reference(traces, ground_plane)
        assert result.passed

    def test_trace_over_slot_fails(self):
        """Signal trace crossing ground slot should fail."""
        traces = [{"net": "SPI_MOSI", "path": [(10, 10), (50, 10)], "layer": "F.Cu"}]
        ground_plane = {
            "layer": "In1.Cu",
            "geometry": [(0, 0, 100, 100)],
            "slots": [{"start": (20, 0), "end": (20, 100), "width": 2.0}],  # Slot crosses trace
        }

        result = check_signal_ground_reference(traces, ground_plane)
        assert not result.passed
        assert result.error_count >= 1

    def test_critical_signals_checked(self):
        """Critical signals (SPI, gate drive, ADC) must have ground reference."""
        critical_nets = ["SPI_CLK", "SPI_MOSI", "GATE_H", "CT_SENSE", "NTC_SENSE"]

        traces = [
            {"net": net, "path": [(10, 10), (50, 10)], "layer": "F.Cu"} for net in critical_nets
        ]
        ground_plane = {
            "layer": "In1.Cu",
            "geometry": [(0, 0, 100, 100)],
            "slots": [{"start": (30, 0), "end": (30, 100), "width": 2.0}],  # Crosses all
        }

        result = check_signal_ground_reference(traces, ground_plane)

        # Should have violations for all critical signals
        assert not result.passed
        assert result.error_count >= len(critical_nets)


# =============================================================================
# Star Ground Point Tests
# =============================================================================


class TestStarGroundPoint:
    """Tests for star ground verification."""

    def test_single_connection_passes(self):
        """Single PGND-CGND connection point should pass."""
        ground_domains = {
            "PGND": {"area": [(0, 0, 50, 100)]},
            "CGND": {"area": [(50, 0, 100, 100)]},
            "connections": [{"from": "PGND", "to": "CGND", "location": (50, 50), "width": 10.0}],
        }

        result = check_star_ground_point(ground_domains)
        assert result.passed

    def test_multiple_connections_fail(self):
        """Multiple PGND-CGND connections should fail (ground loop)."""
        ground_domains = {
            "PGND": {"area": [(0, 0, 50, 100)]},
            "CGND": {"area": [(50, 0, 100, 100)]},
            "connections": [
                {"from": "PGND", "to": "CGND", "location": (50, 30), "width": 10.0},
                {"from": "PGND", "to": "CGND", "location": (50, 70), "width": 10.0},
            ],
        }

        result = check_star_ground_point(ground_domains)
        assert not result.passed
        assert result.error_count >= 1
        assert any(
            "multiple" in v.message.lower() or "star" in v.message.lower()
            for v in result.violations
        )

    def test_isolated_ground_separate(self):
        """ISOGND should be completely separate (no connections)."""
        ground_domains = {
            "PGND": {"area": [(0, 0, 50, 100)]},
            "CGND": {"area": [(50, 0, 80, 100)]},
            "ISOGND": {"area": [(80, 0, 100, 100)]},
            "connections": [
                {"from": "PGND", "to": "CGND", "location": (50, 50), "width": 10.0},
                # No connections to ISOGND - correct
            ],
        }

        result = check_star_ground_point(ground_domains)
        assert result.passed

    def test_direct_tie_into_isolated_domain_fails(self):
        """A bare/direct connection into an isolated domain must fail, even
        as the *only* connection (falsifier for SG-003).

        This is the specific defect docs/hardware/SELV_ISOLATION_REDESIGN.md
        removed: a single-point star join (`power_return ~ gnd`) that looked
        like textbook "one connection = correct star ground" but actually
        shorted a 4.2kVAC isolation barrier between an isolated SELV domain
        and the HV return. A star-ground checker that treats "exactly one
        connection" as always-correct would encode that removed defect as a
        requirement -- this test asserts it does not.
        """
        ground_domains = {
            "PGND": {"area": [(0, 0, 50, 100)]},
            "ISOGND": {"area": [(50, 0, 100, 100)]},
            "connections": [
                # Bare tie, no isolation device -- exactly the shorted-barrier pattern.
                {"from": "PGND", "to": "ISOGND", "location": (50, 50), "width": 10.0},
            ],
        }

        result = check_star_ground_point(ground_domains)
        assert not result.passed
        assert result.error_count >= 1

    def test_isolation_device_tie_into_isolated_domain_passes(self):
        """A connection into an isolated domain marked as going through a
        real isolation device (capacitor/transformer/optocoupler) is
        correct, even though it is a "connection" in the naive sense."""
        ground_domains = {
            "PGND": {"area": [(0, 0, 50, 100)]},
            "ISOGND": {"area": [(50, 0, 100, 100)], "isolated": True},
            "connections": [
                {
                    "from": "PGND",
                    "to": "ISOGND",
                    "location": (50, 50),
                    "component_type": "capacitor",
                },
                {
                    "from": "PGND",
                    "to": "ISOGND",
                    "location": (50, 70),
                    "component_type": "optocoupler",
                },
            ],
        }

        result = check_star_ground_point(ground_domains)
        assert result.passed


# =============================================================================
# Via Stitching Tests
# =============================================================================


class TestViaStitching:
    """Tests for via stitching along ground splits."""

    def test_adequate_stitching_passes(self):
        """Via stitching every 5mm should pass."""
        boundary = {
            "start": (50, 0),
            "end": (50, 100),
            "vias": [
                (50, y)
                for y in range(0, 101, 5)  # Via every 5mm
            ],
        }

        result = check_via_stitching(boundary, max_spacing_mm=5.0)
        assert result.passed

    def test_insufficient_stitching_fails(self):
        """Via stitching with gaps >5mm should fail."""
        boundary = {
            "start": (50, 0),
            "end": (50, 100),
            "vias": [
                (50, 0),
                (50, 10),
                (50, 30),
                (50, 100),  # Large gaps
            ],
        }

        result = check_via_stitching(boundary, max_spacing_mm=5.0)
        assert not result.passed
        assert result.error_count >= 1

    def test_no_vias_fails(self):
        """Ground split with no stitching vias should fail."""
        boundary = {"start": (50, 0), "end": (50, 100), "vias": []}

        result = check_via_stitching(boundary, max_spacing_mm=5.0)
        assert not result.passed


# =============================================================================
# Integration Tests
# =============================================================================


class TestGroundPlaneIntegration:
    """Integration tests for complete ground plane validation."""

    @pytest.mark.slow
    def test_temper_board_ground_plane_compliance(self):
        """Temper board ground plane should meet all REQ-EMC-01 requirements.

        Implemented 2026-07-26, replacing "Temper board fixture not yet
        available". Full accounting in
        docs/evidence/2026-07-26-emc-validators-implemented.md; summary:

        - check_slot_lengths, check_via_stitching, check_signal_ground_reference:
          NOT run against the real board. ``pcb/temper.kicad_pcb`` has zero
          ``(zone ...)`` records (verified: ``grep -c '(zone' pcb/temper.kicad_pcb``
          -> 0) -- no ground-plane copper pour has been created yet at this
          stage of layout, so there is no slot geometry, no split-plane
          boundary, and no ground-plane-vs-trace geometry to check. Feeding
          these functions empty geometry would report a vacuous "0
          violations" pass that misrepresents "no pour exists yet" as
          "pour is compliant" -- reported honestly as not-yet-applicable
          instead.
        - check_star_ground_point: DOES run, and is the one function in this
          module whose data is available today, because it operates on
          net-topology facts (which nets exist and how they cross), not on
          PCB copper geometry. See below.

        check_star_ground_point validates the POST-SELV-float architecture,
        not the removed star join. The `ground_domains` input below is
        built from docs/hardware/SELV_ISOLATION_REDESIGN.md Sec 4 and Sec 6
        (netlist evidence, re-verified there against
        elec/build/default.net): `gnd` (SELV, now bonded to `pe`, no longer
        to `power_return`) and `PWR_RTN` (the HV doubler-midpoint return)
        are two separate nets, crossed only by four components the SELV doc
        confirms are real isolation devices, never a direct/galvanic tie:
        C6 (Y1 capacitor), PS1 (IRM-10-15 transformer), T1 (CST2010-100L
        current-sense transformer), U3 (H11L1 optocoupler). This is
        asserted to PASS -- correctly, because the design is not supposed
        to have a bare connection between these two domains anymore.
        """
        ground_domains = {
            "gnd": {"isolated": True},  # SELV domain, PE-bonded (main.ato: gnd ~ pe)
            "PWR_RTN": {},  # HV doubler-midpoint return (power_return)
            "connections": [
                {
                    "from": "gnd",
                    "to": "PWR_RTN",
                    "component_type": "capacitor",
                    "ref": "C6",
                },
                {
                    "from": "gnd",
                    "to": "PWR_RTN",
                    "component_type": "transformer",
                    "ref": "PS1",
                },
                {
                    "from": "gnd",
                    "to": "PWR_RTN",
                    "component_type": "transformer",
                    "ref": "T1",
                },
                {
                    "from": "gnd",
                    "to": "PWR_RTN",
                    "component_type": "optocoupler",
                    "ref": "U3",
                },
            ],
        }

        result = check_star_ground_point(ground_domains)
        assert result.passed, (
            "Post-SELV-float architecture should pass: gnd/PWR_RTN cross only "
            "through documented isolation devices, never a bare tie"
        )
        assert result.error_count == 0

        # Counterfactual, to show this check actually would have caught the
        # defect that was removed: the old `power_return ~ gnd` star join was
        # a single, bare, unmarked connection between these same two
        # domains -- exactly the SG-003 pattern.
        old_defect_domains = {
            "gnd": {"isolated": True},
            "PWR_RTN": {},
            "connections": [
                {"from": "gnd", "to": "PWR_RTN", "location": (0, 0)},  # no isolation marker
            ],
        }
        old_result = check_star_ground_point(old_defect_domains)
        assert not old_result.passed, (
            "Sanity check: the removed star join pattern (bare gnd~PWR_RTN tie) "
            "must still be flagged by this checker"
        )

    def test_validation_result_aggregation(self):
        """Multiple violations should aggregate correctly."""
        # Create violations from different checks
        violations = [
            GroundPlaneViolation("GP001", "Slot too long", severity="error"),
            GroundPlaneViolation("GP002", "Missing via stitching", severity="error"),
            GroundPlaneViolation("GP003", "Trace over slot", severity="warning"),
        ]

        result = GroundPlaneResult(passed=False, violations=violations)

        assert result.error_count == 2
        assert result.warning_count == 1
        assert not result.passed
