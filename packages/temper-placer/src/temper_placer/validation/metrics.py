"""
Placement quality metrics computation.

This module computes quality metrics for a placement without determining
pass/fail status. Useful for:
- Comparing different placements
- Tracking optimization progress
- Reporting final placement quality

``_compute_overlap_metrics``, ``_compute_clearance_metrics``,
``_compute_wirelength_metrics``'s numeric fold, and
``_compute_distribution_metrics`` run in ``temper-quality-oracle``'s Rust
kernels (``overlap_metrics_py`` / ``clearance_metrics_py`` /
``wirelength_metrics_py`` / ``distribution_metrics_py``, Wave 4); this
module keeps the public API, resolves the pyclass/dataclass fields the
kernels read into primitive arrays (a one-time attribute-read boundary,
not compute), and delegates. Bit-parity against the pre-migration
implementation is pinned by
``tests/validation/test_validation_metrics_rust_differential.py``
(oracle: ``tests/validation/_validation_metrics_py_oracle.py``).

``_compute_boundary_metrics``, ``_compute_zone_metrics`` and
``_compute_keepout_metrics`` are deliberately NOT ported:

- ``_compute_boundary_metrics`` / ``_compute_keepout_metrics`` both call
  ``get_rotated_bounds`` once per component -- already a Rust FFI crossing
  (``temper-geometry``). What's left per component is a handful of
  subtractions and a 4-way ``max`` (boundary) or a small loop over
  ``board.keepout_regions`` / ``board.mounting_holes`` (keepout) -- an
  ``O(n)`` loop dominated by an FFI call this module already makes, not
  worth a second one. Restructuring the call site to batch the rotated
  bounds first (so a kernel could consume them) would touch
  ``compute_metrics``'s shared orchestration for marginal gain.
- ``_compute_zone_metrics`` is dominated by ``board.get_zone(name)`` dict
  lookup and ``KeyError``-as-control-flow -- domain glue, not compute.

See ``packages/temper-quality-oracle/src/validation_metrics.rs`` for the
full bit-exactness catalog this migration measured (CPython ``max``/``min``
first-argument-on-tie semantics; CPython 3.12's compensated builtin
``sum()`` for ``avg_net_length``; and a NEP-50 *narrowing* -- not
promotion -- of ``_compute_distribution_metrics``'s arithmetic to float32,
since both ``state.positions`` and ``netlist.get_bounds_array()`` are
float32 with no float64 array anchor present).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TypeAlias

import numpy as np
import temper_quality_oracle as _qo

Array: TypeAlias = np.ndarray  # numpy alias replacing JAX Array post-JAX retirement

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.pad_identity import net_pin_occurrence_indices, nth_matching_pin
from temper_placer.core.pin_geometry import pin_world_position_at
from temper_placer.core.state import PlacementState
from temper_placer.geometry import (
    compute_pairwise_distances,
)
from temper_placer.geometry.transform import get_rotated_bounds


@dataclass
class PlacementMetrics:
    """
    Quality metrics for a placement.

    All distances/areas are in mm or mm².
    """

    # Overlap metrics
    overlap_count: int = 0  # Number of overlapping component pairs
    total_overlap_area: float = 0.0  # Sum of overlap amounts (mm)
    worst_overlap: float = 0.0  # Largest single overlap (mm)

    # Boundary metrics
    boundary_violations: int = 0  # Components outside board
    total_boundary_violation: float = 0.0  # Sum of violation amounts (mm)

    # Clearance metrics
    clearance_violations: int = 0  # Pairs too close together
    hv_lv_violations: int = 0  # HV-LV pairs violating 10mm clearance
    min_hv_lv_clearance: float = float("inf")  # Minimum HV-LV distance

    # Zone metrics
    zone_violations: int = 0  # Components in wrong zones

    # Keepout metrics
    keepout_violations: int = 0  # Components in keepout regions

    # Wirelength metrics
    total_wirelength: float = 0.0  # Half-perimeter wirelength (mm)
    max_net_length: float = 0.0  # Longest net (mm)
    avg_net_length: float = 0.0  # Average net length (mm)

    # Congestion metrics
    max_congestion: float = 0.0  # Maximum local congestion score
    avg_congestion: float = 0.0  # Average congestion

    # Distribution metrics
    utilization: float = 0.0  # Component area / board area
    spread_score: float = 0.0  # How spread out components are (higher = more spread)
    center_of_mass: tuple = (0.0, 0.0)  # Center of mass of all components

    # Timing
    computation_time_ms: float = 0.0

    def summary(self) -> str:
        """Get a human-readable summary of key metrics."""
        lines = [
            "=== Placement Metrics ===",
            f"Overlaps: {self.overlap_count} ({self.total_overlap_area:.2f}mm² total)",
            f"Boundary violations: {self.boundary_violations}",
            f"Clearance violations: {self.clearance_violations} (HV-LV: {self.hv_lv_violations})",
            f"Zone violations: {self.zone_violations}",
            f"Keepout violations: {self.keepout_violations}",
            f"Wirelength: {self.total_wirelength:.1f}mm (avg: {self.avg_net_length:.1f}mm)",
            f"Utilization: {self.utilization * 100:.1f}%",
            f"Computed in {self.computation_time_ms:.1f}ms",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "overlap_count": self.overlap_count,
            "total_overlap_area": self.total_overlap_area,
            "worst_overlap": self.worst_overlap,
            "boundary_violations": self.boundary_violations,
            "total_boundary_violation": self.total_boundary_violation,
            "clearance_violations": self.clearance_violations,
            "hv_lv_violations": self.hv_lv_violations,
            "min_hv_lv_clearance": self.min_hv_lv_clearance
            if self.min_hv_lv_clearance != float("inf")
            else None,
            "zone_violations": self.zone_violations,
            "keepout_violations": self.keepout_violations,
            "total_wirelength": self.total_wirelength,
            "max_net_length": self.max_net_length,
            "avg_net_length": self.avg_net_length,
            "max_congestion": self.max_congestion,
            "avg_congestion": self.avg_congestion,
            "utilization": self.utilization,
            "spread_score": self.spread_score,
            "center_of_mass": self.center_of_mass,
            "computation_time_ms": self.computation_time_ms,
        }

    @property
    def is_valid(self) -> bool:
        """Check if placement has no critical violations."""
        return (
            self.overlap_count == 0
            and self.boundary_violations == 0
            and self.hv_lv_violations == 0
            and self.keepout_violations == 0
        )


def compute_metrics(
    state: PlacementState,
    netlist: Netlist,
    board: Board,
    hv_lv_clearance: float = 10.0,
) -> PlacementMetrics:
    """
    Compute comprehensive placement quality metrics.

    Args:
        state: Current placement state.
        netlist: Component netlist.
        board: Board definition.
        hv_lv_clearance: Required HV-LV clearance in mm.

    Returns:
        PlacementMetrics with all computed values.
    """
    start_time = time.time()
    metrics = PlacementMetrics()

    # Extract component data
    positions = state.positions
    n_components = positions.shape[0]

    # Get rotation one-hot vectors
    rotation_indices = np.argmax(state.rotation_logits, axis=-1)
    rotations = np.eye(4)[rotation_indices]

    # Get component dimensions
    bounds = netlist.get_bounds_array()
    widths = bounds[:, 0]
    heights = bounds[:, 1]

    # Build rects list for the Rust-backed compute_pairwise_distances
    # (signature changed from 4 args to 1: Vec<f64> of [cx, cy, w, h] per component).
    # Kept flat (row-major n*n, not reshaped to a 2D array) -- both
    # consumers below (_compute_overlap_metrics, _compute_clearance_metrics)
    # now delegate to Rust kernels that take the flat form directly.
    rects = np.column_stack([positions, widths[:, None], heights[:, None]])
    rects_flat = rects.ravel().tolist()
    distances_flat = compute_pairwise_distances(rects_flat)

    # === Overlap metrics ===
    _compute_overlap_metrics(metrics, distances_flat, n_components)

    # === Boundary metrics ===
    _compute_boundary_metrics(metrics, positions, rotations, widths, heights, board)

    # === Clearance metrics ===
    _compute_clearance_metrics(metrics, distances_flat, netlist, hv_lv_clearance)

    # === Zone metrics ===
    _compute_zone_metrics(metrics, positions, netlist, board)

    # === Keepout metrics ===
    _compute_keepout_metrics(metrics, positions, rotations, widths, heights, board)

    # === Wirelength metrics ===
    _compute_wirelength_metrics(metrics, positions, rotation_indices, netlist)

    # === Distribution metrics ===
    _compute_distribution_metrics(metrics, positions, widths, heights, board)

    metrics.computation_time_ms = (time.time() - start_time) * 1000
    return metrics


def _compute_overlap_metrics(metrics: PlacementMetrics, distances_flat: list[float], n: int) -> None:
    """Compute overlap-related metrics.

    Delegates to ``temper_quality_oracle.overlap_metrics_py`` (Wave 4);
    see ``validation_metrics.rs`` for the ported arithmetic.
    """
    overlap_count, total_overlap, worst_overlap = _qo.overlap_metrics_py(
        list(distances_flat), n
    )
    metrics.overlap_count = overlap_count
    metrics.total_overlap_area = total_overlap
    metrics.worst_overlap = worst_overlap


def _compute_boundary_metrics(
    metrics: PlacementMetrics,
    positions: Array,
    rotations: Array,
    widths: Array,
    heights: Array,
    board: Board,
) -> None:
    """Compute boundary violation metrics."""
    # Board bounds (relative to board origin)
    board_min = np.array([0.0, 0.0])
    board_max = np.array([board.width, board.height])

    n = positions.shape[0]
    violation_count = 0
    total_violation = 0.0

    for i in range(n):
        rot = rotations[i]
        rot_idx = int(np.argmax(rot)) if isinstance(rot, np.ndarray) and rot.ndim == 1 else 0
        angle_rad = {0: 0.0, 1: np.pi / 2, 2: np.pi, 3: 3 * np.pi / 2}[rot_idx]
        xmi, ymi, xma, yma = get_rotated_bounds(
            float(positions[i, 0]),
            float(positions[i, 1]),
            float(widths[i]),
            float(heights[i]),
            angle_rad,
        )
        rw, rh = xma - xmi, yma - ymi
        half_w, half_h = rw / 2, rh / 2

        pos = positions[i]

        # Check violations
        violations = [
            max(0, float(board_min[0] - (pos[0] - half_w))),  # left
            max(0, float((pos[0] + half_w) - board_max[0])),  # right
            max(0, float(board_min[1] - (pos[1] - half_h))),  # bottom
            max(0, float((pos[1] + half_h) - board_max[1])),  # top
        ]

        max_violation = max(violations)
        if max_violation > 0:
            violation_count += 1
            total_violation += max_violation

    metrics.boundary_violations = violation_count
    metrics.total_boundary_violation = total_violation


def _compute_clearance_metrics(
    metrics: PlacementMetrics,
    distances_flat: list[float],
    netlist: Netlist,
    hv_lv_clearance: float,
) -> None:
    """Compute clearance violation metrics.

    Delegates to ``temper_quality_oracle.clearance_metrics_py`` (Wave 4);
    see ``validation_metrics.rs`` for the ported arithmetic. ``is_hv`` is
    ``comp.net_class == "HighVoltage"`` per component -- a string
    comparison resolved here (glue), not compute.
    """
    n = len(netlist.components)
    is_hv = [c.net_class == "HighVoltage" for c in netlist.components]

    clearance_violations, hv_lv_violations, min_hv_lv = _qo.clearance_metrics_py(
        list(distances_flat), n, is_hv, float(hv_lv_clearance)
    )

    metrics.clearance_violations = clearance_violations
    metrics.hv_lv_violations = hv_lv_violations
    metrics.min_hv_lv_clearance = min_hv_lv


def _compute_zone_metrics(
    metrics: PlacementMetrics,
    positions: Array,
    netlist: Netlist,
    board: Board,
) -> None:
    """Compute zone violation metrics."""
    zone_violations = 0

    for i, comp in enumerate(netlist.components):
        if comp.zone is None:
            continue

        x, y = float(positions[i, 0]), float(positions[i, 1])

        try:
            required_zone = board.get_zone(comp.zone)
            if not required_zone.contains_point(x, y):
                zone_violations += 1
        except KeyError:
            # Zone not defined - count as violation
            zone_violations += 1

    metrics.zone_violations = zone_violations


def _compute_keepout_metrics(
    metrics: PlacementMetrics,
    positions: Array,
    rotations: Array,
    widths: Array,
    heights: Array,
    board: Board,
) -> None:
    """Compute keepout violation metrics."""
    n = positions.shape[0]
    keepout_violations = 0

    for i in range(n):
        pos = positions[i]
        x, y = float(pos[0]), float(pos[1])

        rot = rotations[i]
        rot_idx = int(np.argmax(rot)) if isinstance(rot, np.ndarray) and rot.ndim == 1 else 0
        angle_rad = {0: 0.0, 1: np.pi / 2, 2: np.pi, 3: 3 * np.pi / 2}[rot_idx]
        xmi, ymi, xma, yma = get_rotated_bounds(
            float(positions[i, 0]),
            float(positions[i, 1]),
            float(widths[i]),
            float(heights[i]),
            angle_rad,
        )
        rw, rh = xma - xmi, yma - ymi
        half_w, half_h = rw / 2, rh / 2

        comp_min_x = x - half_w
        comp_max_x = x + half_w
        comp_min_y = y - half_h
        comp_max_y = y + half_h

        # Check rectangular keepouts
        for kx_min, ky_min, kx_max, ky_max in board.keepout_regions:
            if (
                comp_max_x > kx_min
                and comp_min_x < kx_max
                and comp_max_y > ky_min
                and comp_min_y < ky_max
            ):
                keepout_violations += 1
                break  # Only count once per component
        else:
            # Also check mounting holes
            for hole in board.mounting_holes:
                hx, hy = hole.position
                dist_to_hole = ((x - hx) ** 2 + (y - hy) ** 2) ** 0.5
                min_dist = max(half_w, half_h) + hole.keepout_radius
                if dist_to_hole < min_dist:
                    keepout_violations += 1
                    break

    metrics.keepout_violations = keepout_violations


def _compute_wirelength_metrics(
    metrics: PlacementMetrics,
    positions: Array,
    rotation_indices: Array,
    netlist: Netlist,
) -> None:
    """Compute wirelength metrics using half-perimeter wirelength (HPWL).

    Pin-position resolution (``pin_world_position_at``,
    ``netlist.get_component_index``, the ``try/except (KeyError,
    IndexError)`` guard) is domain geometry glue and stays in Python.
    Once resolved into a flat per-net HPWL value and weight, the fold
    (weighted total, max, and CPython-3.12-compensated-``sum()`` average)
    delegates to ``temper_quality_oracle.wirelength_metrics_py``
    (Wave 4); see ``validation_metrics.rs`` for the ported arithmetic.

    Pin resolution uses
    :func:`temper_placer.core.pad_identity.nth_matching_pin`
    (occurrence-indexed), not ``comp.get_pin(pin_name)``'s first match --
    a component with more than one physical pad sharing a pad number
    (K2/K3's manufacturer-duplicated current-sharing contacts) would
    otherwise have every occurrence resolve to the SAME coordinate,
    silently shrinking that net's HPWL bounding box. See
    ``temper_placer.core.pad_identity``'s module docstring.
    """
    hpwl_values: list[float] = []
    weights: list[float] = []

    for net in netlist.nets:
        if len(net.pins) < 2:
            continue

        # Collect all pin positions for this net
        pin_positions = []
        occurrence_indices = net_pin_occurrence_indices(net.pins)

        for (comp_ref, pin_name), occurrence in zip(net.pins, occurrence_indices, strict=True):
            try:
                comp_idx = netlist.get_component_index(comp_ref)
                comp = netlist.get_component(comp_ref)
                pin = nth_matching_pin(comp, pin_name, occurrence)

                if pin is None:
                    continue

                # Compute absolute pin position from live placement state
                rot_idx = int(rotation_indices[comp_idx])
                pos_override = (float(positions[comp_idx, 0]), float(positions[comp_idx, 1]))
                abs_pos = pin_world_position_at(
                    pin, comp, pos_override=pos_override, rotation_override=rot_idx
                )
                pin_positions.append(abs_pos)
            except (KeyError, IndexError):
                continue

        if len(pin_positions) < 2:
            continue

        # Compute HPWL for this net
        xs = [p[0] for p in pin_positions]
        ys = [p[1] for p in pin_positions]

        hpwl = (max(xs) - min(xs)) + (max(ys) - min(ys))

        hpwl_values.append(hpwl)
        weights.append(float(net.weight))

    total_wirelength, max_net_length, avg_net_length = _qo.wirelength_metrics_py(
        hpwl_values, weights
    )

    metrics.total_wirelength = total_wirelength
    metrics.max_net_length = max_net_length
    metrics.avg_net_length = avg_net_length


def _compute_distribution_metrics(
    metrics: PlacementMetrics,
    positions: Array,
    widths: Array,
    heights: Array,
    board: Board,
) -> None:
    """Compute placement distribution metrics.

    Delegates to ``temper_quality_oracle.distribution_metrics_py``
    (Wave 4); see ``validation_metrics.rs`` for the ported arithmetic and
    the measured NEP-50 float32-narrowing catalog entry (``positions``
    and ``widths``/``heights`` are both float32 with no float64 anchor,
    so ``np.sum``/``np.mean`` run their pairwise-summation reduction in
    float32, not float64).
    """
    n = positions.shape[0]

    utilization, com_x, com_y, spread_score = _qo.distribution_metrics_py(
        [float(positions[i, 0]) for i in range(n)],
        [float(positions[i, 1]) for i in range(n)],
        [float(w) for w in widths],
        [float(h) for h in heights],
        float(board.width),
        float(board.height),
    )

    metrics.utilization = utilization
    metrics.center_of_mass = (com_x, com_y)
    metrics.spread_score = spread_score
