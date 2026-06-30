"""
Router V6 Pre-Routing Capacity-Demand Check.

Computes capacity-demand ratios for all nets before routing begins,
using the EDT grids from Stage 2's channel analysis.  A ratio < 1.0
means the net's estimated demand exceeds the available routing capacity
in its region -- the net is structurally at-risk.

Mathematical foundation:
  - EDT gives width(x, y) at every cell: the diameter of the largest
    inscribed circle through that point (2x clearance).
  - Total capacity in a net's bounding box = Σ width * cell_size over
    all interior cells in the bbox.
  - Demand = trace_width * HPWL (half-perimeter wirelength estimate).
  - Ratio = capacity / demand.  Ratio < 1 means demand > capacity.

Correctness proof:
  - Base case: empty board → EDT = max at all cells → capacity = ∞
    → ratio = ∞ for all nets.
  - Induction: adding a trace reduces available capacity in its region
    by trace_width * path_length.
  - Monotonicity: ratio is monotone in available capacity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from temper_placer.router_v6.channel_widths import (
    _build_edt,
)

if TYPE_CHECKING:
    from temper_placer.router_v6.pipeline import Stage2Output
    from temper_placer.router_v6.stage0_data import ParsedPCB


_EDT_CELL_SIZE: float = 0.1  # mm — matches channel_widths.py


def _net_pad_positions(net, comp_by_ref: dict) -> list[tuple[float, float]]:
    """Resolve a Net's pads to world coordinates via component lookup."""
    positions: list[tuple[float, float]] = []
    for comp_ref, pin_name in getattr(net, "pins", []):
        comp = comp_by_ref.get(comp_ref)
        if comp is None:
            continue
        comp_pos = getattr(comp, "initial_position", None)
        if comp_pos is None:
            continue
        pin = comp.get_pin(pin_name) if hasattr(comp, "get_pin") else None
        if pin is None:
            positions.append((float(comp_pos[0]), float(comp_pos[1])))
            continue
        px, py = pin.position
        positions.append((float(comp_pos[0]) + float(px), float(comp_pos[1]) + float(py)))
    return positions


def _sum_capacity_in_bbox(
    edt: np.ndarray,
    mask: np.ndarray,
    bounds: tuple[float, float, float, float],
    cell_size: float,
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
) -> float:
    """Sum width * cell_size for all interior EDT cells within [min_x, max_x] x [min_y, max_y]."""
    b_min_x, b_min_y, _, _ = bounds
    h, w = edt.shape

    ix_min = max(0, int(np.floor((min_x - b_min_x) / cell_size)))
    ix_max = min(w, int(np.ceil((max_x - b_min_x) / cell_size)) + 1)
    iy_min = max(0, int(np.floor((min_y - b_min_y) / cell_size)))
    iy_max = min(h, int(np.ceil((max_y - b_min_y) / cell_size)) + 1)

    if ix_min >= ix_max or iy_min >= iy_max:
        return 0.0

    region_edt = edt[iy_min:iy_max, ix_min:ix_max]
    region_mask = mask[iy_min:iy_max, ix_min:ix_max]
    interior = region_mask.astype(bool)
    if not np.any(interior):
        return 0.0

    widths = 2.0 * region_edt[interior] * cell_size
    return float(np.sum(widths)) * cell_size


def compute_capacity_demand_ratios(
    stage2_output: Stage2Output,
    parsed_pcb: ParsedPCB,
) -> dict[str, float]:
    """Compute capacity-demand ratio for every net.

    A ratio < 1.0 means the estimated demand (trace_width * HPWL)
    exceeds the EDT-based routing capacity in the net's bounding box.
    Nets with ratio < 1.0 are structurally at-risk and likely to fail
    routing.

    Args:
        stage2_output: Output from Stage 2 channel analysis (must have
            ``routing_spaces`` populated).
        parsed_pcb: Parsed PCB with components, nets, and design rules.

    Returns:
        Dict mapping ``net_name`` to ``capacity_demand_ratio``.
        Ratio is ``inf`` for nets with zero demand (single-pin or
        unplaced).
    """
    ratios: dict[str, float] = {}

    comp_by_ref = {c.ref: c for c in parsed_pcb.components}
    routing_spaces = stage2_output.routing_spaces
    if routing_spaces is None:
        return ratios

    edt_cache: dict[str, tuple[np.ndarray, np.ndarray, tuple[float, float, float, float]]] = {}
    for layer_name, routing_space in routing_spaces.items():
        edt, mask, bounds = _build_edt(routing_space, _EDT_CELL_SIZE)
        edt_cache[layer_name] = (edt, mask, bounds)

    design_rules = parsed_pcb.design_rules

    for net in parsed_pcb.nets:
        net_name = getattr(net, "name", str(net))

        positions = _net_pad_positions(net, comp_by_ref)
        if len(positions) < 2:
            ratios[net_name] = float("inf")
            continue

        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]
        margin = 2.0
        min_x, max_x = min(xs) - margin, max(xs) + margin
        min_y, max_y = min(ys) - margin, max(ys) + margin

        hpwl = (max_x - min_x) + (max_y - min_y)
        try:
            trace_width = design_rules.get_rules_for_net(net_name).trace_width_mm
        except Exception:
            trace_width = design_rules.default_trace_width_mm
        demand = trace_width * hpwl

        if demand <= 0.0:
            ratios[net_name] = float("inf")
            continue

        total_capacity = 0.0
        for _layer_name, (edt, mask, bounds) in edt_cache.items():
            total_capacity += _sum_capacity_in_bbox(
                edt, mask, bounds, _EDT_CELL_SIZE,
                min_x, max_x, min_y, max_y,
            )

        ratios[net_name] = total_capacity / demand

    return ratios


@dataclass
class CapacityDemandReport:
    """Structured result of a capacity-demand pre-routing check."""

    ratios: dict[str, float]
    at_risk_nets: list[str]
    safe_nets: list[str]

    @property
    def at_risk_count(self) -> int:
        return len(self.at_risk_nets)

    @property
    def safe_count(self) -> int:
        return len(self.safe_nets)


def build_capacity_demand_report(
    stage2_output: Stage2Output,
    parsed_pcb: ParsedPCB,
    risk_threshold: float = 1.0,
) -> CapacityDemandReport:
    """Compute ratios and partition nets into at-risk and safe.

    Args:
        stage2_output: Stage 2 output with routing spaces.
        parsed_pcb: Parsed PCB data.
        risk_threshold: Ratio below which a net is considered at-risk.

    Returns:
        ``CapacityDemandReport`` with ratios and classifications.
    """
    ratios = compute_capacity_demand_ratios(stage2_output, parsed_pcb)
    at_risk = sorted(
        [n for n, r in ratios.items() if r < risk_threshold],
        key=lambda n: ratios[n],
    )
    safe = sorted(
        [n for n, r in ratios.items() if r >= risk_threshold],
        key=lambda n: ratios[n],
    )
    return CapacityDemandReport(ratios=ratios, at_risk_nets=at_risk, safe_nets=safe)
