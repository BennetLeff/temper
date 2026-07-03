"""
External physics-oracle adapter for placements produced by arbitrary placers.

This module provides ``score_placement()`` — a lightweight entry point that
accepts raw ``(x, y)`` component positions (in mm) and invokes the existing
metric functions from ``temper_placer.metrics.quality`` **without** running
the JAX optimizer training loop.

Usage::

    from temper_placer.metrics.external_oracle import score_placement

    positions = {
        "R1": (10.0, 20.0),
        "C1": (30.0, 40.0),
        "Q1": (50.0, 15.0),
    }
    result = score_placement(
        positions, netlist, board,
        hv_components={"Q1"},
        lv_components={"R1", "C1"},
        thermal_components={"Q1"},
    )
    print(result["hv_lv_clearance_score"])
    print(result["thermal_score"])
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import jax.numpy as jnp

from temper_placer.core.state import PlacementState
from temper_placer.metrics.quality import (
    compactness_score,
    hv_lv_clearance_score,
    thermal_score,
    zone_compliance_score,
)

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist


def score_placement(
    positions: dict[str, tuple[float, float]],
    netlist: Netlist,
    board: Board,
    design_rules: Any = None,
    footprint_library: Any = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Score a placement from raw ``(x, y)`` positions without invoking the JAX
    optimizer train loop.

    Constructs a ``PlacementState`` from the raw positions and calls the
    existing scorer functions in ``temper_placer.metrics.quality`` directly.

    Args:
        positions:
            Dict mapping each component reference designator to its
            ``(x_mm, y_mm)`` position in millimetres.
        netlist:
            Design netlist whose ``.components`` list defines the ordering of
            rows in the internal state array.
        board:
            Board definition (width, height, origin, zones).
        design_rules:
            Ignored in v1 — reserved for future use when
            ``dual_rail_clearance_report`` is ported.
        footprint_library:
            Ignored in v1 — reserved for future use.
        **kwargs:
            Configuration parameters passed to the underlying scorers:

            - ``hv_components`` (``set[str]``) — refs of HV components.
            - ``lv_components`` (``set[str]``) — refs of LV components.
            - ``min_clearance`` (``float``, default ``8.0``) — HV–LV
              clearance threshold in mm.
            - ``thermal_components`` (``set[str]``) — refs of thermal
              components that should be near a board edge.
            - ``thermal_edge`` (``str``, default ``"TOP"``) — target edge.
            - ``thermal_max_distance`` (``float``, default ``10.0``) —
              acceptable distance from edge in mm.
            - ``zone_assignments`` (``dict[str, str]``) — component → zone
              name mapping for zone-compliance scoring.
            - ``components`` (``list[str]``) — optional explicit component
              order override (default: ``netlist.components`` order).

    Returns:
        Dict with keys matching the convention of the quality metrics:

        - ``hv_lv_clearance_score`` (``float``, ``[0, 1]``)
        - ``thermal_score`` (``float``, ``[0, 1]``)
        - ``zone_compliance_score`` (``float``, ``[0, 1]``)
        - ``compactness_score`` (``float``, ``[0, 1]``)
        - ``clearance_3mm`` (``float``, ``[0, 1]``) — clearance at 3.0 mm
        - ``clearance_6mm`` (``float``, ``[0, 1]``) — clearance at 6.0 mm

        Additional keys from ``measure_geometric`` may be present if the
        underlying scorer produces them.

    Raises:
        ValueError: If *positions* is empty or *netlist* has no components.
    """
    # @req(2026-07-03-001, R7): CP-SAT output scored on existing oracle
    if not positions:
        raise ValueError(
            "positions dict is empty — at least one component is required"
        )

    if netlist.n_components == 0:
        raise ValueError(
            "netlist has no components — cannot build PlacementState"
        )

    # Determine component order — caller may override with a component_order kwarg
    component_order: list[str] | None = kwargs.get("components")

    # Build PlacementState from raw positions
    state = PlacementState.from_positions_dict(
        positions_dict=positions,
        netlist=netlist,
        component_order=component_order,
    )

    # --- Extract scoring parameters from kwargs ---
    hv_components: set[str] = kwargs.get("hv_components", set())
    lv_components: set[str] = kwargs.get("lv_components", set())
    min_clearance: float = kwargs.get("min_clearance", 8.0)

    thermal_comps: set[str] = kwargs.get("thermal_components", set())
    thermal_edge: str = kwargs.get("thermal_edge", "TOP")
    thermal_max_dist: float = kwargs.get("thermal_max_distance", 10.0)

    zone_assignments: dict[str, str] = kwargs.get("zone_assignments", {})

    # --- Run scorer functions ---
    result: dict[str, Any] = {}

    # Clearance score at user-specified threshold (default 8.0 mm)
    hv_clearance = hv_lv_clearance_score(
        state, netlist, hv_components, lv_components, min_clearance,
    )
    result["hv_lv_clearance_score"] = hv_clearance

    # Dual-rail clearance at standard thresholds (3.0 mm and 6.0 mm)
    result["clearance_3mm"] = hv_lv_clearance_score(
        state, netlist, hv_components, lv_components, min_clearance=3.0,
    )
    result["clearance_6mm"] = hv_lv_clearance_score(
        state, netlist, hv_components, lv_components, min_clearance=6.0,
    )

    # Thermal score
    therm = thermal_score(
        state, netlist, board, thermal_comps,
        target_edge=thermal_edge, max_distance=thermal_max_dist,
    )
    result["thermal_score"] = therm

    # Zone compliance
    result["zone_compliance_score"] = zone_compliance_score(
        state, netlist, board, zone_assignments,
    )

    # Compactness
    result["compactness_score"] = compactness_score(state, netlist, board)

    return result
