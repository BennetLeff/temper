"""
Physics-based metrics for PCB design validation.

This module implements measurement functions that ground placement quality
in physical properties (mm, mm², degrees, etc.) rather than abstract scores.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.core.state import PlacementState


@dataclass
class GeometricMetrics:
    """Raw geometric violations."""
    overlap_count: int = 0
    overlap_area_mm2: float = 0.0
    zone_violation_count: int = 0
    zone_violation_max_mm: float = 0.0
    boundary_violation_count: int = 0
    min_hv_lv_clearance_mm: float = 1000.0


@dataclass
class EMIMetrics:
    """EMI-related metrics (loop areas)."""
    gate_loop_area_mm2: float = 0.0
    power_loop_area_mm2: float = 0.0
    total_loop_area_mm2: float = 0.0


@dataclass
class ThermalMetrics:
    """Thermal safety metrics."""
    max_junction_temp_c: float = 0.0
    thermal_margin_c: float = 0.0
    edge_distance_avg_mm: float = 0.0


@dataclass
class RoutabilityMetrics:
    """Routability and congestion metrics."""
    completion_pct: float = 0.0
    overflow_cells: int = 0
    max_congestion: float = 0.0
    total_wirelength_mm: float = 0.0


@dataclass
class PhysicsReport:
    """Comprehensive physical measurement report."""
    geometric: GeometricMetrics = field(default_factory=GeometricMetrics)
    emi: EMIMetrics = field(default_factory=EMIMetrics)
    thermal: ThermalMetrics = field(default_factory=ThermalMetrics)
    routability: RoutabilityMetrics = field(default_factory=RoutabilityMetrics)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        from dataclasses import asdict
        data = asdict(self)
        return self._convert_numpy(data)

    def _convert_numpy(self, obj: Any) -> Any:
        """Recursively convert numpy types to python types for JSON."""
        if isinstance(obj, dict):
            return {k: self._convert_numpy(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_numpy(v) for v in obj]
        elif isinstance(obj, (np.float32, np.float64, np.float16)):
            return float(obj)
        elif isinstance(obj, (np.int32, np.int64, np.int16)):
            return int(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj


def measure_geometric(
    state: PlacementState,
    netlist: Netlist,
    board: Board,
    min_separation: float = 0.5,
) -> GeometricMetrics:
    """
    Measure raw geometric violations.
    """
    positions = np.array(state.positions)
    widths = np.array([c.bounds[0] for c in netlist.components])
    heights = np.array([c.bounds[1] for c in netlist.components])
    n = len(netlist.components)
    
    metrics = GeometricMetrics()
    
    # 1. Overlaps
    for i in range(n):
        hw_i, hh_i = widths[i] / 2, heights[i] / 2
        for j in range(i + 1, n):
            hw_j, hh_j = widths[j] / 2, heights[j] / 2
            
            dx = abs(positions[i, 0] - positions[j, 0])
            dy = abs(positions[i, 1] - positions[j, 1])
            
            ox = (hw_i + hw_j + min_separation) - dx
            oy = (hh_i + hh_j + min_separation) - dy
            
            if ox > 0 and oy > 0:
                metrics.overlap_count += 1
                metrics.overlap_area_mm2 += ox * oy
                
    # 2. Zone Violations
    zone_map = {z.name: z for z in board.zones}
    for i, comp in enumerate(netlist.components):
        if comp.zone and comp.zone in zone_map:
            zone = zone_map[comp.zone]
            x, y = positions[i]
            hw, hh = widths[i] / 2, heights[i] / 2
            
            # Check if component bounds are fully within zone
            dist_x = max(0, zone.bounds[0] - (x - hw), (x + hw) - zone.bounds[2])
            dist_y = max(0, zone.bounds[1] - (y - hh), (y + hh) - zone.bounds[3])
            
            if dist_x > 0 or dist_y > 0:
                metrics.zone_violation_count += 1
                metrics.zone_violation_max_mm = max(
                    metrics.zone_violation_max_mm, 
                    np.sqrt(dist_x**2 + dist_y**2)
                )
                
    # 3. Boundary Violations
    for i in range(n):
        x, y = positions[i]
        hw, hh = widths[i] / 2, heights[i] / 2
        
        if (x - hw < board.origin[0] or x + hw > board.origin[0] + board.width or
            y - hh < board.origin[1] or y + hh > board.origin[1] + board.height):
            metrics.boundary_violation_count += 1
            
    # 4. HV-LV Clearance (Creepage proxy)
    hv_indices = [i for i, c in enumerate(netlist.components) if c.net_class == "HighVoltage"]
    lv_indices = [i for i, c in enumerate(netlist.components) if c.net_class != "HighVoltage"]
    
    if hv_indices and lv_indices:
        for i in hv_indices:
            hw_i, hh_i = widths[i] / 2, heights[i] / 2
            for j in lv_indices:
                hw_j, hh_j = widths[j] / 2, heights[j] / 2
                
                dx = abs(positions[i, 0] - positions[j, 0]) - hw_i - hw_j
                dy = abs(positions[i, 1] - positions[j, 1]) - hh_i - hh_j
                
                dist = max(dx, dy, 0.0)
                if dx > 0 and dy > 0:
                    dist = np.sqrt(dx**2 + dy**2)
                    
                metrics.min_hv_lv_clearance_mm = min(metrics.min_hv_lv_clearance_mm, dist)
                
    return metrics


def measure_emi(
    state: PlacementState,
    netlist: Netlist,
    loop_refs: list[list[str]] | None = None,
) -> EMIMetrics:
    """
    Estimate loop areas and inductances based on component placement.
    """
    if not loop_refs:
        return EMIMetrics()
        
    from temper_placer.physics.inductance import estimate_loop_inductance
    
    positions = np.array(state.positions)
    metrics = EMIMetrics()
    
    for i, loop in enumerate(loop_refs):
        if len(loop) < 2:
            continue
            
        # Get vertices
        vertices = []
        for ref in loop:
            try:
                idx = netlist.get_component_index(ref)
                vertices.append(positions[idx])
            except KeyError:
                continue
                
        if len(vertices) < 2:
            continue
            
        v = np.array(vertices)
        
        # 1. Compute Area (Shoelace)
        if len(v) >= 3:
            area = 0.5 * np.abs(np.dot(v[:, 0], np.roll(v[:, 1], 1)) - np.dot(v[:, 1], np.roll(v[:, 0], 1)))
        else:
            area = 0.0
            
        # 2. Compute Perimeter
        # Manhattan-ish routing factor (1.2x) assumed internally in physics module or applied here?
        # Let's compute raw perimeter and let estimator handle factors.
        diffs = np.diff(np.vstack([v, v[0]]), axis=0)
        perimeter = np.sum(np.sqrt(np.sum(diffs**2, axis=1)))
        
        # 3. Estimate Inductance (nH)
        inductance = estimate_loop_inductance(
            loop_area_mm2=area,
            perimeter_mm=perimeter
        )
            
        if i == 0: # Convention: first loop is gate drive
            metrics.gate_loop_area_mm2 = inductance # Note: field name remains for compatibility
        elif i == 1: # Convention: second loop is power
            metrics.power_loop_area_mm2 = inductance
            
        metrics.total_loop_area_mm2 += inductance
        
    return metrics


def measure_routability(
    state: PlacementState,
    netlist: Netlist,
    board: Board,
) -> RoutabilityMetrics:
    """
    Measure routability indicators (post-placement estimation).
    """
    from temper_placer.routing.congestion import analyze_congestion
    import jax.numpy as jnp
    
    metrics = RoutabilityMetrics()
    
    # Run congestion analysis
    # Use JAX positions
    pos_jax = jnp.array(state.positions)
    res = analyze_congestion(netlist, board, positions=pos_jax)
    
    metrics.max_congestion = res.max_utilization
    metrics.overflow_cells = len(res.bottlenecks)
    
    # total_wirelength (HPWL)
    from temper_placer.metrics.quality import total_wirelength
    from temper_placer.losses.base import LossContext
    
    ctx = LossContext.from_netlist_and_board(netlist, board)
    metrics.total_wirelength_mm = total_wirelength(state, netlist, ctx)
    
    # completion_pct estimation
    # This is hard without a router, but we can use (1 - overflow_ratio)
    metrics.completion_pct = max(0.0, 100.0 * (1.0 - res.overflow_ratio()))
    
    return metrics


def measure_thermal(
    state: PlacementState,
    netlist: Netlist,
    board: Board,
    power_dissipation: dict[str, float] | None = None,
    ambient_temp_c: float = 40.0,
) -> ThermalMetrics:
    """
    Estimate junction temperatures based on placement and power dissipation.
    """
    if not power_dissipation:
        return ThermalMetrics(ambient_temp_c, 0.0, 0.0)
        
    from temper_placer.physics.thermal import estimate_junction_temp
    
    positions = np.array(state.positions)
    max_tj = ambient_temp_c
    edge_dists = []
    
    for ref, power in power_dissipation.items():
        try:
            idx = netlist.get_component_index(ref)
        except KeyError:
            continue
            
        pos = positions[idx]
        # Dist to closest edge
        dx = min(pos[0] - board.origin[0], board.origin[0] + board.width - pos[0])
        dy = min(pos[1] - board.origin[1], board.origin[1] + board.height - pos[1])
        dist = min(dx, dy)
        edge_dists.append(dist)
        
        # Estimate Tj using the refined model
        # TODO: Pull copper_area from netlist/board info
        tj = estimate_junction_temp(
            power_W=power,
            edge_distance_mm=dist,
            ambient_C=ambient_temp_c
        )
        max_tj = max(max_tj, tj)
        
    metrics = ThermalMetrics()
    metrics.max_junction_temp_c = max_tj
    metrics.thermal_margin_c = 150.0 - max_tj # 150C is typical shutdown
    metrics.edge_distance_avg_mm = float(np.mean(edge_dists)) if edge_dists else 0.0
    
    return metrics
