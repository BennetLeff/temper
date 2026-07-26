"""
Tests for isolation barrier validation functions (requirements/validators/isolation.py).

These tests verify:
- Isolation slot width validation
- Trace crossing detection
- UCC21550 gate driver isolation requirements
- ADUM1250 I2C isolator isolation requirements
- Ground plane split validation
- Clearance distance checking
- Power domain separation
"""

import os
import sys

import pytest

# Add project root to path to allow importing from tests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from tests.requirements.validators.isolation import (
    IsolationResult,
    IsolationViolation,
    check_adum1250_barrier,
    check_clearance_distances,
    check_ground_plane_split,
    check_isolation_slot,
    check_no_traces_across_barrier,
    check_power_domain_separation,
    check_ucc21550_barrier,
)


class TestIsolationViolation:
    """Tests for IsolationViolation dataclass."""

    def test_basic_violation(self):
        """Test creating a basic isolation violation."""
        violation = IsolationViolation(
            barrier_type="MAIN_HV_LV",
            component_refs=["U1", "C1"],
            code="SLOT_WIDTH_INSUFFICIENT",
            message="Main HV-LV barrier slot width too narrow",
            location=(50.0, 25.0),
            slot_width_mm=1.5,
            severity="error",
        )
        assert violation.barrier_type == "MAIN_HV_LV"
        assert "U1" in violation.component_refs
        assert violation.slot_width_mm == 1.5
        assert violation.severity == "error"

    def test_ucc21550_violation(self):
        """Test UCC21550-specific violation."""
        violation = IsolationViolation(
            barrier_type="UCC21550",
            component_refs=["U3"],
            code="TRACES_UNDER_TRANSFORMER",
            message="Traces detected under UCC21550 transformer area",
            location=(75.0, 30.0),
            severity="error",
        )
        assert violation.barrier_type == "UCC21550"
        assert violation.code == "TRACES_UNDER_TRANSFORMER"

    def test_adum1250_violation(self):
        """Test ADUM1250-specific violation."""
        violation = IsolationViolation(
            barrier_type="ADUM1250",
            component_refs=["U4"],
            code="INSUFFICIENT_CLEARANCE",
            message="ADUM1250 isolation clearance less than 10mm",
            location=(25.0, 50.0),
            clearance_mm=8.5,
            severity="error",
        )
        assert violation.barrier_type == "ADUM1250"
        assert violation.clearance_mm == 8.5


class TestIsolationResult:
    """Tests for IsolationResult dataclass."""

    def test_pass_result_no_violations(self):
        """Test successful isolation validation with no violations."""
        result = IsolationResult(
            passed=True,
            violations=[],
        )
        assert result.passed
        assert result.error_count == 0
        assert result.warning_count == 0

    def test_result_with_errors(self):
        """Test isolation result with error violations."""
        violations = [
            IsolationViolation(
                barrier_type="MAIN_HV_LV",
                component_refs=["U1"],
                code="SLOT_WIDTH_INSUFFICIENT",
                message="Slot width too narrow",
                severity="error",
            )
        ]
        result = IsolationResult(
            passed=False,
            violations=violations,
        )
        assert not result.passed
        assert result.error_count == 1
        assert result.warning_count == 0

    def test_result_with_mixed_violations(self):
        """Test isolation result with both errors and warnings."""
        violations = [
            IsolationViolation(
                barrier_type="UCC21550",
                component_refs=["U3"],
                code="TRACES_UNDER_TRANSFORMER",
                message="Traces under transformer",
                severity="error",
            ),
            IsolationViolation(
                barrier_type="ADUM1250",
                component_refs=["U4"],
                code="MINOR_CLEARANCE_ISSUE",
                message="Slightly reduced clearance",
                severity="warning",
            ),
        ]
        result = IsolationResult(
            passed=False,
            violations=violations,
        )
        assert not result.passed
        assert result.error_count == 1
        assert result.warning_count == 1


