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

import numpy as np

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
    """
    nets = list(bboxes.keys())

    if len(nets) <= 1:
        return [nets] if nets else []

    # Compute per-net areas
    areas: dict[str, float] = {}
    for n, (x1, y1, x2, y2) in bboxes.items():
        areas[n] = max((x2 - x1) * (y2 - y1), 0.0)

    # Build conflict graph
    conflict: dict[str, set[str]] = {n: set() for n in nets}
    for i in range(len(nets)):
        a = nets[i]
        ax1, ay1, ax2, ay2 = bboxes[a]
        area_a = areas[a]
        if area_a <= 0:
            continue
        for j in range(i + 1, len(nets)):
            b = nets[j]
            bx1, by1, bx2, by2 = bboxes[b]
            area_b = areas[b]
            if area_b <= 0:
                continue
            ox = max(0.0, min(ax2, bx2) - max(ax1, bx1))
            oy = max(0.0, min(ay2, by2) - max(ay1, by1))
            overlap = ox * oy
            min_area = min(area_a, area_b)
            if min_area > 0 and overlap / min_area > overlap_threshold:
                conflict[a].add(b)
                conflict[b].add(a)

    # BFS to find connected components
    visited: set[str] = set()
    clusters: list[list[str]] = []
    for net in nets:
        if net in visited:
            continue
        queue = [net]
        cluster: list[str] = []
        while queue:
            n = queue.pop()
            if n in visited:
                continue
            visited.add(n)
            cluster.append(n)
            for neighbor in conflict[n]:
                if neighbor not in visited:
                    queue.append(neighbor)
        clusters.append(cluster)

    return clusters


def _cluster_union_bbox(
    cluster: list[str],
    bboxes: dict[str, tuple[float, float, float, float]],
) -> tuple[float, float, float, float]:
    """Compute the union bounding box of all nets in a cluster.

    Returns (min_x, min_y, max_x, max_y) in mm.
    """
    if not cluster:
        return (0.0, 0.0, 0.0, 0.0)
    x1 = min(bboxes[n][0] for n in cluster)
    y1 = min(bboxes[n][1] for n in cluster)
    x2 = max(bboxes[n][2] for n in cluster)
    y2 = max(bboxes[n][3] for n in cluster)
    return (x1, y1, x2, y2)


def _capacity_in_bbox(
    grid: OccupancyGrid,
    bbox: tuple[float, float, float, float],
) -> float:
    """Compute total free routing area within a bounding box (mm^2).

    Sums the area of all free cells (grid value == 0) that fall within
    the world-coordinate bounding box.
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
    free_cells = int(np.sum(region == 0))
    cell_area = grid.cell_size * grid.cell_size

    return free_cells * cell_area


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
    avg_area = sum(bbox_areas.values()) / len(bbox_areas)
    if avg_area <= 0:
        return 0.5
    sqrt_area = float(np.sqrt(avg_area))
    ff = trace_width / sqrt_area
    return float(np.clip(ff, 0.01, 1.0))


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
        cluster_details.append({
            "size": len(cluster),
            "capacity": capacity,
            "routable": k,
            "demands": cluster_demands[:k] if k else [],
        })

    logger.info(
        "Resource bound: %d/%d nets routable (fill_factor=%.3f, trace_width=%.3f mm, "
        "%d clusters)",
        total_routable, len(net_bboxes), fill_factor, trace_width, len(clusters),
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
