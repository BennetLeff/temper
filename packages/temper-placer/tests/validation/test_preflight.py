"""
Tests for preflight validation checks.
"""

import pytest
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from unittest.mock import patch

from temper_placer.validation.preflight import (
    PreflightSeverity,
    PreflightIssue,
    PreflightResult,
    check_kicad_cli,
    check_ngspice,
    check_external_tools,
    check_components_have_zones,
    check_zones_fit_on_board,
    check_impossible_constraints,
    run_all_preflight_checks,
    _zones_overlap,
)
from temper_placer.core.board import Zone
from temper_placer.core.netlist import Component, Netlist
from temper_placer.io.config_loader import (
    PlacementConstraints,
    ComponentGroup,
    ThermalConstraint,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def simple_netlist():
    """Create a simple netlist with 3 components."""
    components = [
        Component(ref="R1", footprint="Resistor_SMD:R_0603", bounds=(1.6, 0.8)),
        Component(ref="D1", footprint="LED_SMD:LED_0603", bounds=(1.6, 0.8)),
        Component(ref="J1", footprint="Connector_PinHeader:PinHeader_1x02", bounds=(2.5, 5.0)),
    ]
    return Netlist(components=components, nets=[])


@pytest.fixture
def simple_constraints():
    """Create simple constraints with one zone."""
    return PlacementConstraints(
        board_width_mm=50.0,
        board_height_mm=50.0,
        board_margin_mm=2.0,
        zones=[
            Zone(
                name="MAIN", bounds=(0, 0, 50, 50), net_classes=["Signal"], components=["R1", "D1"]
            ),
        ],
        zone_assignments={"J1": "MAIN"},
    )


@pytest.fixture
def multi_zone_constraints():
    """Create constraints with multiple zones."""
    return PlacementConstraints(
        board_width_mm=100.0,
        board_height_mm=100.0,
        board_margin_mm=3.0,
        zones=[
            Zone(
                name="HV_ZONE",
                bounds=(0, 0, 50, 50),
                net_classes=["HighVoltage"],
                components=["Q1", "Q2"],
            ),
            Zone(
                name="LV_ZONE",
                bounds=(50, 0, 100, 50),
                net_classes=["Signal"],
                components=["U1", "U2"],
            ),
            Zone(
                name="MCU_ZONE",
                bounds=(50, 50, 100, 100),
                net_classes=["Signal"],
                components=["MCU"],
            ),
        ],
        zone_assignments={},
    )


@pytest.fixture
def netlist_with_large_component():
    """Create a netlist with a component larger than zones."""
    components = [
        Component(ref="LARGE", footprint="Large:Package", bounds=(60.0, 60.0)),  # Too big
        Component(ref="SMALL", footprint="Small:Package", bounds=(5.0, 5.0)),
    ]
    return Netlist(components=components, nets=[])


# =============================================================================
# Test External Tool Checks
# =============================================================================


class TestExternalToolChecks:
    """Tests for external tool availability checks."""

    def test_check_kicad_cli_not_found(self):
        """Test kicad-cli check when not available."""
        with patch("temper_placer.validation.preflight.find_kicad_cli", return_value=None):
            result = check_kicad_cli()

        assert result.passed is True  # Warning, not error
        assert result.warning_count == 1
        assert result.issues[0].code == "TOOL_002"
        assert "kicad-cli not found" in result.issues[0].message

    def test_check_kicad_cli_found(self):
        """Test kicad-cli check when available."""
        with patch(
            "temper_placer.validation.preflight.find_kicad_cli", return_value="/usr/bin/kicad-cli"
        ):
            result = check_kicad_cli()

        assert result.passed is True
        assert result.info_count == 1
        assert result.issues[0].code == "TOOL_001"
        assert "/usr/bin/kicad-cli" in result.issues[0].message

    def test_check_ngspice_not_found(self):
        """Test ngspice check when not available."""
        with patch("shutil.which", return_value=None):
            result = check_ngspice()

        assert result.passed is True  # Warning, not error
        assert result.warning_count == 1
        assert result.issues[0].code == "TOOL_004"
        assert "ngspice not found" in result.issues[0].message

    def test_check_ngspice_found(self):
        """Test ngspice check when available."""
        with patch("shutil.which", return_value="/opt/homebrew/bin/ngspice"):
            result = check_ngspice()

        assert result.passed is True
        assert result.info_count == 1
        assert result.issues[0].code == "TOOL_003"

    def test_check_external_tools_combines_results(self):
        """Test combined tool check."""
        with patch("temper_placer.validation.preflight.find_kicad_cli", return_value=None):
            with patch("shutil.which", return_value="/opt/homebrew/bin/ngspice"):
                result = check_external_tools()

        assert result.passed is True
        assert result.warning_count == 1  # kicad-cli warning
        assert result.info_count == 1  # ngspice info
        assert len(result.issues) == 2


# =============================================================================
# Test Zone Boundary Checks
# =============================================================================


class TestZoneBoundaryChecks:
    """Tests for zone boundary validation."""

    def test_zones_fit_on_board(self, simple_constraints):
        """Test zones within board boundaries."""
        result = check_zones_fit_on_board(simple_constraints)

        assert result.passed is True
        assert result.error_count == 0
        assert result.info_count >= 1

    def test_zone_exceeds_board_x(self):
        """Test zone extending past board X boundary."""
        constraints = PlacementConstraints(
            board_width_mm=50.0,
            board_height_mm=50.0,
            zones=[
                Zone(
                    name="TOO_WIDE", bounds=(0, 0, 100, 50), net_classes=["Signal"], components=[]
                ),
            ],
        )
        result = check_zones_fit_on_board(constraints)

        assert result.passed is False
        assert result.error_count == 1
        assert result.issues[0].code == "ZONE_003"
        assert "TOO_WIDE" in result.issues[0].message

    def test_zone_exceeds_board_y(self):
        """Test zone extending past board Y boundary."""
        constraints = PlacementConstraints(
            board_width_mm=50.0,
            board_height_mm=50.0,
            zones=[
                Zone(
                    name="TOO_TALL", bounds=(0, 0, 50, 100), net_classes=["Signal"], components=[]
                ),
            ],
        )
        result = check_zones_fit_on_board(constraints)

        assert result.passed is False
        assert result.error_count == 1

    def test_zone_negative_coordinates(self):
        """Test zone with negative coordinates."""
        constraints = PlacementConstraints(
            board_width_mm=50.0,
            board_height_mm=50.0,
            zones=[
                Zone(
                    name="NEGATIVE",
                    bounds=(-10, -10, 40, 40),
                    net_classes=["Signal"],
                    components=[],
                ),
            ],
        )
        result = check_zones_fit_on_board(constraints)

        assert result.passed is False
        assert result.error_count == 1

    def test_overlapping_zones_warning(self):
        """Test overlapping zones generate warning."""
        constraints = PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            zones=[
                Zone(name="ZONE_A", bounds=(0, 0, 60, 60), net_classes=["Signal"], components=[]),
                Zone(
                    name="ZONE_B", bounds=(40, 40, 100, 100), net_classes=["Signal"], components=[]
                ),
            ],
        )
        result = check_zones_fit_on_board(constraints)

        assert result.passed is True  # Overlap is warning, not error
        assert result.warning_count == 1
        assert result.issues[0].code == "ZONE_004"

    def test_zones_overlap_helper(self):
        """Test _zones_overlap helper function."""
        zone_a = Zone(name="A", bounds=(0, 0, 50, 50), net_classes=[], components=[])
        zone_b = Zone(name="B", bounds=(25, 25, 75, 75), net_classes=[], components=[])
        zone_c = Zone(name="C", bounds=(100, 0, 150, 50), net_classes=[], components=[])

        assert _zones_overlap(zone_a, zone_b) is True
        assert _zones_overlap(zone_a, zone_c) is False
        assert _zones_overlap(zone_b, zone_c) is False


