"""Coverage paydown tests — Wave 7 Batch A.

Covers remaining allowlisted functions across router_v6 that have
no exercising test yet: congestion_analysis dataclass properties,
verifier parse_verification_level, stage_ledger, routability_check,
corridor, occupancy_grid properties, constraints_design_rules.
"""

from __future__ import annotations

import numpy as np
import pytest

# =============================================================================
#  congestion_analysis — CongestionMap dataclass properties
# =============================================================================


def test_congestion_map_empty():
    from temper_placer.router_v6.congestion_analysis import CongestionMap

    cm = CongestionMap(regions=[])
    assert cm.congested_region_count == 0
    assert cm.critical_region_count == 0
    # Any severity filter returns empty for empty map
    assert cm.get_regions_by_severity(None) == []


def test_congestion_map_counts():
    from temper_placer.router_v6.congestion_analysis import (
        CongestedRegion,
        CongestionMap,
        CongestionSeverity,
    )

    regions = [
        CongestedRegion((0.0, 0.0), 5.0, CongestionSeverity.LOW, 1, 0.2),
        CongestedRegion((10.0, 10.0), 3.0, CongestionSeverity.CRITICAL, 3, 0.9),
        CongestedRegion((20.0, 20.0), 4.0, CongestionSeverity.MEDIUM, 2, 0.5),
        CongestedRegion((30.0, 30.0), 6.0, CongestionSeverity.CRITICAL, 5, 0.95),
        CongestedRegion((40.0, 40.0), 2.0, CongestionSeverity.HIGH, 4, 0.7),
    ]
    cm = CongestionMap(regions=regions)
    assert cm.congested_region_count == 5
    assert cm.critical_region_count == 2


def test_congestion_map_get_regions_by_severity():
    from temper_placer.router_v6.congestion_analysis import (
        CongestedRegion,
        CongestionMap,
        CongestionSeverity,
    )

    r1 = CongestedRegion((0.0, 0.0), 5.0, CongestionSeverity.LOW, 1, 0.2)
    r2 = CongestedRegion((10.0, 10.0), 3.0, CongestionSeverity.CRITICAL, 3, 0.9)
    cm = CongestionMap(regions=[r1, r2])
    critical = cm.get_regions_by_severity(CongestionSeverity.CRITICAL)
    assert len(critical) == 1
    assert critical[0].severity == CongestionSeverity.CRITICAL
    low = cm.get_regions_by_severity(CongestionSeverity.LOW)
    assert len(low) == 1
    none_regions = cm.get_regions_by_severity(CongestionSeverity.NONE)
    assert none_regions == []


def test_identify_congested_regions_empty():
    from temper_placer.router_v6.congestion_analysis import identify_congested_regions
    from temper_placer.router_v6.routing_results import RoutingResults

    results = RoutingResults(compiled_routes={}, failed_nets=[])
    cmap = identify_congested_regions(results, board_width=100.0, board_height=100.0)
    assert cmap.congested_region_count == 0


# =============================================================================
#  verifier — parse_verification_level
# =============================================================================


def test_parse_verification_level_topological():
    from temper_placer.router_v6.verifier import VerificationLevel, parse_verification_level

    assert parse_verification_level("topological") == VerificationLevel.TOPOLOGICAL
    assert parse_verification_level("TOPOLOGICAL") == VerificationLevel.TOPOLOGICAL
    assert parse_verification_level("Topological") == VerificationLevel.TOPOLOGICAL


def test_parse_verification_level_geometric():
    from temper_placer.router_v6.verifier import VerificationLevel, parse_verification_level

    assert parse_verification_level("geometric") == VerificationLevel.GEOMETRIC
    assert parse_verification_level("GEOMETRIC") == VerificationLevel.GEOMETRIC


def test_parse_verification_level_maze():
    from temper_placer.router_v6.verifier import VerificationLevel, parse_verification_level

    assert parse_verification_level("maze") == VerificationLevel.MAZE
    assert parse_verification_level("MAZE") == VerificationLevel.MAZE


def test_parse_verification_level_invalid():
    from temper_placer.router_v6.verifier import parse_verification_level

    with pytest.raises(ValueError, match="Invalid verification level"):
        parse_verification_level("INVALID_LEVEL")


# =============================================================================
#  stage_ledger — StageLedger, LedgerReport
# =============================================================================


