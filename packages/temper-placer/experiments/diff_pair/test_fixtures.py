"""
Test Fixtures for Differential Pair Routing Experiments

Provides diverse test cases for incremental router validation.
"""

from dataclasses import dataclass
from typing import List, Tuple, Set, Optional


@dataclass
class TestFixture:
    """
    A test case for differential pair routing.

    Attributes:
        name: Human-readable test name
        description: What this test validates
        start_pins: ((p_x, p_y), (n_x, n_y)) in mm
        goal_pins: ((p_x, p_y), (n_x, n_y)) in mm
        obstacles: Set of (x, y, layer) grid cells that are blocked
        board_size: (width_mm, height_mm, num_layers)
        grid_resolution_mm: Grid cell size (0.1mm for diff pairs)
        trace_width_mm: Width of each trace
        spacing_mm: Target P-N spacing
        expected_success: Should routing succeed?
        expected_violations: Expected DRC violations (for negative tests)
        tags: Classification tags (e.g., "straight", "corner", "obstacle")
    """

    name: str
    description: str
    start_pins: Tuple[Tuple[float, float], Tuple[float, float]]
    goal_pins: Tuple[Tuple[float, float], Tuple[float, float]]
    obstacles: Set[Tuple[int, int, int]]
    board_size: Tuple[float, float, int]
    grid_resolution_mm: float = 0.1
    trace_width_mm: float = 0.127
    spacing_mm: float = 0.25
    expected_success: bool = True
    expected_violations: int = 0
    tags: Optional[List[str]] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