# =============================================================================
# Test Zone Assignment Checks
# =============================================================================


class TestZoneAssignmentChecks:
    """Tests for component zone assignment validation."""

    def test_all_components_assigned(self, simple_netlist, simple_constraints):
        """Test all components have zone assignments."""
        result = check_components_have_zones(simple_netlist, simple_constraints, require_all=True)

        assert result.passed is True
        assert result.error_count == 0

    def test_some_components_unassigned_warning(self, simple_netlist):
        """Test unassigned components generate warning."""
        constraints = PlacementConstraints(
            board_width_mm=50.0,
            board_height_mm=50.0,
            zones=[
                Zone(name="MAIN", bounds=(0, 0, 50, 50), net_classes=["Signal"], components=["R1"]),
            ],
        )
        result = check_components_have_zones(simple_netlist, constraints, require_all=False)

        assert result.passed is True  # Warning, not error
        assert result.warning_count == 1
        assert "D1" in result.issues[0].components or "J1" in result.issues[0].components

    def test_unassigned_components_error_when_required(self, simple_netlist):
        """Test unassigned components generate error when require_all=True."""
        constraints = PlacementConstraints(
            board_width_mm=50.0,
            board_height_mm=50.0,
            zones=[
                Zone(name="MAIN", bounds=(0, 0, 50, 50), net_classes=["Signal"], components=["R1"]),
            ],
        )
        result = check_components_have_zones(simple_netlist, constraints, require_all=True)

        assert result.passed is False
        assert result.error_count == 1

    def test_fixed_components_exempt(self, simple_netlist):
        """Test fixed components don't need zone assignment."""
        constraints = PlacementConstraints(
            board_width_mm=50.0,
            board_height_mm=50.0,
            zones=[
                Zone(
                    name="MAIN",
                    bounds=(0, 0, 50, 50),
                    net_classes=["Signal"],
                    components=["R1", "D1"],
                ),
            ],
            fixed_components=["J1"],  # J1 is exempt
        )
        result = check_components_have_zones(simple_netlist, constraints, require_all=True)

        assert result.passed is True
        assert result.error_count == 0

    def test_group_with_zone_assigns_components(self, simple_netlist):
        """Test component groups with zones count as assigned."""
        constraints = PlacementConstraints(
            board_width_mm=50.0,
            board_height_mm=50.0,
            zones=[
                Zone(name="MAIN", bounds=(0, 0, 50, 50), net_classes=["Signal"], components=[]),
            ],
            component_groups=[
                ComponentGroup(name="group1", components=["R1", "D1", "J1"], zone="MAIN"),
            ],
        )
        result = check_components_have_zones(simple_netlist, constraints, require_all=True)

        assert result.passed is True


