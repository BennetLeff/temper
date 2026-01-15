"""
Standalone validation experiment for MinCutMapper.

This validates the min-cut to component mapping logic without pytest dependencies.
"""

import sys
from pathlib import Path
from dataclasses import dataclass

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# Minimal ComponentData definition (to avoid ortools import)
@dataclass
class ComponentData:
    """Component placement data."""

    ref: str
    width_mm: float
    height_mm: float
    x_mm: float
    y_mm: float
    classification: str
    hv_nets: list = None

    def __post_init__(self):
        if self.hv_nets is None:
            self.hv_nets = []


# Now import mapper (which doesn't have ortools dependency)
from temper_placer.placement.benders_mincut_mapper import (
    MinCutMapper,
    BlockingComponent,
    CutDirection,
    estimate_required_gap,
)


def test_horizontal_cut():
    """Test horizontal cut identification."""
    print("\n=== Test 1: Horizontal Cut Identification ===")

    components = [
        ComponentData(ref="U1", width_mm=10.0, height_mm=5.0, x_mm=20.0, y_mm=20.0, classification="FREE"),
        ComponentData(ref="U2", width_mm=10.0, height_mm=5.0, x_mm=40.0, y_mm=20.0, classification="FREE"),
    ]

    mapper = MinCutMapper(components, tolerance_mm=2.0)

    # Vertical edge between U1 and U2 (blocks horizontal flow)
    min_cut_edges = [
        (("F.Cu", (30.0, 15.0)), ("F.Cu", (30.0, 25.0)), 0),
    ]

    result = mapper.map_mincut_to_components(min_cut_edges)

    print(f"Found {len(result)} blocking components:")
    for b in result:
        print(f"  - {b.component_ref} ({b.direction.value}): {b.position}, edges={b.edges_involved}")

    # Validation
    assert len(result) > 0, "Should find at least one blocking component"
    refs = {b.component_ref for b in result}
    assert refs & {"U1", "U2"}, f"Should find U1 or U2, got {refs}"
    assert any(b.direction == CutDirection.HORIZONTAL for b in result), "Should identify horizontal cut"

    print("✓ Test passed!")


def test_vertical_cut():
    """Test vertical cut identification."""
    print("\n=== Test 2: Vertical Cut Identification ===")

    components = [
        ComponentData(ref="U1", width_mm=10.0, height_mm=5.0, x_mm=20.0, y_mm=20.0, classification="FREE"),
        ComponentData(ref="U3", width_mm=10.0, height_mm=5.0, x_mm=20.0, y_mm=40.0, classification="FREE"),
    ]

    mapper = MinCutMapper(components, tolerance_mm=2.0)

    # Horizontal edge between U1 and U3 (blocks vertical flow)
    min_cut_edges = [
        (("F.Cu", (15.0, 30.0)), ("F.Cu", (25.0, 30.0)), 0),
    ]

    result = mapper.map_mincut_to_components(min_cut_edges)

    print(f"Found {len(result)} blocking components:")
    for b in result:
        print(f"  - {b.component_ref} ({b.direction.value}): {b.position}")

    assert len(result) > 0, "Should find blocking components"
    assert any(b.direction == CutDirection.VERTICAL for b in result), "Should identify vertical cut"

    print("✓ Test passed!")


def test_component_pairs():
    """Test component pair identification."""
    print("\n=== Test 3: Component Pair Identification ===")

    components = [
        ComponentData(ref="Q1", width_mm=14.4, height_mm=3.5, x_mm=25.0, y_mm=15.0, classification="HV"),
        ComponentData(ref="Q2", width_mm=14.4, height_mm=3.5, x_mm=50.0, y_mm=15.0, classification="HV"),
        ComponentData(ref="U_GATE", width_mm=11.0, height_mm=9.5, x_mm=37.5, y_mm=30.0, classification="HV"),
    ]

    mapper = MinCutMapper(components, tolerance_mm=2.0)

    # Vertical edge between Q1 and Q2
    min_cut_edges = [
        (("F.Cu", (37.5, 10.0)), ("F.Cu", (37.5, 20.0)), 0),
    ]

    result = mapper.map_mincut_to_components(min_cut_edges)
    pairs = mapper.get_component_pairs(result)

    print(f"Found {len(result)} blocking components:")
    for b in result:
        print(f"  - {b.component_ref} ({b.direction.value})")

    print(f"Identified {len(pairs)} component pairs:")
    for c1, c2, direction in pairs:
        print(f"  - {c1} <-> {c2} ({direction.value})")

    assert len(pairs) > 0, "Should identify at least one pair"
    pair_refs = {(p[0], p[1]) for p in pairs}
    assert ("Q1", "Q2") in pair_refs or ("Q2", "Q1") in pair_refs, "Should identify Q1-Q2 pair"

    print("✓ Test passed!")