class TestCheckIsolationSlot:
    """Tests for check_isolation_slot function."""

    def test_main_hv_lv_barrier_valid_width(self):
        """Test main HV-LV barrier with valid 2.0mm slot width."""
        barrier = {
            "type": "MAIN_HV_LV",
            "position": (50.0, 25.0),
            "slot_width": 2.0,
            "slot_length": 100.0,
            "board_width": 100.0,
        }
        result = check_isolation_slot(barrier, min_width_mm=2.0)
        assert result.passed
        assert len(result.violations) == 0

    def test_main_hv_lv_barrier_insufficient_width(self):
        """Test main HV-LV barrier with insufficient 1.5mm slot width."""
        barrier = {
            "type": "MAIN_HV_LV",
            "position": (50.0, 25.0),
            "slot_width": 1.5,
            "slot_length": 100.0,
            "board_width": 100.0,
        }
        result = check_isolation_slot(barrier, min_width_mm=2.0)
        assert not result.passed
        assert len(result.violations) == 1
        violation = result.violations[0]
        assert violation.code == "SLOT_WIDTH_INSUFFICIENT"
        assert violation.slot_width_mm == 1.5

    def test_ucc21550_barrier_valid_width(self):
        """Test UCC21550 barrier with valid 1.5mm slot width."""
        barrier = {
            "type": "UCC21550",
            "position": (75.0, 30.0),
            "slot_width": 1.5,
            "slot_length": 10.0,
        }
        result = check_isolation_slot(barrier, min_width_mm=1.5)
        assert result.passed
        assert len(result.violations) == 0

    def test_adum1250_barrier_valid_width(self):
        """Test ADUM1250 barrier with valid 1.5mm slot width."""
        barrier = {
            "type": "ADUM1250",
            "position": (25.0, 50.0),
            "slot_width": 1.5,
            "slot_length": 10.0,
        }
        result = check_isolation_slot(barrier, min_width_mm=1.5)
        assert result.passed
        assert len(result.violations) == 0

    def test_custom_min_width(self):
        """Test with custom minimum width requirement."""
        barrier = {
            "type": "MAIN_HV_LV",
            "position": (50.0, 25.0),
            "slot_width": 2.5,
            "slot_length": 100.0,
        }
        result = check_isolation_slot(barrier, min_width_mm=3.0)
        assert not result.passed
        assert len(result.violations) == 1


class TestCheckNoTracesAcrossBarrier:
    """Tests for check_no_traces_across_barrier function."""

    def test_no_traces_crossing_horizontal_barrier(self):
        """Test horizontal barrier with no crossing traces."""
        traces = [
            {
                "start": (10.0, 10.0),
                "end": (40.0, 15.0),
                "net": "VCC",
                "layer": "Top",
            },
            {
                "start": (60.0, 35.0),
                "end": (90.0, 40.0),
                "net": "GND",
                "layer": "Top",
            },
        ]
        barrier = {
            "type": "MAIN_HV_LV",
            "position": (50.0, 25.0),
            "orientation": "horizontal",
            "clearance_mm": 10.0,
        }
        result = check_no_traces_across_barrier(traces, barrier)
        assert result.passed
        assert len(result.violations) == 0

    def test_trace_crossing_horizontal_barrier(self):
        """Test horizontal barrier with a crossing trace."""
        traces = [
            {
                "start": (10.0, 10.0),
                "end": (90.0, 40.0),  # Crosses barrier at y=25
                "net": "SIGNAL",
                "layer": "Top",
            }
        ]
        barrier = {
            "type": "MAIN_HV_LV",
            "position": (50.0, 25.0),
            "orientation": "horizontal",
            "clearance_mm": 10.0,
        }
        result = check_no_traces_across_barrier(traces, barrier)
        assert not result.passed
        assert len(result.violations) == 1
        violation = result.violations[0]
        assert violation.code == "TRACE_CROSSING_BARRIER"

    def test_no_traces_crossing_vertical_barrier(self):
        """Test vertical barrier with no crossing traces."""
        traces = [
            {
                "start": (10.0, 10.0),
                "end": (15.0, 40.0),
                "net": "VCC",
                "layer": "Top",
            },
            {
                "start": (85.0, 10.0),
                "end": (90.0, 40.0),
                "net": "GND",
                "layer": "Top",
            },
        ]
        barrier = {
            "type": "UCC21550",
            "position": (50.0, 25.0),
            "orientation": "vertical",
            "clearance_mm": 10.0,
        }
        result = check_no_traces_across_barrier(traces, barrier)
        assert result.passed
        assert len(result.violations) == 0

    def test_trace_crossing_vertical_barrier(self):
        """Test vertical barrier with a crossing trace."""
        traces = [
            {
                "start": (10.0, 10.0),
                "end": (90.0, 40.0),  # Crosses barrier at x=50
                "net": "SIGNAL",
                "layer": "Top",
            }
        ]
        barrier = {
            "type": "UCC21550",
            "position": (50.0, 25.0),
            "orientation": "vertical",
            "clearance_mm": 10.0,
        }
        result = check_no_traces_across_barrier(traces, barrier)
        assert not result.passed
        assert len(result.violations) == 1

    def test_trace_near_barrier_but_not_crossing(self):
        """Test trace near barrier but not actually crossing."""
        traces = [
            {
                "start": (10.0, 10.0),
                "end": (45.0, 20.0),  # Ends before barrier at x=50
                "net": "SIGNAL",
                "layer": "Top",
            }
        ]
        barrier = {
            "type": "MAIN_HV_LV",
            "position": (50.0, 25.0),
            "orientation": "vertical",
            "clearance_mm": 10.0,
        }
        result = check_no_traces_across_barrier(traces, barrier)
        assert result.passed
        assert len(result.violations) == 0