# =============================================================================
# Test Constraint Feasibility Checks
# =============================================================================


class TestConstraintFeasibilityChecks:
    """Tests for constraint feasibility validation."""

    def test_feasible_constraints(self, simple_netlist, simple_constraints):
        """Test feasible constraints pass."""
        result = check_impossible_constraints(simple_netlist, simple_constraints)

        assert result.passed is True
        assert result.error_count == 0

    def test_component_too_large_for_zone(self, netlist_with_large_component):
        """Test component larger than zone generates error."""
        constraints = PlacementConstraints(
            board_width_mm=100.0,
            board_height_mm=100.0,
            zones=[
                Zone(
                    name="SMALL_ZONE", bounds=(0, 0, 30, 30), net_classes=["Signal"], components=[]
                ),
            ],
            zone_assignments={"LARGE": "SMALL_ZONE"},
        )
        result = check_impossible_constraints(netlist_with_large_component, constraints)

        assert result.passed is False
        assert result.error_count >= 1
        assert any(i.code == "CONSTRAINT_002" for i in result.issues)

    def test_nonexistent_zone_assignment(self, simple_netlist):
        """Test assignment to nonexistent zone generates error."""
        constraints = PlacementConstraints(
            board_width_mm=50.0,
            board_height_mm=50.0,
            zones=[],  # No zones defined
            zone_assignments={"R1": "MISSING_ZONE"},
        )
        result = check_impossible_constraints(simple_netlist, constraints)

        assert result.passed is False
        assert result.error_count >= 1
        assert any(i.code == "CONSTRAINT_001" for i in result.issues)

    def test_group_missing_components_warning(self, simple_netlist):
        """Test group referencing missing components generates warning."""
        constraints = PlacementConstraints(
            board_width_mm=50.0,
            board_height_mm=50.0,
            zones=[
                Zone(name="MAIN", bounds=(0, 0, 50, 50), net_classes=["Signal"], components=[]),
            ],
            component_groups=[
                ComponentGroup(
                    name="test_group",
                    components=["R1", "MISSING1", "MISSING2"],
                    zone="MAIN",
                ),
            ],
        )
        result = check_impossible_constraints(simple_netlist, constraints)

        # Missing group components is a warning, not error
        assert result.warning_count >= 1
        assert any(i.code == "CONSTRAINT_003" for i in result.issues)

    def test_group_nonexistent_zone(self, simple_netlist):
        """Test group with nonexistent zone generates error."""
        constraints = PlacementConstraints(
            board_width_mm=50.0,
            board_height_mm=50.0,
            zones=[],  # No zones
            component_groups=[
                ComponentGroup(name="test_group", components=["R1"], zone="MISSING_ZONE"),
            ],
        )
        result = check_impossible_constraints(simple_netlist, constraints)

        assert result.passed is False
        assert any(i.code == "CONSTRAINT_004" for i in result.issues)

    def test_thermal_missing_components_warning(self, simple_netlist):
        """Test thermal constraint referencing missing components."""
        constraints = PlacementConstraints(
            board_width_mm=50.0,
            board_height_mm=50.0,
            zones=[],
            thermal_constraints=[
                ThermalConstraint(components=["Q1", "Q2"]),  # Not in netlist
            ],
        )
        result = check_impossible_constraints(simple_netlist, constraints)

        assert result.warning_count >= 1
        assert any(i.code == "CONSTRAINT_005" for i in result.issues)


