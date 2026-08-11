"""Coverage paydown v14: deterministic state, router_v6 congestion, clearance,
routability, routing_space, congestion_analysis, capacity_check, congestion_tensor.

Targets allowlist entries across:
- deterministic/state.py (4): BoardState.with_locked_route, with_locked_routes,
  is_route_locked, with_config
- deterministic/__init__.py (1): SidecarAwarePipeline.record_sidecar_load
- router_v6/capacity_check.py (2): CapacityDemandReport.at_risk_count, safe_count
- router_v6/congestion_analysis.py (3): CongestionMap.congested_region_count,
  critical_region_count, get_regions_by_severity
- router_v6/congestion.py (9): CongestionGrid.from_board, get_utilization,
  get_overflow, Bottleneck.to_coordinates, CongestionResult.is_feasible,
  overflow_ratio, get_top_bottlenecks, analyze_congestion, estimate_net_demand
- router_v6/routing_space.py (2): RoutingSpace.utilization_ratio, available_ratio
- router_v6/routability_check.py (6): build_passability_mask, check_routability,
  check_routability_bidi, check_routability_cc, check_routability_direct,
  astar_passability
- router_v6/congestion_tensor.py (6): CongestionTensor.cost, decay, increment,
  increment_path, reset, zeros
- router_v6/clearance_engine.py (2): calculate_safety_distances, get_clearance
"""

from __future__ import annotations

import numpy as np
from shapely.geometry import MultiPolygon


# ===========================================================================
# deterministic/state.py
# ===========================================================================


class TestBoardStateRouteLocking:
    """Covers BoardState.with_locked_route, with_locked_routes, is_route_locked."""

    def test_is_route_locked_default(self):
        from temper_placer.deterministic.state import BoardState

        bs = BoardState()
        assert bs.is_route_locked("NET1") is False
        assert bs.is_route_locked("") is False

    def test_with_locked_route_single(self):
        from temper_placer.deterministic.state import BoardState

        bs = BoardState()
        bs2 = bs.with_locked_route("NET1")
        # Mutated copy
        assert bs2.is_route_locked("NET1") is True
        # Original unchanged (immutability)
        assert bs.is_route_locked("NET1") is False

    def test_with_locked_route_multiple_calls(self):
        from temper_placer.deterministic.state import BoardState

        bs = BoardState()
        bs2 = bs.with_locked_route("NET1")
        bs3 = bs2.with_locked_route("NET2")
        assert bs3.is_route_locked("NET1") is True
        assert bs3.is_route_locked("NET2") is True
        assert bs3.is_route_locked("NET3") is False
        # bs2 unchanged
        assert bs2.is_route_locked("NET1") is True
        assert bs2.is_route_locked("NET2") is False

    def test_with_locked_routes(self):
        from temper_placer.deterministic.state import BoardState

        bs = BoardState()
        bs2 = bs.with_locked_routes({"A", "B", "C"})
        assert bs2.is_route_locked("A") is True
        assert bs2.is_route_locked("B") is True
        assert bs2.is_route_locked("C") is True
        assert bs2.is_route_locked("D") is False

    def test_with_locked_routes_empty_set(self):
        from temper_placer.deterministic.state import BoardState

        bs = BoardState()
        bs2 = bs.with_locked_routes(set())
        # No change when empty set is added
        assert bs2.locked_routes == bs.locked_routes

    def test_with_locked_route_idempotent(self):
        from temper_placer.deterministic.state import BoardState

        bs = BoardState()
        bs2 = bs.with_locked_route("NET1")
        bs3 = bs2.with_locked_route("NET1")
        assert bs3.is_route_locked("NET1") is True
        # frozenset dedup: size still 1
        assert len(bs3.locked_routes) == 1

    def test_with_config(self):
        from temper_placer.deterministic.state import BoardState

        bs = BoardState()
        bs2 = bs.with_config({"key": "value"})
        assert bs2.config == {"key": "value"}
        # Original unchanged
        assert bs.config is None

    def test_with_config_none(self):
        from temper_placer.deterministic.state import BoardState

        bs = BoardState()
        bs2 = bs.with_config(None)
        assert bs2.config is None

    def test_with_config_overwrite(self):
        from temper_placer.deterministic.state import BoardState

        bs = BoardState()
        bs2 = bs.with_config({"a": 1})
        bs3 = bs2.with_config({"b": 2})
        assert bs3.config == {"b": 2}


# ===========================================================================
# deterministic/__init__.py
# ===========================================================================


