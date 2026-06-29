from dataclasses import dataclass

import numpy as np
import pytest

from temper_placer.placer.deterministic import (
    PlacementResult,
    place_by_proximity,
    place_in_zone_center,
    place_power_stage_template,
)
from temper_placer.placer.template import ComponentPosition, ComponentTemplate


# Mocks
@dataclass
class MockZone:
    name: str
    bounds: tuple[float, float, float, float]  # x_min, y_min, x_max, y_max

@dataclass
class MockBoard:
    zones: list[MockZone]
    width: float = 100.0
    height: float = 100.0

@dataclass
class MockComponent:
    ref: str

@dataclass
class MockNetlist:
    components: list[MockComponent]

    @property
    def n_components(self):
        return len(self.components)

@pytest.fixture
def basic_board():
    return MockBoard(zones=[
        MockZone("power_zone", (0, 0, 50, 50)),
        MockZone("logic_zone", (50, 50, 100, 100))
    ])

@pytest.fixture
def basic_netlist():
    return MockNetlist(components=[
        MockComponent("Q1"), MockComponent("Q2"),
        MockComponent("D1"), MockComponent("D2"),
        MockComponent("C1"), MockComponent("U1")
    ])

@pytest.fixture
def hb_template():
    return ComponentTemplate(
        name="test_hb",
        components=[
            ComponentPosition("Q1", 0, 0, 0),
            ComponentPosition("Q2", 0, -20, 0),
            ComponentPosition("D1", 10, 0, 0),
            ComponentPosition("D2", 10, -20, 0),
        ],
        anchor_point="Q1"
    )

def test_place_power_stage_template(basic_board, basic_netlist, hb_template):
    result = place_power_stage_template(
        basic_netlist, basic_board, hb_template, zone_name="power_zone"
    )

    assert isinstance(result, PlacementResult)
    assert isinstance(result.positions, np.ndarray)
    assert result.positions.shape == (6, 2)
    assert "Q1" in result.placed_refs
    assert "U1" in result.unplaced_refs

    # Check Q1 position (anchor) at zone center (25, 25)
    # Ref Q1 is index 0
    np.testing.assert_allclose(result.positions[0], [25, 25])
    # Check Q2 position (0, -20 relative to Q1) -> (25, 5)
    np.testing.assert_allclose(result.positions[1], [25, 5])

def test_place_by_proximity(basic_board, basic_netlist):
    # Place U1 at center, then others spiral around it
    result = place_by_proximity(
        basic_netlist, basic_board,
        target_ref="U1",
        refs_to_place=["C1", "D1"]
    )

    assert isinstance(result, PlacementResult)
    assert "U1" not in result.placed_refs # Target itself is not "placed", it's the anchor
    assert "C1" in result.placed_refs

    # C1 should be spiral placed
    idx_c1 = 4 # C1 is 5th component
    assert not np.allclose(result.positions[idx_c1], [0, 0])

def test_place_in_zone_center(basic_board, basic_netlist):
    result = place_in_zone_center(
        basic_netlist, basic_board,
        refs_to_place=["U1", "C1"],
        zone_name="logic_zone"
    )

    # Logic zone center is (75, 75)
    # With 2 components, grid is 2x2.

    assert "U1" in result.placed_refs
    idx_u1 = 5
    # Just check it's within zone bounds
    pos = result.positions[idx_u1]
    assert 50 <= pos[0] <= 100
    assert 50 <= pos[1] <= 100
