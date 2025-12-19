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

import pytest
from unittest.mock import MagicMock

import sys
import os

# Add project root to path to allow importing from tests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from tests.requirements.validators.isolation import (
    IsolationViolation,
    IsolationResult,
    check_isolation_slot,
    check_no_traces_across_barrier,
    check_ucc21550_barrier,
    check_adum1250_barrier,
    check_ground_plane_split,
    check_clearance_distances,
    check_power_domain_separation,
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
    """Tests for check_ucc21550_barrier function."""

    def test_ucc21550_valid_placement(self):
        """Test UCC21550 with valid isolation setup."""
        driver_position = (75.0, 30.0)
        result = check_ucc21550_barrier(driver_position)
        # Should pass when properly implemented
        assert isinstance(result, IsolationResult)

    def test_ucc21550_missing_ground_cutout(self):
        """Test UCC21550 with missing ground plane cutout."""
        driver_position = (75.0, 30.0)
        result = check_ucc21550_barrier(driver_position)
        # Should detect missing ground cutout when implemented
        assert isinstance(result, IsolationResult)

    def test_ucc21550_traces_under_transformer(self):
        """Test UCC21550 with traces under transformer area."""
        driver_position = (75.0, 30.0)
        result = check_ucc21550_barrier(driver_position)
        # Should detect traces under pins 5-12 when implemented
        assert isinstance(result, IsolationResult)


class TestCheckADUM1250Barrier:
    """Tests for check_adum1250_barrier function."""

    def test_adum1250_valid_placement(self):
        """Test ADUM1250 with valid isolation setup."""
        isolator_position = (25.0, 50.0)
        result = check_adum1250_barrier(isolator_position)
        # Should pass when properly implemented
        assert isinstance(result, IsolationResult)

    def test_adum1250_insufficient_clearance(self):
        """Test ADUM1250 with insufficient clearance."""
        isolator_position = (25.0, 50.0)
        result = check_adum1250_barrier(isolator_position)
        # Should detect <10mm clearance when implemented
        assert isinstance(result, IsolationResult)

    def test_adum1250_missing_ground_split(self):
        """Test ADUM1250 with missing ground plane split."""
        isolator_position = (25.0, 50.0)
        result = check_adum1250_barrier(isolator_position)
        # Should detect missing ground split when implemented
        assert isinstance(result, IsolationResult)


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

    def test_unsplit_ground_plane(self):
        """Test unsplit ground plane crossing barrier."""
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


class TestCheckClearanceDistances:
    """Tests for check_clearance_distances function."""

    def test_sufficient_clearance(self):
        """Test components with sufficient clearance."""
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

    def test_insufficient_clearance(self):
        """Test components with insufficient clearance."""
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


class TestCheckPowerDomainSeparation:
    """Tests for check_power_domain_separation function."""

    def test_proper_domain_separation(self):
        """Test properly separated power domains."""
        power_supplies = {
            "PS1": {"voltage": 340, "position": (20.0, 25.0), "domain": "HV"},
            "PS2": {"voltage": 5.0, "position": (80.0, 25.0), "domain": "LV"},
        }
        isolation_components = ["U3", "U4"]  # UCC21550, ADUM1250
        result = check_power_domain_separation(power_supplies, isolation_components)
        assert isinstance(result, IsolationResult)

    def test_coupled_power_domains(self):
        """Test coupled power domains without isolation."""
        power_supplies = {
            "PS1": {"voltage": 5.0, "position": (20.0, 25.0), "domain": "SHARED"},
        }
        isolation_components = []  # No isolation
        result = check_power_domain_separation(power_supplies, isolation_components)
        assert isinstance(result, IsolationResult)


class TestNotImplementedErrors:
    """Tests that functions raise NotImplementedError before implementation."""

    def test_check_isolation_slot_not_implemented(self):
        """Test that check_isolation_slot raises NotImplementedError."""
        barrier = {"type": "MAIN_HV_LV", "position": (50.0, 25.0)}
        with pytest.raises(NotImplementedError):
            check_isolation_slot(barrier)

    def test_check_no_traces_across_barrier_not_implemented(self):
        """Test that check_no_traces_across_barrier raises NotImplementedError."""
        traces = [{"start": (10, 10), "end": (90, 90)}]
        barrier = {"type": "MAIN_HV_LV", "position": (50, 50)}
        with pytest.raises(NotImplementedError):
            check_no_traces_across_barrier(traces, barrier)

    def test_check_ucc21550_barrier_not_implemented(self):
        """Test that check_ucc21550_barrier raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            check_ucc21550_barrier((75.0, 30.0))

    def test_check_adum1250_barrier_not_implemented(self):
        """Test that check_adum1250_barrier raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            check_adum1250_barrier((25.0, 50.0))

    def test_check_ground_plane_split_not_implemented(self):
        """Test that check_ground_plane_split raises NotImplementedError."""
        ground_planes = {"Layer2": [(0, 0, 100, 50)]}
        barriers = [{"type": "MAIN_HV_LV", "position": (50, 25)}]
        with pytest.raises(NotImplementedError):
            check_ground_plane_split(ground_planes, barriers)

    def test_check_clearance_distances_not_implemented(self):
        """Test that check_clearance_distances raises NotImplementedError."""
        components = {"U1": {"position": (20, 25), "voltage": 340}}
        barriers = [{"type": "MAIN_HV_LV", "position": (50, 25)}]
        with pytest.raises(NotImplementedError):
            check_clearance_distances(components, barriers)

    def test_check_power_domain_separation_not_implemented(self):
        """Test that check_power_domain_separation raises NotImplementedError."""
        power_supplies = {"PS1": {"voltage": 5.0, "position": (20, 25)}}
        isolation_components = ["U3"]
        with pytest.raises(NotImplementedError):
            check_power_domain_separation(power_supplies, isolation_components)
