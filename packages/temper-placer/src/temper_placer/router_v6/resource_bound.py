"""
Resource Exhaustion Theorem for PCB Routing

Computes a provable upper bound on the maximum number of simultaneously
routable nets in a region using the bin-packing lower bound.

Theorem (bin-packing lower bound):
  For items with sizes s_i and bin capacity C, the maximum number of
  items is max{k : sum(smallest k) <= C}.

By the rearrangement inequality, ascending order gives the minimum prefix
sum at every step, so k_max is the provable upper bound.

Soundness:
  If k_max < N, at least N - k_max nets MUST fail --- no algorithm can
  succeed because even the smallest k_max+1 demands exceed capacity.

Completeness:
  k_max is an upper bound, not a guarantee --- nets may still fail for
  geometric reasons (blocking, clearance, detour).

Part of feat/resource-exhaustion.

Wave 4 migration note: every computation that turns bboxes + a grid into a
bound now delegates to ``temper_geometry``'s ``resource_bound`` kernels
(``packages/temper-geometry/src/resource_bound.rs``); this module keeps its
original public API. ``_net_bboxes_from_pcb`` / ``max_routable_nets_from_pcb``
stay Python (ParsedPCB / ``pin_world_position`` coupling). See
``packages/temper-geometry/VERIFICATION.md`` for the full writeup.
"""

from __future__ import annotations

import logging

import numpy as np
import temper_geometry as _tg

from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.stage0_data import ParsedPCB

logger = logging.getLogger(__name__)

_OVERLAP_THRESHOLD = 0.1


def _net_bboxes_from_pcb(pcb: ParsedPCB) -> dict[str, tuple[float, float, float, float]]:
    """Compute per-net bounding boxes from PCB pin positions.

    Resolves each net's pins to world coordinates and returns the min/max
    axis-aligned bounding box as (min_x, min_y, max_x, max_y) in mm.

    Nets with fewer than 2 pins receive a zero-area bbox at (0, 0, 0, 0).

    Pin resolution goes through
    :func:`temper_placer.core.pad_identity.resolve_net_pins`
    (occurrence-indexed), not ``comp.get_pin(pin_name)``'s first match --
    an independent, previously-unfixed copy of the same bug
    ``_pipeline_grid._net_pad_positions`` had (see
    ``temper_placer.core.pad_identity``'s module docstring): a component
    with more than one physical pad sharing a pad number (K2/K3's
    current-sharing contacts) would otherwise have every occurrence
    resolve to the SAME coordinate, silently shrinking that net's bbox and
    understating its conflict-cluster / resource-exhaustion exposure.
    """
    from temper_placer.core.pad_identity import resolve_net_pins
    from temper_placer.core.pin_geometry import pin_world_position

    bboxes: dict[str, tuple[float, float, float, float]] = {}
    comp_by_ref = {c.ref: c for c in pcb.components}

    for net in pcb.nets:
        xs: list[float] = []
        ys: list[float] = []

        for comp_ref, _pin_name, pin in resolve_net_pins(net, comp_by_ref):
            comp = comp_by_ref.get(comp_ref)
            if comp is None:
                continue
            comp_pos = getattr(comp, "initial_position", None)
            if comp_pos is None:
                continue
            if pin is None:
                continue
            wx, wy = pin_world_position(pin, comp)
            xs.append(wx)
            ys.append(wy)

        if len(xs) < 2:
            bboxes[net.name] = (0.0, 0.0, 0.0, 0.0)
        else:
            bboxes[net.name] = (min(xs), min(ys), max(xs), max(ys))

    return bboxes


def _compute_conflict_clusters(
    bboxes: dict[str, tuple[float, float, float, float]],
    overlap_threshold: float = _OVERLAP_THRESHOLD,
) -> list[list[str]]:
    """Build conflict graph and find connected components (clusters).

    Two nets conflict if their bounding boxes overlap more than
    ``overlap_threshold`` of the smaller net's area.

    Returns a list of clusters, where each cluster is a list of net names.
    """
    names = list(bboxes.keys())
    flat = [c for n in names for c in bboxes[n]]
    clusters = _tg.conflict_clusters_py(flat, overlap_threshold)
    return [[names[i] for i in cl] for cl in clusters]


def _cluster_union_bbox(
    cluster: list[str],
    bboxes: dict[str, tuple[float, float, float, float]],
) -> tuple[float, float, float, float]:
    """Compute the union bounding box of all nets in a cluster.

    Returns (min_x, min_y, max_x, max_y) in mm.
    """
    if not cluster:
        return (0.0, 0.0, 0.0, 0.0)
    names = list(bboxes.keys())
    idx = [names.index(n) for n in cluster]
    flat = [c for n in names for c in bboxes[n]]
    return tuple(_tg.cluster_union_bbox_py(idx, flat))


