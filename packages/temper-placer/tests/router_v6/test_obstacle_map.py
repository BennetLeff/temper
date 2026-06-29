
import pytest
from shapely.geometry import Point

from temper_placer.core.netlist import Component, Pin
from temper_placer.router_v6.escape_via_generator import EscapeVia
from temper_placer.router_v6.obstacle_map import build_obstacle_map
from temper_placer.router_v6.stage0_data import LayerInfo, ParsedPCB, StackupInfo


@pytest.fixture
def simple_stackup():
    return StackupInfo(
        layers=[
            LayerInfo(0, "F.Cu", "signal", 35.0),
            LayerInfo(1, "In1.Cu", "plane", 35.0, "GND"),
            LayerInfo(2, "B.Cu", "signal", 35.0),
        ],
        total_thickness_mm=1.6,
        layer_count=3
    )

@pytest.fixture
def empty_pcb(simple_stackup):
    # Minimal mock
    return ParsedPCB(
        components=[],
        nets=[],
        zones=[],
        board=None, # Mock if needed
        design_rules=None, # Not used in obstacle map currently
        stackup=simple_stackup,
        source_path=None
    )

def test_component_pads(empty_pcb):
    # Component with 1 pad on F.Cu
    pad = Pin(
        name="1", number="1", position=(0, 0),
        width=1.0, height=1.0, shape="rect", layer="F.Cu"
    )
    comp = Component(
        ref="U1", footprint="FP", bounds=(2,2), pins=[pad],
        initial_position=(10, 10), initial_rotation=0
    )
    empty_pcb.components = [comp]

    obstacles = build_obstacle_map(empty_pcb, [])

    assert "F.Cu" in obstacles
    poly = obstacles["F.Cu"]
    assert not poly.is_empty
    # Centered at 10,10, width 1.0 -> bounds should be 9.5 to 10.5
    assert poly.bounds == (9.5, 9.5, 10.5, 10.5)

    # Check B.Cu is empty
    assert "B.Cu" not in obstacles or obstacles["B.Cu"].is_empty

def test_rotated_pad(empty_pcb):
    # Pad rotated 90 degrees via component rotation
    # Original: 2.0 x 1.0 (wide)
    pad = Pin(
        name="1", number="1", position=(0, 0),
        width=2.0, height=1.0, shape="rect", layer="F.Cu"
    )
    comp = Component(
        ref="U1", footprint="FP", bounds=(2,2), pins=[pad],
        initial_position=(10, 10),
        initial_rotation=1 # 90 degrees
    )
    empty_pcb.components = [comp]

    obstacles = build_obstacle_map(empty_pcb, [])
    poly = obstacles["F.Cu"]

    # Should be tall now (1.0 x 2.0)
    # Bounds: x=[9.5, 10.5], y=[9.0, 11.0]
    minx, miny, maxx, maxy = poly.bounds
    assert abs(minx - 9.5) < 1e-6
    assert abs(maxx - 10.5) < 1e-6
    assert abs(miny - 9.0) < 1e-6
    assert abs(maxy - 11.0) < 1e-6

def test_escape_vias(empty_pcb):
    via = EscapeVia(
        position=(5, 5),
        net_name="N1",
        pin_number="1",
        diameter=1.0,
        drill=0.5,
        via_type="dog-bone"
    )

    obstacles = build_obstacle_map(empty_pcb, [via])

    # Via should appear on F.Cu and B.Cu (signal layers)
    # And potentially In1.Cu if we treated it as signal, but it's plane.
    # The code filters for ["signal", "mixed"].

    assert "F.Cu" in obstacles
    assert "B.Cu" in obstacles

    # Check geometry (approx circle)
    poly = obstacles["F.Cu"]
    assert poly.area > 0.7 # pi*0.5^2 = 0.785
    assert poly.centroid.x == pytest.approx(5.0)
    assert poly.centroid.y == pytest.approx(5.0)

def test_union_overlapping(empty_pcb):
    # Two overlapping vias
    v1 = EscapeVia(position=(0, 0), net_name="N", pin_number="1", diameter=2.0, drill=0.5, via_type="x")
    v2 = EscapeVia(position=(1, 0), net_name="N", pin_number="2", diameter=2.0, drill=0.5, via_type="x")

    obstacles = build_obstacle_map(empty_pcb, [v1, v2])
    poly = obstacles["F.Cu"]

    # Should be a single polygon (merged)
    assert len(poly.geoms) == 1
    # Area should be less than sum of individual areas
    area1 = Point(0,0).buffer(1.0).area
    assert poly.area < area1 * 2
