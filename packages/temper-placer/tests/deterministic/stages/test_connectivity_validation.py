import pytest

from temper_placer.deterministic.stages.connectivity_validation import (
    ConnectivityValidationError,
    ConnectivityValidationStage,
)
from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix
from temper_placer.router_v6.constraints_drc_oracle import DRCOracle
from temper_placer.router_v6.constraints_geometry import Point
from temper_placer.router_v6.constraints_spatial_index import Pad, Track, Via


def test_connectivity_stage_clean_board():
    '''Fully connected net should have no violations.'''
    rules = ClearanceMatrix(default_clearance=0.2)
    oracle = DRCOracle(rules=rules)

    # Net A: Two pads connected by a track
    oracle.register_pad(Pad(center=Point(0, 0), shape='circle', size=(1, 1), net='A', layer=0))
    oracle.register_pad(Pad(center=Point(10, 0), shape='circle', size=(1, 1), net='A', layer=0))
    oracle.register_track(Track(start=Point(0, 0), end=Point(10, 0), width=0.25, net='A', layer=0))

    state = BoardState(drc_oracle=oracle)
    result = ConnectivityValidationStage().run(state)

    assert result.connectivity_violations == ()

def test_connectivity_stage_unconnected_pads():
    '''Two isolated pads of the same net should be detected.'''
    rules = ClearanceMatrix(default_clearance=0.2)
    oracle = DRCOracle(rules=rules)

    # Net A: Two pads, no track
    oracle.register_pad(Pad(center=Point(0, 0), shape='circle', size=(1, 1), net='A', layer=0, id="P1"))
    oracle.register_pad(Pad(center=Point(10, 0), shape='circle', size=(1, 1), net='A', layer=0, id="P2"))

    state = BoardState(drc_oracle=oracle)
    result = ConnectivityValidationStage().run(state)

    assert len(result.connectivity_violations) > 0
    assert any(v.type == "unconnected_pad" for v in result.connectivity_violations)

def test_connectivity_stage_orphan_island():
    '''Isolated copper with no pads should be detected.'''
    rules = ClearanceMatrix(default_clearance=0.2)
    oracle = DRCOracle(rules=rules)

    # Net A: Just a track, no pads
    oracle.register_track(Track(start=Point(0, 0), end=Point(10, 0), width=0.25, net='A', layer=0))

    state = BoardState(drc_oracle=oracle)
    result = ConnectivityValidationStage().run(state)

    assert len(result.connectivity_violations) > 0
    assert any(v.type == "orphan_island" for v in result.connectivity_violations)

def test_connectivity_stage_mixed_violations():
    '''Should detect both unconnected pads and orphan islands in the same net.'''
    rules = ClearanceMatrix(default_clearance=0.2)
    oracle = DRCOracle(rules=rules)

    # Net A:
    # Group 1: Pad 1 connected to Pad 2
    oracle.register_pad(Pad(center=Point(0, 0), shape='circle', size=(1, 1), net='A', layer=0, id="P1"))
    oracle.register_pad(Pad(center=Point(10, 0), shape='circle', size=(1, 1), net='A', layer=0, id="P2"))
    oracle.register_track(Track(start=Point(0, 0), end=Point(10, 0), width=0.25, net='A', layer=0))

    # Group 2: Pad 3 (isolated)
    oracle.register_pad(Pad(center=Point(0, 10), shape='circle', size=(1, 1), net='A', layer=0, id="P3"))

    # Group 3: Isolated track (orphan)
    oracle.register_track(Track(start=Point(10, 10), end=Point(15, 10), width=0.25, net='A', layer=0))

    state = BoardState(drc_oracle=oracle)
    result = ConnectivityValidationStage().run(state)

    # Expected: 1 unconnected_pad (P3), 1 orphan_island (Track at 10,10), 1 dangling_track (Track at 10,10)
    assert len(result.connectivity_violations) == 3
    assert any(v.type == "unconnected_pad" for v in result.connectivity_violations)
    assert any(v.type == "orphan_island" for v in result.connectivity_violations)
    assert any(v.type == "dangling_track" for v in result.connectivity_violations)

def test_connectivity_stage_dangling_track():
    '''Track segment with one open end should be detected.'''
    rules = ClearanceMatrix(default_clearance=0.2)
    oracle = DRCOracle(rules=rules)

    # Pad at (0,0). Track from (0,0) to (5,0). Nothing at (5,0).
    oracle.register_pad(Pad(center=Point(0, 0), shape='circle', size=(1, 1), net='A', layer=0))
    oracle.register_track(Track(start=Point(0, 0), end=Point(5, 0), width=0.25, net='A', layer=0))

    state = BoardState(drc_oracle=oracle)
    result = ConnectivityValidationStage().run(state)

    assert len(result.connectivity_violations) > 0
    assert any(v.type == "dangling_track" for v in result.connectivity_violations)

def test_connectivity_stage_via_connection():
    '''Pads connected via a track and a via should be valid.'''
    rules = ClearanceMatrix(default_clearance=0.2)
    oracle = DRCOracle(rules=rules)

    # Pad 1 (L0) -> Track (L0) -> Via -> Pad 2 (L1)
    oracle.register_pad(Pad(center=Point(0, 0), shape='circle', size=(1, 1), net='A', layer=0))
    oracle.register_track(Track(start=Point(0, 0), end=Point(5, 0), width=0.25, net='A', layer=0))
    oracle.register_via(Via(center=Point(5, 0), diameter=0.6, drill=0.3, net='A'))
    oracle.register_pad(Pad(center=Point(5, 0), shape='circle', size=(1, 1), net='A', layer=1))

    state = BoardState(drc_oracle=oracle)
    result = ConnectivityValidationStage().run(state)

    assert result.connectivity_violations == ()

def test_connectivity_stage_fail_on_violations():
    '''Should raise error if fail_on_violations is True.'''
    rules = ClearanceMatrix(default_clearance=0.2)
    oracle = DRCOracle(rules=rules)
    oracle.register_track(Track(start=Point(0, 0), end=Point(10, 0), width=0.25, net='A', layer=0))

    state = BoardState(drc_oracle=oracle)
    stage = ConnectivityValidationStage(fail_on_violations=True)

    with pytest.raises(ConnectivityValidationError):
        stage.run(state)
