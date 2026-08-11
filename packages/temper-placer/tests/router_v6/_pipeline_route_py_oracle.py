"""Verbatim pre-migration oracle for the Phase E batch E6 pipeline-route
orchestration (Rust Orchestration Engine plan 2026-08-09-001, Phase E E6).

This file is a byte-exact snapshot of the ORCHESTRATION bodies of
``router_v6/_pipeline_route.py`` AS COMMITTED at the dispatch base
(origin/main cfc9415c1), extracted verbatim (AST ranges):

- ``_select_sat_nets`` -- the top-N-by-ascending-pin-count net selection
- ``_build_clause_origin`` -- the CNF clause->constraint-name registry
- ``select_routing_grids`` -- the (primary, alternate) occupancy-grid pick

The rest of ``_pipeline_route.py`` (``_run_stage3`` / ``_run_stage4`` /
``_run_stage5`` / ``_augment_with_pcl_constraints``) stays Python in the
shim -- the ortools/CP-SAT-boundary glue (net-batching branch, the
temper_rust_router solve invocation, the ModelBuilder/BundleAnalyzer and
the TopologicalSolution/TopologyGraph/Stage4Orchestrator wiring), argued
in the shim header and VERIFICATION.md.

The ``temper_placer`` imports below resolve to the pinned pre-E6 modules.
Do NOT edit: it is the reference.

"""

from __future__ import annotations

from typing import Any

def _select_sat_nets(self, pcb: ParsedPCB) -> list[str] | None:
    """Select top N nets by ascending pin count for selective SAT routing."""
    if self.max_sat_nets is None or self.max_sat_nets >= len(pcb.nets):
        return None
    pin_counts = {net.name: len(net.pins) for net in pcb.nets}
    scored = sorted(pin_counts, key=lambda n: pin_counts.get(n, 0))
    return scored[: self.max_sat_nets]


def _build_clause_origin(model: ConstraintModel) -> list[str]:
    """Build a clause-origin registry mapping CNF clause indices to constraint names.

    Each constraint in the model may produce multiple CNF clauses
    (e.g., AtMostK produces O(n*k) clauses). This function estimates
    the owner constraint for each clause position so that UNSAT core
    clause indices can be mapped back to constraint names.

    Returns:
        List where ``clause_origin[i]`` is the constraint name for clause i.
    """
    origins: list[str] = []
    if model is None:
        return origins
    for c in model.constraints:
        if hasattr(c, "terms") and c.terms:
            n = len(c.terms)
            clause_count = max(1, n * 3)
        elif hasattr(c, "group_a_indices") and c.group_a_indices:
            n = len(c.group_a_indices) + len(c.group_b_indices)
            clause_count = max(1, n * 3)
        elif hasattr(c, "p_var") and hasattr(c, "n_var"):
            clause_count = 2
        else:
            clause_count = 1
        origins.extend([c.name] * clause_count)
    return origins


def select_routing_grids(
    occupancy_grids: dict[str, OccupancyGrid] | None,
) -> tuple[OccupancyGrid, OccupancyGrid | None]:
    """Pick the (primary, alternate) occupancy grids handed to A*.

    Outer layers are preferred because most boards route on them, but they are
    only *preferences*: a board whose F.Cu/B.Cu carry copper pours has those
    layers classified as planes (``_parse_board.py``), so they get no routing
    space and therefore no occupancy grid at all, and routing happens on the
    inner layers instead.

    The alternate must be a different *layer* from the primary.  Selecting it
    by excluding the literal name ``"F.Cu"`` — rather than the primary grid's
    actual layer — returned the primary grid a second time on exactly those
    plane-outer boards, so the router was handed one layer twice and the
    second real inner layer was dropped before pathfinding ever saw it.
    """
    if not occupancy_grids:
        raise ValueError("No occupancy grid available for A* pathfinding")
    primary = occupancy_grids.get("F.Cu") or next(iter(occupancy_grids.values()))
    alternate = occupancy_grids.get("B.Cu") or next(
        (candidate for name, candidate in occupancy_grids.items() if name != primary.layer_name),
        None,
    )
    return primary, alternate

