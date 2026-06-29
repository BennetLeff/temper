"""
Unit tests for ZoneGeometryStage.

Tests the creation of 4 board zones (HV, Power, Signal, MCU) with correct proportions,
no overlaps, and full board coverage.
"""

from temper_placer.core.board import Board
from temper_placer.deterministic.stages.zone_geometry import ZoneGeometryStage
from temper_placer.deterministic.state import BoardState


def test_zone_geometry_creates_four_zones():
    """Verify that exactly 4 zones are created."""
    board = Board(width=100, height=100)
    initial_state = BoardState(board=board)

    stage = ZoneGeometryStage()
    result_state = stage.run(initial_state)

    assert len(result_state.zones) == 4
    zone_names = {z.name for z in result_state.zones}
    assert zone_names == {"HV", "Power", "Signal", "MCU"}


def test_zones_have_correct_proportions():
    """Verify HV=30%, Power=30%, Signal=30%, MCU=10% of board width."""
    board = Board(width=100, height=100)
    initial_state = BoardState(board=board)

    stage = ZoneGeometryStage()
    result_state = stage.run(initial_state)

    zones_by_name = {z.name: z for z in result_state.zones}

    # HV: 0 to 30
    hv = zones_by_name["HV"]
    assert hv.bounds == ((0, 0), (30, 100))

    # Power: 30 to 60
    power = zones_by_name["Power"]
    assert power.bounds == ((30, 0), (60, 100))

    # Signal: 60 to 90
    signal = zones_by_name["Signal"]
    assert signal.bounds == ((60, 0), (90, 100))

    # MCU: 90 to 100
    mcu = zones_by_name["MCU"]
    assert mcu.bounds == ((90, 0), (100, 100))


def test_zones_do_not_overlap():
    """Verify no geometric overlap between zones."""
    board = Board(width=100, height=100)
    initial_state = BoardState(board=board)

    stage = ZoneGeometryStage()
    result_state = stage.run(initial_state)

    zones = list(result_state.zones)

    for i, zone1 in enumerate(zones):
        for zone2 in zones[i+1:]:
            # Check if zones overlap
            (x1_min, y1_min), (x1_max, y1_max) = zone1.bounds
            (x2_min, y2_min), (x2_max, y2_max) = zone2.bounds

            # Zones overlap if they share interior points
            x_overlap = (x1_min < x2_max) and (x2_min < x1_max)
            y_overlap = (y1_min < y2_max) and (y2_min < y1_max)

            assert not (x_overlap and y_overlap), f"{zone1.name} overlaps with {zone2.name}"


def test_zones_cover_entire_board():
    """Verify union of all zones covers the entire board."""
    board = Board(width=100, height=100)
    initial_state = BoardState(board=board)

    stage = ZoneGeometryStage()
    result_state = stage.run(initial_state)

    # Check horizontal coverage: zones should span 0 to 100
    zones = sorted(result_state.zones, key=lambda z: z.bounds[0][0])

    # First zone should start at 0
    assert zones[0].bounds[0][0] == 0

    # Last zone should end at board width
    assert zones[-1].bounds[1][0] == 100

    # Check continuity: each zone's right edge should match next zone's left edge
    for i in range(len(zones) - 1):
        current_right = zones[i].bounds[1][0]
        next_left = zones[i+1].bounds[0][0]
        assert current_right == next_left, f"Gap between {zones[i].name} and {zones[i+1].name}"

    # All zones should span full height
    for zone in zones:
        assert zone.bounds[0][1] == 0
        assert zone.bounds[1][1] == 100


def test_zone_geometry_with_different_board_sizes():
    """Verify proportions are maintained for different board sizes."""
    for width, height in [(50, 50), (150, 100), (200, 150)]:
        board = Board(width=width, height=height)
        initial_state = BoardState(board=board)

        stage = ZoneGeometryStage()
        result_state = stage.run(initial_state)

        zones_by_name = {z.name: z for z in result_state.zones}

        # Verify proportions
        hv_width = zones_by_name["HV"].bounds[1][0] - zones_by_name["HV"].bounds[0][0]
        assert abs(hv_width - width * 0.3) < 0.01

        power_width = zones_by_name["Power"].bounds[1][0] - zones_by_name["Power"].bounds[0][0]
        assert abs(power_width - width * 0.3) < 0.01

        signal_width = zones_by_name["Signal"].bounds[1][0] - zones_by_name["Signal"].bounds[0][0]
        assert abs(signal_width - width * 0.3) < 0.01

        mcu_width = zones_by_name["MCU"].bounds[1][0] - zones_by_name["MCU"].bounds[0][0]
        assert abs(mcu_width - width * 0.1) < 0.01
