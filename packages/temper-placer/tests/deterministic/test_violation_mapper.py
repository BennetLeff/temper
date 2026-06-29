import pytest

from temper_placer.core.netlist import Component, Netlist, Pin
from temper_placer.deterministic.feedback import DRCViolation, ViolationComponentMapper


@pytest.fixture
def sample_netlist():
    """Create netlist with known component positions."""
    q2 = Component(
        ref='Q2',
        footprint='TO-247',
        bounds=(15.0, 20.0),
        pins=[
            Pin(name='G', number='1', position=(-5.0, -5.0)),
            Pin(name='C', number='2', position=(0.0, -5.0)),
            Pin(name='E', number='3', position=(5.0, -5.0)),
            Pin(name='D', number='4', position=(0.0, 5.0)),
        ],
        initial_position=(65.0, 5.0)
    )
    u_gate = Component(
        ref='U_GATE',
        footprint='SOIC-8',
        bounds=(5.0, 5.0),
        pins=[
            Pin(name='8', number='8', position=(2.0, 2.0)),
        ],
        initial_position=(70.0, 5.0)
    )
    d1 = Component(
        ref='D1',
        footprint='D_SOD-123',
        bounds=(2.0, 4.0),
        pins=[],
        initial_position=(72.0, 8.0)
    )
    return Netlist(components=[q2, u_gate, d1])

def test_short_violation_maps_to_both_components(sample_netlist):
    """Shorting violation should identify both components involved."""
    violation = DRCViolation(
        type='shorting_items',
        items=['Track on F.Cu at (67.5, 6.0)', 'Pad Q2-D on F.Cu'],
        severity='error'
    )
    mapper = ViolationComponentMapper(sample_netlist)
    result = mapper.map_violation(violation)

    assert 'Q2' in result.components
    assert len(result.components) >= 1

def test_clearance_violation_extracts_position(sample_netlist):
    """Clearance violation should extract violation position."""
    violation = DRCViolation(
        type='clearance',
        description='Clearance violation (0.15mm < 0.20mm required)',
        pos=(67.5, 6.0)
    )
    mapper = ViolationComponentMapper(sample_netlist)
    result = mapper.map_violation(violation)

    assert result.position == (67.5, 6.0)
    assert result.required_clearance == 0.20
    assert result.actual_clearance == 0.15

def test_solder_mask_bridge_identifies_pad_components(sample_netlist):
    """Mask bridge violation should identify components with nearby pads."""
    violation = DRCViolation(
        type='solder_mask_bridge',
        items=['Pad Q2-D', 'Pad U_GATE-8'],
        pos=(68.0, 5.5)
    )
    mapper = ViolationComponentMapper(sample_netlist)
    result = mapper.map_violation(violation)

    assert 'Q2' in result.components
    assert 'U_GATE' in result.components

def test_violation_maps_to_zone(sample_netlist):
    """Violations should be assigned to the containing zone."""
    violation = DRCViolation(type='clearance', pos=(67.5, 6.0))
    zone_config = {'HV_POWER': {'bounds': [(60, 0), (80, 15)]}}

    mapper = ViolationComponentMapper(sample_netlist, zone_config)
    result = mapper.map_violation(violation)

    assert result.zone == 'HV_POWER'

def test_hole_clearance_extracts_drill_info(sample_netlist):
    """Hole clearance should identify via/PTH involvement."""
    # Update Q2 pins to have a PTH one
    for p in sample_netlist.components[0].pins:
        if p.name == 'E':
            p.name = 'S'
            p.is_pth = True

    violation = DRCViolation(
        type='hole_clearance',
        items=['Via at (68.0, 7.0)', 'PTH pad Q2-S'],
        required=0.25
    )
    mapper = ViolationComponentMapper(sample_netlist)
    result = mapper.map_violation(violation)

    assert result.involves_via
    assert result.involves_pth
    assert 'Q2' in result.components
