"""Rust-backed Tier-3 N-layer, via-aware A*.

Replaces ``astar_core._astar_search_3d`` / ``_route_segment_3d`` with
``temper_rust_router_core::astar_nlayer`` (via
``temper_rust_router.route_segment_3d_py``).

Parity contract
---------------
The Rust kernel is held to **bit-exact f64 parity** with the pre-migration
Python, pinned at
``tests/router_v6/_astar_nlayer_py_oracle.py`` and proven by
``tests/router_v6/test_astar_nlayer_rust_differential.py`` on real
``pcb/temper.kicad_pcb`` geometry. This is a deliberately stricter standard
than the 2D kernel's (``astar_core_rust``), whose f32 arithmetic makes only
invariant-level agreement possible.

What stays in Python here, and why
----------------------------------
1. ``available_layers`` ordering. The Python derived it from
   ``core.board.STANDARD_LAYER_ORDER`` -- a canonical *4-layer* tuple
   (``F.Cu, In1.Cu, In2.Cu, B.Cu``) that matches **none** of the production
   6-layer board's inner signal layers (``In3.Cu``/``In4.Cu``), while the two
   it does name are power planes that never receive an occupancy grid. The
   preference therefore degenerates to ``[F.Cu, B.Cu]`` + append-the-rest.
   That is a filed defect, NOT fixed here: this module reproduces the
   ordering exactly so the port is behaviour-preserving, and keeps it at the
   Python call site where it stays visible rather than baking it into Rust.
   It does not change search results today -- the frontier's tie-break is on
   the layer *name*, not on this list's position -- but it is a hard-coded
   4-layer assumption in a live 6-layer path.

2. Via marking. Python marked vias onto every grid from inside
   ``_astar_search_3d``; that mutation happens here instead, through the
   existing (already Rust-backed) ``OccupancyGrid.mark_via_blocked``.
   Equivalent: marking runs only after the goal is reached, and nothing
   downstream re-reads occupancy within the same call.
"""

from __future__ import annotations

import numpy as np

from temper_placer.core.board import STANDARD_LAYER_ORDER

__all__ = ["route_segment_3d_rust"]

#: Mirrors ``astar_core._ROUTE_SEGMENT_3D_DEFAULT_MAX_ITER``.
ROUTE_SEGMENT_3D_DEFAULT_MAX_ITER: int = 200_000


def _available_layers(grids: dict) -> list[str]:
    """The layer-transition order, reproducing the pre-migration Python.

    See this module's docstring for why the ``STANDARD_LAYER_ORDER``
    degeneracy is preserved rather than fixed.
    """
    standard_order = [str(idx) for idx in STANDARD_LAYER_ORDER]
    available = [layer for layer in standard_order if layer in grids]
    for layer in grids:
        if layer not in available:
            available.append(layer)
    return available


def route_segment_3d_rust(
    start_world: tuple[float, float],
    goal_world: tuple[float, float],
    start_layer: str,
    goal_layer: str,
    grids: dict,
    via_cost: float = 10.0,
    via_diameter: float = 0.6,
    clearance: float = 0.2,
    net_id: int = 0,
    max_iter: int | None = ROUTE_SEGMENT_3D_DEFAULT_MAX_ITER,
) -> tuple[list[tuple[float, float, str]], list[tuple[float, float]]] | None:
    """Route one segment across N layers with via insertion.

    Signature and return shape mirror ``astar_core._route_segment_3d``:
    ``(world_path, via_world_positions)`` or ``None``.
    """
    import temper_rust_router as _trr

    if not grids:
        return None
    # `_astar_search_3d` returned None (hence `_route_segment_3d` too) when
    # either terminal named a layer with no grid.
    if start_layer not in grids or goal_layer not in grids:
        return None

    # Layer index order = `grids` iteration order, so index 0's frame is the
    # `next(iter(grids.values()))` sample grid the Python used for every
    # coordinate conversion.
    layer_names = list(grids)
    index_of = {name: i for i, name in enumerate(layer_names)}
    sample = grids[layer_names[0]]

    # Heap tie-break stands in for Python's layer-NAME comparison, so the rank
    # must be the name's position in lexicographic order.
    ranked = sorted(layer_names)
    name_ranks = [ranked.index(name) for name in layer_names]

    planes = np.concatenate(
        [np.ascontiguousarray(grids[n].grid, dtype=np.int8).reshape(-1) for n in layer_names]
    ).tobytes()

    world_path, via_world, via_cells, found, _iters = _trr.route_segment_3d_py(
        (float(start_world[0]), float(start_world[1])),
        (float(goal_world[0]), float(goal_world[1])),
        index_of[start_layer],
        index_of[goal_layer],
        planes,
        name_ranks,
        int(sample.width_cells),
        int(sample.height_cells),
        [index_of[n] for n in _available_layers(grids)],
        float(via_cost),
        None if max_iter is None else int(max_iter),
        (float(sample.origin[0]), float(sample.origin[1])),
        float(sample.cell_size),
    )
    if not found:
        return None

    # Via marking, lifted out of the search (see the module docstring). Same
    # gate as the Python: `if vias and net_id > 0`.
    if via_cells and net_id > 0:
        for via_gx, via_gy in via_cells:
            via_wx, via_wy = sample.grid_to_world(via_gx, via_gy)
            for layer_grid in grids.values():
                layer_grid.mark_via_blocked(via_wx, via_wy, via_diameter, clearance, net_id)

    return (
        [(x, y, layer_names[li]) for x, y, li in world_path],
        [(x, y) for x, y in via_world],
    )
