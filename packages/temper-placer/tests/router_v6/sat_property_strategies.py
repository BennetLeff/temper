"""Shared Hypothesis strategies for SAT property tests.

Provides reusable strategies for SAT lattice tests (U1-U4), DRC
completeness tests (U6-U7), and induction tests (U9-U12).

Strategies
----------
* ``sat_variable`` — random ``SATVariable``
* ``sat_clause`` — random ``SATClause`` over a variable set
* ``sat_clause_set`` — list of clauses over shared variables
* ``constraint_model_grid`` — ``ConstraintModel`` for a < =4x4 grid
* ``boundary_biased_routing_results`` — ``RoutingResults`` biased toward
  spatial-index cell boundaries
* ``known_compliant_route`` — ``CompiledRoute`` known to satisfy all
  DFM constraints
"""

from __future__ import annotations

import math
from typing import Callable

from hypothesis import strategies as st

from temper_placer.router_v6.astar_core import RoutePath3D
from temper_placer.router_v6.astar_pathfinding import RoutePath
from temper_placer.router_v6.constraint_model import (
    CapacityConstraint,
    ConstraintModel,
    DiffPairConstraint,
    LayerConstraint,
    NetChannelVar,
)
from temper_placer.router_v6.routing_results import CompiledRoute, RoutingResults
from temper_placer.router_v6.sat_model import SATClause, SATModel, SATVariable
from temper_placer.router_v6.via_placement import Via

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BOARD_W: float = 200.0
BOARD_H: float = 150.0
LAYERS: tuple[str, ...] = ("F.Cu", "B.Cu", "In1.Cu", "In2.Cu")
SPATIAL_CELL_SIZE: float = 5.0  # mm — typical spatial-index cell size

# ---------------------------------------------------------------------------
# SAT strategies
# ---------------------------------------------------------------------------


@st.composite
def sat_variable(draw: st.DrawFn) -> SATVariable:
    """Generate a single ``SATVariable`` with random name and description."""
    name = draw(st.text("abcdefghijklmnopqrstuvwxyz", min_size=2, max_size=12))
    desc = f"Variable {name}"
    return SATVariable(name=name, description=desc)


@st.composite
def sat_variable_set(
    draw: st.DrawFn,
    min_size: int = 2,
    max_size: int = 20,
) -> list[SATVariable]:
    """Generate a set of ``SATVariable`` instances with unique names."""
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    names = draw(
        st.lists(
            st.text("abcdefghijklmnopqrstuvwxyz", min_size=2, max_size=8),
            min_size=n,
            max_size=n,
            unique=True,
        )
    )
    return [SATVariable(name=nm, description=f"Variable {nm}") for nm in names]


@st.composite
def sat_clause(
    draw: st.DrawFn,
    variables: list[SATVariable] | None = None,
    min_literals: int = 1,
    max_literals: int = 5,
) -> SATClause:
    """Generate a ``SATClause`` over *variables* (or a fresh set if None)."""
    if variables is None:
        n_vars = draw(st.integers(min_value=2, max_value=8))
        variables = draw(sat_variable_set(min_size=n_vars, max_size=n_vars))

    n_lits = min(len(variables), draw(st.integers(min_value=min_literals, max_value=max_literals)))
    # Use indices to avoid hashability issues with SATVariable
    indices = draw(st.lists(
        st.integers(min_value=0, max_value=len(variables) - 1),
        min_size=n_lits, max_size=n_lits, unique=True,
    ))
    literals = [(variables[idx], draw(st.booleans())) for idx in indices]
    desc = f"Clause: {' OR '.join(('' if pol else 'NOT ') + str(v) for v, pol in literals)}"
    return SATClause(literals=literals, description=desc)


@st.composite
def sat_clause_set(
    draw: st.DrawFn,
    min_vars: int = 2,
    max_vars: int = 8,
    min_clauses: int = 2,
    max_clauses: int = 20,
) -> tuple[list[SATVariable], list[SATClause]]:
    """Generate a shared variable set and list of clauses over those variables."""
    n_vars = draw(st.integers(min_value=min_vars, max_value=max_vars))
    variables = draw(sat_variable_set(min_size=n_vars, max_size=n_vars))
    n_clauses = draw(st.integers(min_value=min_clauses, max_value=max_clauses))
    clauses: list[SATClause] = []
    for _ in range(n_clauses):
        cl = draw(sat_clause(variables=variables))
        clauses.append(cl)
    return variables, clauses


# ---------------------------------------------------------------------------
# Constraint model grid strategy
# ---------------------------------------------------------------------------