class TestSidecarAwarePipeline:
    """Covers SidecarAwarePipeline.record_sidecar_load."""

    def test_record_sidecar_load_increments(self):
        from temper_placer.deterministic import SidecarAwarePipeline

        p = SidecarAwarePipeline()
        assert p.record_sidecar_load() == 1
        assert p.record_sidecar_load() == 2
        assert p.record_sidecar_load() == 3

    def test_record_sidecar_load_per_instance(self):
        from temper_placer.deterministic import SidecarAwarePipeline

        p1 = SidecarAwarePipeline()
        p2 = SidecarAwarePipeline()
        assert p1.record_sidecar_load() == 1
        assert p1.record_sidecar_load() == 2
        # p2 is independent
        assert p2.record_sidecar_load() == 1


# ===========================================================================
# router_v6/capacity_check.py
# ===========================================================================


class TestCapacityDemandReport:
    """Covers CapacityDemandReport.at_risk_count, safe_count."""

    def test_at_risk_count(self):
        from temper_placer.router_v6.capacity_check import CapacityDemandReport

        r = CapacityDemandReport(
            ratios={},
            at_risk_nets=["N1", "N2"],
            safe_nets=["N3"],
        )
        assert r.at_risk_count == 2

    def test_safe_count(self):
        from temper_placer.router_v6.capacity_check import CapacityDemandReport

        r = CapacityDemandReport(
            ratios={},
            at_risk_nets=["N1"],
            safe_nets=["N3", "N4", "N5"],
        )
        assert r.safe_count == 3

    def test_empty(self):
        from temper_placer.router_v6.capacity_check import CapacityDemandReport

        r = CapacityDemandReport(ratios={}, at_risk_nets=[], safe_nets=[])
        assert r.at_risk_count == 0
        assert r.safe_count == 0


# ===========================================================================
# router_v6/congestion_analysis.py
# ===========================================================================


class TestCongestionMap:
    """Covers CongestionMap.congested_region_count, critical_region_count,
    get_regions_by_severity."""

    def test_congested_region_count(self):
        from temper_placer.router_v6.congestion_analysis import (
            CongestedRegion,
            CongestionMap,
            CongestionSeverity,
        )

        regions = [
            CongestedRegion((0, 0), 1.0, CongestionSeverity.LOW, 0, 0.1),
            CongestedRegion((10, 10), 2.0, CongestionSeverity.HIGH, 2, 0.5),
        ]
        cm = CongestionMap(regions=regions)
        assert cm.congested_region_count == 2

    def test_congested_region_count_empty(self):
        from temper_placer.router_v6.congestion_analysis import CongestionMap

        cm = CongestionMap(regions=[])
        assert cm.congested_region_count == 0

    def test_critical_region_count(self):
        from temper_placer.router_v6.congestion_analysis import (
            CongestedRegion,
            CongestionMap,
            CongestionSeverity,
        )

        regions = [
            CongestedRegion((0, 0), 1.0, CongestionSeverity.CRITICAL, 3, 0.9),
            CongestedRegion((10, 10), 2.0, CongestionSeverity.CRITICAL, 1, 0.8),
            CongestedRegion((20, 20), 1.5, CongestionSeverity.HIGH, 2, 0.5),
            CongestedRegion((30, 30), 1.0, CongestionSeverity.LOW, 0, 0.2),
        ]
        cm = CongestionMap(regions=regions)
        assert cm.critical_region_count == 2

    def test_critical_region_count_none(self):
        from temper_placer.router_v6.congestion_analysis import (
            CongestedRegion,
            CongestionMap,
            CongestionSeverity,
        )

        regions = [
            CongestedRegion((0, 0), 1.0, CongestionSeverity.LOW, 0, 0.1),
        ]
        cm = CongestionMap(regions=regions)
        assert cm.critical_region_count == 0

    def test_get_regions_by_severity(self):
        from temper_placer.router_v6.congestion_analysis import (
            CongestedRegion,
            CongestionMap,
            CongestionSeverity,
        )

        r_crit1 = CongestedRegion((0, 0), 1.0, CongestionSeverity.CRITICAL, 2, 0.9)
        r_crit2 = CongestedRegion((10, 10), 1.0, CongestionSeverity.CRITICAL, 1, 0.85)
        r_high = CongestedRegion((20, 20), 2.0, CongestionSeverity.HIGH, 0, 0.4)
        cm = CongestionMap(regions=[r_crit1, r_crit2, r_high])

        critical_regions = cm.get_regions_by_severity(CongestionSeverity.CRITICAL)
        assert len(critical_regions) == 2

        high_regions = cm.get_regions_by_severity(CongestionSeverity.HIGH)
        assert len(high_regions) == 1

        low_regions = cm.get_regions_by_severity(CongestionSeverity.LOW)
        assert len(low_regions) == 0

        none_regions = cm.get_regions_by_severity(CongestionSeverity.NONE)
        assert len(none_regions) == 0


# ===========================================================================
# router_v6/congestion.py
# ===========================================================================


