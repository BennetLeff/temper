"""Tests for preflight module."""

from dataclasses import dataclass, field
from unittest import mock

import pytest

from temper_placer.pipeline.preflight import (
    PreflightCheck,
    PreflightChecker,
    PreflightReport,
    PreflightResult,
)


def test_preflight_report_passed_true():
    """PreflightReport with PASS overall returns passed=True."""
    report = PreflightReport(
        checks=[],
        overall=PreflightResult.PASS,
        total_time_ms=10.0,
    )
    assert report.passed is True


def test_preflight_report_passed_warn():
    """PreflightReport with WARN overall returns passed=True (not FAIL)."""
    report = PreflightReport(
        checks=[],
        overall=PreflightResult.WARN,
        total_time_ms=10.0,
    )
    assert report.passed is True


def test_preflight_report_passed_false():
    """PreflightReport with FAIL overall returns passed=False."""
    report = PreflightReport(
        checks=[],
        overall=PreflightResult.FAIL,
        total_time_ms=10.0,
    )
    assert report.passed is False


def test_preflight_report_summary():
    """summary() returns a multi-line string with check results."""
    checks = [
        PreflightCheck(
            name="Layer Count",
            result=PreflightResult.PASS,
            message="4-layer stackup verified",
        ),
        PreflightCheck(
            name="Component Area",
            result=PreflightResult.WARN,
            message="Fill ratio 75.0%",
        ),
        PreflightCheck(
            name="Constraint Satisfiability",
            result=PreflightResult.FAIL,
            message="Found 2 issues",
        ),
    ]
    report = PreflightReport(
        checks=checks,
        overall=PreflightResult.FAIL,
        total_time_ms=42.0,
    )
    summary = report.summary()
    assert "Preflight Checks:" in summary
    assert "[OK]" in summary
    assert "[WARN]" in summary
    assert "[FAIL]" in summary
    assert "Layer Count" in summary
    assert "Component Area" in summary
    assert "Constraint Satisfiability" in summary
    assert "Overall: FAIL" in summary
    assert "42.0ms" in summary


# =============================================================================
# PreflightChecker.run tests
# =============================================================================


@dataclass
class _MockLayer:
    name: str


@dataclass
class _MockStackup:
    layers: list[_MockLayer]


@dataclass
class _MockComponent:
    ref: str
    width: float = 10.0
    height: float = 10.0
    net_class: str = "Signal"
    zone: str = ""


@dataclass
class _MockProximityRule:
    component_a: str
    component_b: str
    max_distance_mm: float = 50.0


@dataclass
class _MockComponentGroup:
    proximity_rules: list[_MockProximityRule]


@dataclass
class _MockConstraints:
    component_groups: list[_MockComponentGroup] = field(default_factory=list)
    critical_loops: list = field(default_factory=list)


@dataclass
class _MockZone:
    name: str
    width: float
    height: float


class _MockBoard:
    def __init__(self):
        self.width = 100.0
        self.height = 100.0
        self.zones: list[_MockZone] = []
        # Provide a minimal layer_stackup with 4 layers so _check_layer_count passes
        self.layer_stackup = _MockStackup(
            layers=[
                _MockLayer("F.Cu"),
                _MockLayer("In1.Cu"),
                _MockLayer("In2.Cu"),
                _MockLayer("B.Cu"),
            ]
        )
        self.keepouts: list = []


class _MockNetlist:
    def __init__(self):
        self.components: list[_MockComponent] = []
        self.nets: list = []


class TestPreflightCheckerRun:
    """Tests for PreflightChecker.run()."""

    def test_run_returns_report(self):
        """run() returns a PreflightReport when given minimal valid inputs."""
        checker = PreflightChecker()
        board = _MockBoard()
        netlist = _MockNetlist()
        netlist.components = [_MockComponent("U1")]
        constraints = _MockConstraints()

        report = checker.run(board, netlist, constraints, _fab_preset=None)

        assert isinstance(report, PreflightReport)
        assert len(report.checks) == 10  # 10 checks total
        assert report.total_time_ms > 0

    def test_run_layer_count_fails_for_wrong_layer_count(self):
        """run() returns FAIL when layer stackup has wrong count."""
        checker = PreflightChecker()
        board = _MockBoard()
        board.layer_stackup = _MockStackup(
            layers=[_MockLayer("F.Cu"), _MockLayer("B.Cu")]
        )
        netlist = _MockNetlist()
        netlist.components = [_MockComponent("U1")]
        constraints = _MockConstraints()

        report = checker.run(board, netlist, constraints, _fab_preset=None)
        assert report.overall == PreflightResult.FAIL

    def test_run_layer_count_fails_for_no_stackup(self):
        """run() returns FAIL when board has no layer stackup."""
        checker = PreflightChecker()
        board = _MockBoard()
        board.layer_stackup = None
        netlist = _MockNetlist()
        netlist.components = [_MockComponent("U1")]
        constraints = _MockConstraints()

        report = checker.run(board, netlist, constraints, _fab_preset=None)
        assert report.overall == PreflightResult.FAIL

    def test_run_passes_for_valid_input(self):
        """run() returns PASS when all checks pass with valid 4-layer board."""
        checker = PreflightChecker()
        board = _MockBoard()
        netlist = _MockNetlist()
        # Components with enough space on a 100x100 board
        netlist.components = [
            _MockComponent("U1", width=5.0, height=5.0),
            _MockComponent("U2", width=5.0, height=5.0),
        ]
        constraints = _MockConstraints()

        report = checker.run(board, netlist, constraints, _fab_preset=None)
        # With no keepouts and small components, area and all checks should pass
        assert report.overall != PreflightResult.FAIL

    def test_run_constraint_satisfiability_fails(self):
        """run() returns FAIL when proximity constraints are impossible."""
        checker = PreflightChecker()
        board = _MockBoard()
        netlist = _MockNetlist()
        netlist.components = [
            _MockComponent("A", width=10.0, height=10.0),
            _MockComponent("B", width=10.0, height=10.0),
        ]
        constraints = _MockConstraints(
            component_groups=[
                _MockComponentGroup(
                    proximity_rules=[
                        _MockProximityRule("A", "B", max_distance_mm=0.1),
                    ]
                )
            ]
        )

        report = checker.run(board, netlist, constraints, _fab_preset=None)
        assert report.overall == PreflightResult.FAIL

    def test_run_zone_capacity_pass_when_no_zones(self):
        """run() zone capacity check passes when there are no zones."""
        checker = PreflightChecker()
        board = _MockBoard()
        board.zones = []
        netlist = _MockNetlist()
        netlist.components = [_MockComponent("U1")]
        constraints = _MockConstraints()

        report = checker.run(board, netlist, constraints, _fab_preset=None)
        # No zones = zone check passes = overall may pass
        zone_check = [c for c in report.checks if c.name == "Zone Capacity"][0]
        assert zone_check.result == PreflightResult.PASS

    def test_run_loop_area_feasibility_with_no_loops(self):
        """run() loop area check passes when no critical loops defined."""
        checker = PreflightChecker()
        board = _MockBoard()
        netlist = _MockNetlist()
        netlist.components = [_MockComponent("U1")]
        constraints = _MockConstraints(critical_loops=[])

        report = checker.run(board, netlist, constraints, _fab_preset=None)
        loop_check = [c for c in report.checks if c.name == "Loop Area Feasibility"][0]
        assert loop_check.result == PreflightResult.PASS

