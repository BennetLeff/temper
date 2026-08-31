"""Coverage paydown tests — Wave 7 Batch A.

Covers remaining allowlisted functions across router_v6 that have
no exercising test yet: verifier parse_verification_level, stage_ledger,
routability_check, corridor, occupancy_grid properties, constraints_design_rules.
"""

from __future__ import annotations

import numpy as np
import pytest

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
