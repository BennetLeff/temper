"""
Standalone validation experiment for BendersCutGenerator.

This validates the cut generation logic without pytest dependencies.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from temper_placer.placement.benders_cut_generator import (
    BendersCutGenerator,
    RoutabilityCut,
    CutType,
    direction_to_cut_type,
)
from temper_placer.placement.benders_mincut_mapper import (
    BlockingComponent,
    CutDirection,
)


def test_horizontal_cut():
    """Test horizontal cut generation."""
    print("\n=== Test 1: Horizontal Cut Generation ===")

    generator = BendersCutGenerator()
    blocking = [
        BlockingComponent("U1", CutDirection.HORIZONTAL, (20.0, 20.0), 2),
        BlockingComponent("U2", CutDirection.HORIZONTAL, (40.0, 20.0), 2),
    ]

    cuts = generator.generate_cuts(blocking)

    print(f"Generated {len(cuts)} cuts:")
    for cut in cuts:
        print(f"  - {cut.cut_type.value}: {cut.component_pair[0]} <-> {cut.component_pair[1]}")
        print(f"    Gap required: {cut.gap_required:.2f}mm")

    assert len(cuts) > 0, "Should generate at least one cut"
    assert cuts[0].cut_type == CutType.HORIZONTAL
    assert set(cuts[0].component_pair) == {"U1", "U2"}
    assert cuts[0].gap_required > 0

    print("✓ Test passed!")


def test_vertical_cut():
    """Test vertical cut generation."""
    print("\n=== Test 2: Vertical Cut Generation ===")

    generator = BendersCutGenerator()
    blocking = [
        BlockingComponent("U1", CutDirection.VERTICAL, (20.0, 20.0), 1),
        BlockingComponent("U3", CutDirection.VERTICAL, (20.0, 40.0), 1),
    ]

    cuts = generator.generate_cuts(blocking)

    print(f"Generated {len(cuts)} cuts:")
    for cut in cuts:
        print(f"  - {cut.cut_type.value}: {cut.component_pair[0]} <-> {cut.component_pair[1]}")
        print(f"    Gap required: {cut.gap_required:.2f}mm")

    assert len(cuts) > 0
    assert cuts[0].cut_type == CutType.VERTICAL
    assert set(cuts[0].component_pair) == {"U1", "U3"}

    print("✓ Test passed!")


def test_multiple_cuts():
    """Test generating multiple cuts."""
    print("\n=== Test 3: Multiple Cuts ===")

    generator = BendersCutGenerator()
    blocking = [
        BlockingComponent("U1", CutDirection.HORIZONTAL, (10.0, 20.0), 1),
        BlockingComponent("U2", CutDirection.HORIZONTAL, (30.0, 20.0), 1),
        BlockingComponent("U3", CutDirection.HORIZONTAL, (50.0, 20.0), 1),
        BlockingComponent("U4", CutDirection.VERTICAL, (20.0, 10.0), 1),
        BlockingComponent("U5", CutDirection.VERTICAL, (20.0, 30.0), 1),
    ]

    cuts = generator.generate_cuts(blocking)

    print(f"Generated {len(cuts)} cuts:")
    for cut in cuts:
        print(f"  - {cut.cut_type.value}: {cut.component_pair[0]} <-> {cut.component_pair[1]}")

    h_cuts = [c for c in cuts if c.cut_type == CutType.HORIZONTAL]
    v_cuts = [c for c in cuts if c.cut_type == CutType.VERTICAL]

    print(f"Horizontal cuts: {len(h_cuts)}, Vertical cuts: {len(v_cuts)}")

    assert len(cuts) >= 2
    assert len(h_cuts) > 0
    assert len(v_cuts) > 0

    print("✓ Test passed!")


def test_gap_estimation():
    """Test gap estimation based on congestion."""
    print("\n=== Test 4: Gap Estimation Based on Congestion ===")

    generator = BendersCutGenerator()

    # Light congestion
    light = [
        BlockingComponent("U1", CutDirection.HORIZONTAL, (20.0, 20.0), 1),
        BlockingComponent("U2", CutDirection.HORIZONTAL, (40.0, 20.0), 1),
    ]

    # Heavy congestion
    heavy = [
        BlockingComponent("U1", CutDirection.HORIZONTAL, (20.0, 20.0), 8),
        BlockingComponent("U2", CutDirection.HORIZONTAL, (40.0, 20.0), 8),
    ]

    light_cuts = generator.generate_cuts(light)
    heavy_cuts = generator.generate_cuts(heavy)

    print(f"Light congestion gap: {light_cuts[0].gap_required:.2f}mm")
    print(f"Heavy congestion gap: {heavy_cuts[0].gap_required:.2f}mm")

    assert heavy_cuts[0].gap_required >= light_cuts[0].gap_required
    print("✓ Test passed!")


def test_empty_input():
    """Test empty blocking list."""
    print("\n=== Test 5: Empty Input ===")

    generator = BendersCutGenerator()
    cuts = generator.generate_cuts([])

    print(f"Empty input produces {len(cuts)} cuts")
    assert len(cuts) == 0

    print("✓ Test passed!")


def test_single_blocker():
    """Test single blocker (no pairs)."""
    print("\n=== Test 6: Single Blocker ===")

    generator = BendersCutGenerator()
    blocking = [
        BlockingComponent("U1", CutDirection.HORIZONTAL, (20.0, 20.0), 1),
    ]

    cuts = generator.generate_cuts(blocking)

    print(f"Single blocker produces {len(cuts)} cuts")
    assert len(cuts) == 0

    print("✓ Test passed!")


def test_cut_data_structure():
    """Test RoutabilityCut data structure."""
    print("\n=== Test 7: Cut Data Structure ===")

    generator = BendersCutGenerator()
    blocking = [
        BlockingComponent("U1", CutDirection.HORIZONTAL, (20.0, 20.0), 2),
        BlockingComponent("U2", CutDirection.HORIZONTAL, (40.0, 20.0), 2),
    ]

    cuts = generator.generate_cuts(blocking, iteration=5)
    cut = cuts[0]

    print(f"Cut type: {cut.cut_type}")
    print(f"Component pair: {cut.component_pair}")
    print(f"Gap required: {cut.gap_required}mm")
    print(f"Iteration: {cut.iteration}")

    assert isinstance(cut.cut_type, CutType)
    assert isinstance(cut.component_pair, tuple)
    assert len(cut.component_pair) == 2
    assert isinstance(cut.gap_required, float)
    assert cut.iteration == 5

    print("✓ Test passed!")


def test_master_problem_compatibility():
    """Test compatibility with Master Problem interface."""
    print("\n=== Test 8: Master Problem Compatibility ===")

    generator = BendersCutGenerator()
    blocking = [
        BlockingComponent("U1", CutDirection.HORIZONTAL, (20.0, 20.0), 2),
        BlockingComponent("U2", CutDirection.HORIZONTAL, (40.0, 20.0), 2),
    ]

    cuts = generator.generate_cuts(blocking)
    cut = cuts[0]

    # Convert to Master Problem arguments
    cut_type, components, gap = cut.to_master_problem_args()

    print(f"Master Problem args:")
    print(f"  cut_type: {cut_type} (type: {type(cut_type).__name__})")
    print(f"  components: {components} (type: {type(components).__name__})")
    print(f"  gap_required: {gap} (type: {type(gap).__name__})")

    assert isinstance(cut_type, str)
    assert cut_type in ("horizontal", "vertical")
    assert isinstance(components, list)
    assert len(components) == 2
    assert isinstance(gap, float)
    assert gap > 0

    print("✓ Test passed!")


def test_direction_conversion():
    """Test CutDirection to CutType conversion."""
    print("\n=== Test 9: Direction Conversion ===")

    h_cut = direction_to_cut_type(CutDirection.HORIZONTAL)
    v_cut = direction_to_cut_type(CutDirection.VERTICAL)

    print(f"CutDirection.HORIZONTAL -> {h_cut}")
    print(f"CutDirection.VERTICAL -> {v_cut}")

    assert h_cut == CutType.HORIZONTAL
    assert v_cut == CutType.VERTICAL

    print("✓ Test passed!")


def test_end_to_end_mincut_to_cut():
    """Test complete flow from min-cut to cuts."""
    print("\n=== Test 10: End-to-End Min-Cut to Cut ===")

    from temper_placer.placement.benders_mincut_mapper import MinCutMapper
    from dataclasses import dataclass

    @dataclass
    class ComponentData:
        ref: str
        width_mm: float
        height_mm: float
        x_mm: float
        y_mm: float
        classification: str

    components = [
        ComponentData("U1", 10.0, 5.0, 20.0, 20.0, "FREE"),
        ComponentData("U2", 10.0, 5.0, 40.0, 20.0, "FREE"),
    ]

    mapper = MinCutMapper(components, tolerance_mm=2.0)
    generator = BendersCutGenerator()

    # Min-cut edge
    min_cut_edges = [
        (("F.Cu", (30.0, 15.0)), ("F.Cu", (30.0, 25.0)), 0),
    ]

    # Map to components
    blocking = mapper.map_mincut_to_components(min_cut_edges)
    print(f"Mapper found {len(blocking)} blocking components")

    # Generate cuts
    cuts = generator.generate_cuts(blocking)
    print(f"Generator produced {len(cuts)} cuts")

    for cut in cuts:
        print(f"  - {cut.cut_type.value}: {cut.component_pair[0]} <-> {cut.component_pair[1]}")
        print(f"    Gap: {cut.gap_required:.2f}mm")

    assert len(cuts) > 0
    assert cuts[0].cut_type == CutType.HORIZONTAL

    print("✓ Test passed!")


def run_all_tests():
    """Run all validation tests."""
    print("=" * 60)
    print("BendersCutGenerator Validation Experiments")
    print("=" * 60)

    tests = [
        test_horizontal_cut,
        test_vertical_cut,
        test_multiple_cuts,
        test_gap_estimation,
        test_empty_input,
        test_single_blocker,
        test_cut_data_structure,
        test_master_problem_compatibility,
        test_direction_conversion,
        test_end_to_end_mincut_to_cut,
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