class TestCongestionGrid:
    """Covers CongestionGrid.from_board, get_utilization, get_overflow."""

    def test_from_board_basic(self):
        from temper_placer.core.board import Board
        from temper_placer.router_v6.congestion import CongestionGrid

        b = Board(width=100.0, height=100.0)
        g = CongestionGrid.from_board(b, cell_size_mm=1.0)
        assert g.width_cells == 100
        assert g.height_cells == 100
        assert g.num_layers == 1
        assert g.origin == (0.0, 0.0)

    def test_from_board_multi_layer(self):
        from temper_placer.core.board import Board
        from temper_placer.router_v6.congestion import CongestionGrid

        b = Board(width=80.0, height=60.0, origin=(10.0, 20.0))
        g = CongestionGrid.from_board(b, cell_size_mm=2.0, num_layers=4)
        assert g.width_cells == 40
        assert g.height_cells == 30
        assert g.num_layers == 4
        assert g.origin == (10.0, 20.0)

    def test_from_board_defaults(self):
        from temper_placer.core.board import Board
        from temper_placer.router_v6.congestion import CongestionGrid

        b = Board(width=50.0, height=50.0)
        g = CongestionGrid.from_board(b)
        assert g.cell_size_mm == 1.0
        assert g.num_layers == 1

    def test_get_utilization_all_zero_demand(self):
        from temper_placer.core.board import Board
        from temper_placer.router_v6.congestion import CongestionGrid

        b = Board(width=100.0, height=100.0)
        g = CongestionGrid.from_board(b, cell_size_mm=1.0)
        u = g.get_utilization()
        # Zero demand / supply = 0
        assert float(u.max()) == 0.0

    def test_get_overflow_all_zero(self):
        from temper_placer.core.board import Board
        from temper_placer.router_v6.congestion import CongestionGrid

        b = Board(width=100.0, height=100.0)
        g = CongestionGrid.from_board(b, cell_size_mm=1.0)
        o = g.get_overflow()
        assert float(o.max()) == 0.0

    def test_get_utilization_shape_2d(self):
        from temper_placer.core.board import Board
        from temper_placer.router_v6.congestion import CongestionGrid

        b = Board(width=50.0, height=40.0)
        g = CongestionGrid.from_board(b, cell_size_mm=1.0, num_layers=1)
        u = g.get_utilization()
        assert u.ndim == 2
        assert u.shape == (40, 50)

    def test_get_utilization_shape_3d(self):
        from temper_placer.core.board import Board
        from temper_placer.router_v6.congestion import CongestionGrid

        b = Board(width=50.0, height=40.0)
        g = CongestionGrid.from_board(b, cell_size_mm=1.0, num_layers=2)
        u = g.get_utilization()
        assert u.ndim == 3
        assert u.shape == (2, 40, 50)


class TestBottleneck:
    """Covers Bottleneck.to_coordinates."""

    def test_to_coordinates_defaults(self):
        from temper_placer.router_v6.congestion import Bottleneck

        bn = Bottleneck(x=5, y=3, utilization=1.5, overflow=0.5, layer=0)
        cx, cy = bn.to_coordinates()
        # Default cell_size=1.0, origin=(0,0) -> cell center at 0.5 offset
        assert cx == 5.5
        assert cy == 3.5

    def test_to_coordinates_custom_origin(self):
        from temper_placer.router_v6.congestion import Bottleneck

        bn = Bottleneck(x=2, y=4, utilization=2.0, overflow=1.0, layer=1)
        cx, cy = bn.to_coordinates(cell_size_mm=2.0, origin=(10.0, 20.0))
        # x = origin_x + (cell_x + 0.5) * cell_size = 10 + 2.5*2 = 15.0
        assert cx == 15.0
        # y = 20 + 4.5*2 = 29.0
        assert cy == 29.0


