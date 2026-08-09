"""Tests for validation.preflight module — preflight check functions."""
from temper_placer.core.netlist import Component, Netlist
from temper_placer.io.config_loader import PlacementConstraints
from temper_placer.validation.preflight import (
    PreflightResult,
    check_components_have_zones,
    check_external_tools,
    check_impossible_constraints,
    check_kicad_cli,
    check_ngspice,
    check_zones_fit_on_board,
    run_all_preflight_checks,
)


class TestCheckKicadCli:
    """Tests for check_kicad_cli."""

    def test_returns_preflight_result(self):
        result = check_kicad_cli()
        assert isinstance(result, PreflightResult)
        assert result.passed is True  # warning, not error


class TestCheckNgspice:
    """Tests for check_ngspice."""

    def test_returns_preflight_result(self):
        result = check_ngspice()
        assert isinstance(result, PreflightResult)
        assert result.passed is True  # warning, not error


class TestCheckExternalTools:
    """Tests for check_external_tools."""

    def test_returns_preflight_result(self):
        result = check_external_tools()
        assert isinstance(result, PreflightResult)


class TestCheckComponentsHaveZones:
    """Tests for check_components_have_zones."""

    def test_empty_netlist(self):
        netlist = Netlist(components=[], nets=[])
        constraints = PlacementConstraints()
        result = check_components_have_zones(netlist, constraints)
        assert isinstance(result, PreflightResult)

    def test_with_component(self):
        comp = Component(ref="U1", footprint="SOIC-8", bounds=(10.0, 10.0), pins=[])
        netlist = Netlist(components=[comp], nets=[])
        constraints = PlacementConstraints()
        result = check_components_have_zones(netlist, constraints)
        assert isinstance(result, PreflightResult)


class TestCheckZonesFitOnBoard:
    """Tests for check_zones_fit_on_board."""

    def test_no_zones(self):
        constraints = PlacementConstraints(board_width_mm=100.0, board_height_mm=100.0)
        result = check_zones_fit_on_board(constraints)
        assert isinstance(result, PreflightResult)
        assert result.passed is True


class TestCheckImpossibleConstraints:
    """Tests for check_impossible_constraints."""

    def test_empty_constraints(self):
        netlist = Netlist(components=[], nets=[])
        constraints = PlacementConstraints()
        result = check_impossible_constraints(netlist, constraints)
        assert isinstance(result, PreflightResult)


class TestRunAllPreflightChecks:
    """Tests for run_all_preflight_checks."""

    def test_runs_all_checks(self):
        netlist = Netlist(components=[], nets=[])
        constraints = PlacementConstraints(board_width_mm=100.0, board_height_mm=100.0)
        result = run_all_preflight_checks(
            netlist=netlist,
            constraints=constraints,
        )
        assert isinstance(result, PreflightResult)
