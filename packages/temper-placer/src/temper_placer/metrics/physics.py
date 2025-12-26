"""
Physics-based metrics for PCB design validation.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.core.state import PlacementState


@dataclass
class GeometricMetrics:
    overlap_count: int = 0
    overlap_area_mm2: float = 0.0
    zone_violation_count: int = 0
    zone_violation_max_mm: float = 0.0
    boundary_violation_count: int = 0
    min_hv_lv_clearance_mm: float = 1000.0


@dataclass
class EMIMetrics:
    gate_loop_area_mm2: float = 0.0
    power_loop_area_mm2: float = 0.0
    total_loop_area_mm2: float = 0.0


@dataclass
class ThermalMetrics:
    max_junction_temp_c: float = 0.0
    thermal_margin_c: float = 0.0
    edge_distance_avg_mm: float = 0.0


@dataclass
class RoutabilityMetrics:
    completion_pct: float = 0.0
    overflow_cells: int = 0
    max_congestion: float = 0.0
    total_wirelength_mm: float = 0.0


@dataclass
class PhysicsReport:
    geometric: GeometricMetrics = field(default_factory=GeometricMetrics)
    emi: EMIMetrics = field(default_factory=EMIMetrics)
    thermal: ThermalMetrics = field(default_factory=ThermalMetrics)
    routability: RoutabilityMetrics = field(default_factory=RoutabilityMetrics)
    
    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return self._convert_numpy(asdict(self))

    def _convert_numpy(self, obj: Any) -> Any:
        if isinstance(obj, dict): return {k: self._convert_numpy(v) for k, v in obj.items()}
        if isinstance(obj, list): return [self._convert_numpy(v) for v in obj]
        if isinstance(obj, (np.float32, np.float64)): return float(obj)
        if isinstance(obj, (np.int32, np.int64)): return int(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        return obj


def measure_geometric(state: PlacementState, netlist: Netlist, board: Board, min_sep: float = 0.5) -> GeometricMetrics:
    pos = np.array(state.positions)
    ws = np.array([c.bounds[0] for c in netlist.components])
    hs = np.array([c.bounds[1] for c in netlist.components])
    n = len(netlist.components)
    m = GeometricMetrics()
    for i in range(n):
        for j in range(i+1, n):
            dx, dy = abs(pos[i,0]-pos[j,0]), abs(pos[i,1]-pos[j,1])
            ox, oy = (ws[i]+ws[j])/2+min_sep-dx, (hs[i]+hs[j])/2+min_sep-dy
            if ox > 0 and oy > 0:
                m.overlap_count += 1
                m.overlap_area_mm2 += ox * oy
    for i, c in enumerate(netlist.components):
        if c.zone:
            z = next((z for z in board.zones if z.name == c.zone), None)
            if z:
                dx = max(0, z.bounds[0]-(pos[i,0]-ws[i]/2), (pos[i,0]+ws[i]/2)-z.bounds[2])
                dy = max(0, z.bounds[1]-(pos[i,1]-hs[i]/2), (pos[i,1]+hs[i]/2)-z.bounds[3])
                if dx > 0 or dy > 0:
                    m.zone_violation_count += 1
                    m.zone_violation_max_mm = max(m.zone_violation_max_mm, np.sqrt(dx**2+dy**2))
    for i in range(n):
        if (pos[i,0]-ws[i]/2 < board.origin[0] or pos[i,0]+ws[i]/2 > board.origin[0]+board.width or
            pos[i,1]-hs[i]/2 < board.origin[1] or pos[i,1]+hs[i]/2 > board.origin[1]+board.height):
            m.boundary_violation_count += 1
    hv = [i for i, c in enumerate(netlist.components) if c.net_class == "HighVoltage"]
    lv = [i for i, c in enumerate(netlist.components) if c.net_class != "HighVoltage"]
    if hv and lv:
        for i in hv:
            for j in lv:
                dx, dy = abs(pos[i,0]-pos[j,0])-(ws[i]+ws[j])/2, abs(pos[i,1]-pos[j,1])-(hs[i]+hs[j])/2
                d = max(dx, dy, 0.0)
                if dx > 0 and dy > 0: d = np.sqrt(dx**2+dy**2)
                m.min_hv_lv_clearance_mm = min(m.min_hv_lv_clearance_mm, d)
    return m


def measure_emi(state: PlacementState, netlist: Netlist, loop_refs: list[list[str]] | None = None) -> EMIMetrics:
    if not loop_refs: return EMIMetrics()
    pos = np.array(state.positions)
    m = EMIMetrics()
    for i, loop in enumerate(loop_refs):
        v = []
        for ref in loop:
            try: v.append(pos[netlist.get_component_index(ref)])
            except KeyError: continue
        if len(v) < 3: continue
        v = np.array(v)
        area = 0.5 * np.abs(np.dot(v[:,0], np.roll(v[:,1], 1)) - np.dot(v[:,1], np.roll(v[:,0], 1)))
        if i == 0: m.gate_loop_area_mm2 = area
        elif i == 1: m.power_loop_area_mm2 = area
        m.total_loop_area_mm2 += area
    return m


def measure_routability(state: PlacementState, netlist: Netlist, board: Board) -> RoutabilityMetrics:
    from temper_placer.routing.congestion import analyze_congestion
    import jax.numpy as jnp
    from temper_placer.metrics.quality import total_wirelength
    from temper_placer.losses.base import LossContext
    m = RoutabilityMetrics()
    res = analyze_congestion(netlist, board, positions=jnp.array(state.positions))
    m.max_congestion, m.overflow_cells = res.max_utilization, len(res.bottlenecks)
    ctx = LossContext.from_netlist_and_board(netlist, board)
    m.total_wirelength_mm = total_wirelength(state, netlist, ctx)
    m.completion_pct = max(0.0, 100.0 * (1.0 - res.overflow_ratio()))
    return m


def measure_thermal(
    state: PlacementState,
    netlist: Netlist,
    board: Board,
    power_dissipation: dict[str, float] | None = None,
    amb: float = 40.0
) -> ThermalMetrics:
    """
    Predict junction temperatures using a calibrated thermal resistance network.

    Model: Tj = Tamb + P * (Rjc + Rch + Rha)
    Rha is modeled as a base resistance plus a penalty for distance from the board edge.
    
    Targets: IKW40N120H3 IGBT (TO-247) at 15A/1.8kW.
    """
    if not power_dissipation:
        return ThermalMetrics(amb, 0.0, 0.0)

    pos = np.array(state.positions)
    max_tj = amb
    edge_dists = []

    # Calibrated values for Temper project
    # RJC: Junction-to-Case (0.6 K/W from IKW40N120H3 datasheet)
    # RCH: Case-to-Heatsink (0.25 K/W for high-quality silicone grease)
    # RHA_BASE: Heatsink-to-Ambient (2.0 K/W for 100mm extruded aluminum)
    RJC = 0.6
    RCH = 0.25
    RHA_BASE = 2.0
    MAX_ALLOWED_TJ = 150.0  # Celsius

    for ref, p in power_dissipation.items():
        try:
            idx = netlist.get_component_index(ref)
            cp = pos[idx]

            # Distance to closest board edge
            d = min(
                cp[0] - board.origin[0],
                board.origin[0] + board.width - cp[0],
                cp[1] - board.origin[1],
                board.origin[1] + board.height - cp[1]
            )
            edge_dists.append(d)

            # Rha penalty: 0.2 K/W per mm away from board edge
            # This represents the effective increase in thermal resistance
            # when mounting becomes suboptimal or remote.
            rha_penalty = d * 0.2
            r_total = RJC + RCH + RHA_BASE + rha_penalty

            tj = amb + p * r_total
            max_tj = max(max_tj, tj)
        except KeyError:
            continue

    return ThermalMetrics(
        max_junction_temp_c=max_tj,
        thermal_margin_c=MAX_ALLOWED_TJ - max_tj,
        edge_distance_avg_mm=np.mean(edge_dists) if edge_dists else 0.0
    )