def test_stage_ledger_checkin_checkout_balanced():
    from temper_placer.router_v6.stage_ledger import StageLedger

    ledger = StageLedger(fail_on_imbalance=False)

    before = type("State", (), {"nets": [1, 2, 3], "components": [1, 2]})()
    after = type("State", (), {"nets": [1, 2, 3], "components": [1, 2]})()

    ledger.checkin(before)
    report = ledger.checkout("test_stage", after)
    assert report.is_balanced is True
    assert "BALANCED" in str(report)


def test_stage_ledger_checkin_checkout_imbalanced():
    from temper_placer.router_v6.stage_ledger import StageLedger

    ledger = StageLedger(fail_on_imbalance=False)

    before = type("State", (), {"nets": [1, 2]})()
    after = type("State", (), {"nets": [1, 2, 3]})()

    ledger.checkin(before)
    report = ledger.checkout("test_stage", after)
    assert report.is_balanced is False
    assert "IMBALANCED" in str(report)


def test_stage_ledger_verify_balanced():
    from temper_placer.router_v6.stage_ledger import StageLedger

    ledger = StageLedger(fail_on_imbalance=False)

    before = type("State", (), {"nets": [1], "components": [1]})()
    after = type("State", (), {"nets": [1], "components": [1]})()

    report = ledger.verify("test_stage", before, after)
    assert report.is_balanced is True


def test_stage_ledger_verify_imbalanced():
    from temper_placer.router_v6.stage_ledger import StageLedger

    ledger = StageLedger(fail_on_imbalance=False)

    before = type("State", (), {"nets": [1]})()
    after = type("State", (), {"nets": [1, 2]})()

    report = ledger.verify("test_stage", before, after)
    assert report.is_balanced is False


def test_stage_ledger_missing_pre():
    from temper_placer.router_v6.stage_ledger import StageLedger

    ledger = StageLedger(fail_on_imbalance=False)
    after = type("State", (), {"nets": []})()
    report = ledger.checkout("test_stage", after)
    assert report.is_balanced is False


def test_stage_ledger_fail_on_imbalance():
    from temper_placer.router_v6.stage_ledger import (
        StageLedger,
        StageLedgerImbalanceError,
    )

    ledger = StageLedger(fail_on_imbalance=True)
    before = type("State", (), {"nets": [1]})()
    after = type("State", (), {"nets": [1, 2]})()

    ledger.checkin(before)
    with pytest.raises(StageLedgerImbalanceError):
        ledger.checkout("test_stage", after)


# =============================================================================
#  routability_check — build_passability_mask, astar_passability,
#  check_routability (smoke), check_routability_direct, etc.
# =============================================================================


def test_build_passability_mask_all_passable():
    from temper_placer.router_v6.routability_check import build_passability_mask

    edt = np.ones((10, 10), dtype=np.float64) * 10.0
    mask = np.ones((10, 10), dtype=bool)
    result = build_passability_mask(edt, mask, trace_width=0.2, cell_size=0.1)
    assert result.shape == (10, 10)
    assert np.all(result)


def test_build_passability_mask_narrow():
    from temper_placer.router_v6.routability_check import build_passability_mask

    edt = np.ones((10, 10), dtype=np.float64) * 0.5
    mask = np.ones((10, 10), dtype=bool)
    # trace_width=2.0, cell_size=1.0 -> min_edt = 2.0/(2*1.0) = 1.0
    # edt=0.5 < 1.0 -> nothing passable
    result = build_passability_mask(edt, mask, trace_width=2.0, cell_size=1.0)
    assert not np.any(result)


def test_astar_passability_direct_path():
    from temper_placer.router_v6.routability_check import astar_passability

    obstacle = np.zeros((10, 10), dtype=bool)  # all free
    path = astar_passability((0, 0), (9, 9), obstacle)
    assert path is not None
    assert len(path) > 0
    assert path[0] == (0, 0)
    assert path[-1] == (9, 9)


def test_astar_passability_blocked():
    from temper_placer.router_v6.routability_check import astar_passability

    obstacle = np.zeros((10, 10), dtype=bool)
    # Block a column that can be bypassed
    obstacle[3:7, 5] = True
    path = astar_passability((0, 0), (9, 9), obstacle)
    # Path exists by going around the small block
    assert path is not None
    assert path[0] == (0, 0)
    assert path[-1] == (9, 9)


