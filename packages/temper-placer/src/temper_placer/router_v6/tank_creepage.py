"""
Router V6: pairwise HV<->HV creepage keepout for the resonant-tank node.

See docs/evidence/2026-08-12-router-tank-creepage.md for the full
investigation this module implements the conclusion of. Short version:

**What the router reads today.** ``OccupancyGrid.mark_path_blocked`` /
``mark_via_blocked`` (``occupancy_grid.py``) dilate a just-routed net's own
copper by ``trace_width/2 + clearance`` before the *next* net's A* search
runs (called from ``terminal_tree_execution.py`` and
``_astar_reconstruct.py``). The ``clearance`` value comes from
``design_rules.get_rules_for_net(net_name).clearance_mm`` -- a per-net
-CLASS scalar. ``NetClassRules.creepage_mm`` is marshalled all the way
through (``_adapter_convert.py``'s ``_to_stage0_netclass_rules``) but is
never read by this dilation call -- the same gap PR #1084 found on the
Rust DRC-kernel side (they key on net name, not netclass; here the router
does not consult the field at all). A true per-net-PAIR clearance table
*does* exist -- ``constraints_design_rules.py``'s ``ClearanceMatrix`` /
``set_class_to_class_clearance`` -- but it is wired only into the post-route
verification pass, ``constraints_drc_oracle.py``; nothing in the A*
occupancy-grid hot path calls it.

**Why a true pairwise fix is tractable here, not just a per-net
approximation.** Creepage is a property of a *pair* (tank net vs. other
HV/AC-domain net), not of a net in isolation. Widening the tank net's own
dilation radius to 10.0mm (the per-net approximation) would push EVERY net
-- including Signal/GND, which only need the ordinary 6.0mm
``HighVoltageTank-Signal`` clearance -- an extra 10.0mm away from the tank
node's routed copper, which is exactly the over-broad, expensive shape
this board has repeatedly shown makes placement/routing infeasible (see
this module's own evidence doc and PR #1089's placement-constraint
measurements). Because ``HighVoltageTank`` contains exactly one net
(``tank.c_tank1-p2``), a CLASS-pair rule (HighVoltageTank vs. every other
HV/AC-domain class) is, in practice on this board, already a true NET-pair
rule -- no additional per-net-pair plumbing is needed to get pairwise
behaviour for this specific case.

**The mechanism.** The tank node's PAD positions (not its routed path) are
static and known before any routing starts -- the measured violation this
module exists to close (C25 pad 2 <-> discharge.k_dis1-nc) is pad-to-track,
not the tank net's own trace. Before any OTHER HV/AC-domain net's A* search
runs, this module temporarily marks every currently-FREE cell within
``pad_radius + TANK_CREEPAGE_MM`` of a tank pad as blocked (reusing the
occupancy grid's existing sentinel semantics), on the SAME real, shared
grid objects every net's search and commit already use -- not a discarded
copy -- so real via placements committed mid-search (``astar_core.py``'s
``_astar_search_3d`` mutates its ``grids`` argument in place for real, not
just for the duration of one call) and the ripup mechanism inside
``_astar_route_with_ripup`` both keep working unmodified. The keepout is
released immediately after that net's routing attempt, restoring exactly
the cells this module changed (mirroring ``astar_grid.py``'s existing
``_unblock_net_pads`` / ``_restore_net_pads`` idiom, in the opposite
direction). Nets that are not HV/AC-domain never see the keepout at all --
so LV/GND/Signal routing is completely unaffected, and the extra margin is
paid only by the pairs that actually need it.

**Order independence.** Because the keepout is derived from PAD positions
(placement, fixed from the start) rather than from the tank net's own
ROUTED path, this works regardless of what order ``_compute_net_order``
puts nets in -- the tank net does not need to route before the nets this
protects it from.

**Known residual gap, stated plainly.** This protects tank PADS, which is
what the measured violation is. It does not additionally protect the tank
net's own ROUTED TRACE from a later HV/AC net's trace swinging close to it
mid-span (a trace-to-trace, not pad-to-track, creepage defect) -- doing
that too would require re-deriving the keepout from the tank net's routed
geometry once it exists, order-dependent, and no measured violation on
this board currently requires it. Left as a documented gap rather than
implemented speculatively (YAGNI, AGENTS.md's own general coding
principle) -- see the evidence doc's "what this does not cover" section.
"""