class TestCongestionResult:
    """Covers CongestionResult.is_feasible, overflow_ratio, get_top_bottlenecks."""

    def test_is_feasible_below_threshold(self):
        from temper_placer.core.board import Board
        from temper_placer.router_v6.congestion import CongestionGrid, CongestionResult

        b = Board(width=100.0, height=100.0)
        g = CongestionGrid.from_board(b, cell_size_mm=1.0)
        r = CongestionResult(grid=g, max_utilization=0.5)
        assert r.is_feasible() is True

    def test_is_feasible_above_threshold(self):
        from temper_placer.core.board import Board
        from temper_placer.router_v6.congestion import CongestionGrid, CongestionResult

        b = Board(width=100.0, height=100.0)
        g = CongestionGrid.from_board(b, cell_size_mm=1.0)
        r = CongestionResult(grid=g, max_utilization=1.5)
        assert r.is_feasible() is False

    def test_is_feasible_at_threshold(self):
        from temper_placer.core.board import Board
        from temper_placer.router_v6.congestion import CongestionGrid, CongestionResult

        b = Board(width=100.0, height=100.0)
        g = CongestionGrid.from_board(b, cell_size_mm=1.0)
        r = CongestionResult(grid=g, max_utilization=1.0)
        # <= threshold means feasible (1.0 <= 1.0)
        assert r.is_feasible() is True

    def test_is_feasible_custom_threshold(self):
        from temper_placer.core.board import Board
        from temper_placer.router_v6.congestion import CongestionGrid, CongestionResult

        b = Board(width=100.0, height=100.0)
        g = CongestionGrid.from_board(b, cell_size_mm=1.0)
        r = CongestionResult(grid=g, max_utilization=0.8)
        assert r.is_feasible(threshold=0.7) is False
        assert r.is_feasible(threshold=0.8) is True

    def test_overflow_ratio_zero_demand(self):
        from temper_placer.core.board import Board
        from temper_placer.router_v6.congestion import CongestionGrid, CongestionResult

        b = Board(width=100.0, height=100.0)
        g = CongestionGrid.from_board(b, cell_size_mm=1.0)
        r = CongestionResult(grid=g, total_overflow=5.0)
        # Zero demand => ratio is 0
        assert r.overflow_ratio() == 0.0

    def test_get_top_bottlenecks(self):
        from temper_placer.core.board import Board
        from temper_placer.router_v6.congestion import (
            Bottleneck,
            CongestionGrid,
            CongestionResult,
        )

        b = Board(width=100.0, height=100.0)
        g = CongestionGrid.from_board(b, cell_size_mm=1.0)
        bn_list = [
            Bottleneck(x=1, y=1, utilization=0.9, overflow=0.3, layer=0),
            Bottleneck(x=2, y=2, utilization=1.2, overflow=1.0, layer=0),
            Bottleneck(x=3, y=3, utilization=1.5, overflow=2.0, layer=0),
            Bottleneck(x=4, y=4, utilization=0.8, overflow=0.1, layer=0),
            Bottleneck(x=5, y=5, utilization=1.1, overflow=0.7, layer=0),
        ]
        r = CongestionResult(grid=g, bottlenecks=bn_list)
        top = r.get_top_bottlenecks(3)
        assert len(top) == 3
        # Sorted by overflow descending
        assert [b.overflow for b in top] == [2.0, 1.0, 0.7]

    def test_get_top_bottlenecks_more_than_available(self):
        from temper_placer.core.board import Board
        from temper_placer.router_v6.congestion import (
            Bottleneck,
            CongestionGrid,
            CongestionResult,
        )

        b = Board(width=100.0, height=100.0)
        g = CongestionGrid.from_board(b, cell_size_mm=1.0)
        bn_list = [
            Bottleneck(x=0, y=0, utilization=0.5, overflow=0.1, layer=0),
        ]
        r = CongestionResult(grid=g, bottlenecks=bn_list)
        top = r.get_top_bottlenecks(10)
        assert len(top) == 1

    def test_get_top_bottlenecks_empty(self):
        from temper_placer.core.board import Board
        from temper_placer.router_v6.congestion import CongestionGrid, CongestionResult

        b = Board(width=100.0, height=100.0)
        g = CongestionGrid.from_board(b, cell_size_mm=1.0)
        r = CongestionResult(grid=g, bottlenecks=[])
        top = r.get_top_bottlenecks(5)
        assert top == []


class TestEstimateNetDemand:
    """Covers estimate_net_demand."""

    def test_single_pin_no_change(self):
        from temper_placer.core.board import Board
        from temper_placer.router_v6.congestion import CongestionGrid, estimate_net_demand

        b = Board(width=100.0, height=100.0)
        g = CongestionGrid.from_board(b, cell_size_mm=1.0)
        g2 = estimate_net_demand(g, [(10.0, 10.0)])
        # Single pin -> identity return
        assert g2 is g

    def test_two_pins_updates_grid(self):
        from temper_placer.core.board import Board
        from temper_placer.router_v6.congestion import CongestionGrid, estimate_net_demand

        b = Board(width=100.0, height=100.0)
        g = CongestionGrid.from_board(b, cell_size_mm=1.0)
        g2 = estimate_net_demand(g, [(10.0, 10.0), (30.0, 30.0)])
        # Should return a new grid (not identity)
        assert g2 is not g
        # Some demand should be added
        assert g2.demand.max() > 0