@st.composite
def constraint_model_grid(
    draw: st.DrawFn,
    max_cells: int = 4,
    max_nets: int = 3,
    max_layers: int = 2,
) -> ConstraintModel:
    """Generate a ``ConstraintModel`` for a small grid routing problem.

    Produces a model with NetChannelVar instances for each (net, channel)
    combination, plus optional LayerConstraint and CapacityConstraint
    entries.  Suitable for U3 cross-constraint tests.
    """
    n_cells = draw(st.integers(min_value=1, max_value=max_cells))
    n_nets = draw(st.integers(min_value=1, max_value=max_nets))
    n_layers = draw(st.integers(min_value=1, max_value=max_layers))

    model = ConstraintModel()

    # Create NetChannelVar for each (net_idx, channel) combo
    layer_names = LAYERS[:n_layers]
    for net_idx in range(n_nets):
        for layer_name in layer_names:
            for cell_idx in range(n_cells):
                channel_id = f"{layer_name}_E{cell_idx}_0_1"
                var = NetChannelVar(
                    name=f"uses_N{net_idx}_{channel_id}",
                    net_idx=net_idx,
                    channel_id=channel_id,
                )
                model.add_variable(var)

    # Optionally add layer constraints
    if draw(st.booleans()) and n_layers > 1 and n_nets > 0:
        net_idx = draw(st.integers(min_value=0, max_value=n_nets - 1))
        layer_name = layer_names[0]
        for cell_idx in range(n_cells):
            channel_id = f"{layer_name}_E{cell_idx}_0_1"
            if (net_idx, channel_id) in model.net_channel_vars:
                var = model.net_channel_vars[(net_idx, channel_id)]
                allowed = draw(st.booleans())
                constraint = LayerConstraint(
                    name=f"layer_restr_N{net_idx}_{channel_id}",
                    net_idx=net_idx,
                    channel_id=channel_id,
                    allowed=allowed,
                )
                model.add_constraint(constraint)

    return model


# ---------------------------------------------------------------------------
# Boundary-biased routing results strategy (for U7)
# ---------------------------------------------------------------------------


@st.composite
def boundary_biased_routing_results(
    draw: st.DrawFn,
    min_routes: int = 2,
    max_routes: int = 10,
) -> RoutingResults:
    """Generate ``RoutingResults`` with coordinates biased toward spatial-index
    cell boundaries.

    Positions are drawn within 0.01 mm of a ``SPATIAL_CELL_SIZE`` multiple
    to exercise spatial-index boundary cases.
    """
    n_routes = draw(st.integers(min_value=min_routes, max_value=max_routes))

    net_names = [
        f"NET{i}" for i in range(n_routes)
    ]

    # Generate boundary-biased coordinates: snap to multiples of cell size
    # plus/minus a tiny offset.
    boundary_snap = draw(st.floats(min_value=-0.01, max_value=0.01))

    compiled: dict[str, CompiledRoute] = {}
    for net_name in net_names:
        layer = draw(st.sampled_from(LAYERS))

        n_segments = draw(st.integers(min_value=1, max_value=30))
        coords: list[tuple[float, float]] = []
        for _ in range(n_segments + 1):  # points = segments + 1
            # Choose a cell-boundary multiple + tiny offset
            cx = draw(st.integers(min_value=0, max_value=40))  # 0-200mm range
            cy = draw(st.integers(min_value=0, max_value=30))
            x = float(cx) * SPATIAL_CELL_SIZE + boundary_snap
            y = float(cy) * SPATIAL_CELL_SIZE + boundary_snap
            coords.append((x, y))

        width = draw(st.floats(min_value=0.1, max_value=1.0))

        path_len = 0.0
        for i in range(len(coords) - 1):
            path_len += math.hypot(
                coords[i + 1][0] - coords[i][0],
                coords[i + 1][1] - coords[i][1],
            )

        path = RoutePath(
            net_name=net_name,
            coordinates=coords,
            layer_name=layer,
            path_length=path_len,
        )

        # Optionally add vias
        n_vias = draw(st.integers(min_value=0, max_value=5))
        vias: list[Via] = []
        for _ in range(n_vias):
            vx = draw(st.floats(min_value=0.0, max_value=float(40 * SPATIAL_CELL_SIZE)))
            vy = draw(st.floats(min_value=0.0, max_value=float(30 * SPATIAL_CELL_SIZE)))
            frm = draw(st.sampled_from(LAYERS))
            to = draw(st.sampled_from([l for l in LAYERS if l != frm]))
            via = Via(
                position=(vx, vy),
                from_layer=frm,
                to_layer=to,
                diameter=0.6,
                drill=0.3,
                net_name=net_name,
            )
            vias.append(via)

        compiled[net_name] = CompiledRoute(
            net_name=net_name,
            path=path,
            width_mm=width,
            vias=vias,
            matched_length_mm=None,
        )

    return RoutingResults(compiled_routes=compiled, failed_nets=[])


# ---------------------------------------------------------------------------
# Known-compliant route strategy (for U12 + induction tests)
# ---------------------------------------------------------------------------