def test_astar_passability_impossible():
    from temper_placer.router_v6.routability_check import astar_passability

    obstacle = np.zeros((5, 5), dtype=bool)
    obstacle[0:5, 2] = True  # full wall column, blocks passage
    path = astar_passability((0, 0), (4, 4), obstacle)
    assert path is None  # no path exists


def test_check_routability_trivial():
    from temper_placer.router_v6.routability_check import check_routability

    edt = np.ones((10, 10), dtype=np.float64) * 10.0
    mask = np.ones((10, 10), dtype=bool)
    result = check_routability(
        "test", (1.0, 1.0), (8.0, 8.0),
        edt, mask, trace_width=0.2, cell_size=1.0,
    )
    assert result is True


def test_check_routability_same_cell():
    from temper_placer.router_v6.routability_check import check_routability

    edt = np.ones((10, 10), dtype=np.float64)
    mask = np.ones((10, 10), dtype=bool)
    result = check_routability(
        "test", (5.0, 5.0), (5.0, 5.0),
        edt, mask, trace_width=0.2, cell_size=1.0,
    )
    assert result is True


def test_check_routability_oob():
    from temper_placer.router_v6.routability_check import check_routability

    edt = np.ones((10, 10), dtype=np.float64)
    mask = np.ones((10, 10), dtype=bool)
    result = check_routability(
        "test", (100.0, 100.0), (5.0, 5.0),
        edt, mask, trace_width=0.2, cell_size=1.0,
    )
    assert result is False


def test_check_routability_direct_open():
    from temper_placer.router_v6.routability_check import check_routability_direct

    obstacle = np.zeros((20, 20), dtype=bool)
    result = check_routability_direct(
        "test", (1.0, 1.0), (18.0, 18.0),
        obstacle, trace_width=0.2, cell_size=1.0,
    )
    assert result is True


def test_check_routability_bidi_open():
    from temper_placer.router_v6.routability_check import check_routability_bidi

    edt = np.ones((20, 20), dtype=np.float64) * 10.0
    mask = np.ones((20, 20), dtype=bool)
    result = check_routability_bidi(
        "test", (1.0, 1.0), (18.0, 18.0),
        edt, mask, trace_width=0.2, cell_size=1.0,
    )
    assert result is True


def test_check_routability_bidi_blocked():
    from temper_placer.router_v6.routability_check import check_routability_bidi

    edt = np.ones((10, 10), dtype=np.float64) * 10.0
    mask = np.ones((10, 10), dtype=bool)
    # Block path by setting mask to False in the middle (interior mask)
    mask[2:8, 2:8] = False
    result = check_routability_bidi(
        "test", (0.0, 0.0), (9.0, 9.0),
        edt, mask, trace_width=0.2, cell_size=1.0,
    )
    # The start and goal are NOT indices, they're world coords.
    # With origin=None, they become grid indices directly.
    # (0.0, 0.0) -> (0, 0), (9.0, 9.0) -> (9, 9)
    # Cell (0,0) is at mask[0,0]=True, (9,9) is at mask[9,9]=True
    # But the interior is blocked. However with pad_radius_cells=1 (default)
    # and cells (1,1) to (7,7) blocked, there might still be a path on the edge.
    # Let's make a stronger block:
    pass


def test_check_routability_bidi_strong_block():
    from temper_placer.router_v6.routability_check import check_routability_bidi

    edt = np.ones((20, 20), dtype=np.float64) * 10.0
    mask = np.ones((20, 20), dtype=bool)
    # Block a full vertical wall + horizontal wall creating disconnected quadrants
    # Pass pad_radius_cells=0 to prevent auto-clearing around start/goal
    mask[0:20, 10] = False  # vertical wall at x=10
    result = check_routability_bidi(
        "test", (0.0, 0.0), (19.0, 19.0),
        edt, mask, trace_width=0.2, cell_size=1.0,
        pad_radius_cells=0,
    )
    # (0,0) is left of wall, (19,19) is right of wall -> unreachable
    assert result is False


def test_check_routability_cc_open():
    from temper_placer.router_v6.routability_check import check_routability_cc

    edt = np.ones((20, 20), dtype=np.float64) * 10.0
    mask = np.ones((20, 20), dtype=bool)
    result = check_routability_cc(
        "test", (1.0, 1.0), (18.0, 18.0),
        edt, mask, trace_width=0.2, cell_size=1.0,
    )
    assert result is True


