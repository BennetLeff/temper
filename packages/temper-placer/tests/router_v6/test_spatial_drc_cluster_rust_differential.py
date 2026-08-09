"""Differential tests: Rust spatial-DRC cluster kernels vs the pre-migration
pure-Python reference.

The kernels migrated to ``temper-geometry`` (Wave 4):

- ``resource_bound.py`` — bbox conflict clustering, cluster union bbox,
  capacity-in-bbox, fill factor, and the bin-packing ``max_routable_nets`` /
  ``demand_budget_summary`` bounds (pinned via ``_oracle_*`` copies).
- ``power_plane.py`` — rect corners, isolated pour-strip partition, and the
  thermal-via NxN grid (pinned via ``_oracle_*`` copies).
- ``diff_pair_inference.py`` — the three-pass suffix matcher (pinned via
  ``_oracle_infer_differential_pairs``).
- ``trace_width_assignment.py`` — ``_kw_boundary_match`` and
  ``_determine_trace_width`` (pinned via ``_oracle_*`` copies).
- ``dense_package_detection.py`` — ``_estimate_pitch`` and
  ``_infer_package_type`` (pinned via ``_oracle_*`` copies).

All comparisons are bit-exact: floats are compared with ``==`` (equal bit
patterns) and, for the computed values, also via ``float.hex()`` where the
reference does real arithmetic.  Cluster lists are compared in the
normalized form (each cluster's contents sorted) because the reference's
intra-cluster order is Python-set-iteration (hash-seed) dependent; every
downstream consumer is order-independent, which the resource-bound tests
pin by comparing the aggregated bounds exactly.
"""

from __future__ import annotations

import logging
import math
import random
import re
from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np
import pytest

