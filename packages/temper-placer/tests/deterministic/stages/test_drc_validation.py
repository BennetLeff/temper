import logging

import pytest

from temper_placer.deterministic.stages.drc_validation import DRCValidationError, DRCValidationStage
from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix
from temper_placer.router_v6.constraints_drc_oracle import DRCOracle
from temper_placer.router_v6.constraints_geometry import Point
from temper_placer.router_v6.constraints_spatial_index import Pad, Track, Via


def test_validation_stage_returns_violations():
    '''Stage should return violations from oracle.validate_all().'''
    # Basic rules: 0.2mm clearance
    rules = ClearanceMatrix(default_clearance=0.2)
    oracle = DRCOracle(rules=rules)

    # Create intentional violation: two tracks too close
    oracle.register_track(Track(
        start=Point(0, 0), end=Point(10, 0), width=0.25, net='A', layer=0
    ))
    oracle.register_track(Track(
        start=Point(0, 0.2), end=Point(10, 0.2), width=0.25, net='B', layer=0
    ))

    state = BoardState(drc_oracle=oracle)
    stage = DRCValidationStage()
    result = stage.run(state)

    assert result.drc_violations is not None
    assert len(result.drc_violations) > 0
    assert any(v.type == 'track_clearance' for v in result.drc_violations)

def test_validation_stage_no_violations_clean_board():
    '''Clean board should have empty violations list.'''
    rules = ClearanceMatrix(default_clearance=0.2)
    oracle = DRCOracle(rules=rules)

    # Well-spaced tracks
    oracle.register_track(Track(
        start=Point(0, 0), end=Point(10, 0), width=0.25, net='A', layer=0
    ))
    oracle.register_track(Track(
        start=Point(0, 5), end=Point(10, 5), width=0.25, net='B', layer=0
    ))  # 5mm apart - plenty of clearance

    state = BoardState(drc_oracle=oracle)
    result = DRCValidationStage().run(state)

    assert result.drc_violations == ()

def test_validation_stage_skips_when_no_oracle():
    '''Should return state unchanged if oracle is None.'''
    state = BoardState(drc_oracle=None)
    result = DRCValidationStage().run(state)
    assert result.drc_violations is None

def test_validation_stage_logs_violation_summary(caplog):
    '''Should log violation count and breakdown.'''
    caplog.set_level(logging.WARNING)
    rules = ClearanceMatrix(default_clearance=0.2)
    oracle = DRCOracle(rules=rules)

    oracle.register_track(Track(
        start=Point(0, 0), end=Point(10, 0), width=0.25, net='A', layer=0
    ))
    oracle.register_track(Track(
        start=Point(0, 0.2), end=Point(10, 0.2), width=0.25, net='B', layer=0
    ))

    state = BoardState(drc_oracle=oracle)
    DRCValidationStage().run(state)

    assert "DRC validation: 1 violations" in caplog.text
    assert "track_clearance: 1" in caplog.text

def test_validation_catches_via_to_pad_violation():
    '''Should detect via-to-pad clearance violations.'''
    rules = ClearanceMatrix(default_clearance=0.2)
    oracle = DRCOracle(rules=rules)
    oracle.register_pad(Pad(center=Point(10, 10), shape='rect', size=(1, 1), net='GND', layer=0))
    # Via too close to pad
    oracle.register_via(Via(center=Point(10.5, 10), diameter=0.6, drill=0.3, net='VCC'))

    state = BoardState(drc_oracle=oracle)
    result = DRCValidationStage().run(state)

    assert result.drc_violations is not None
    assert len(result.drc_violations) > 0

def test_validation_stage_fail_thresholds():
    '''Should raise error if thresholds exceeded.'''
    rules = ClearanceMatrix(default_clearance=0.2)
    oracle = DRCOracle(rules=rules)
    oracle.register_track(Track(Point(0,0), Point(10,0), 0.25, 'A', 0))
    oracle.register_track(Track(Point(0,0.2), Point(10,0.2), 0.25, 'B', 0))

    state = BoardState(drc_oracle=oracle)

    # Test fail_on_violations
    stage_fail = DRCValidationStage(fail_on_violations=True)
    with pytest.raises(DRCValidationError, match="1 DRC violations found"):
        stage_fail.run(state)

    # Test max_violations
    stage_max_1 = DRCValidationStage(max_violations=1)
    # 1 violation is NOT more than 1, so it should pass if we use >
    stage_max_1.run(state)

    # Add another violation
    oracle.register_track(Track(Point(0, 5), Point(10, 5), 0.25, 'C', 0))
    oracle.register_track(Track(Point(0, 5.2), Point(10, 5.2), 0.25, 'D', 0))

    # Now we have 2 violations
    with pytest.raises(DRCValidationError, match="violations exceeds max 1"):
        stage_max_1.run(state)