class TestAnalyzeCongestion:
    """Covers analyze_congestion."""

    def test_analyze_congestion_simple(self):
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Net, Netlist, Pin
        from temper_placer.router_v6.congestion import analyze_congestion

        p1 = Pin(name="1", number="1", position=(0.0, 0.0))
        p2 = Pin(name="2", number="2", position=(5.0, 0.0))
        c1 = Component(
            ref="U1",
            footprint="SOIC8",
            pins=[p1, p2],
            initial_position=(10.0, 10.0),
            bounds=(5.0, 5.0),
        )
        net = Net(name="N1", pins=[("U1", "1"), ("U1", "2")])
        nl = Netlist(components=[c1], nets=[net])
        b = Board(width=100.0, height=100.0)

        result = analyze_congestion(nl, b)
        assert result.max_utilization <= 1.0
        assert result.is_feasible() is True

    def test_analyze_congestion_empty_netlist(self):
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Netlist
        from temper_placer.router_v6.congestion import analyze_congestion

        nl = Netlist(components=[], nets=[])
        b = Board(width=100.0, height=100.0)
        result = analyze_congestion(nl, b)
        assert result.max_utilization == 0.0
        assert len(result.bottlenecks) == 0

    def test_analyze_congestion_returns_result_type(self):
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Net, Netlist, Pin
        from temper_placer.router_v6.congestion import CongestionResult, analyze_congestion

        c1 = Component(
            ref="U1",
            footprint="DIP8",
            pins=[Pin("1", "1", (0, 0)), Pin("2", "2", (5, 0))],
            initial_position=(10.0, 10.0),
            bounds=(5.0, 5.0),
        )
        net = Net(name="N1", pins=[("U1", "1"), ("U1", "2")])
        nl = Netlist(components=[c1], nets=[net])
        b = Board(width=100.0, height=100.0)
        result = analyze_congestion(nl, b)
        assert isinstance(result, CongestionResult)
        assert result.grid is not None


# ===========================================================================
# router_v6/routing_space.py
# ===========================================================================


class TestRoutingSpace:
    """Covers RoutingSpace.utilization_ratio, available_ratio."""

    def test_utilization_ratio_normal(self):
        from temper_placer.router_v6.routing_space import RoutingSpace

        rs = RoutingSpace(
            layer_name="F.Cu",
            available_area=MultiPolygon(),
            total_area=100.0,
            obstacle_area=30.0,
            routing_area=70.0,
        )
        assert rs.utilization_ratio == 0.3

    def test_utilization_ratio_zero_obstacles(self):
        from temper_placer.router_v6.routing_space import RoutingSpace

        rs = RoutingSpace(
            layer_name="F.Cu",
            available_area=MultiPolygon(),
            total_area=100.0,
            obstacle_area=0.0,
            routing_area=100.0,
        )
        assert rs.utilization_ratio == 0.0

    def test_utilization_ratio_zero_total(self):
        from temper_placer.router_v6.routing_space import RoutingSpace

        rs = RoutingSpace(
            layer_name="F.Cu",
            available_area=MultiPolygon(),
            total_area=0.0,
            obstacle_area=10.0,
            routing_area=0.0,
        )
        # Zero total area -> returns 0.0
        assert rs.utilization_ratio == 0.0

    def test_available_ratio_normal(self):
        from temper_placer.router_v6.routing_space import RoutingSpace

        rs = RoutingSpace(
            layer_name="B.Cu",
            available_area=MultiPolygon(),
            total_area=200.0,
            obstacle_area=50.0,
            routing_area=150.0,
        )
        assert rs.available_ratio == 0.75

    def test_available_ratio_full(self):
        from temper_placer.router_v6.routing_space import RoutingSpace

        rs = RoutingSpace(
            layer_name="F.Cu",
            available_area=MultiPolygon(),
            total_area=100.0,
            obstacle_area=0.0,
            routing_area=100.0,
        )
        assert rs.available_ratio == 1.0

    def test_available_ratio_zero_total(self):
        from temper_placer.router_v6.routing_space import RoutingSpace

        rs = RoutingSpace(
            layer_name="F.Cu",
            available_area=MultiPolygon(),
            total_area=0.0,
            obstacle_area=0.0,
            routing_area=0.0,
        )
        assert rs.available_ratio == 0.0


# ===========================================================================
# router_v6/routability_check.py
# ===========================================================================


class TestBuildPassabilityMask:
    """Covers build_passability_mask."""

    def test_all_passable(self):
        from temper_placer.router_v6.routability_check import build_passability_mask

        edt = np.ones((10, 10), dtype=np.float64)
        mask = np.ones((10, 10), dtype=bool)
        pm = build_passability_mask(edt, mask, trace_width=0.2, cell_size=0.1)
        assert pm.shape == (10, 10)
        assert pm.all()

    def test_narrow_trace_on_thin_edt(self):
        from temper_placer.router_v6.routability_check import build_passability_mask

        edt = np.full((10, 10), 0.5, dtype=np.float64)
        mask = np.ones((10, 10), dtype=bool)
        # width = 2 * edt * cell_size; with edt=0.5, cell=0.1 -> width=0.1
        pm = build_passability_mask(edt, mask, trace_width=0.2, cell_size=0.1)
        # min_edt = 0.2 / 0.2 = 1.0; edt=0.5 < 1.0 -> not passable
        assert not pm.any()

    def test_mask_filters(self):
        from temper_placer.router_v6.routability_check import build_passability_mask

        edt = np.ones((5, 5), dtype=np.float64)
        mask = np.zeros((5, 5), dtype=bool)
        mask[2, 2] = True
        pm = build_passability_mask(edt, mask, trace_width=0.1, cell_size=0.1)
        assert bool(pm[2, 2]) is True
        assert bool(pm[0, 0]) is False