from __future__ import annotations

import math

from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.stage0_data import DesignRules

# The net class carrying the resonant-tank node (packages/temper-placer/src/
# temper_placer/core/design_rules.py's TEMPER_NET_CLASSES, PR #1084).
TANK_NET_CLASS: str = "HighVoltageTank"

# PD3, as-built-governing (the PD2 sealed-compartment prerequisite does not
# exist -- docs/evidence/2026-08-11-pd2-decision-record.md sec 2; matches
# scripts/generate_kicad_dru.py's HV_TANK_CREEPAGE_ENFORCED_MM at
# `_TANK_POLLUTION_DEGREE = "PD3"` and PR #1089's placement-constraint
# margin). Kept as a bare module constant, not read from NetClassRules at
# call time, so a mismatch between this figure and the netclass config is a
# visible two-place diff rather than a silent single-sourced drift; both are
# exercised by docs/evidence/2026-08-12-router-tank-creepage.md's
# measurement.
TANK_CREEPAGE_MM: float = 10.0

# The net-class safety categories treated as "the other side of the HV<->HV
# pair" -- i.e. the domain scripts/generate_kicad_dru.py's RULE 5a (the
# "HighVoltageTank functional creepage" rule) charges this figure against.
# "AC" is included because NetClassRules.safety_category treats ACMains as
# HV-side in separation checks (AGENTS.md's "NetClassRules Fields (N4)"
# table) and RULE 5a's own B-side condition includes both HighVoltage and
# HighVoltageTank -- ACMains is not currently a B-side match in the DRU rule
# itself, but is included here on the conservative side deliberately: this
# is a router-time AVOIDANCE heuristic, not the enforcement point, so a
# false-positive extra margin against ACMains costs nothing -- and ACMains
# nets do not currently route anywhere near the tank node.
_OTHER_HV_SAFETY_CATEGORIES: frozenset[str] = frozenset({"HV", "AC"})

# Sentinel written into cells while a keepout is temporarily active. Reuses
# -1 -- the SAME value OccupancyGrid already uses for a permanent static
# obstacle -- rather than inventing a new one: `is_free`/`is_blocked`,
# `blocked_cell_count`, and `occupancy_ratio` already treat -1 correctly,
# and the keepout is always fully released (`release_tank_creepage_keepout`)
# before control returns to any code that could observe it persisting, so no
# other consumer of the grid ever needs to learn a new sentinel value. Only
# cells that were FREE (0) immediately before a keepout is applied are ever
# touched -- a cell already carrying a real net's committed copper is left
# completely alone, so the ripup mechanism inside `_astar_route_with_ripup`
# (which identifies blockers by their real net_id) is never confused by a
# borrowed identity.
_KEEPOUT_SENTINEL: int = -1

TankPad = tuple[float, float, float, str]  # (x_mm, y_mm, radius_mm, layer)


def tank_pad_positions(
    pad_centers_per_net: dict[str, list[TankPad]],
    design_rules: DesignRules,
) -> list[TankPad]:
    """Every pad belonging to a net in :data:`TANK_NET_CLASS`.

    Reads ``design_rules.net_class_assignments`` directly (net_name ->
    class_name) rather than calling ``get_rules_for_net`` once per net in
    ``pad_centers_per_net`` -- both give the same answer, this is just the
    cheaper direction for "which nets are in class X" (a dict-value
    equality scan) versus "what class is net X in, for every net" (one
    dict lookup per net, discarding the class name immediately after).
    """
    tank_nets = {
        net for net, cls in design_rules.net_class_assignments.items() if cls == TANK_NET_CLASS
    }
    return [pad for net in tank_nets for pad in pad_centers_per_net.get(net, [])]


