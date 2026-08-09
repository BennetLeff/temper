"""Tests for validation.tht_check module."""
from dataclasses import dataclass

from temper_placer.core.netlist import Netlist
from temper_placer.validation.tht_check import validate_hole_clearance


@dataclass
class _MockPad:
    """Mock pad for tht_check tests."""
    drill: float
    position: tuple[float, float]
    number: str = "1"


@dataclass
class _MockComp:
    """Mock component with pads attribute."""
    ref: str
    bounds: tuple[float, float]
    pads: list[_MockPad]
    pins: list = None

    def __post_init__(self):
        if self.pins is None:
            self.pins = []


class TestValidateHoleClearance:
    """Tests for validate_hole_clearance."""

    def test_empty_netlist(self):
        netlist = Netlist(components=[], nets=[])
        positions = []
        result = validate_hole_clearance(netlist, positions)
        assert result == []

    def test_no_tht_pads(self):
        comp = _MockComp(ref="U1", bounds=(10.0, 10.0), pads=[])
        netlist = Netlist(components=[comp], nets=[])
        positions = [(25.0, 25.0)]
        result = validate_hole_clearance(netlist, positions)
        assert result == []

    def test_single_tht_hole_no_collision(self):
        pad = _MockPad(drill=1.0, position=(0.0, 0.0))
        comp = _MockComp(ref="U1", bounds=(10.0, 10.0), pads=[pad])
        netlist = Netlist(components=[comp], nets=[])
        positions = [(25.0, 25.0)]
        result = validate_hole_clearance(netlist, positions)
        # Single hole -> no collision pairs
        assert result == []

    def test_two_holes_far_apart(self):
        comp1 = _MockComp(
            ref="U1", bounds=(10.0, 10.0),
            pads=[_MockPad(drill=1.0, position=(0.0, 0.0))],
        )
        comp2 = _MockComp(
            ref="U2", bounds=(10.0, 10.0),
            pads=[_MockPad(drill=1.0, position=(0.0, 0.0))],
        )
        netlist = Netlist(components=[comp1, comp2], nets=[])
        positions = [(10.0, 10.0), (80.0, 80.0)]
        result = validate_hole_clearance(netlist, positions)
        # Far apart -> no collision
        assert result == []
