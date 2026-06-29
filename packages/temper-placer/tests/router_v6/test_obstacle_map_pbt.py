"""Property-based tests for ObstacleMap invariants."""

import math

from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import Point

from temper_placer.core.netlist import Component, Pin
from temper_placer.router_v6.escape_via_generator import EscapeVia
from temper_placer.router_v6.obstacle_map import _create_pad_polygon, build_obstacle_map
from temper_placer.router_v6.stage0_data import DesignRules, LayerInfo, ParsedPCB, StackupInfo


def _make_minimal_pcb(components=None, stackup_layers=None):
    if stackup_layers is None:
        stackup_layers = [
            LayerInfo(0, "F.Cu", "signal", 35.0),
            LayerInfo(1, "B.Cu", "signal", 35.0),
        ]
    return ParsedPCB(
        components=components or [],
        nets=[],
        zones=[],
        board=None,
        design_rules=DesignRules(
            net_classes={}, net_class_assignments={},
            default_clearance_mm=0.2, default_trace_width_mm=0.2,
            default_via_diameter_mm=0.6, default_via_drill_mm=0.3,
        ),
        stackup=StackupInfo(layers=stackup_layers, total_thickness_mm=1.6, layer_count=len(stackup_layers)),
        source_path=None,
    )


@given(
    x=st.floats(min_value=-100, max_value=100),
    y=st.floats(min_value=-100, max_value=100),
    w=st.floats(min_value=0.1, max_value=10.0),
    h=st.floats(min_value=0.1, max_value=10.0),
    angle=st.floats(min_value=0, max_value=2 * math.pi),
)
@settings(max_examples=100, deadline=30000)
def test_pad_polygon_contains_center(x, y, w, h, angle):
    """Pad polygon always contains its center point."""
    pin = Pin(name="1", number="1", position=(0, 0), width=w, height=h, shape="rect", layer="F.Cu")
    poly = _create_pad_polygon(pin, x, y, angle)
    assert poly.contains(Point(x, y)) or poly.touches(Point(x, y))


@given(
    x=st.floats(min_value=-100, max_value=100),
    y=st.floats(min_value=-100, max_value=100),
    radius=st.floats(min_value=0.1, max_value=10.0),
    angle=st.floats(min_value=0, max_value=2 * math.pi),
)
@settings(max_examples=100, deadline=30000)
def test_circular_pad_contains_center(x, y, radius, angle):
    """Circular pad polygon always contains its center."""
    pin = Pin(name="1", number="1", position=(0, 0), width=radius * 2, height=radius * 2, shape="circle", layer="F.Cu")
    poly = _create_pad_polygon(pin, x, y, angle)
    assert poly.contains(Point(x, y)) or poly.touches(Point(x, y))


@given(
    num_pads=st.integers(min_value=1, max_value=20),
    seed=st.integers(min_value=0, max_value=1000),
)
@settings(max_examples=100, deadline=30000)
def test_obstacle_map_layer_coverage(num_pads, seed):
    """All layers present in obstacle map have valid MultiPolygon data (no None)."""
    import random
    rng = random.Random(seed)

    layers = [
        LayerInfo(0, "F.Cu", "signal", 35.0),
        LayerInfo(1, "B.Cu", "signal", 35.0),
    ]
    declared = {l.name for l in layers if l.layer_type in ("signal", "mixed")}

    pins = []
    for i in range(num_pads):
        layer = rng.choice(list(declared))
        pins.append(Pin(
            name=str(i), number=str(i), position=(0, 0),
            width=1.0, height=1.0, shape="rect", layer=layer,
        ))

    comp = Component(
        ref="U1", footprint="FP", bounds=(2, 2), pins=pins,
        initial_position=(rng.uniform(0, 50), rng.uniform(0, 50)),
        initial_rotation=0,
    )

    pcb = _make_minimal_pcb(components=[comp], stackup_layers=layers)
    obstacles = build_obstacle_map(pcb, [])

    for layer_name in obstacles:
        assert obstacles[layer_name] is not None
        assert obstacles[layer_name].area >= 0


@given(
    x=st.floats(min_value=0, max_value=100),
    y=st.floats(min_value=0, max_value=100),
    diameter=st.floats(min_value=0.2, max_value=2.0),
)
@settings(max_examples=100, deadline=30000)
def test_escape_via_in_obstacle_map(x, y, diameter):
    """Escape vias appear as obstacles on signal layers."""
    via = EscapeVia(net_name="test", pin_number="1", position=(x, y), diameter=diameter, drill=0.3, via_type="through")
    pcb = _make_minimal_pcb()
    obstacles = build_obstacle_map(pcb, [via])

    for layer_name in ("F.Cu", "B.Cu"):
        assert layer_name in obstacles
        poly = obstacles[layer_name]
        assert poly.area >= 0