def needs_tank_creepage_check(net_name: str, design_rules: DesignRules) -> bool:
    """True if *net_name* is a DIFFERENT net in an HV/AC-domain class from
    the tank node, and therefore needs the extra pairwise creepage margin
    kept away from :data:`TANK_NET_CLASS` pads while it routes.

    The tank net itself is excluded (checked by class name, not identity,
    so it is correct even if a future board ever carries more than one
    :data:`TANK_NET_CLASS` net): a net never needs an extra keepout against
    its own pads.
    """
    rules = design_rules.get_rules_for_net(net_name)
    if rules.name == TANK_NET_CLASS:
        return False
    return rules.safety_category in _OTHER_HV_SAFETY_CATEGORIES


def apply_tank_creepage_keepout(
    grids: dict[str, OccupancyGrid],
    tank_pads: list[TankPad],
    creepage_mm: float = TANK_CREEPAGE_MM,
) -> list[tuple[OccupancyGrid, int, int]]:
    """Temporarily block every FREE cell within ``pad_radius + creepage_mm``
    of each tank pad, mutating *grids* in place.

    Mirrors ``astar_grid.py``'s ``_unblock_net_pads`` (same clamped-bbox +
    Euclidean-distance loop, same real-grid-in-place mutation, same
    only-touch-cells-in-a-known-state discipline) in the opposite
    direction: that function frees static obstacles so a net can reach its
    own pads; this one blocks free cells so a DIFFERENT net's search
    cannot approach a tank pad too closely. Only ``layer`` grids present in
    *grids* are touched -- a multi-layer board with the tank node on F.Cu
    only affects nets currently searching on F.Cu, which is correct: a
    net's B.Cu-only geometry cannot violate an F.Cu creepage requirement.

    Returns the list of ``(grid, row, col)`` cells this call changed, for
    :func:`release_tank_creepage_keepout` to restore. Every returned cell
    was FREE (0) immediately before this call -- a cell already occupied by
    real copper (any positive net_id) or already a permanent static
    obstacle (-1) is left untouched, so this function can never mask a real
    net's identity from the ripup mechanism or turn a permanent obstacle
    into a temporary one.
    """
    changed: list[tuple[OccupancyGrid, int, int]] = []
    for x_mm, y_mm, pad_radius_mm, layer in tank_pads:
        grid = grids.get(layer)
        if grid is None:
            continue
        radius_mm = pad_radius_mm + creepage_mm
        cell_size = grid.cell_size
        expansion = int(math.ceil(radius_mm / cell_size)) + 1
        cx, cy = grid.world_to_grid(x_mm, y_mm)

        x_start = max(0, cx - expansion)
        x_end = min(grid.width_cells, cx + expansion + 1)
        y_start = max(0, cy - expansion)
        y_end = min(grid.height_cells, cy + expansion + 1)

        for gy in range(y_start, y_end):
            for gx in range(x_start, x_end):
                if grid.grid[gy, gx] != 0:
                    continue
                wx, wy = grid.grid_to_world(gx, gy)
                dist = math.hypot(wx - x_mm, wy - y_mm)
                if dist <= radius_mm:
                    grid.grid[gy, gx] = _KEEPOUT_SENTINEL
                    changed.append((grid, gy, gx))

    return changed


def release_tank_creepage_keepout(changed: list[tuple[OccupancyGrid, int, int]]) -> None:
    """Undo :func:`apply_tank_creepage_keepout`.

    Every recorded cell was FREE before it was marked, so restoring is
    unconditionally "set back to 0" -- EXCEPT defensively guarded the same
    way ``_restore_net_pads`` guards its own restore (only restore if the
    cell is still exactly the sentinel this call wrote): the keepout is
    only ever applied around one net's routing attempt and released
    immediately after, with no legitimate way for anything else to have
    written into it in between, but the guard costs nothing and keeps this
    function safe to call even if that invariant is ever violated by a
    future caller.
    """
    for grid, gy, gx in changed:
        if grid.grid[gy, gx] == _KEEPOUT_SENTINEL:
            grid.grid[gy, gx] = 0