class TestCheckRoutability:
    """Covers check_routability."""

    def test_open_grid_reachable(self):
        from temper_placer.router_v6.routability_check import check_routability

        edt = np.ones((20, 20), dtype=np.float64)
        mask = np.ones((20, 20), dtype=bool)
        result = check_routability(
            "test", (2, 2), (18, 18), edt, mask, trace_width=0.2, cell_size=0.1
        )
        assert result is True

    def test_same_cell(self):
        from temper_placer.router_v6.routability_check import check_routability

        edt = np.ones((10, 10), dtype=np.float64)
        mask = np.ones((10, 10), dtype=bool)
        result = check_routability(
            "test", (5, 5), (5, 5), edt, mask, trace_width=0.2, cell_size=0.1
        )
        assert result is True

    def test_out_of_bounds_start(self):
        from temper_placer.router_v6.routability_check import check_routability

        edt = np.ones((10, 10), dtype=np.float64)
        mask = np.ones((10, 10), dtype=bool)
        result = check_routability(
            "test", (-1, 0), (5, 5), edt, mask, trace_width=0.2, cell_size=0.1
        )
        assert result is False

    def test_out_of_bounds_goal(self):
        from temper_placer.router_v6.routability_check import check_routability

        edt = np.ones((10, 10), dtype=np.float64)
        mask = np.ones((10, 10), dtype=bool)
        result = check_routability(
            "test", (2, 2), (15, 5), edt, mask, trace_width=0.2, cell_size=0.1
        )
        assert result is False

    def test_blocked_by_narrow_channels(self):
        from temper_placer.router_v6.routability_check import check_routability

        # EDT with very thin channels
        edt = np.ones((10, 10), dtype=np.float64) * 0.1
        mask = np.ones((10, 10), dtype=bool)
        result = check_routability(
            "test", (1, 1), (8, 8), edt, mask, trace_width=0.5, cell_size=0.1
        )
        # min_edt = 0.5/0.2 = 2.5; edt=0.1 < 2.5 -> impassable
        assert result is False

    def test_with_origin(self):
        from temper_placer.router_v6.routability_check import check_routability

        # Grid is 10x10 with cell_size=1.0, origin=(10.0, 20.0)
        # So grid covers x in [10.0, 20.0), y in [20.0, 30.0)
        edt = np.ones((20, 20), dtype=np.float64)
        mask = np.ones((20, 20), dtype=bool)
        result = check_routability(
            "test",
            (10.5, 20.5),  # world: grid index (0, 0) after rounding
            (15.5, 25.5),  # world: grid index (5, 5)
            edt,
            mask,
            trace_width=0.2,
            cell_size=1.0,
            origin=(10.0, 20.0),  # grid[0,0] maps to world (10.0, 20.0)
        )
        assert result is True


class TestCheckRoutabilityBidi:
    """Covers check_routability_bidi."""

    def test_open_grid_reachable(self):
        from temper_placer.router_v6.routability_check import check_routability_bidi

        edt = np.ones((20, 20), dtype=np.float64)
        mask = np.ones((20, 20), dtype=bool)
        result = check_routability_bidi(
            "test", (2, 2), (18, 18), edt, mask, trace_width=0.2, cell_size=0.1
        )
        assert result is True

    def test_same_cell(self):
        from temper_placer.router_v6.routability_check import check_routability_bidi

        edt = np.ones((10, 10), dtype=np.float64)
        mask = np.ones((10, 10), dtype=bool)
        result = check_routability_bidi(
            "test", (3, 3), (3, 3), edt, mask, trace_width=0.2, cell_size=0.1
        )
        assert result is True

    def test_out_of_bounds(self):
        from temper_placer.router_v6.routability_check import check_routability_bidi

        edt = np.ones((10, 10), dtype=np.float64)
        mask = np.ones((10, 10), dtype=bool)
        result = check_routability_bidi(
            "test", (20, 5), (5, 5), edt, mask, trace_width=0.2, cell_size=0.1
        )
        assert result is False

    def test_blocked_by_wall(self):
        from temper_placer.router_v6.routability_check import check_routability_bidi

        edt = np.ones((10, 10), dtype=np.float64)
        mask = np.ones((10, 10), dtype=bool)
        # Block a vertical wall separating left and right
        mask[:, 5] = False
        result = check_routability_bidi(
            "test", (2, 2), (8, 8), edt, mask, trace_width=0.1, cell_size=0.1
        )
        assert result is False


