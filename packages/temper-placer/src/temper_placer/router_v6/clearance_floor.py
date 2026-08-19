"""The clearance the router must *reserve* so that what it emits passes the
clearance the DRC *grades*.

The two are not the same number, and until 2026-08-12 nothing in the tree
made them agree.

The rule that grades
--------------------
``scripts/generate_kicad_dru.py`` RULE 10::

    (rule "Default routing"
       (condition "A.Type == 'Track' || B.Type == 'Track'")
       (constraint clearance (min 0.2mm)))

Its condition is ``||``, not ``&&``: **any** pair where either side is a
track is graded at 0.2mm unless a more specific rule matches first. So
0.2mm is a global floor for track-involving pairs, and a net class whose
own clearance is *below* it (``FinePitch``, 0.1mm) cannot actually route
to its own number without producing DRC errors.

What the router reserves
------------------------
Stage 4 blocks routed copper through ``OccupancyGrid.mark_path_blocked``
-> ``temper_geometry::mark_segment_rect``, which is a **rasteriser**, not
an exact geometric reservation::

    radius_mm = trace_width / 2 + clearance
    expansion = ceil(radius_mm / cell_size)        # in CELLS
    # ... then stamps a square of +/-expansion cells around each sampled
    # point (Chebyshev, not Euclidean)

The next net's centreline may therefore sit on the first cell centre
outside that square, i.e. at ``(expansion + 1) * cell_size``. The
edge-to-edge gap two same-width traces actually end up with is

    gap = (ceil((w/2 + c) / cell) + 1) * cell - w

which is a **step function of c**, not ``c`` itself. The rows below were
measured against the real kernel when this module was written, and this
docstring is their ONLY home: an earlier version of this paragraph cited
``tests/router_v6/test_clearance_floor.py`` as probing them, but that file
has never existed on any branch (``git log --all --diff-filter=A`` for it
is empty) and no test anywhere in the tree calls any function in this
module. ``scripts/check_router_clearance_floor.py`` does not close the gap
either -- its P1-P5 compare four *constants* and AST-scan for literal
``default_clearance_mm`` writes; it never calls ``blocking_clearance_mm``.
Treat the rows as unpinned prose, not as assertions:

    w=0.25 c=0.15 -> expansion 3 -> pitch 0.40mm -> gap 0.1500  (FAILS 0.2)
    w=0.25 c=0.20 -> expansion 4 -> pitch 0.50mm -> gap 0.2500
    w=0.20 c=0.20 -> expansion 4 -> pitch 0.50mm -> gap 0.3000
    w=0.20 c=0.15 -> expansion 3 -> pitch 0.40mm -> gap 0.2000  (exactly 0.2)
    w=0.127 c=0.10 -> expansion 2 -> pitch 0.30mm -> gap 0.1730 (FAILS 0.2)

The first row is what the board shipped with, and it is why 136 of the
heatsink candidate's 505 ``clearance`` errors read ``actual 0.1500 mm``
to four decimal places, with another 149 at its near-diagonal companion
``0.1972mm`` (the first free cell at a 4-across/2-down offset,
sqrt(0.4^2 + 0.2^2) = 0.4472mm centre distance). See
``docs/evidence/2026-08-12-clearance-congestion-band.md``.

Note the fourth row against the second and third: **passing a larger
clearance is not free and is not always better.** 0.15 with a 0.20mm
trace lands the reservation exactly on the DRC floor at a 0.40mm pitch;
0.20 pushes it a whole lattice step out to 0.50mm — 25% coarser routing
for 0.10mm of margin nobody asked for. (0.20 + 0.20/2 is 0.30000000000000004
in IEEE754, so it does not even sit on the boundary; it ceils to 4.) This
module picks the clearance that satisfies the floor at the *tightest*
lattice step, rather than picking a number that reads well.

What this module provides
-------------------------
``blocking_clearance_mm(trace_width_mm)`` -- the clearance to hand the
rasteriser so the emitted geometry clears ``DEFAULT_ROUTING_CLEARANCE_MM``
with the fewest lattice steps, never below the net class's own declared
clearance where that is stricter.

REACHABILITY, MEASURED 2026-08-18 (read this before extending anything here)
---------------------------------------------------------------------------
On the production recipe (``scripts/route_board.py`` defaults, this board),
**every function in this module is called zero times**; the only live symbol
is the constant ``DEFAULT_ROUTING_CLEARANCE_MM``, read by
``_astar_nlayer._family_signature``. Two independent gates close, both of
them upstream of this file:

* Stage 4 takes ``_astar_nlayer.run_astar_pathfinding_nlayer`` whenever the
  board has more than two routable signal layers (``_pipeline_route.py``'s
  ``use_nlayer``), and this board has four. The legacy
  ``_astar_reconstruct.run_astar_pathfinding``, which holds every
  ``effective_blocking_clearance`` call site, does not run.
* Those call sites are additionally behind ``if profile_grids is None``,
  i.e. ``enable_pair_clearance=False`` -- a keyword no caller in the repo
  passes.

And the correction this module computes is *obsolete*, not merely unreached:
it compensates for a missing neighbour half-width in the single-grid stamp
(``radius = w_self/2 + c``), and both live stamping paths now add that term
directly (``_astar_nlayer.py``'s ``max(cl_F, C, creepage) + W_fam/2`` and
``pair_clearance.stamp_clearance_mm``'s ``max(required, cl) + w_search/2``).
With the two-sided radius the lattice rounding over-reserves rather than
under-reserving, so there is nothing left to correct -- while this module's
own same-width assumption still under-reserves mixed-width pairs (352
measured, ``docs/evidence/2026-08-12-clearance-floor-reland.md`` sec 5).

Full measurement, including the reproduced 4553/169/151 ``6d4e1733`` route:
``docs/evidence/2026-08-18-no-rust-ledger-clearance-floor-and-topology-copper-audit.md``.
"""