# =============================================================================
# Test Combined Preflight Checks
# =============================================================================


class TestCombinedPreflightChecks:
    """Tests for combined preflight check runner."""

    def test_run_all_checks(self, simple_netlist, simple_constraints):
        """Test running all preflight checks."""
        with patch(
            "temper_placer.validation.preflight.find_kicad_cli", return_value="/usr/bin/kicad-cli"
        ):
            with patch("shutil.which", return_value="/usr/bin/ngspice"):
                result = run_all_preflight_checks(
                    netlist=simple_netlist,
                    constraints=simple_constraints,
                    check_tools=True,
                    require_zone_assignments=True,
                )

        assert result.passed is True
        assert len(result.issues) > 0

    def test_run_without_tools(self, simple_netlist, simple_constraints):
        """Test running without tool checks."""
        result = run_all_preflight_checks(
            netlist=simple_netlist,
            constraints=simple_constraints,
            check_tools=False,
        )

        # No tool-related issues
        tool_codes = {"TOOL_001", "TOOL_002", "TOOL_003", "TOOL_004"}
        assert not any(i.code in tool_codes for i in result.issues)

    def test_run_without_netlist(self, simple_constraints):
        """Test running without netlist skips component checks."""
        result = run_all_preflight_checks(
            netlist=None,
            constraints=simple_constraints,
            check_tools=False,
        )

        # Should still check zone boundaries
        assert result.passed is True

    def test_run_without_constraints(self, simple_netlist):
        """Test running without constraints only checks tools."""
        with patch(
            "temper_placer.validation.preflight.find_kicad_cli", return_value="/usr/bin/kicad-cli"
        ):
            with patch("shutil.which", return_value="/usr/bin/ngspice"):
                result = run_all_preflight_checks(
                    netlist=simple_netlist,
                    constraints=None,
                    check_tools=True,
                )

        assert result.passed is True
        assert result.info_count == 2  # kicad-cli and ngspice found


# =============================================================================
# Test PreflightResult Methods
# =============================================================================


class TestPreflightResult:
    """Tests for PreflightResult dataclass."""

    def test_merge_results(self):
        """Test merging two preflight results."""
        result1 = PreflightResult(
            passed=True,
            issues=[PreflightIssue(PreflightSeverity.INFO, "CODE1", "msg1")],
        )
        result2 = PreflightResult(
            passed=False,
            issues=[PreflightIssue(PreflightSeverity.ERROR, "CODE2", "msg2")],
        )

        merged = result1.merge(result2)

        assert merged.passed is False  # False dominates
        assert len(merged.issues) == 2
        assert merged.error_count == 1
        assert merged.info_count == 1

    def test_count_properties(self):
        """Test count properties."""
        result = PreflightResult(
            passed=False,
            issues=[
                PreflightIssue(PreflightSeverity.ERROR, "E1", "error1"),
                PreflightIssue(PreflightSeverity.ERROR, "E2", "error2"),
                PreflightIssue(PreflightSeverity.WARNING, "W1", "warning1"),
                PreflightIssue(PreflightSeverity.INFO, "I1", "info1"),
                PreflightIssue(PreflightSeverity.INFO, "I2", "info2"),
                PreflightIssue(PreflightSeverity.INFO, "I3", "info3"),
            ],
        )

        assert result.error_count == 2
        assert result.warning_count == 1
        assert result.info_count == 3