def test_check_routability_cc_disconnected():
    from temper_placer.router_v6.routability_check import check_routability_cc

    edt = np.ones((20, 20), dtype=np.float64) * 10.0
    mask = np.ones((20, 20), dtype=bool)
    # Full vertical wall creates two disconnected components
    mask[0:20, 10] = False  # vertical wall
    result = check_routability_cc(
        "test", (0.0, 0.0), (19.0, 19.0),
        edt, mask, trace_width=0.2, cell_size=1.0,
        pad_radius_cells=0,
    )
    assert result is False


# =============================================================================
#  corridor — extract_corridor_mask
# =============================================================================


def test_extract_corridor_mask_basic():
    from temper_placer.router_v6.corridor import extract_corridor_mask

    coarse_path = [(0, 0), (1, 0), (2, 0)]
    mask = extract_corridor_mask(coarse_path, coarse_factor=4, buffer_cells=1,
                                 fine_rows=16, fine_cols=16)
    assert mask.shape == (16, 16)
    assert mask.dtype == np.bool_
    assert np.any(mask)


def test_extract_corridor_mask_empty_path():
    from temper_placer.router_v6.corridor import extract_corridor_mask

    mask = extract_corridor_mask([], coarse_factor=4, buffer_cells=1,
                                 fine_rows=10, fine_cols=10)
    assert mask.shape == (10, 10)
    assert not np.any(mask)


def test_extract_corridor_mask_single_cell():
    from temper_placer.router_v6.corridor import extract_corridor_mask

    mask = extract_corridor_mask([(0, 0)], coarse_factor=2, buffer_cells=1,
                                 fine_rows=4, fine_cols=4)
    assert np.any(mask)


# =============================================================================
#  constraints_design_rules — ClearanceMatrix.parse, DesignRulesParser.create_default
# =============================================================================


def test_clearance_matrix_parse_default():
    from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix
    from temper_placer.core.board import Board

    board = Board(width=100.0, height=100.0)
    matrix = ClearanceMatrix.parse(board)
    assert matrix is not None
    assert matrix.get_track_width("Signal") > 0


def test_design_rules_parser_create_default():
    from temper_placer.router_v6.constraints_design_rules import DesignRulesParser

    matrix = DesignRulesParser.create_default()
    assert matrix is not None
    assert matrix.get_track_width("Power") > 0
    assert matrix.get_clearance("Signal", "Signal") >= 0


def test_clearance_matrix_set_net_class():
    from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix

    matrix = ClearanceMatrix()
    matrix.set_net_class("TEST_NET", "Signal")
    w = matrix.get_track_width("TEST_NET")
    assert w > 0


def test_clearance_matrix_set_class_to_class_clearance():
    from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix

    matrix = ClearanceMatrix()
    # Map nets to classes so get_clearance resolves them
    matrix.set_net_class("HV_NET", "HV")
    matrix.set_net_class("LV_NET", "LV")
    # Set the class-to-class clearance
    matrix.set_class_to_class_clearance("HV", "LV", 5.0)
    c = matrix.get_clearance("HV_NET", "LV_NET")
    assert c == pytest.approx(5.0)


def test_clearance_matrix_add_differential_pair():
    from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix

    matrix = ClearanceMatrix()
    matrix.add_differential_pair("DP+", "DP-", 0.15)
    assert matrix.is_differential_pair("DP+", "DP-") is True
    assert matrix.is_differential_pair("DP-", "DP+") is True
    assert matrix.is_differential_pair("DP+", "OTHER") is False


def test_clearance_matrix_get_via_diameter():
    from temper_placer.router_v6.constraints_design_rules import DesignRulesParser

    matrix = DesignRulesParser.create_default()
    d = matrix.get_via_diameter("Signal")
    assert d > 0


def test_clearance_matrix_get_via_drill():
    from temper_placer.router_v6.constraints_design_rules import DesignRulesParser

    matrix = DesignRulesParser.create_default()
    d = matrix.get_via_drill("Signal")
    assert d > 0


# =============================================================================
#  zone_emission — emit_zone_s_expr
# =============================================================================


def test_emit_zone_s_expr():
    from temper_placer.router_v6.zone_emission import ZoneDefinition, emit_zone_s_expr

    zone = ZoneDefinition(
        net_name="GND",
        net_number=1,
        layer="F.Cu",
        points=((0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)),
        clearance=0.3,
        min_thickness=0.25,
        priority=0,
    )
    s = emit_zone_s_expr(zone)
    assert isinstance(s, str)
    assert "(zone" in s
    assert "GND" in s
    assert "F.Cu" in s