class TestCheckUCC21550Barrier:
    """Tests for check_ucc21550_barrier function.

    check_ucc21550_barrier is deliberately left raising NotImplementedError
    (see its docstring in validators/isolation.py): its signature provides
    only a bare (x, y) position, with none of the trace/ground-plane/net
    data needed to check "no traces under transformer", "ground plane
    cutout", or "separate power domains" against. These three tests
    (originally written expecting a real IsolationResult once implemented)
    now assert that precise, honest failure mode instead of a fabricated
    pass -- each names the specific requirement it would otherwise probe.
    """

    def test_ucc21550_valid_placement(self):
        """UCC21550 isolation cannot be evaluated from position alone."""
        driver_position = (75.0, 30.0)
        with pytest.raises(NotImplementedError):
            check_ucc21550_barrier(driver_position)

    def test_ucc21550_missing_ground_cutout(self):
        """Detecting a missing ground cutout needs ground-plane geometry,
        which this function's signature does not provide."""
        driver_position = (75.0, 30.0)
        with pytest.raises(NotImplementedError):
            check_ucc21550_barrier(driver_position)

    def test_ucc21550_traces_under_transformer(self):
        """Detecting traces under pins 5-12 needs a trace list, which this
        function's signature does not provide."""
        driver_position = (75.0, 30.0)
        with pytest.raises(NotImplementedError):
            check_ucc21550_barrier(driver_position)


class TestCheckADUM1250Barrier:
    """Tests for check_adum1250_barrier function.

    check_adum1250_barrier is deliberately left raising NotImplementedError
    for the same reason as check_ucc21550_barrier above: a bare (x, y)
    position cannot support checking clearance, ground-plane split, or
    power-supply separation.
    """

    def test_adum1250_valid_placement(self):
        """ADUM1250 isolation cannot be evaluated from position alone."""
        isolator_position = (25.0, 50.0)
        with pytest.raises(NotImplementedError):
            check_adum1250_barrier(isolator_position)

    def test_adum1250_insufficient_clearance(self):
        """Detecting <10mm clearance needs component/clearance data, which
        this function's signature does not provide."""
        isolator_position = (25.0, 50.0)
        with pytest.raises(NotImplementedError):
            check_adum1250_barrier(isolator_position)

    def test_adum1250_missing_ground_split(self):
        """Detecting a missing ground split needs ground-plane geometry,
        which this function's signature does not provide."""
        isolator_position = (25.0, 50.0)
        with pytest.raises(NotImplementedError):
            check_adum1250_barrier(isolator_position)


class TestCheckGroundPlaneSplit:
    """Tests for check_ground_plane_split function."""

    def test_proper_ground_plane_split(self):
        """Test properly split ground planes at barriers."""
        ground_planes = {
            "Layer2": [(0, 0, 45, 50), (55, 0, 45, 50)],  # Split at x=50
            "Layer4": [(0, 0, 45, 50), (55, 0, 45, 50)],  # Split at x=50
        }
        barriers = [
            {
                "type": "MAIN_HV_LV",
                "position": (50.0, 25.0),
                "orientation": "vertical",
            }
        ]
        result = check_ground_plane_split(ground_planes, barriers)
        assert isinstance(result, IsolationResult)
        assert result.passed
        assert len(result.violations) == 0

    def test_unsplit_ground_plane(self):
        """A single rectangle spanning x=[0,100] straddles the barrier at
        x=50 -- falsifier: if this reports 0 violations, the check is
        inspecting nothing and passing on a ground plane that was never
        actually cut at the isolation barrier."""
        ground_planes = {
            "Layer2": [(0, 0, 100, 50)],  # No split
        }
        barriers = [
            {
                "type": "MAIN_HV_LV",
                "position": (50.0, 25.0),
                "orientation": "vertical",
            }
        ]
        result = check_ground_plane_split(ground_planes, barriers)
        assert isinstance(result, IsolationResult)
        assert not result.passed
        assert len(result.violations) == 1
        assert result.violations[0].code == "GROUND_PLANE_NOT_SPLIT"