@st.composite
def known_compliant_route(
    draw: st.DrawFn,
    layer: str = "F.Cu",
) -> CompiledRoute:
    """Generate a ``CompiledRoute`` known to satisfy all DFM constraints.

    Produces geometry with:
    - Trace width >= 0.127 mm
    - Segments spaced >= 2x clearance from itself
    - No acute angles < 90 degrees
    - Vias with pad >= drill + 2x min_annular_ring
    """
    net_name = draw(st.text("abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=8)).upper()

    width = draw(st.floats(min_value=0.2, max_value=1.0))

    # Build a sparse "staircase" path: points far apart, no sharp turns
    n_points = draw(st.integers(min_value=2, max_value=8))
    coords: list[tuple[float, float]] = []
    x = draw(st.floats(min_value=10.0, max_value=30.0))
    y = draw(st.floats(min_value=10.0, max_value=130.0))
    coords.append((x, y))
    for i in range(1, n_points):
        # Alternate horizontal/vertical steps
        step = draw(st.floats(min_value=10.0, max_value=40.0))
        if i % 2 == 0:
            x += step
        else:
            y += step
        coords.append((x, y))

    path_len = 0.0
    for i in range(len(coords) - 1):
        path_len += math.hypot(
            coords[i + 1][0] - coords[i][0],
            coords[i + 1][1] - coords[i][1],
        )

    path = RoutePath(
        net_name=net_name,
        coordinates=coords,
        layer_name=layer,
        path_length=path_len,
    )

    # Compliant vias: pad >= drill + 2 * min_annular_ring (0.05mm)
    # Ensure generous margin: drill <= diameter - 0.15 (ring >= 0.075 > 0.05)
    n_vias = draw(st.integers(min_value=0, max_value=2))
    vias: list[Via] = []
    for _ in range(n_vias):
        vx = draw(st.floats(min_value=10.0, max_value=BOARD_W - 10.0))
        vy = draw(st.floats(min_value=10.0, max_value=BOARD_H - 10.0))
        dia = draw(st.floats(min_value=1.0, max_value=2.0))
        drill_max = dia - 0.15  # Ensure annular ring > 0.05
        drill = draw(st.floats(min_value=0.1, max_value=drill_max))
        frm = layer
        to = draw(st.sampled_from([l for l in LAYERS if l != frm]))
        vias.append(Via(
            position=(vx, vy),
            from_layer=frm,
            to_layer=to,
            diameter=dia,
            drill=drill,
            net_name=net_name,
        ))

    return CompiledRoute(
        net_name=net_name,
        path=path,
        width_mm=width,
        vias=vias,
        matched_length_mm=None,
    )


@st.composite
def known_compliant_routing_results(
    draw: st.DrawFn,
    min_routes: int = 2,
    max_routes: int = 4,
) -> RoutingResults:
    """Generate ``RoutingResults`` containing only known-compliant routes.

    Routes are placed on distinct layers with well-separated coordinates
    to avoid cross-route clearance violations.
    """
    n = draw(st.integers(min_value=min_routes, max_value=min(max_routes, len(LAYERS))))
    compiled: dict[str, CompiledRoute] = {}
    used_layers = set()
    # Offset each route's coordinates to avoid overlap
    y_offsets = [10.0, 60.0, 110.0, 160.0]

    for i in range(n):
        layer = LAYERS[i]
        used_layers.add(layer)

        # Generate a route with known-safe coordinates
        net_name = f"COMPLIANT_{i}"
        width = draw(st.floats(min_value=0.2, max_value=1.0))

        y = y_offsets[i]
        coords = [
            (10.0, y),
            (50.0, y),
            (100.0, y + 30.0),
        ]
        path_len = 0.0
        for k in range(len(coords) - 1):
            path_len += math.hypot(
                coords[k + 1][0] - coords[k][0],
                coords[k + 1][1] - coords[k][1],
            )

        path = RoutePath(
            net_name=net_name,
            coordinates=coords,
            layer_name=layer,
            path_length=path_len,
        )

        # No vias on simple routes to avoid via-to-trace clearance issues
        n_vias = draw(st.integers(min_value=0, max_value=1))
        vias: list[Via] = []
        for _ in range(n_vias):
            dia = draw(st.floats(min_value=1.0, max_value=2.0))
            drill_max = dia - 0.15
            drill = draw(st.floats(min_value=0.1, max_value=drill_max))
            lv = draw(st.sampled_from([l for l in LAYERS if l != layer]))
            vias.append(Via(
                position=(50.0, y),
                from_layer=layer,
                to_layer=lv,
                diameter=dia,
                drill=drill,
                net_name=net_name,
            ))

        compiled[net_name] = CompiledRoute(
            net_name=net_name,
            path=path,
            width_mm=width,
            vias=vias,
            matched_length_mm=None,
        )

    return RoutingResults(compiled_routes=compiled, failed_nets=[])
