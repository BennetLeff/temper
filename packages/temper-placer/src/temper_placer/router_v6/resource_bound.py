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

Wave 4: the bin-packing/clustering/capacity arithmetic
(``_compute_conflict_clusters``, ``_cluster_union_bbox``,
``_capacity_in_bbox``, ``_compute_fill_factor``, ``max_routable_nets``,
``demand_budget_summary``) delegates to ``temper_drc_rs`` (see
``packages/temper-drc-rs/src/resource_bound.rs``); the pre-migration
implementations are pinned VERBATIM as the differential oracle in
``packages/temper-placer/tests/router_v6/_resource_bound_py_oracle.py``.
``_net_bboxes_from_pcb`` (glue over the ``ParsedPCB``/``Component``/``Pin``
object graph) and ``max_routable_nets_from_pcb`` (thin wrapper) stay
Python -- see the Rust module's docstring for the full rationale.
"""

from __future__ import annotations

import logging

import numpy as np
import temper_drc_rs as _drc

from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.stage0_data import ParsedPCB

logger = logging.getLogger(__name__)

_OVERLAP_THRESHOLD = 0.1


def _net_bboxes_from_pcb(pcb: ParsedPCB) -> dict[str, tuple[float, float, float, float]]:
    """Compute per-net bounding boxes from PCB pin positions.

    Resolves each net's pins to world coordinates and returns the min/max
    axis-aligned bounding box as (min_x, min_y, max_x, max_y) in mm.

    Nets with fewer than 2 pins receive a zero-area bbox at (0, 0, 0, 0).
    """
    from temper_placer.core.pin_geometry import pin_world_position

    bboxes: dict[str, tuple[float, float, float, float]] = {}
    comp_by_ref = {c.ref: c for c in pcb.components}

    for net in pcb.nets:
        xs: list[float] = []
        ys: list[float] = []

        for comp_ref, pin_name in getattr(net, "pins", []):
            comp = comp_by_ref.get(comp_ref)
            if comp is None:
                continue
            comp_pos = getattr(comp, "initial_position", None)
            if comp_pos is None:
                continue
            pin = comp.get_pin(pin_name) if hasattr(comp, "get_pin") else None
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


def _grid_rust_args(
    grid: OccupancyGrid,
) -> tuple[bytes, int, int, tuple[float, float], float]:
    """Flatten an ``OccupancyGrid`` into the plain-value shape
    ``temper_drc_rs``'s resource-bound kernels expect: the cell grid as
    raw bytes (row-major, one byte per int8 cell — same convention as
    ``astar_core_rust.py``'s ``grid_contig.tobytes()``), plus the scalar
    fields the kernel needs to replicate ``OccupancyGrid.world_to_grid``
    and the free-cell-area arithmetic.
    """
    grid_contig = np.ascontiguousarray(grid.grid, dtype=np.int8)
    return (
        grid_contig.tobytes(),
        grid.width_cells,
        grid.height_cells,
        (float(grid.origin[0]), float(grid.origin[1])),
        float(grid.cell_size),
    )


def _compute_conflict_clusters(
    bboxes: dict[str, tuple[float, float, float, float]],
    overlap_threshold: float = _OVERLAP_THRESHOLD,
) -> list[list[str]]:
    """Build conflict graph and find connected components (clusters).

    Two nets conflict if their bounding boxes overlap more than
    ``overlap_threshold`` of the smaller net's area.

    Returns a list of clusters, where each cluster is a list of net names.

    Delegates to ``temper_drc_rs.resource_bound_compute_conflict_clusters``
    — see the Rust kernel's docstring for why within-cluster net order is
    safe to differ from the pre-migration oracle's hash-order-dependent
    traversal.
    """
    return _drc.resource_bound_compute_conflict_clusters(list(bboxes.items()), overlap_threshold)


def _cluster_union_bbox(
    cluster: list[str],
    bboxes: dict[str, tuple[float, float, float, float]],
) -> tuple[float, float, float, float]:
    """Compute the union bounding box of all nets in a cluster.

    Returns (min_x, min_y, max_x, max_y) in mm.
    """
    return _drc.resource_bound_cluster_union_bbox([bboxes[n] for n in cluster])


def _capacity_in_bbox(
    grid: OccupancyGrid,
    bbox: tuple[float, float, float, float],
) -> float:
    """Compute total free routing area within a bounding box (mm^2).

    Sums the area of all free cells (grid value == 0) that fall within
    the world-coordinate bounding box.
    """
    grid_bytes, width_cells, height_cells, origin, cell_size = _grid_rust_args(grid)
    return _drc.resource_bound_capacity_in_bbox(grid_bytes, width_cells, height_cells, origin, cell_size, bbox)


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
    return _drc.resource_bound_compute_fill_factor(trace_width, list(bbox_areas.values()))


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
    grid_bytes, width_cells, height_cells, origin, cell_size = _grid_rust_args(edt_grid)
    total_routable = _drc.resource_bound_max_routable_nets(
        grid_bytes,
        width_cells,
        height_cells,
        origin,
        cell_size,
        list(net_bboxes.items()),
        trace_width,
        fill_factor,
    )

    logger.info(
        "Resource bound: %d/%d nets routable (trace_width=%.3f mm)",
        total_routable,
        len(net_bboxes),
        trace_width,
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
    grid_bytes, width_cells, height_cells, origin, cell_size = _grid_rust_args(edt_grid)
    return _drc.resource_bound_demand_budget_summary(
        grid_bytes,
        width_cells,
        height_cells,
        origin,
        cell_size,
        list(net_bboxes.items()),
        trace_width,
        fill_factor,
    )