def create_test_fixtures() -> List[TestFixture]:
    """
    Create diverse test fixtures for differential pair routing experiments.

    Returns:
        List of TestFixture objects covering various scenarios
    """
    fixtures = []

    # =========================================================================
    # Fixture 1: Simple Horizontal Routing (Straight Line)
    # =========================================================================
    fixtures.append(
        TestFixture(
            name="straight_horizontal",
            description="Simple horizontal routing with no obstacles - validates basic coupled movement",
            start_pins=((1.0, 5.0), (1.0, 5.25)),  # Vertically stacked
            goal_pins=((10.0, 5.0), (10.0, 5.25)),
            obstacles=set(),
            board_size=(20.0, 10.0, 1),
            spacing_mm=0.25,
            expected_success=True,
            tags=["straight", "horizontal", "basic"],
        )
    )

    # =========================================================================
    # Fixture 2: Simple Vertical Routing (Straight Line)
    # =========================================================================
    fixtures.append(
        TestFixture(
            name="straight_vertical",
            description="Simple vertical routing with no obstacles - validates basic coupled movement",
            start_pins=((5.0, 1.0), (5.25, 1.0)),  # Horizontally stacked
            goal_pins=((5.0, 10.0), (5.25, 10.0)),
            obstacles=set(),
            board_size=(10.0, 20.0, 1),
            spacing_mm=0.25,
            expected_success=True,
            tags=["straight", "vertical", "basic"],
        )
    )

    # =========================================================================
    # Fixture 3: Single 45° Corner (L-Shaped)
    # =========================================================================
    fixtures.append(
        TestFixture(
            name="single_corner_45deg",
            description="L-shaped path with single 45° corner - validates corner geometry",
            start_pins=((1.0, 5.0), (1.0, 5.25)),
            goal_pins=((5.0, 9.0), (5.25, 9.0)),
            obstacles=set(),
            board_size=(10.0, 10.0, 1),
            spacing_mm=0.25,
            expected_success=True,
            tags=["corner", "45deg", "L-shape"],
        )
    )

    # =========================================================================
    # Fixture 4: Obstacle Avoidance (Single Pad)
    # =========================================================================
    # Create obstacle: 2mm x 2mm pad at center
    center_x_mm, center_y_mm = 5.0, 5.0
    pad_radius_mm = 1.0
    obstacles_pad = set()

    # Convert to grid cells (0.1mm resolution)
    for dx in range(-10, 11):  # -1.0mm to +1.0mm in 0.1mm steps
        for dy in range(-10, 11):
            x_mm = center_x_mm + dx * 0.1
            y_mm = center_y_mm + dy * 0.1
            dist = ((x_mm - center_x_mm) ** 2 + (y_mm - center_y_mm) ** 2) ** 0.5
            if dist <= pad_radius_mm:
                # Convert mm to grid cells
                grid_x = int(x_mm / 0.1)
                grid_y = int(y_mm / 0.1)
                obstacles_pad.add((grid_x, grid_y, 0))

    fixtures.append(
        TestFixture(
            name="obstacle_single_pad",
            description="Route around single circular pad obstacle - validates divergence and reconvergence",
            start_pins=((1.0, 5.0), (1.0, 5.25)),
            goal_pins=((9.0, 5.0), (9.0, 5.25)),
            obstacles=obstacles_pad,
            board_size=(10.0, 10.0, 1),
            spacing_mm=0.25,
            expected_success=True,
            tags=["obstacle", "divergence", "avoidance"],
        )
    )

    # =========================================================================
    # Fixture 5: Narrow Corridor
    # =========================================================================
    # Create corridor walls (top and bottom)
    obstacles_corridor = set()
    corridor_width_mm = 1.0  # 1mm wide corridor
    corridor_start_mm = 3.0
    corridor_end_mm = 7.0

    # Top wall
    for x in range(int(corridor_start_mm / 0.1), int(corridor_end_mm / 0.1)):
        for dy in range(5):  # 0.5mm thick wall
            obstacles_corridor.add((x, int(6.0 / 0.1) + dy, 0))

    # Bottom wall
    for x in range(int(corridor_start_mm / 0.1), int(corridor_end_mm / 0.1)):
        for dy in range(5):  # 0.5mm thick wall
            obstacles_corridor.add((x, int(4.5 / 0.1) - dy, 0))

    fixtures.append(
        TestFixture(
            name="narrow_corridor",
            description="Route through narrow corridor - validates tight coupling maintenance",
            start_pins=((1.0, 5.0), (1.0, 5.25)),
            goal_pins=((9.0, 5.0), (9.0, 5.25)),
            obstacles=obstacles_corridor,
            board_size=(10.0, 10.0, 1),
            spacing_mm=0.25,
            expected_success=True,
            tags=["corridor", "tight-coupling", "constrained"],
        )
    )

    # =========================================================================
    # Fixture 6: DRC Violation Test (Pad Too Close)
    # =========================================================================
    # Place pad very close to goal pins - should fail with DRC violation
    obstacles_too_close = set()
    pad_center_x = 8.5  # Very close to goal at 9.0
    pad_center_y = 5.0

    for dx in range(-10, 11):
        for dy in range(-10, 11):
            x_mm = pad_center_x + dx * 0.1
            y_mm = pad_center_y + dy * 0.1
            dist = ((x_mm - pad_center_x) ** 2 + (y_mm - pad_center_y) ** 2) ** 0.5
            if dist <= 1.0:
                grid_x = int(x_mm / 0.1)
                grid_y = int(y_mm / 0.1)
                obstacles_too_close.add((grid_x, grid_y, 0))

    fixtures.append(
        TestFixture(
            name="drc_violation_pad_clearance",
            description="Pad too close to goal - should fail with DRC violation (negative test)",
            start_pins=((1.0, 5.0), (1.0, 5.25)),
            goal_pins=((9.0, 5.0), (9.0, 5.25)),
            obstacles=obstacles_too_close,
            board_size=(10.0, 10.0, 1),
            spacing_mm=0.25,
            expected_success=False,
            expected_violations=1,
            tags=["drc", "negative-test", "clearance"],
        )
    )

    # =========================================================================
    # Fixture 7: Length Mismatch (Triggers Serpentine)
    # =========================================================================
    fixtures.append(
        TestFixture(
            name="length_mismatch_serpentine",
            description="P and N start/end at different offsets - triggers serpentine for length matching",
            start_pins=((1.0, 5.0), (1.0, 5.25)),
            goal_pins=((10.0, 7.0), (10.0, 7.25)),  # Diagonal path creates length mismatch
            obstacles=set(),
            board_size=(15.0, 10.0, 1),
            spacing_mm=0.25,
            expected_success=True,
            tags=["length-matching", "serpentine", "diagonal"],
        )
    )

    # =========================================================================
    # Fixture 8: Multi-Layer Transition (Via Pair)
    # =========================================================================
    # This will be used in EXP-5
    fixtures.append(
        TestFixture(
            name="via_transition_simple",
            description="Simple via transition from F.Cu to B.Cu - validates via pair placement",
            start_pins=((1.0, 5.0), (1.0, 5.25)),
            goal_pins=((9.0, 5.0), (9.0, 5.25)),
            obstacles=set(),
            board_size=(10.0, 10.0, 2),  # 2 layers
            spacing_mm=0.25,
            expected_success=True,
            tags=["via", "layer-transition", "multi-layer"],
        )
    )

    return fixtures


def get_fixture_by_name(name: str) -> Optional[TestFixture]:
    """Get a specific test fixture by name."""
    fixtures = create_test_fixtures()
    for fixture in fixtures:
        if fixture.name == name:
            return fixture
    return None


def get_fixtures_by_tag(tag: str) -> List[TestFixture]:
    """Get all test fixtures with a specific tag."""
    fixtures = create_test_fixtures()
    return [f for f in fixtures if f.tags and tag in f.tags]