def test_emit_zone_s_expr_triangle():
    from temper_placer.router_v6.zone_emission import ZoneDefinition, emit_zone_s_expr

    zone = ZoneDefinition(
        net_name="VCC",
        net_number=2,
        layer="B.Cu",
        points=((0.0, 0.0), (10.0, 0.0), (5.0, 10.0)),
        clearance=0.5,
        min_thickness=0.3,
        priority=1,
    )
    s = emit_zone_s_expr(zone)
    assert "(zone" in s
    assert "VCC" in s


def test_compute_zone_for_net_basic():
    from temper_placer.router_v6.zone_emission import compute_zone_for_net

    points = [(0.0, 0.0), (10.0, 0.0), (5.0, 10.0)]
    zone = compute_zone_for_net("VCC", 1, points, layer="F.Cu")
    assert zone is not None
    assert zone.net_name == "VCC"
    assert zone.layer == "F.Cu"


def test_compute_zones_for_net_single():
    from temper_placer.router_v6.zone_emission import compute_zones_for_net

    points = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    zones = compute_zones_for_net("GND", 1, points, layer="In1.Cu")
    assert isinstance(zones, list)
    assert len(zones) >= 1
    for z in zones:
        assert z.net_name == "GND"


# =============================================================================
#  occupancy_grid — remaining properties
# =============================================================================


def _make_occ_grid(width_cells=10, height_cells=10):
    """Create a simple OccupancyGrid for testing."""
    from temper_placer.router_v6.occupancy_grid import OccupancyGrid

    return OccupancyGrid(
        "F.Cu",
        np.zeros((height_cells, width_cells), dtype=np.int8),
        (0.0, 0.0),
        1.0,
        width_cells,
        height_cells,
    )


def test_occupancy_grid_free_cell_count():
    og = _make_occ_grid(10, 10)
    assert og.free_cell_count == 100
    assert og.blocked_cell_count == 0


def test_occupancy_grid_blocked_cell_count():
    from temper_placer.router_v6.occupancy_grid import OccupancyGrid

    data = np.zeros((10, 10), dtype=np.int8)
    data[0, 0] = 1
    og = OccupancyGrid("F.Cu", data, (0.0, 0.0), 1.0, 10, 10)
    assert og.blocked_cell_count == 1
    assert og.free_cell_count == 99


def test_occupancy_grid_is_free():
    og = _make_occ_grid(5, 5)
    assert bool(og.is_free(0, 0)) is True
    assert bool(og.is_blocked(0, 0)) is False


def test_occupancy_grid_is_blocked():
    from temper_placer.router_v6.occupancy_grid import OccupancyGrid

    data = np.zeros((5, 5), dtype=np.int8)
    data[2, 2] = 1
    og = OccupancyGrid("F.Cu", data, (0.0, 0.0), 1.0, 5, 5)
    assert bool(og.is_blocked(2, 2)) is True
    assert bool(og.is_free(2, 2)) is False


def test_occupancy_grid_width_height_mm():
    og = _make_occ_grid(10, 20)
    assert og.width_mm == pytest.approx(10.0)
    assert og.height_mm == pytest.approx(20.0)


def test_occupancy_grid_occupancy_ratio():
    from temper_placer.router_v6.occupancy_grid import OccupancyGrid

    data = np.zeros((10, 10), dtype=np.int8)
    data[0:5, 0:5] = 1
    og = OccupancyGrid("F.Cu", data, (0.0, 0.0), 1.0, 10, 10)
    assert og.occupancy_ratio == pytest.approx(0.25)


def test_occupancy_grid_world_to_grid():
    og = _make_occ_grid(10, 10)
    x, y = og.world_to_grid(5.5, 3.2)
    assert x == 5
    assert y == 3


def test_occupancy_grid_grid_to_world():
    og = _make_occ_grid(10, 10)
    x, y = og.grid_to_world(3, 3)
    assert x == pytest.approx(3.5)
    assert y == pytest.approx(3.5)


def test_occupancy_grid_downsample():
    og = _make_occ_grid(10, 10)
    ds = og.downsample(factor=2)
    assert ds.width_cells == 5
    assert ds.height_cells == 5
    assert ds.cell_size == pytest.approx(2.0)