class TestCheckClearanceDistances:
    """Tests for check_clearance_distances function."""

    def test_sufficient_clearance(self):
        """Both components are 30mm from the barrier (>= the 10mm
        requirement) -- falsifier: if this reports any violation, the
        check is over-triggering on components that are nowhere near the
        barrier."""
        components = {
            "U1": {"position": (20.0, 25.0), "voltage": 340, "type": "HV"},
            "U2": {"position": (80.0, 25.0), "voltage": 3.3, "type": "LV"},
        }
        barriers = [
            {
                "type": "MAIN_HV_LV",
                "position": (50.0, 25.0),
                "clearance_mm": 10.0,
            }
        ]
        result = check_clearance_distances(components, barriers, min_clearance_mm=10.0)
        assert isinstance(result, IsolationResult)
        assert result.passed
        assert len(result.violations) == 0

    def test_insufficient_clearance(self):
        """Both components are only 5mm from the barrier (< the 10mm
        requirement) -- falsifier: if this reports 0 violations, the check
        is inspecting nothing and passing (exactly the vacuous-validator
        failure mode this task warns against)."""
        components = {
            "U1": {"position": (45.0, 25.0), "voltage": 340, "type": "HV"},
            "U2": {"position": (55.0, 25.0), "voltage": 3.3, "type": "LV"},
        }
        barriers = [
            {
                "type": "MAIN_HV_LV",
                "position": (50.0, 25.0),
                "clearance_mm": 10.0,
            }
        ]
        result = check_clearance_distances(components, barriers, min_clearance_mm=10.0)
        assert isinstance(result, IsolationResult)
        assert not result.passed
        assert len(result.violations) == 2
        refs = {v.component_refs[0] for v in result.violations}
        assert refs == {"U1", "U2"}
        assert all(v.code == "INSUFFICIENT_CLEARANCE" for v in result.violations)


class TestCheckPowerDomainSeparation:
    """Tests for check_power_domain_separation function."""

    def test_proper_domain_separation(self):
        """Two distinct, named domains plus isolation components declared
        -- falsifier: if this reports any violation, the check is flagging
        a design that is not actually coupled."""
        power_supplies = {
            "PS1": {"voltage": 340, "position": (20.0, 25.0), "domain": "HV"},
            "PS2": {"voltage": 5.0, "position": (80.0, 25.0), "domain": "LV"},
        }
        isolation_components = ["U3", "U4"]  # UCC21550, ADUM1250
        result = check_power_domain_separation(power_supplies, isolation_components)
        assert isinstance(result, IsolationResult)
        assert result.passed
        assert len(result.violations) == 0

    def test_coupled_power_domains(self):
        """A supply with an explicit "SHARED" domain and no isolation
        components -- falsifier: if this reports 0 violations, the check
        is inspecting nothing and passing on a design that has explicitly
        declared its HV/LV sides are not separated (the exact failure mode
        docs/hardware/IEC60335_CRITICAL_COMPONENTS.md Sec 2 documents for
        this design's real pre-redesign star join)."""
        power_supplies = {
            "PS1": {"voltage": 5.0, "position": (20.0, 25.0), "domain": "SHARED"},
        }
        isolation_components = []  # No isolation
        result = check_power_domain_separation(power_supplies, isolation_components)
        assert isinstance(result, IsolationResult)
        assert not result.passed
        assert len(result.violations) == 1
        assert result.violations[0].code == "POWER_DOMAIN_NOT_SEPARATED"
        assert result.violations[0].severity == "error"

    def test_multiple_domains_without_isolation_components_warns(self):
        """Two distinct real domains declared, but no isolation_components
        given -- falsifier: if this passes with 0 violations, the check
        never notices that nothing in the given data actually enforces the
        claimed separation."""
        power_supplies = {
            "PS1": {"voltage": 340, "position": (20.0, 25.0), "domain": "HV"},
            "PS2": {"voltage": 5.0, "position": (80.0, 25.0), "domain": "LV"},
        }
        result = check_power_domain_separation(power_supplies, isolation_components=[])
        assert len(result.violations) == 1
        assert result.violations[0].code == "MISSING_ISOLATION_COMPONENTS"
        assert result.violations[0].severity == "warning"
        # A warning alone doesn't fail the domain-separation check itself.
        assert result.passed


class TestNotImplementedErrors:
    """check_ucc21550_barrier and check_adum1250_barrier are the only two
    isolation.py functions still raising NotImplementedError, and
    deliberately so: both take only a bare (x, y) position with no trace,
    ground-plane, or net-assignment data to check anything real against.
    See their docstrings in validators/isolation.py for the precise
    reasoning. The other 5 functions that used to be tested here
    (check_isolation_slot, check_no_traces_across_barrier,
    check_ground_plane_split, check_clearance_distances,
    check_power_domain_separation) are now implemented -- their own
    positive/negative-fixture tests above (TestCheckIsolationSlot etc.)
    replace the old "raises NotImplementedError" assertions for them.
    """

    def test_check_ucc21550_barrier_not_implemented(self):
        """Test that check_ucc21550_barrier raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            check_ucc21550_barrier((75.0, 30.0))

    def test_check_adum1250_barrier_not_implemented(self):
        """Test that check_adum1250_barrier raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            check_adum1250_barrier((25.0, 50.0))