def test_tolerance_effect():
    """Test tolerance parameter effect."""
    print("\n=== Test 4: Tolerance Parameter Effect ===")

    components = [
        ComponentData(ref="U1", width_mm=10.0, height_mm=5.0, x_mm=20.0, y_mm=20.0, classification="FREE"),
    ]

    # Edge just outside U1's bounding box (U1 bbox: 15-25 in x, 17.5-22.5 in y)
    min_cut_edges = [
        (("F.Cu", (26.0, 20.0)), ("F.Cu", (26.0, 25.0)), 0),  # At x=26, just 1mm outside
    ]

    mapper_small = MinCutMapper(components, tolerance_mm=0.5)
    mapper_large = MinCutMapper(components, tolerance_mm=2.0)

    result_small = mapper_small.map_mincut_to_components(min_cut_edges)
    result_large = mapper_large.map_mincut_to_components(min_cut_edges)

    print(f"Small tolerance (0.5mm): {len(result_small)} components")
    print(f"Large tolerance (2.0mm): {len(result_large)} components")

    assert len(result_large) >= len(result_small), "Larger tolerance should find more or equal components"

    print("✓ Test passed!")


def test_gap_estimation():
    """Test gap estimation logic."""
    print("\n=== Test 5: Gap Estimation ===")

    blocking = [
        BlockingComponent(
            component_ref="U1", direction=CutDirection.HORIZONTAL, position=(20.0, 20.0), edges_involved=3
        ),
        BlockingComponent(
            component_ref="U2", direction=CutDirection.HORIZONTAL, position=(40.0, 20.0), edges_involved=5
        ),
    ]

    gap = estimate_required_gap(blocking)
    print(f"Estimated gap for {len(blocking)} blockers with max 5 edges: {gap:.2f}mm")

    assert 2.0 <= gap <= 10.0, "Gap should be within reasonable range"
    assert gap >= 2.0, "Gap should be at least 2mm"

    print("✓ Test passed!")


def test_empty_mincut():
    """Test empty min-cut edge list."""
    print("\n=== Test 6: Empty Min-Cut ===")

    components = [
        ComponentData(ref="U1", width_mm=10.0, height_mm=5.0, x_mm=20.0, y_mm=20.0, classification="FREE"),
    ]

    mapper = MinCutMapper(components, tolerance_mm=2.0)
    result = mapper.map_mincut_to_components([])

    print(f"Empty min-cut result: {len(result)} components")
    assert len(result) == 0, "Empty min-cut should return empty result"

    print("✓ Test passed!")


def test_temper_board_scenario():
    """Test with realistic Temper board scenario."""
    print("\n=== Test 7: Temper Board Power Stage Bottleneck ===")

    # Power stage components
    components = [
        ComponentData(ref="Q1", width_mm=14.4, height_mm=3.5, x_mm=25.45, y_mm=15.0, classification="HV"),
        ComponentData(ref="Q2", width_mm=14.4, height_mm=3.5, x_mm=50.45, y_mm=15.0, classification="HV"),
        ComponentData(ref="U_GATE", width_mm=11.0, height_mm=9.49, x_mm=35.0, y_mm=30.0, classification="HV"),
        ComponentData(ref="C_BUS1", width_mm=10.5, height_mm=3.0, x_mm=28.75, y_mm=60.0, classification="HV"),
        ComponentData(ref="C_BUS2", width_mm=10.5, height_mm=3.0, x_mm=48.75, y_mm=60.0, classification="HV"),
    ]

    mapper = MinCutMapper(components, tolerance_mm=2.0)

    # Simulate horizontal cut between power stage (Q1, Q2, U_GATE) and bus capacitors
    # This represents congestion between power switches and DC bus
    min_cut_edges = [
        (("F.Cu", (25.0, 45.0)), ("F.Cu", (55.0, 45.0)), 1),  # Horizontal barrier
    ]

    result = mapper.map_mincut_to_components(min_cut_edges)
    refs = {b.component_ref for b in result}

    print(f"Found {len(result)} blocking components:")
    for b in result:
        print(f"  - {b.component_ref} ({b.direction.value}): {b.position}")

    print(f"Component refs: {refs}")

    # Should identify power components
    power_components = {"Q1", "Q2", "U_GATE", "C_BUS1", "C_BUS2"}
    assert len(refs & power_components) > 0, f"Should identify power components, got {refs}"

    pairs = mapper.get_component_pairs(result)
    print(f"Identified {len(pairs)} separation pairs")

    print("✓ Test passed!")


def run_all_tests():
    """Run all validation tests."""
    print("=" * 60)
    print("MinCutMapper Validation Experiments")
    print("=" * 60)

    tests = [
        test_horizontal_cut,
        test_vertical_cut,
        test_component_pairs,
        test_tolerance_effect,
        test_gap_estimation,
        test_empty_mincut,
        test_temper_board_scenario,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"✗ Test failed: {e}")
            import traceback

            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