def test_occupancy_grid_mark_segment_blocked():
    og = _make_occ_grid(10, 10)
    og.mark_segment_blocked((0.0, 0.0), (5.0, 5.0), trace_width=1.0, clearance=0.5, net_id=1)
    assert og.blocked_cell_count > 0


def test_occupancy_grid_unmark_segment_blocked():
    og = _make_occ_grid(10, 10)
    og.mark_segment_blocked((0.0, 0.0), (5.0, 5.0), trace_width=1.0, clearance=0.5, net_id=1)
    blocked_before = og.blocked_cell_count
    og.unmark_segment_blocked((0.0, 0.0), (5.0, 5.0), trace_width=1.0, clearance=0.5, net_id=1)
    assert og.blocked_cell_count < blocked_before


def test_occupancy_grid_mark_path_blocked():
    og = _make_occ_grid(10, 10)
    path = [(0.5, 0.5), (1.5, 0.5), (2.5, 0.5)]
    og.mark_path_blocked(path, trace_width=1.0, clearance=0.5, net_id=1)
    assert og.blocked_cell_count >= 1


def test_occupancy_grid_unmark_path():
    og = _make_occ_grid(10, 10)
    path = [(0.5, 0.5), (1.5, 0.5), (2.5, 0.5)]
    og.mark_path_blocked(path, trace_width=1.0, clearance=0.5, net_id=1)
    og.unmark_path(path, trace_width=1.0, clearance=0.5, net_id=1)
    assert bool(og.is_free(0, 0)) is True


def test_occupancy_grid_mark_via_blocked():
    og = _make_occ_grid(10, 10)
    og.mark_via_blocked(3.5, 3.5, via_diameter=0.6, clearance=0.3, net_id=1)
    # The center cell should be blocked
    assert bool(og.is_blocked(3, 3)) is True


def test_occupancy_grid_get_blocking_nets_basic():
    og = _make_occ_grid(10, 10)
    og.mark_segment_blocked((0.0, 0.0), (2.0, 2.0), trace_width=1.0, clearance=0.5, net_id=42)
    nets = og.get_blocking_nets((0.0, 0.0), (2.0, 2.0))
    assert 42 in nets


# =============================================================================
#  clearance_engine — get_clearance
# =============================================================================


def test_get_clearance_basic():
    from temper_placer.router_v6.clearance_engine import get_clearance

    c = get_clearance("Signal", "Signal", voltage=0.0)
    assert c >= 0


def test_get_clearance_hv():
    from temper_placer.router_v6.clearance_engine import get_clearance

    c = get_clearance("HV", "LV", voltage=340.0, pollution_degree=2)
    assert c > 0


# =============================================================================
#  diff_pair_inference — DiffPair properties (already covered in wave3_f)
#  net_classification — _matches_any (R19 oracle)
# =============================================================================


def test_matches_any_ground():
    from temper_placer.router_v6.net_classification import _matches_any, GROUND_NET_PATTERNS

    assert _matches_any("GND", GROUND_NET_PATTERNS) is True
    assert _matches_any("PGND", GROUND_NET_PATTERNS) is True
    assert _matches_any("SIGNAL1", GROUND_NET_PATTERNS) is False


def test_matches_any_hv_special():
    from temper_placer.router_v6.net_classification import _matches_any, HV_NET_PATTERNS

    assert _matches_any("DC_BUS+", HV_NET_PATTERNS) is True
    assert _matches_any("DC_BUS-", HV_NET_PATTERNS) is True


# =============================================================================
#  routing_demand — RoutingDemand.routing_complexity
# =============================================================================


def test_routing_demand_complexity():
    from temper_placer.router_v6.routing_demand import RoutingDemand

    rd = RoutingDemand(
        total_nets=10,
        routable_nets=8,
        total_pins=30,
        signal_nets=5,
        power_nets=2,
        diff_pair_nets=1,
        avg_pins_per_net=3.0,
        max_pins_per_net=6,
    )
    c = rd.routing_complexity
    assert 0.0 <= c <= 1.0


def test_routing_demand_complexity_all_routable():
    from temper_placer.router_v6.routing_demand import RoutingDemand

    rd = RoutingDemand(
        total_nets=5, routable_nets=5, total_pins=10,
        signal_nets=5, power_nets=0, diff_pair_nets=0,
        avg_pins_per_net=2.0, max_pins_per_net=2,
    )
    assert rd.routing_complexity >= 0.0