from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.resource_bound import (
    _capacity_in_bbox,
    _cluster_union_bbox,
    _compute_conflict_clusters,
    _compute_fill_factor,
    demand_budget_summary,
    max_routable_nets,
)
from temper_placer.router_v6.power_plane import (
    CopperPour,
    DEFAULT_POWER_DOMAINS,
    _rect_polygon,
    _thermal_via_positions,
    generate_ground_pour,
    generate_power_pours,
)
from temper_placer.router_v6.diff_pair_inference import infer_differential_pairs
from temper_placer.router_v6.trace_width_assignment import (
    TraceWidth,
    _determine_trace_width,
    _kw_boundary_match,
)
from temper_placer.router_v6.dense_package_detection import (
    _estimate_pitch,
    _infer_package_type,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Verbatim pre-migration oracles (copied from the modules AS COMMITTED
# before the Wave 4 spatial-DRC migration; do not edit — they are the
# reference).
# ---------------------------------------------------------------------------
# resource_bound.py


def _oracle_compute_conflict_clusters(
    bboxes: dict[str, tuple[float, float, float, float]],
    overlap_threshold: float = 0.1,
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


def _oracle_cluster_union_bbox(
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


def _oracle_capacity_in_bbox(
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


def _oracle_compute_fill_factor(
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


def _oracle_max_routable_nets(
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
        fill_factor = _oracle_compute_fill_factor(trace_width, bbox_areas)

    # Compute demand per net
    demands: dict[str, float] = {n: bbox_areas[n] * fill_factor for n in net_bboxes}

    # Build conflict clusters
    clusters = _oracle_compute_conflict_clusters(net_bboxes)

    total_routable = 0
    cluster_details: list[dict] = []

    for cluster in clusters:
        union_bbox = _oracle_cluster_union_bbox(cluster, net_bboxes)
        capacity = _oracle_capacity_in_bbox(edt_grid, union_bbox)

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


def _oracle_demand_budget_summary(
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
        fill_factor = _oracle_compute_fill_factor(trace_width, bbox_areas)

    demands = {n: bbox_areas[n] * fill_factor for n in net_bboxes}
    clusters = _oracle_compute_conflict_clusters(net_bboxes)

    total_capacity = 0.0
    total_demand = sum(demands.values())
    total_routable = 0

    for cluster in clusters:
        union_bbox = _oracle_cluster_union_bbox(cluster, net_bboxes)
        capacity = _oracle_capacity_in_bbox(edt_grid, union_bbox)
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


# power_plane.py


def _oracle_board_bounds(board) -> tuple[float, float, float, float]:
    """Return the board copper extent as (x_min, y_min, x_max, y_max)."""
    ox, oy = board.origin
    return (ox, oy, ox + board.width, oy + board.height)


def _oracle_rect_polygon(
    bounds: tuple[float, float, float, float],
) -> list[tuple[float, float]]:
    """Return the 4 corners of an axis-aligned rectangle (CCW)."""
    x_min, y_min, x_max, y_max = bounds
    return [
        (x_min, y_min),
        (x_max, y_min),
        (x_max, y_max),
        (x_min, y_max),
    ]


def _oracle_generate_ground_pour(board, layer: str = "In1.Cu") -> CopperPour:
    """Generate one solid GND copper pour covering the full board on ``layer``."""
    bounds = _oracle_board_bounds(board)
    return CopperPour(
        net="GND",
        layer=layer,
        bounds=bounds,
        polygon=_oracle_rect_polygon(bounds),
        is_ground=True,
    )


def _oracle_generate_power_pours(
    board,
    domains: list[str] | tuple[str, ...] | None = None,
    layer: str = "In2.Cu",
    *,
    isolation_gap_mm: float = 0.3,
) -> list[CopperPour]:
    """Generate isolated per-domain copper pours on ``layer`` (In2.Cu)."""
    resolved = tuple(domains) if domains is not None else DEFAULT_POWER_DOMAINS
    if not resolved:
        return []
    if isolation_gap_mm < 0:
        raise ValueError(f"isolation_gap_mm must be >= 0, got {isolation_gap_mm}")

    x_min, y_min, x_max, y_max = _oracle_board_bounds(board)
    n = len(resolved)
    total_width = x_max - x_min
    total_gap = isolation_gap_mm * (n - 1)
    strip_width = (total_width - total_gap) / n
    if strip_width <= 0:
        raise ValueError(
            f"Board too narrow ({total_width}mm) for {n} isolated pours "
            f"with {isolation_gap_mm}mm gaps"
        )

    pours: list[CopperPour] = []
    for i, net in enumerate(resolved):
        strip_x_min = x_min + i * (strip_width + isolation_gap_mm)
        strip_x_max = strip_x_min + strip_width
        bounds = (strip_x_min, y_min, strip_x_max, y_max)
        pours.append(
            CopperPour(
                net=net,
                layer=layer,
                bounds=bounds,
                polygon=_oracle_rect_polygon(bounds),
            )
        )
    return pours


def _oracle_thermal_via_positions(
    center: tuple[float, float],
    count: int,
    pitch_mm: float,
) -> list[tuple[float, float]]:
    """Return an NxN grid of via centres around ``center``."""
    side = int(round(count**0.5))
    if side * side != count:
        raise ValueError(f"count must be a perfect square, got {count}")

    cx, cy = center
    span = (side - 1) * pitch_mm
    x0 = cx - span / 2.0
    y0 = cy - span / 2.0
    return [
        (x0 + col * pitch_mm, y0 + row * pitch_mm) for row in range(side) for col in range(side)
    ]


# diff_pair_inference.py


@dataclass
class _OracleDiffPair:
    """A differential pair of nets."""

    base_name: str  # "USB_D", "CLK", etc.
    p_net: str  # Positive net: "USB_D+", "CLK_P"
    n_net: str  # Negative net: "USB_D-", "CLK_N"

    def __post_init__(self):
        """Validate differential pair."""
        if self.p_net == self.n_net:
            raise ValueError(f"Differential pair nets must be different: {self.p_net}")

    @property
    def positive_net(self) -> str:
        """Alias for p_net for API compatibility."""
        return self.p_net

    @property
    def negative_net(self) -> str:
        """Alias for n_net for API compatibility."""
        return self.n_net


def _oracle_infer_differential_pairs(net_names: list[str]) -> list[_OracleDiffPair]:
    """Infer differential pairs from net naming conventions."""
    # Normalize net names to uppercase for matching
    net_map = {name.upper(): name for name in net_names}
    net_set = set(net_map.keys())

    pairs = []
    matched_nets = set()

    # Pattern 1: +/- suffix (USB_D+, USB_D-)
    for net in net_names:
        upper = net.upper()
        if upper in matched_nets:
            continue

        if upper.endswith("+"):
            base = upper[:-1]
            neg_candidate = base + "-"
            if neg_candidate in net_set:
                pairs.append(
                    _OracleDiffPair(
                        base_name=base,
                        p_net=net_map[upper],
                        n_net=net_map[neg_candidate],
                    )
                )
                matched_nets.add(upper)
                matched_nets.add(neg_candidate)

    # Pattern 2: DP/DN suffix (check BEFORE _P/_N to avoid USB_DP matching as USB_D_P)
    for net in net_names:
        upper = net.upper()
        if upper in matched_nets:
            continue

        # Match patterns like: USB_DP, USBDP, ETH_DP
        if upper.endswith("_DP"):
            base = upper[:-3]  # Remove _DP
            neg_candidate = base + "_DN"
            if neg_candidate in net_set:
                pairs.append(
                    _OracleDiffPair(
                        base_name=base,
                        p_net=net_map[upper],
                        n_net=net_map[neg_candidate],
                    )
                )
                matched_nets.add(upper)
                matched_nets.add(neg_candidate)
        elif upper.endswith("DP") and not upper.endswith("_DP") and len(upper) > 2:
            # Handle USBDP (no underscore)
            base = upper[:-2]  # Remove DP
            neg_candidate = base + "DN"
            if neg_candidate in net_set:
                pairs.append(
                    _OracleDiffPair(
                        base_name=base,
                        p_net=net_map[upper],
                        n_net=net_map[neg_candidate],
                    )
                )
                matched_nets.add(upper)
                matched_nets.add(neg_candidate)

    # Pattern 3: _P / _N suffix (after DP/DN check)
    for net in net_names:
        upper = net.upper()
        if upper in matched_nets:
            continue

        if upper.endswith("_P"):
            base = upper[:-2]
            neg_candidate = base + "_N"
            if neg_candidate in net_set:
                pairs.append(
                    _OracleDiffPair(
                        base_name=base,
                        p_net=net_map[upper],
                        n_net=net_map[neg_candidate],
                    )
                )
                matched_nets.add(upper)
                matched_nets.add(neg_candidate)
        elif (
            upper.endswith("P")
            and not upper.endswith("_P")
            and not upper.endswith("DP")
            and len(upper) > 1
        ):
            # Match P suffix without underscore (but not DP)
            base = upper[:-1]
            neg_candidate = base + "N"
            if neg_candidate in net_set:
                pairs.append(
                    _OracleDiffPair(
                        base_name=base,
                        p_net=net_map[upper],
                        n_net=net_map[neg_candidate],
                    )
                )
                matched_nets.add(upper)
                matched_nets.add(neg_candidate)

    return pairs


# trace_width_assignment.py


def _oracle_kw_boundary_match(upper: str, keywords: tuple[str, ...]) -> bool:
    """Word-boundary keyword match, delimited by "_" or start/end of the
    uppercased net name."""
    for kw in keywords:
        kw = kw[:-1] if kw.endswith("_") else kw
        if re.search(rf"(?:^|_){re.escape(kw)}(?:$|[\d_])", upper):
            return True
    return False


def _oracle_determine_trace_width(
    net_name: str,
    default_width: float,
    power_width: float,
    hv_width: float,
) -> TraceWidth:
    """Determine appropriate trace width for a net."""
    name_upper = net_name.upper()

    # High voltage nets (AC, HV)
    if _oracle_kw_boundary_match(name_upper, ("AC_", "HV_", "HIGH_VOLTAGE")):
        return TraceWidth(
            net_name=net_name,
            width_mm=hv_width,
            reason="High voltage net requires wider trace",
        )

    # Power nets (GND, VCC, etc.)
    if _oracle_kw_boundary_match(name_upper, ("GND", "VCC", "VDD", "VSS", "POWER")) or re.search(
        r"^\+", name_upper
    ):
        return TraceWidth(
            net_name=net_name,
            width_mm=power_width,
            reason="Power net requires wider trace for current capacity",
        )

    # Gate drive signals (medium current)
    if _oracle_kw_boundary_match(name_upper, ("GATE", "DRIVE")):
        return TraceWidth(
            net_name=net_name,
            width_mm=power_width * 0.6,  # 60% of power width
            reason="Gate drive signal requires medium-width trace",
        )

    # Default signal nets
    return TraceWidth(
        net_name=net_name,
        width_mm=default_width,
        reason="Standard signal trace",
    )


# dense_package_detection.py


def _oracle_estimate_pitch(comp) -> float:
    """Estimate pin pitch from footprint name or pin positions.

    Tries in order:
    1. Parse from footprint name (e.g., "QFN-48_0.5mm" -> 0.5mm)
    2. Calculate from actual pin positions
    """
    import re

    # Try to parse pitch from footprint name
    # Common patterns: QFN-48_0.5mm, TQFP-100_0.4mm, BGA-256_0.8mm
    footprint_upper = comp.footprint.upper()

    # Pattern: _0.5MM or _0.5
    match = re.search(r"[_-](\d+\.?\d*)\s*MM", footprint_upper)
    if match:
        return float(match.group(1))

    match = re.search(r"[_P](\d+\.?\d*)(?:[_-]|$)", comp.footprint)
    if match:
        pitch_str = match.group(1)
        try:
            pitch = float(pitch_str)
            # If it's > 10, it's probably in mil (e.g., _50 = 50mil = 1.27mm)
            if pitch > 10:
                pitch = pitch * 0.0254  # mil to mm
            return pitch
        except ValueError:
            pass

    # Fallback: Calculate from pin positions
    if len(comp.pins) >= 4:
        # Find minimum distance between adjacent pins
        pin_positions = [p.position for p in comp.pins]
        min_dist = float("inf")

        for i, (x1, y1) in enumerate(pin_positions):
            for j, (x2, y2) in enumerate(pin_positions):
                if i >= j:
                    continue
                dist = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
                if dist > 0.01:  # Ignore near-zero distances (same pin)
                    min_dist = min(min_dist, dist)

        if min_dist != float("inf"):
            return min_dist

    # Default: 0.65mm (common SOIC/TQFP pitch)
    return 0.65


def _oracle_infer_package_type(comp) -> str:
    """Infer package type from footprint name."""
    footprint_upper = comp.footprint.upper()

    # Check for common package types
    package_types = [
        "BGA",
        "FBGA",
        "LFBGA",
        "TFBGA",  # Ball grid arrays
        "QFN",
        "DFN",
        "SON",  # Quad flat no-lead
        "TQFP",
        "LQFP",
        "QFP",  # Quad flat packages
        "SOIC",
        "SOP",
        "SSOP",
        "TSSOP",  # Small outline
        "TO-",
        "SOT-",  # Transistor outlines
    ]

    for pkg_type in package_types:
        if pkg_type in footprint_upper:
            # Return the base type (e.g., "BGA" not "FBGA")
            if "BGA" in pkg_type:
                return "BGA"
            elif "QFN" in pkg_type or "DFN" in pkg_type or "SON" in pkg_type:
                return "QFN"
            elif "QFP" in pkg_type:
                return "TQFP"
            elif "SOIC" in pkg_type or "SOP" in pkg_type:
                return "SOIC"
            elif "TO-" in pkg_type or "SOT-" in pkg_type:
                return "SOT"
            return pkg_type

    # Default: Unknown
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _make_grid(
    rng: random.Random,
    width_cells: int,
    height_cells: int,
    cell_size: float,
    origin: tuple[float, float],
    blocked_ratio: float = 0.0,
) -> OccupancyGrid:
    grid = np.zeros((height_cells, width_cells), dtype=np.int8)
    if blocked_ratio >= 1.0:
        grid[:] = 1
    elif blocked_ratio > 0:
        n_block = int(width_cells * height_cells * blocked_ratio)
        placed = 0
        while placed < n_block:
            x = rng.randrange(width_cells)
            y = rng.randrange(height_cells)
            if grid[y, x] == 0:
                grid[y, x] = 1
                placed += 1
    return OccupancyGrid(
        layer_name="F.Cu",
        grid=grid,
        origin=origin,
        cell_size=cell_size,
        width_cells=width_cells,
        height_cells=height_cells,
    )


def _random_bboxes(rng: random.Random, n: int) -> dict[str, tuple[float, float, float, float]]:
    bboxes: dict[str, tuple[float, float, float, float]] = {}
    for i in range(n):
        x1 = rng.uniform(-5.0, 50.0)
        y1 = rng.uniform(-5.0, 50.0)
        w = rng.choice([0.0, rng.uniform(0.0, 8.0)])
        h = rng.choice([0.0, rng.uniform(0.0, 8.0)])
        bboxes[f"N{i}"] = (x1, y1, x1 + w, y1 + h)
    return bboxes


def _comp(footprint: str, positions: list[tuple[float, float]]) -> SimpleNamespace:
    pins = [SimpleNamespace(position=p) for p in positions]
    return SimpleNamespace(footprint=footprint, pins=pins)


# ---------------------------------------------------------------------------
# resource_bound differential
# ---------------------------------------------------------------------------


def test_conflict_clusters_match_reference_on_randomized_bboxes() -> None:
    rng = random.Random(20260808)
    for _ in range(60):
        n = rng.randrange(0, 12)
        bboxes = _random_bboxes(rng, n)
        shim = _compute_conflict_clusters(bboxes)
        oracle = _oracle_compute_conflict_clusters(bboxes)
        # intra-cluster order is hash-seed dependent in the reference; the
        # normalized (sorted-within) form and the outer discovery order are
        # deterministic and equal.
        assert shim == [sorted(c) for c in oracle], f"mismatch on {bboxes}"


def test_conflict_clusters_match_reference_on_edge_cases() -> None:
    cases: list[dict[str, tuple[float, float, float, float]]] = [
        {},
        {"A": (0.0, 0.0, 5.0, 5.0)},
        {"A": (0.0, 0.0, 5.0, 5.0), "B": (10.0, 10.0, 15.0, 15.0)},
        {"A": (0.0, 0.0, 10.0, 10.0), "B": (1.0, 1.0, 9.0, 9.0), "C": (2.0, 2.0, 8.0, 8.0)},
        {"A": (0.0, 0.0, 5.0, 5.0), "B": (3.0, 3.0, 8.0, 8.0), "C": (6.0, 6.0, 11.0, 11.0)},
        # zero-area nets never conflict -> their own singleton clusters
        {"A": (0.0, 0.0, 0.0, 5.0), "B": (0.0, 0.0, 5.0, 5.0)},
    ]
    for bboxes in cases:
        shim = _compute_conflict_clusters(bboxes)
        oracle = _oracle_compute_conflict_clusters(bboxes)
        assert shim == [sorted(c) for c in oracle], f"mismatch on {bboxes}"
        # cluster membership sanity: partition
        all_nets = [n for c in shim for n in c]
        assert sorted(all_nets) == sorted(bboxes.keys())


def test_cluster_union_bbox_matches_reference() -> None:
    rng = random.Random(20260809)
    for _ in range(40):
        bboxes = _random_bboxes(rng, rng.randrange(0, 8))
        clusters = _oracle_compute_conflict_clusters(bboxes)
        for cluster in clusters:
            shim = _cluster_union_bbox(cluster, bboxes)
            oracle = _oracle_cluster_union_bbox(cluster, bboxes)
            assert shim == oracle, f"mismatch cluster={cluster} bboxes={bboxes}"
    assert _cluster_union_bbox([], {}) == (0.0, 0.0, 0.0, 0.0)


def test_capacity_in_bbox_matches_reference() -> None:
    rng = random.Random(20260810)
    total = 0
    for _ in range(40):
        w = rng.choice([1, 2, 5, 10, 25])
        h = rng.choice([1, 2, 5, 10, 25])
        og = _make_grid(rng, w, h, rng.choice([0.1, 0.5, 1.0]), (rng.uniform(-3, 3), rng.uniform(-3, 3)), blocked_ratio=rng.choice([0.0, 0.3, 1.0]))
        for _ in range(5):
            bbox = (
                rng.uniform(-10.0, 30.0),
                rng.uniform(-10.0, 30.0),
                rng.uniform(-10.0, 30.0),
                rng.uniform(-10.0, 30.0),
            )
            total += 1
            shim = _capacity_in_bbox(og, bbox)
            oracle = _oracle_capacity_in_bbox(og, bbox)
            assert shim == oracle, f"mismatch bbox={bbox} grid={og.width_cells}x{og.height_cells}"
    assert total >= 150


def test_fill_factor_matches_reference() -> None:
    rng = random.Random(20260811)
    for _ in range(60):
        n = rng.randrange(0, 8)
        areas = {f"N{i}": rng.uniform(0.0, 200.0) for i in range(n)}
        tw = rng.uniform(0.05, 2.0)
        shim = _compute_fill_factor(tw, areas)
        oracle = _oracle_compute_fill_factor(tw, areas)
        assert shim == oracle, f"mismatch areas={areas} tw={tw}"
    assert _compute_fill_factor(0.2, {}) == 0.5
    assert _compute_fill_factor(0.2, {"A": 0.0, "B": 0.0}) == 0.5


def test_max_routable_matches_reference() -> None:
    rng = random.Random(20260812)
    total = 0
    for _ in range(50):
        og = _make_grid(
            rng,
            rng.choice([2, 5, 10, 20]),
            rng.choice([2, 5, 10, 20]),
            rng.choice([0.1, 0.5, 1.0]),
            (rng.uniform(-2, 2), rng.uniform(-2, 2)),
            blocked_ratio=rng.choice([0.0, 0.2, 1.0]),
        )
        bboxes = _random_bboxes(rng, rng.randrange(0, 10))
        tw = rng.uniform(0.1, 0.6)
        use_explicit = rng.random() < 0.5
        ff = rng.choice([0.01, 0.1, 0.5, 1.0]) if use_explicit else None
        total += 1
        shim = max_routable_nets(og, bboxes, tw, fill_factor=ff)
        oracle = _oracle_max_routable_nets(og, bboxes, tw, fill_factor=ff)
        assert shim == oracle, f"mismatch bboxes={bboxes} grid={og.width_cells}x{og.height_cells} tw={tw} ff={ff}"
    assert total >= 40
    # empty bboxes
    og = _make_grid(rng, 5, 5, 1.0, (0.0, 0.0))
    assert max_routable_nets(og, {}, 0.2) == _oracle_max_routable_nets(og, {}, 0.2) == 0


def test_demand_budget_matches_reference_bit_exact() -> None:
    rng = random.Random(20260813)
    for _ in range(50):
        og = _make_grid(
            rng,
            rng.choice([2, 5, 10]),
            rng.choice([2, 5, 10]),
            rng.choice([0.1, 0.5, 1.0]),
            (rng.uniform(-2, 2), rng.uniform(-2, 2)),
            blocked_ratio=rng.choice([0.0, 0.3, 1.0]),
        )
        bboxes = _random_bboxes(rng, rng.randrange(0, 9))
        tw = rng.uniform(0.1, 0.6)
        use_explicit = rng.random() < 0.5
        ff = rng.choice([0.01, 0.5, 1.0]) if use_explicit else None
        shim = demand_budget_summary(og, bboxes, tw, fill_factor=ff)
        oracle = _oracle_demand_budget_summary(og, bboxes, tw, fill_factor=ff)
        assert shim == oracle, f"mismatch bboxes={bboxes} tw={tw} ff={ff}"
    # empty bboxes
    og = _make_grid(rng, 5, 5, 1.0, (0.0, 0.0))
    assert demand_budget_summary(og, {}, 0.2) == _oracle_demand_budget_summary(og, {}, 0.2)


# ---------------------------------------------------------------------------
# power_plane differential
# ---------------------------------------------------------------------------


def _board(origin, width, height) -> SimpleNamespace:
    return SimpleNamespace(origin=origin, width=width, height=height)


def test_rect_polygon_matches_reference() -> None:
    rng = random.Random(20260814)
    for _ in range(40):
        bounds = tuple(rng.uniform(-20.0, 20.0) for _ in range(4))
        x_min, y_min, x_max, y_max = bounds
        if x_min > x_max:
            x_min, x_max = x_max, x_min
        if y_min > y_max:
            y_min, y_max = y_max, y_min
        bounds = (x_min, y_min, x_max, y_max)
        shim = _rect_polygon(bounds)
        oracle = _oracle_rect_polygon(bounds)
        assert shim == oracle, f"mismatch bounds={bounds}"


def test_power_pours_match_reference() -> None:
    rng = random.Random(20260815)
    for _ in range(50):
        board = _board((rng.uniform(-5, 5), rng.uniform(-5, 5)), rng.uniform(5.0, 60.0), rng.uniform(5.0, 40.0))
        domains = tuple(f"+{i}V" for i in range(rng.choice([1, 2, 3, 4, 5])))
        gap = rng.choice([0.0, 0.1, 0.3, 0.5])
        shim = generate_power_pours(board, domains, isolation_gap_mm=gap)
        oracle = _oracle_generate_power_pours(board, domains, isolation_gap_mm=gap)
        assert [(p.net, p.layer, p.bounds, p.polygon) for p in shim] == [
            (p.net, p.layer, p.bounds, p.polygon) for p in oracle
        ]
    # defaults + empty domains
    board = _board((0.0, 0.0), 100.0, 50.0)
    shim = generate_power_pours(board)
    oracle = _oracle_generate_power_pours(board)
    assert [(p.net, p.layer, p.bounds, p.polygon) for p in shim] == [
        (p.net, p.layer, p.bounds, p.polygon) for p in oracle
    ]
    assert generate_power_pours(board, []) == _oracle_generate_power_pours(board, []) == []


def test_power_pours_errors_match_reference_messages() -> None:
    board = _board((0.0, 0.0), 10.0, 10.0)
    with pytest.raises(ValueError) as ei:
        generate_power_pours(board, ("A", "B", "C"), isolation_gap_mm=-0.3)
    with pytest.raises(ValueError) as ej:
        _oracle_generate_power_pours(board, ("A", "B", "C"), isolation_gap_mm=-0.3)
    assert str(ei.value) == str(ej.value) == "isolation_gap_mm must be >= 0, got -0.3"

    narrow = _board((0.0, 0.0), 0.5, 10.0)
    with pytest.raises(ValueError) as ei:
        generate_power_pours(narrow, ("A", "B", "C"), isolation_gap_mm=0.3)
    with pytest.raises(ValueError) as ej:
        _oracle_generate_power_pours(narrow, ("A", "B", "C"), isolation_gap_mm=0.3)
    assert str(ei.value) == str(ej.value) == (
        "Board too narrow (0.5mm) for 3 isolated pours with 0.3mm gaps"
    )


def test_ground_pour_matches_reference() -> None:
    rng = random.Random(20260816)
    for _ in range(30):
        board = _board((rng.uniform(-10, 10), rng.uniform(-10, 10)), rng.uniform(1.0, 100.0), rng.uniform(1.0, 100.0))
        layer = rng.choice(["In1.Cu", "F.Cu"])
        shim = generate_ground_pour(board, layer=layer)
        oracle = _oracle_generate_ground_pour(board, layer=layer)
        assert (shim.net, shim.layer, shim.bounds, shim.polygon, shim.is_ground) == (
            oracle.net,
            oracle.layer,
            oracle.bounds,
            oracle.polygon,
            oracle.is_ground,
        )


def test_thermal_via_positions_match_reference() -> None:
    rng = random.Random(20260817)
    counts = [1, 4, 9, 16, 25]
    for _ in range(40):
        count = rng.choice(counts)
        center = (rng.uniform(-50.0, 50.0), rng.uniform(-50.0, 50.0))
        pitch = rng.choice([0.5, 1.0, 1.2, 2.5])
        shim = _thermal_via_positions(center, count, pitch)
        oracle = _oracle_thermal_via_positions(center, count, pitch)
        assert shim == oracle, f"mismatch center={center} count={count} pitch={pitch}"
    # non-square counts raise identical messages
    for bad in (2, 3, 5, 6, 7, 8, 10):
        with pytest.raises(ValueError) as ei:
            _thermal_via_positions((0.0, 0.0), bad, 1.0)
        with pytest.raises(ValueError) as ej:
            _oracle_thermal_via_positions((0.0, 0.0), bad, 1.0)
        assert str(ei.value) == str(ej.value) == f"count must be a perfect square, got {bad}"


# ---------------------------------------------------------------------------
# diff_pair differential
# ---------------------------------------------------------------------------


def test_infer_pairs_match_reference_on_randomized_lists() -> None:
    rng = random.Random(20260818)
    pool = [
        "USB_D+", "USB_D-", "USB_DP", "USB_DN", "USBDP", "USBDN",
        "CLK_P", "CLK_N", "TX+", "TX-", "GND", "3V3", "SIG_1",
        "ETH_DP", "ETH_DN", "LVDS_P", "LVDS_N", "DIGP", "DIGN",
        "USB_P", "USB_N", "AC_L", "HV_DC", "AUDIO_L", "AUDIO_R",
    ]
    for _ in range(80):
        k = rng.randrange(0, 12)
        names = [rng.choice(pool) for _ in range(k)]
        if rng.random() < 0.3:
            names = [n.lower() if rng.random() < 0.5 else n for n in names]
        shim = [(p.base_name, p.p_net, p.n_net) for p in infer_differential_pairs(names)]
        oracle = [
            (p.base_name, p.p_net, p.n_net) for p in _oracle_infer_differential_pairs(names)
        ]
        assert shim == oracle, f"mismatch names={names}"


def test_infer_pairs_match_reference_on_pattern_cases() -> None:
    cases = [
        ["USB_D+", "USB_D-", "GND", "3V3"],
        ["CLK_P", "CLK_N"],
        ["LVDS_TX_P", "LVDS_TX_N"],
        ["TX+", "TX-"],
        ["dp", "dn"],
        ["USB_DP", "USB_DN", "USB_P", "USB_N"],
        ["DIGP", "DIGN"],
        ["SIG"],
        [],
        ["GND", "3V3", "SIG1"],
        ["USB_DP", "USB_DN", "USB_DP"],
    ]
    for names in cases:
        shim = [(p.base_name, p.p_net, p.n_net) for p in infer_differential_pairs(names)]
        oracle = [(p.base_name, p.p_net, p.n_net) for p in _oracle_infer_differential_pairs(names)]
        assert shim == oracle, f"mismatch names={names}"


# ---------------------------------------------------------------------------
# trace_width differential
# ---------------------------------------------------------------------------


def test_kw_boundary_match_matches_reference() -> None:
    rng = random.Random(20260819)
    kwsets = [("AC_", "HV_", "HIGH_VOLTAGE"), ("GND", "VCC", "VDD", "VSS", "POWER"), ("GATE", "DRIVE")]
    names = [
        "AC_L", "HV", "HV_DC", "3V3_HV", "HIGH_VOLTAGE_SIDE", "NONHV", "HVX",
        "GND", "VCC", "VDD_1", "POWER", "+5V", "SIGND", "GNDX",
        "GATE_HS", "GATE", "DRIVE", "IGATE", "GATE2",
        "SIG_1", "USB_D-", "DC_BUS+", "MISC",
    ]
    for name in names:
        upper = name.upper()
        for kws in kwsets:
            shim = _kw_boundary_match(upper, kws)
            oracle = _oracle_kw_boundary_match(upper, kws)
            assert shim == oracle, f"mismatch upper={upper} kws={kws}"
    for _ in range(40):
        upper = "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ_+-0123456789") for _ in range(rng.randrange(1, 14)))
        kws = tuple(rng.sample(["AC_", "HV_", "HIGH_VOLTAGE", "GND", "VCC", "VDD", "VSS", "POWER", "GATE", "DRIVE"], rng.randrange(0, 5)))
        assert _kw_boundary_match(upper, kws) == _oracle_kw_boundary_match(upper, kws), f"mismatch upper={upper} kws={kws}"


def test_determine_trace_width_matches_reference() -> None:
    names = [
        "AC_L", "AC", "HV", "HV_MAINS", "3V3_HV", "HIGH_VOLTAGE", "NONHV", "HVX",
        "GND", "VCC", "VDD", "VSS", "POWER", "DC_POWER", "+5V", "+", "SIGND",
        "GATE_HS", "GATE", "DRIVE", "GATE1", "IGATE", "GATE_X",
        "SIG_1", "USB_D-", "DC_BUS+", "R41", "Q1_COLLECTOR",
    ]
    params_list = [
        (0.127, 0.508, 0.635),
        (0.1, 0.3, 0.7),
        (0.2, 0.4, 0.6),
    ]
    for net in names:
        for default_width, power_width, hv_width in params_list:
            shim = _determine_trace_width(net, default_width, power_width, hv_width)
            oracle = _oracle_determine_trace_width(net, default_width, power_width, hv_width)
            assert shim.net_name == oracle.net_name
            assert shim.reason == oracle.reason, f"mismatch reason net={net}"
            assert shim.width_mm == oracle.width_mm, f"mismatch width net={net}"
            assert shim.width_mm.hex() == oracle.width_mm.hex(), f"mismatch hex net={net}"


# ---------------------------------------------------------------------------
# dense_package differential
# ---------------------------------------------------------------------------


def test_estimate_pitch_matches_reference() -> None:
    rng = random.Random(20260820)
    footprints = [
        "QFN-48_0.5mm", "TQFP-100_0.4mm", "BGA-256_0.8mm", "SOIC-16_1.27mm",
        "X_50", "X_0.5", "QFP-64_0.3MM", "LQFP-48_0.65", "CUSTOM", "0805",
        "QFN-32_0.5", "BGA_1.0MM", "TSSOP_0.65MM",
    ]
    for fp in footprints:
        comp = _comp(fp, [])
        assert _estimate_pitch(comp) == _oracle_estimate_pitch(comp), f"mismatch fp={fp}"
    for _ in range(40):
        n = rng.choice([0, 2, 4, 6])
        positions = [
            (rng.uniform(-10.0, 10.0), rng.uniform(-10.0, 10.0)) for _ in range(n)
        ]
        comp = _comp(rng.choice(footprints), positions)
        shim = _estimate_pitch(comp)
        oracle = _oracle_estimate_pitch(comp)
        assert shim == oracle, f"mismatch fp={comp.footprint} positions={positions}"
        assert shim.hex() == oracle.hex()


def test_estimate_pitch_overflow_raises_like_reference() -> None:
    positions = [(0.0, 0.0), (1e308, 0.0), (1e308, 1e308), (0.0, 1e308)]
    comp = _comp("CUSTOM", positions)
    with pytest.raises(OverflowError):
        _oracle_estimate_pitch(comp)
    with pytest.raises(OverflowError):
        _estimate_pitch(comp)


def test_infer_package_type_matches_reference() -> None:
    footprints = [
        "QFN-48_0.5mm", "BGA-256_0.8mm", "FBGA-484", "LFBGA-169", "TFBGA-100",
        "DFN-8", "SON-12", "TQFP-100", "LQFP-64", "QFP-44", "SOIC-16", "SOP-8",
        "SSOP-28", "TSSOP-20", "TO-220", "SOT-23", "UNKNOWN_PKG", "0805",
        "qfn-16", "soic-8",
    ]
    for fp in footprints:
        comp = _comp(fp, [])
        assert _infer_package_type(comp) == _oracle_infer_package_type(comp), f"mismatch fp={fp}"


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------


def test_resource_bound_deterministic_across_runs() -> None:
    rng = random.Random(99)
    og = _make_grid(rng, 12, 12, 1.0, (0.0, 0.0), blocked_ratio=0.2)
    bboxes = _random_bboxes(rng, 8)
    a = max_routable_nets(og, bboxes, 0.2)
    b = max_routable_nets(og, bboxes, 0.2)
    assert a == b
