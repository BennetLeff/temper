"""Pinned Python oracle for the MST pad-to-pad stitch + creepage-aware
C-space gate migration (`temper_geometry.stitch_mst_with_gate_py`,
`packages/temper-geometry/src/zone_generator.rs::stitch_mst_with_gate`).

DO NOT EDIT -- THIS IS THE REFERENCE.
======================================
``_mst_edges`` and ``_gate_filter_edges`` below are a **verbatim** ``git
show`` extraction from commit ``9a55b56be95f985098c4cb9c0abfc4569a79dcad``
(this migration's base commit) of
``temper_placer/router_v6/_zone_pour_stitch.py``. Nothing has been cleaned
up, refactored, or fixed by this file.
``test_stitch_mst_with_gate_rust_differential.py::test_oracle_is_verbatim_copy``
re-extracts both functions from the pinned commit and compares the source
text character for character.

Why this function specifically
-------------------------------
docs/evidence/2026-08-18-zone-pour-fragmentation-rootcause.md root-causes
9 mains-derived nets (`+170V_BUS`, `DC_BUS_RTN`, `PWR_RTN`, `SW_NODE`,
`ac_n`, `power_in.ntc-no`, `tank.c_tank1-p2`, `w1_1`, `w1_2`) failing to
connect through their zone pours: most are Ward-clustered by
`zone_emission.py` into several small, spatially disjoint per-component
hulls before the Rust carve ever runs, and `_net_policy.py::_should_route`
excludes every zone-eligible net from A* entirely -- so the pour is the
ONLY conductive path, and nothing currently bridges the resulting disjoint
clusters. A general MST pad-to-pad stitcher with a creepage-aware C-space
gate already existed (`_stitch_pads_to_each_other`, added 2026-08-14,
C-space-gated 2026-08-16) but was hardcoded to run for exactly one net
(`power_in.ntc-no`) and never generalised.

This pins the two pure-geometry functions this migration ports to Rust
(`packages/temper-geometry/src/zone_generator.rs::mst_edges` /
`stitch_mst_with_gate`) and generalises to every zone-eligible net, so the
port's correctness can be verified against the exact behaviour the single
net (`power_in.ntc-no`'s MST fallback path -- its own edges are actually
the hand-verified `_CONTINUITY_EXEMPT_NET_VERIFIED_EDGES` override, never
the MST fallback in production, but the fallback algorithm itself is
identical code, exercised the same way for every other net once
generalised) already ran.

See docs/evidence/2026-08-18-zone-pour-fragmentation-rootcause.md for the
full root-cause analysis, differential results, and the port decision.
"""

from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# From _zone_pour_stitch.py @ 9a55b56be95f985098c4cb9c0abfc4569a79dcad
# ---------------------------------------------------------------------------


def _mst_edges(positions: list[tuple[float, float]]) -> list[tuple[int, int]]:
    """Euclidean minimum spanning tree over *positions*, Prim's O(n^2).

    Extracted, unchanged, from ``_stitch_pads_to_each_other``'s inline MST
    fallback (2026-08-14) so it can be exercised standalone -- board-scale
    pad counts are never more than a handful, so O(n^2) is simple,
    deterministic, and needs no external dependency at this size. A
    reasonable STARTING GUESS, not a DRC-verified result on its own; see
    ``_gate_filter_edges`` for the check that makes it safe to emit.

    Deterministic tie-break: ties are broken by iterating ``in_tree`` in
    insertion order and ``remaining`` in ascending original-index order,
    keeping the FIRST edge found (strict ``<``). ``positions[0]`` is always
    the tree's root.
    """
    remaining = list(range(1, len(positions)))
    in_tree = [0]
    edges: list[tuple[int, int]] = []
    while remaining:
        best = None
        best_d2 = float("inf")
        for i in in_tree:
            xi, yi = positions[i]
            for j in remaining:
                xj, yj = positions[j]
                d2 = (xj - xi) ** 2 + (yj - yi) ** 2
                if d2 < best_d2:
                    best_d2 = d2
                    best = (i, j)
        assert best is not None
        edges.append(best)
        in_tree.append(best[1])
        remaining.remove(best[1])
    return edges


def _gate_filter_edges(
    positions: list[tuple[float, float]],
    edges: list[tuple[int, int]],
    obstacle_records: list[tuple[int, float, float, float, float, float, float]],
    stitch_width_mm: float,
) -> tuple[list[tuple[int, int]], int]:
    """Drop every edge whose buffered footprint intersects the obstacle union.

    Extracted, unchanged, from ``_stitch_pads_to_each_other``'s inline
    C-space gate (2026-08-16). ``obstacle_records`` is the same
    ``collect_zone_obstacle_records`` flat-record convention the Rust zone
    carve (``pour_outline_py``) consumes -- each item already buffered by
    its own pair-resolved ``max(clearance, creepage)`` separation, so this
    gate is creepage-aware for HV pairs by construction, not merely
    clearance-aware: there is no separate "is this pair HV" branch here to
    drift out of step with the carve's own figure.

    Returns ``(kept_edges, skipped_count)``. A skipped edge is dropped
    fail-closed -- never emitted as a known-shorting/creeping straight
    line.
    """
    from shapely.geometry import LineString, Point
    from shapely.ops import unary_union

    geoms: list = []
    for kind, x, y, a, b, w, separation in obstacle_records:
        if kind == 0:  # Pad
            geoms.append(Point(x, y).buffer(math.hypot(a, b) + separation, quad_segs=8))
        elif kind == 1:  # Track
            geoms.append(LineString([(x, y), (a, b)]).buffer(w / 2.0 + separation, quad_segs=8))
        else:  # Via
            geoms.append(Point(x, y).buffer(a / 2.0 + separation, quad_segs=8))
    obstacle_union = unary_union(geoms) if geoms else None

    kept: list[tuple[int, int]] = []
    skipped = 0
    for i, j in edges:
        xi, yi = positions[i]
        xj, yj = positions[j]
        if obstacle_union is not None and not obstacle_union.is_empty:
            footprint = LineString([(xi, yi), (xj, yj)]).buffer(
                stitch_width_mm / 2.0, quad_segs=8
            )
            if footprint.intersects(obstacle_union):
                skipped += 1
                continue
        kept.append((i, j))
    return kept, skipped
