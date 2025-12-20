"""
Tests for preflight feasibility checker.
"""

import pytest
from pathlib import Path

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Netlist, Component, Net
from temper_placer.pcl.parser import ConstraintCollection
from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    SeparatedConstraint,
    EnclosingConstraint,
    ConstraintTier
)
from temper_placer.pipeline.preflight import PreflightChecker, PreflightResult, FabPreset


@pytest.fixture
def board():
    return Board(width=100.0, height=100.0)


@pytest.fixture
def netlist():
    components = [
        Component(ref="U1", footprint="SOIC-8", bounds=(5.0, 5.0)),
        Component(ref="U2", footprint="SOIC-8", bounds=(5.0, 5.0)),
    ]
    return Netlist(components=components, nets=[])


@pytest.fixture
def checker():
    return PreflightChecker()


def test_check_component_area_pass(checker, board, netlist):
    report = checker._check_component_area(board, netlist)
    assert report.result == PreflightResult.PASS
    assert "OK" in report.message


def test_check_component_area_fail(checker, board):
    # Create huge component that exceeds 85% of board (100x100 = 10000)
    # 95x95 = 9025 (90%)
    components = [Component(ref="HUGE", footprint="X", bounds=(95.0, 95.0))]
    netlist = Netlist(components=components)
    
    report = checker._check_component_area(board, netlist)
    assert report.result == PreflightResult.FAIL
    assert "exceeds 85%" in report.message


def test_check_constraint_satisfiability_contradiction(checker):
    constraints = ConstraintCollection([
        AdjacentConstraint(
            a="U1", b="U2", max_distance_mm=5.0, 
            tier=ConstraintTier.HARD, because="Components must be close together"
        ),
        SeparatedConstraint(
            a="U1", b="U2", min_distance_mm=10.0,
            tier=ConstraintTier.HARD, because="Components must be far apart"
        )
    ])
    
    report = checker._check_constraint_satisfiability(constraints)
    assert report.result == PreflightResult.FAIL
    assert "contradiction" in report.message
    assert any("conflicts" in c for c in report.details["contradictions"])


def test_check_constraint_satisfiability_mutual_exclusion(checker):
    constraints = ConstraintCollection([
        EnclosingConstraint(
            outer="ZONE_A", inner=["U1"],
            tier=ConstraintTier.HARD, because="Assigned to Zone A for thermal"
        ),
        EnclosingConstraint(
            outer="ZONE_B", inner=["U1"],
            tier=ConstraintTier.HARD, because="Assigned to Zone B for signal"
        )
    ])
    
    report = checker._check_constraint_satisfiability(constraints)
    assert report.result == PreflightResult.FAIL
    assert "contradiction" in report.message
    assert any("multiple zones" in c for c in report.details["contradictions"])


def test_check_clearance_feasibility_fail(checker):
    # Tiny board where clearance is impossible
    board = Board(width=10.0, height=10.0)
    
    # Two components that take up most of the board
    components = [
        Component(ref="H1", footprint="X", bounds=(5.0, 5.0)),
        Component(ref="L1", footprint="X", bounds=(5.0, 5.0)),
    ]
    netlist = Netlist(components=components)
    
    constraints = ConstraintCollection([
        EnclosingConstraint(outer="HV_ZONE", inner=["H1"], tier=ConstraintTier.HARD, because="High voltage safety critical"),
        SeparatedConstraint(a="H1", b="L1", min_distance_mm=10.0, tier=ConstraintTier.HARD, because="Clearance requirement")
    ])
    
    # hv_width = 5**0.5 * 1.5 = 2.23 * 1.5 = 3.35
    # lv_width = 3.35
    # total = 3.35 + 3.35 + 10.0 = 16.7
    # 16.7 > 10.0 (board.width)
    
    fab = FabPreset.jlcpcb_standard()
    report = checker._check_clearance_feasibility(board, netlist, constraints, fab)
    assert report.result == PreflightResult.FAIL


def test_check_routing_channels_warn(checker, board):
    # Pack many components into a small board
    components = [
        Component(ref=f"R{i}", footprint="0603", bounds=(2.0, 1.0))
        for i in range(100)
    ]
    # Board 10x10 = 100mm2. 100 * 2mm2 = 200mm2 (already fails area but we test channels)
    board = Board(width=10.0, height=10.0)
    netlist = Netlist(components=components)
    
    report = checker._check_routing_channels(board, netlist)
    assert report.result == PreflightResult.WARN
    assert "Limited routing channel" in report.message


def test_run_full_pass(checker, board, netlist):
    constraints = ConstraintCollection([])
    report = checker.run(board, netlist, constraints)
    assert report.overall == PreflightResult.PASS
    assert len(report.checks) == 5