class TestCheckRoutabilityCC:
    """Covers check_routability_cc."""

    def test_open_grid_reachable(self):
        from temper_placer.router_v6.routability_check import check_routability_cc

        edt = np.ones((20, 20), dtype=np.float64)
        mask = np.ones((20, 20), dtype=bool)
        result = check_routability_cc(
            "test", (2, 2), (18, 18), edt, mask, trace_width=0.2, cell_size=0.1
        )
        assert result is True

    def test_same_cell(self):
        from temper_placer.router_v6.routability_check import check_routability_cc

        edt = np.ones((10, 10), dtype=np.float64)
        mask = np.ones((10, 10), dtype=bool)
        result = check_routability_cc(
            "test", (4, 4), (4, 4), edt, mask, trace_width=0.2, cell_size=0.1
        )
        assert result is True

    def test_out_of_bounds(self):
        from temper_placer.router_v6.routability_check import check_routability_cc

        edt = np.ones((10, 10), dtype=np.float64)
        mask = np.ones((10, 10), dtype=bool)
        result = check_routability_cc(
            "test", (-5, 5), (5, 5), edt, mask, trace_width=0.2, cell_size=0.1
        )
        assert result is False

    def test_disconnected_regions(self):
        from temper_placer.router_v6.routability_check import check_routability_cc

        edt = np.ones((10, 10), dtype=np.float64)
        mask = np.ones((10, 10), dtype=bool)
        # Block the middle completely
        mask[:, 5] = False
        result = check_routability_cc(
            "test", (2, 2), (8, 8), edt, mask, trace_width=0.1, cell_size=0.1
        )
        assert result is False


class TestCheckRoutabilityDirect:
    """Covers check_routability_direct."""

    def test_open_grid(self):
        from temper_placer.router_v6.routability_check import check_routability_direct

        obs = np.zeros((20, 20), dtype=bool)
        result = check_routability_direct(
            "test", (2, 2), (18, 18), obs, trace_width=0.2, cell_size=0.1
        )
        assert result is True

    def test_blocked(self):
        from temper_placer.router_v6.routability_check import check_routability_direct

        obs = np.zeros((10, 10), dtype=bool)
        # Block a wall
        obs[:, 5] = True
        result = check_routability_direct(
            "test", (2, 2), (8, 8), obs, trace_width=0.1, cell_size=0.1
        )
        assert result is False


class TestAstarPassability:
    """Covers astar_passability."""

    def test_finds_path_open_grid(self):
        from temper_placer.router_v6.routability_check import astar_passability

        obs = np.zeros((20, 20), dtype=bool)
        path = astar_passability((2, 2), (18, 18), obs)
        assert path is not None
        assert len(path) > 0
        assert path[0] == (2, 2)
        assert path[-1] == (18, 18)

    def test_no_path_blocked(self):
        from temper_placer.router_v6.routability_check import astar_passability

        obs = np.zeros((10, 10), dtype=bool)
        obs[:, 5] = True
        path = astar_passability((2, 2), (8, 8), obs)
        assert path is None

    def test_same_cell(self):
        from temper_placer.router_v6.routability_check import astar_passability

        obs = np.zeros((10, 10), dtype=bool)
        path = astar_passability((5, 5), (5, 5), obs)
        assert path is not None
        assert path == [(5, 5)]


# ===========================================================================
# router_v6/congestion_tensor.py
# ===========================================================================


