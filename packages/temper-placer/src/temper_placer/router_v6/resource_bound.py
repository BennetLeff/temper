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
"""

from __future__ import annotations

import logging

import temper_drc_rs as _temper_drc_rs

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


def _compute_conflict_clusters(
    bboxes: dict[str, tuple[float, float, float, float]],
    overlap_threshold: float = _OVERLAP_THRESHOLD,
) -> list[list[str]]:
    """Build conflict graph and find connected components (clusters).

    Two nets conflict if their bounding boxes overlap more than
    ``overlap_threshold`` of the smaller net's area.

    Returns a list of clusters, where each cluster is a list of net names.

    Wave 4: delegates to ``temper_drc_rs`` (the O(n^2) conflict-graph
    kernel). Cluster/within-cluster element order is NOT guaranteed to
    match a from-scratch Python re-implementation bit-for-bit -- the
    original algorithm's own within-cluster traversal order depended on
    CPython's salted ``set`` iteration, which was never reproducible
    across processes to begin with. Cluster count and membership are
    unaffected. See ``resource_bound.rs``'s module doc for the full
    reasoning.
    """
    net_names = list(bboxes.keys())
    bbox_values = [bboxes[n] for n in net_names]
    return _temper_drc_rs.resource_bound_conflict_clusters_py(net_names, bbox_values, overlap_threshold)


def _cluster_union_bbox(
    cluster: list[str],
    bboxes: dict[str, tuple[float, float, float, float]],
) -> tuple[float, float, float, float]:
    """Compute the union bounding box of all nets in a cluster.

    Returns (min_x, min_y, max_x, max_y) in mm.

    Wave 4: delegates to ``temper_drc_rs``.
    """
    net_names = list(bboxes.keys())
    bbox_values = [bboxes[n] for n in net_names]
    return _temper_drc_rs.resource_bound_cluster_union_bbox_py(list(cluster), net_names, bbox_values)


def _capacity_in_bbox(
    grid: OccupancyGrid,
    bbox: tuple[float, float, float, float],
) -> float:
    """Compute total free routing area within a bounding box (mm^2).

    Sums the area of all free cells (grid value == 0) that fall within
    the world-coordinate bounding box.

    Wave 4: ``world_to_grid`` conversion, clamping, and the degenerate-
    region check stay here (widely-used general-purpose grid arithmetic,
    called only twice per invocation -- see ``resource_bound.rs``'s module
    doc); the ``np.sum(region == 0)`` reduction over the sliced region
    delegates to ``temper_drc_rs``.
    """
    min_x, min_y, max_x, max_y = bbox

    gx1, gy1 = grid.world_to_grid(min_x, min_y)
    gx2, gy2 = grid.world_to_grid(max_x, max_y)

    # Clamp to grid bounds
    gx1 = max(0, min(gx1, grid.width_cells - 1))
    gx2 = max(0, min(gx2, grid.width_cells - 1))
    gy1 = max(0, min(gy1, grid.height_cells - 1))
    gy2 = max(0, min(gy2, grid.height_cells - 1))

    if gx1 > gx2:
        gx1, gx2 = gx2, gx1
    if gy1 > gy2:
        gy1, gy2 = gy2, gy1

    # Guard against degenerate regions
    if gx1 > gx2 or gy1 > gy2:
        return 0.0

    region = grid.grid[gy1 : gy2 + 1, gx1 : gx2 + 1]
    region_flat = [int(v) for v in region.flatten().tolist()]
    return _temper_drc_rs.resource_bound_capacity_in_bbox_py(region_flat, grid.cell_size)


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

    Wave 4: delegates to ``temper_drc_rs`` (the ``sqrt``/``np.clip`` NaN
    trap -- see ``resource_bound.rs``'s module doc).
    """
    return _temper_drc_rs.resource_bound_compute_fill_factor_py(trace_width, list(bbox_areas.values()))


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

    # Compute per-net area
    bbox_areas: dict[str, float] = {}
    for name, bbox in net_bboxes.items():
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        bbox_areas[name] = max(w * h, 0.0)

    # Determine fill factor
    if fill_factor is None:
        fill_factor = _compute_fill_factor(trace_width, bbox_areas)

    # Compute demand per net
    demands: dict[str, float] = {n: bbox_areas[n] * fill_factor for n in net_bboxes}

    # Build conflict clusters
    clusters = _compute_conflict_clusters(net_bboxes)

    total_routable = 0
    cluster_details: list[dict] = []

    for cluster in clusters:
        union_bbox = _cluster_union_bbox(cluster, net_bboxes)
        capacity = _capacity_in_bbox(edt_grid, union_bbox)

        cluster_demands = sorted(demands[n] for n in cluster)
        running = 0.0
        k = 0
        for d in cluster_demands:
            if running + d > capacity:
                break
            running += d
            k += 1

        total_routable += k
        cluster_details.append(
            {
                "size": len(cluster),
                "capacity": capacity,
                "routable": k,
                "demands": cluster_demands[:k] if k else [],
            }
        )

    logger.info(
        "Resource bound: %d/%d nets routable (fill_factor=%.3f, trace_width=%.3f mm, %d clusters)",
        total_routable,
        len(net_bboxes),
        fill_factor,
        trace_width,
        len(clusters),
    )
    logger.debug("Resource bound cluster details: %s", cluster_details)

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

    bbox_areas = {}
    for name, bbox in net_bboxes.items():
        bbox_areas[name] = max((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]), 0.0)

    if fill_factor is None:
        fill_factor = _compute_fill_factor(trace_width, bbox_areas)

    demands = {n: bbox_areas[n] * fill_factor for n in net_bboxes}
    clusters = _compute_conflict_clusters(net_bboxes)

    total_capacity = 0.0
    total_demand = sum(demands.values())
    total_routable = 0

    for cluster in clusters:
        union_bbox = _cluster_union_bbox(cluster, net_bboxes)
        capacity = _capacity_in_bbox(edt_grid, union_bbox)
        total_capacity += capacity

        cluster_demands = sorted(demands[n] for n in cluster)
        running = 0.0
        k = 0
        for d in cluster_demands:
            if running + d > capacity:
                break
            running += d
            k += 1
        total_routable += k

    return {
        "max_routable": total_routable,
        "total_nets": len(net_bboxes),
        "fill_factor": fill_factor,
        "cluster_count": len(clusters),
        "total_capacity_mm2": total_capacity,
        "total_demand_mm2": total_demand,
        "utilization": total_demand / max(total_capacity, 1e-6),
    }
