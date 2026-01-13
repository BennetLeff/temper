import pytest
from temper_placer.deterministic.feedback import (
    ZoneAdjuster, MappedViolation, ZoneAdjustment, DRCViolation
)

@pytest.fixture
def zone_config():
    return {
        'HV_POWER': {
            'bounds': [(60, 0), (75, 15)],
            'min_size': (10, 10),
            'max_size': (25, 20),
            'can_expand': ['right', 'down']
        },
        'CONTROL': {
            'bounds': [(0, 0), (60, 30)],
            'min_size': (40, 20),
            'max_size': (70, 35),
            'can_expand': ['right']
        }
    }

def test_no_adjustments_when_violations_below_threshold(zone_config):
    """Zones with few violations should not be adjusted."""
    violations = [
        MappedViolation(type='clearance', components=['Q2'], position=(65, 5), zone='HV_POWER')
    ]
    adjuster = ZoneAdjuster(zone_config, violation_threshold=5)
    result = adjuster.compute_adjustments(violations)

    assert len(result.adjustments) == 0

def test_zone_expands_when_violations_exceed_threshold(zone_config):
    """Zone with many violations should expand."""
    violations = [
        MappedViolation(type='clearance', components=['Q2'], position=(65 + i * 0.5, 5), zone='HV_POWER')
        for i in range(10)
    ]
    adjuster = ZoneAdjuster(zone_config, violation_threshold=5)
    result = adjuster.compute_adjustments(violations)

    assert 'HV_POWER' in result.adjustments
    adj = result.adjustments['HV_POWER']
    assert adj.delta_width > 0 or adj.delta_height > 0

def test_respects_max_size_limits(zone_config):
    """Expansion should stop at max_size limits."""
    violations = [
        MappedViolation(type='clearance', components=['Q2'], position=(65, 5), zone='HV_POWER')
        for _ in range(100)
    ]
    # Max size for HV_POWER is (25, 20), current is (15, 15)
    # So max delta is (10, 5)
    adjuster = ZoneAdjuster(zone_config, expansion_per_violation=1.0)
    result = adjuster.compute_adjustments(violations)

    adj = result.adjustments['HV_POWER']
    assert adj.delta_width <= 10.0
    assert adj.delta_height <= 5.0

def test_expansion_directions(zone_config):
    """Only allowed directions should be used for expansion."""
    violations = [
        MappedViolation(type='clearance', components=['Q2'], position=(10, 10), zone='CONTROL')
        for _ in range(10)
    ]
    # CONTROL can only expand 'right' (width)
    adjuster = ZoneAdjuster(zone_config)
    result = adjuster.compute_adjustments(violations)

    adj = result.adjustments['CONTROL']
    assert adj.delta_width > 0
    assert adj.delta_height == 0