def _capacity_in_bbox(
    grid: OccupancyGrid,
    bbox: tuple[float, float, float, float],
) -> float:
    """Compute total free routing area within a bounding box (mm^2).

    Sums the area of all free cells (grid value == 0) that fall within
    the world-coordinate bounding box.
    """
    min_x, min_y, max_x, max_y = bbox
    return _tg.capacity_in_bbox_py(
        grid.grid.astype(np.int64).ravel().tolist(),
        grid.width_cells,
        grid.height_cells,
        grid.cell_size,
        grid.origin[0],
        grid.origin[1],
        min_x,
        min_y,
        max_x,
        max_y,
    )


def _compute_fill_factor(
    trace_width: float,
    bbox_areas: dict[str, float],
) -> float:
    """Estimate the fraction of bbox area actually consumed by traces.

    The fill factor accounts for the fact that traces do not fill their
    entire bounding box.  For a 2-pin net, the trace covers roughly
    HPWL * trace_width.  We approximate HPWL as sqrt(bbox_area), yielding:

        fill_factor = trace_width / sqrt(avg_bbox_area)

    clamped to [0.01, 1.0].
    """
    if not bbox_areas:
        return 0.5
    return _tg.fill_factor_py(trace_width, list(bbox_areas.values()))


def max_routable_nets(
    edt_grid: OccupancyGrid,
    net_bboxes: dict[str, tuple[float, float, float, float]],
    trace_width: float,
    fill_factor: float | None = None,
) -> int:
    """Compute the theoretical maximum number of simultaneously routable nets.

    Algorithm:
      1. Per net: demand = bbox_area * fill_factor
      2. Per conflict cluster: capacity = sum(free area in cluster union bbox)
      3. Sort nets by demand ascending (rearrangement inequality)
      4. Find largest k s.t. sum(k smallest demands) <= capacity
      5. Return sum of k over all clusters

    Args:
        edt_grid: OccupancyGrid representing available routing area.
        net_bboxes: Dict mapping net_name -> (min_x, min_y, max_x, max_y) mm.
        trace_width: Width of traces in mm.
        fill_factor: Fraction of bbox area actually consumed by traces.
            If None, estimated as trace_width / sqrt(avg_bbox_area).

    Returns:
        Maximum number of routable nets (provable upper bound).
    """
    if not net_bboxes:
        return 0

    names = list(net_bboxes.keys())
    flat = [c for n in names for c in net_bboxes[n]]
    grid_flat = edt_grid.grid.astype(np.int64).ravel().tolist()

    total_routable, resolved_fill, cluster_count = _tg.max_routable_py(
        flat,
        grid_flat,
        edt_grid.width_cells,
        edt_grid.height_cells,
        edt_grid.cell_size,
        edt_grid.origin[0],
        edt_grid.origin[1],
        trace_width,
        fill_factor,
    )

    logger.info(
        "Resource bound: %d/%d nets routable (fill_factor=%.3f, trace_width=%.3f mm, %d clusters)",
        total_routable,
        len(net_bboxes),
        resolved_fill,
        trace_width,
        cluster_count,
    )

    return total_routable


def max_routable_nets_from_pcb(
    edt_grid: OccupancyGrid,
    pcb: ParsedPCB,
    trace_width: float,
    fill_factor: float | None = None,
) -> int:
    """Convenience wrapper: compute net bboxes from ParsedPCB, then call max_routable_nets.

    Args:
        edt_grid: OccupancyGrid representing available routing area.
        pcb: ParsedPCB with component and net data.
        trace_width: Width of traces in mm.
        fill_factor: Fraction of bbox area actually consumed by traces.

    Returns:
        Maximum number of routable nets (provable upper bound).
    """
    bboxes = _net_bboxes_from_pcb(pcb)
    return max_routable_nets(edt_grid, bboxes, trace_width, fill_factor)


def demand_budget_summary(
    edt_grid: OccupancyGrid,
    net_bboxes: dict[str, tuple[float, float, float, float]],
    trace_width: float,
    fill_factor: float | None = None,
) -> dict:
    """Compute and return a detailed demand-budget summary.

    Returns a dict with keys:
      - max_routable: int
      - total_nets: int
      - fill_factor: float
      - cluster_count: int
      - total_capacity_mm2: float
      - total_demand_mm2: float
      - utilization: float  (total_demand / total_capacity)
    """
    if not net_bboxes:
        return {
            "max_routable": 0,
            "total_nets": 0,
            "fill_factor": fill_factor if fill_factor is not None else 0.5,
            "cluster_count": 0,
            "total_capacity_mm2": 0.0,
            "total_demand_mm2": 0.0,
            "utilization": 0.0,
        }

    names = list(net_bboxes.keys())
    flat = [c for n in names for c in net_bboxes[n]]
    grid_flat = edt_grid.grid.astype(np.int64).ravel().tolist()

    mr, tn, ff, cc, tc, td, util = _tg.demand_budget_py(
        flat,
        grid_flat,
        edt_grid.width_cells,
        edt_grid.height_cells,
        edt_grid.cell_size,
        edt_grid.origin[0],
        edt_grid.origin[1],
        trace_width,
        fill_factor,
    )

    return {
        "max_routable": mr,
        "total_nets": tn,
        "fill_factor": ff,
        "cluster_count": cc,
        "total_capacity_mm2": tc,
        "total_demand_mm2": td,
        "utilization": util,
    }