class TestCongestionTensor:
    """Covers CongestionTensor.zeros, cost, decay, increment, increment_path, reset."""

    def test_zeros_creates_tensor(self):
        from temper_placer.router_v6.congestion_tensor import CongestionTensor

        t = CongestionTensor.zeros(10, 20)
        arr = t.array
        assert arr.shape == (10, 20)
        assert arr.dtype == np.float32
        assert arr.max() == 0.0

    def test_zeros_with_options(self):
        from temper_placer.router_v6.congestion_tensor import CongestionTensor

        t = CongestionTensor.zeros(5, 5, max_cost=50.0, weight=0.5)
        assert t.max_cost == 50.0
        assert t.weight == 0.5

    def test_cost_default(self):
        from temper_placer.router_v6.congestion_tensor import CongestionTensor

        t = CongestionTensor.zeros(10, 10)
        # No usage -> cost = 1.0 (baseline)
        assert t.cost(0, 0) == 1.0

    def test_cost_after_increment(self):
        from temper_placer.router_v6.congestion_tensor import CongestionTensor

        t = CongestionTensor.zeros(10, 10)
        t.increment(5, 5, 1.0)
        # cost = min(max_cost, 1.0 + log(1+1)) = 1.0 + 0.693... = 1.693...
        c = t.cost(5, 5)
        assert c > 1.0
        assert c < 2.0

    def test_increment_multiple(self):
        from temper_placer.router_v6.congestion_tensor import CongestionTensor

        t = CongestionTensor.zeros(10, 10)
        t.increment(3, 3, 2.0)
        c = t.cost(3, 3)
        # cost = 1.0 + log(1+2) = 1.0 + 1.098... = 2.098...
        assert c > 2.0

    def test_reset(self):
        from temper_placer.router_v6.congestion_tensor import CongestionTensor

        t = CongestionTensor.zeros(10, 10)
        t.increment(5, 5, 1.0)
        assert t.cost(5, 5) > 1.0
        t.reset()
        assert t.cost(5, 5) == 1.0

    def test_decay(self):
        from temper_placer.router_v6.congestion_tensor import CongestionTensor

        t = CongestionTensor.zeros(10, 10)
        t.increment(5, 5, 10.0)  # usage=10
        t.decay(0.5)  # usage *= 0.5 = 5.0
        c = t.cost(5, 5)
        # cost = 1.0 + log(1+5) = 1.0 + 1.791... = 2.791...
        assert c > 2.0
        assert c < 3.0

    def test_increment_path(self):
        from temper_placer.router_v6.congestion_tensor import CongestionTensor
        from temper_placer.router_v6.occupancy_grid import OccupancyGrid

        grid = OccupancyGrid(
            "test",
            np.zeros((20, 20), dtype=np.int32),
            (0.0, 0.0),
            1.0,
            20,
            20,
        )
        t = CongestionTensor.zeros(20, 20)
        t.increment_path([(5.5, 8.3), (12.0, 15.0)], grid)
        # Check that the cells at those world coords got incremented
        # world_to_grid(5.5, 8.3) -> (5, 8) -> increment(8, 5) [row=y, col=x]
        assert t.cost(8, 5) > 1.0
        assert t.cost(15, 12) > 1.0
        # Unused cell unchanged
        assert t.cost(0, 0) == 1.0

    def test_cost_capped(self):
        from temper_placer.router_v6.congestion_tensor import CongestionTensor

        t = CongestionTensor.zeros(10, 10, max_cost=2.0)
        t.increment(5, 5, 100.0)
        c = t.cost(5, 5)
        # Capped at max_cost=2.0
        assert c <= 2.0

    def test_weight_property(self):
        from temper_placer.router_v6.congestion_tensor import CongestionTensor

        t = CongestionTensor.zeros(5, 5, weight=0.5)
        assert abs(t.weight - 0.5) < 1e-6
        t.weight = 0.8
        assert abs(t.weight - 0.8) < 1e-6

    def test_max_cost_property(self):
        from temper_placer.router_v6.congestion_tensor import CongestionTensor

        t = CongestionTensor.zeros(5, 5, max_cost=50.0)
        assert t.max_cost == 50.0
        t.max_cost = 25.0
        assert t.max_cost == 25.0


# ===========================================================================
# router_v6/clearance_engine.py
# ===========================================================================


class TestCalculateSafetyDistances:
    """Covers calculate_safety_distances."""

    def test_returns_safety_distances(self):
        from temper_placer.router_v6.clearance_engine import calculate_safety_distances

        result = calculate_safety_distances(340.0)
        assert result.clearance_mm > 0
        assert result.creepage_mm > 0
        assert result.voltage_v == 340.0

    def test_low_voltage(self):
        from temper_placer.router_v6.clearance_engine import calculate_safety_distances

        result = calculate_safety_distances(12.0)
        assert result.clearance_mm > 0
        assert result.creepage_mm > 0

    def test_creepage_gte_clearance(self):
        from temper_placer.router_v6.clearance_engine import calculate_safety_distances

        result = calculate_safety_distances(340.0)
        assert result.creepage_mm >= result.clearance_mm

    def test_with_pollution_degree(self):
        from temper_placer.router_v6.clearance_engine import calculate_safety_distances

        r1 = calculate_safety_distances(340.0, pollution_degree=1)
        r2 = calculate_safety_distances(340.0, pollution_degree=3)
        assert r1.clearance_mm > 0
        assert r2.clearance_mm > 0


class TestGetClearance:
    """Covers get_clearance."""

    def test_hv_to_signal(self):
        from temper_placer.router_v6.clearance_engine import get_clearance

        c = get_clearance("HV", "Signal", 340.0)
        assert c > 0
        assert isinstance(c, float)

    def test_same_net_class(self):
        from temper_placer.router_v6.clearance_engine import get_clearance

        c = get_clearance("Signal", "Signal", 5.0)
        assert c > 0

    def test_with_design_rule_creepage(self):
        from temper_placer.router_v6.clearance_engine import get_clearance

        c = get_clearance("HV", "Signal", 340.0, design_rule_creepage=8.0)
        assert c >= 8.0

    def test_internal_layer(self):
        from temper_placer.router_v6.clearance_engine import get_clearance

        c_ext = get_clearance("HV", "Signal", 340.0, layer_type="external")
        c_int = get_clearance("HV", "Signal", 340.0, layer_type="internal")
        # Internal layer should have reduced clearance (IEC 60664-1 factor)
        assert c_int <= c_ext