from __future__ import annotations

import math

#: RULE 10's floor. Also ``netclass_rules.yaml::default_clearance_mm`` and
#: ``pcb/temper.kicad_pro``'s ``Default`` net class clearance.
#: ``scripts/check_router_clearance_floor.py`` asserts all four agree.
DEFAULT_ROUTING_CLEARANCE_MM = 0.2

#: ``OccupancyGrid``'s default cell size (``occupancy_grid.py``'s
#: ``create_occupancy_grid(cell_size=0.1)``), which is what the production
#: pipeline builds its layer grids at.
ROUTING_GRID_CELL_MM = 0.1


def rasterised_pitch_mm(
    trace_width_mm: float,
    clearance_mm: float,
    cell_size_mm: float = ROUTING_GRID_CELL_MM,
) -> float:
    """Centre-to-centre distance of the first cell the rasteriser leaves
    free, for a trace blocked at ``(trace_width_mm, clearance_mm)``.

    Mirrors ``temper_geometry::mark_segment_rect``'s
    ``ceil((w/2 + c) / cell)`` expansion, plus the one cell to the first
    unblocked centre.
    """
    radius = trace_width_mm / 2.0 + clearance_mm
    expansion = math.ceil(radius / cell_size_mm)
    return (expansion + 1) * cell_size_mm


def rasterised_gap_mm(
    trace_width_mm: float,
    clearance_mm: float,
    cell_size_mm: float = ROUTING_GRID_CELL_MM,
    other_width_mm: float | None = None,
) -> float:
    """Edge-to-edge gap the rasterised reservation actually yields.

    ``other_width_mm`` defaults to ``trace_width_mm`` (two traces of the
    same class, the case the lattice pitch is set by).
    """
    other = trace_width_mm if other_width_mm is None else other_width_mm
    pitch = rasterised_pitch_mm(trace_width_mm, clearance_mm, cell_size_mm)
    return pitch - trace_width_mm / 2.0 - other / 2.0


def blocking_clearance_mm(
    trace_width_mm: float,
    declared_clearance_mm: float = 0.0,
    floor_mm: float = DEFAULT_ROUTING_CLEARANCE_MM,
    cell_size_mm: float = ROUTING_GRID_CELL_MM,
) -> float:
    """Clearance to pass the blocking rasteriser.

    ``declared_clearance_mm`` and the return value are **not the same
    quantity**, and conflating them is the original defect in reverse.
    The declared figure is a required *gap*; the return value is a
    rasteriser *input*, related to the gap only through the step function
    above. This returns the input whose achieved gap is the required gap,
    at the tightest lattice step that reaches it.

    The required gap is ``max(declared_clearance_mm, floor_mm)`` -- a
    class asking for 6.0mm gets 6.0mm; this is a floor and never a cap.

    The input is chosen at the *midpoint* of the lattice step that
    delivers it, not at its boundary: the boundary is where IEEE754
    rounding decides whether ``ceil`` returns n or n+1 (``0.2/2 + 0.2``
    is 0.30000000000000004), and a whole extra lattice step is a 25%
    routing-density change.
    """
    if cell_size_mm <= 0:
        raise ValueError("cell_size_mm must be positive")

    required_gap = max(declared_clearance_mm, floor_mm)

    # Smallest expansion E with (E + 1) * cell >= required_gap + w, i.e. the
    # first lattice step whose gap reaches the requirement for two
    # same-width traces.
    needed_pitch = required_gap + trace_width_mm
    expansion = max(1, math.ceil(round(needed_pitch / cell_size_mm, 9)) - 1)

    # c values yielding this expansion: ((E-1)*cell - w/2, E*cell - w/2].
    # Take the midpoint so neither end is decided by float error.
    lo = (expansion - 1) * cell_size_mm - trace_width_mm / 2.0
    hi = expansion * cell_size_mm - trace_width_mm / 2.0
    return max(0.0, (lo + hi) / 2.0)


def effective_blocking_clearance(
    net_rule: object,
    cell_size_mm: float = ROUTING_GRID_CELL_MM,
) -> float:
    """``blocking_clearance_mm`` for a ``NetClassRules``-shaped object.

    Every site that stamps a routed net into the occupancy grid must use
    this, and every site that *unstamps* one must use it too -- mark and
    unmark have to agree or ripup leaves a stale footprint behind.
    """
    width = float(getattr(net_rule, "trace_width_mm", 0.0) or 0.0)
    declared = float(getattr(net_rule, "clearance_mm", 0.0) or 0.0)
    return blocking_clearance_mm(width, declared, cell_size_mm=cell_size_mm)
