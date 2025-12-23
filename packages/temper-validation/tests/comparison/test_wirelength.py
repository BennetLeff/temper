"""Tests for wirelength comparison module."""

import pytest
from dataclasses import dataclass
from typing import NamedTuple


# Mock data structures (will be replaced with real imports later)
@dataclass
class Point:
    x: float
    y: float


@dataclass  
class Pin:
    name: str
    position: Point


@dataclass
class Net:
    name: str
    pins: list[Pin]


@dataclass
class Component:
    name: str
    position: Point
    pins: list[Pin]


@dataclass
class Placement:
    components: list[Component]
    nets: list[Net]


@dataclass
class WirelengthResult:
    optimized: float
    reference: float
    ratio: float
    margin: float
    verdict: str


def create_test_placement(component_positions: dict[str, tuple[float, float]]) -> Placement:
    """Helper to create test placement."""
    components = []
    for name, (x, y) in component_positions.items():
        comp = Component(
            name=name,
            position=Point(x, y),
            pins=[
                Pin(f"{name}.1", Point(x, y)),
                Pin(f"{name}.2", Point(x + 1, y))
            ]
        )
        components.append(comp)
    
    return Placement(components=components, nets=[])


def create_test_net(pin_names: list[str]) -> Net:
    """Helper to create test net."""
    # Find pins in placement by name (simplified)
    pins = [Pin(name, Point(0, 0)) for name in pin_names]
    return Net(name="TEST_NET", pins=pins)


def test_manhattan_wirelength_simple():
    """Calculate wirelength for simple 2-component board."""
    # Setup: R1 at (0,0), R2 at (10,10)
    placement = create_test_placement({
        "R1": (0, 0),
        "R2": (10, 10)
    })
    
    # Create net connecting R1.1 to R2.1
    net = Net(name="NET1", pins=[
        Pin("R1.1", Point(0, 0)),
        Pin("R2.1", Point(10, 10))
    ])
    
    # Expected: Manhattan distance = |10-0| + |10-0| = 20
    expected_wirelength = 20.0
    
    # This will FAIL until we implement manhattan_wirelength
    from temper_validation.comparison.wirelength import manhattan_wirelength
    
    wirelength = manhattan_wirelength(placement, net)
    
    assert wirelength == expected_wirelength, \
        f"Expected {expected_wirelength}, got {wirelength}"


def test_manhattan_wirelength_multi_net():
    """Calculate total wirelength for multiple nets."""
    placement = create_test_placement({
        "R1": (0, 0),
        "R2": (10, 0),
        "R3": (0, 10)
    })
    
    nets = [
        Net(name="NET1", pins=[
            Pin("R1.1", Point(0, 0)),
            Pin("R2.1", Point(10, 0))
        ]),
        Net(name="NET2", pins=[
            Pin("R1.2", Point(1, 0)),
            Pin("R3.1", Point(0, 10))
        ])
    ]
    
    # Net1: 10, Net2: 1 + 10 = 11, Total: 21
    expected_total = 21.0
    
    from temper_validation.comparison.wirelength import manhattan_wirelength
    
    total_wirelength = sum(
        manhattan_wirelength(placement, net) for net in nets
    )
    
    assert total_wirelength == expected_total, \
        f"Expected {expected_total}, got {total_wirelength}"


def test_compare_wirelength_ratio():
    """Compute ratio of optimized vs reference wirelength."""
    # Setup: Optimized = 100, Reference = 120
    optimized = create_test_placement({"R1": (0, 0), "R2": (10, 0)})
    reference = create_test_placement({"R1": (0, 0), "R2": (12, 0)})
    
    # Create same net for both
    net = Net(name="NET1", pins=[
        Pin("R1.1", Point(0, 0)),
        Pin("R2.1", Point(10, 0))
    ])
    
    # This will FAIL until we implement compare_wirelength
    from temper_validation.comparison.wirelength import compare_wirelength
    
    result = compare_wirelength(optimized, reference, [net])
    
    assert result.ratio == pytest.approx(10/12, rel=0.01), \
        f"Expected ratio ~0.833, got {result.ratio}"


def test_compare_wirelength_verdict():
    """Verdict PASS if ratio < 1.1, FAIL otherwise."""
    from temper_validation.comparison.wirelength import compare_wirelength
    
    # Case 1: ratio = 0.9 (should PASS)
    optimized = create_test_placement({"R1": (0, 0), "R2": (9, 0)})
    reference = create_test_placement({"R1": (0, 0), "R2": (10, 0)})
    net = Net(name="NET1", pins=[
        Pin("R1.1", Point(0, 0)),
        Pin("R2.1", Point(10, 0))
    ])
    
    result = compare_wirelength(optimized, reference, [net])
    assert result.verdict == "PASS", \
        f"Ratio 0.9 should PASS, got {result.verdict}"
    
    # Case 2: ratio = 1.2 (should FAIL)
    optimized = create_test_placement({"R1": (0, 0), "R2": (12, 0)})
    result = compare_wirelength(optimized, reference, [net])
    assert result.verdict == "FAIL", \
        f"Ratio 1.2 should FAIL, got {result.verdict}"


def test_steiner_tree_approximation():
    """Steiner tree wirelength should be <= Manhattan wirelength."""
    from temper_validation.comparison.wirelength import (
        manhattan_wirelength, steiner_wirelength
    )
    
    # 3-component case where Steiner point is beneficial
    placement = create_test_placement({
        "R1": (0, 0),
        "R2": (10, 0),
        "R3": (5, 10)
    })
    
    net = Net(name="NET1", pins=[
        Pin("R1.1", Point(0, 0)),
        Pin("R2.1", Point(10, 0)),
        Pin("R3.1", Point(5, 10))
    ])
    
    manhattan = manhattan_wirelength(placement, net)
    steiner = steiner_wirelength(placement, net)
    
    # Steiner should be shorter or equal (better approximation)
    assert steiner <= manhattan, \
        f"Steiner ({steiner}) should be <= Manhattan ({manhattan})"
