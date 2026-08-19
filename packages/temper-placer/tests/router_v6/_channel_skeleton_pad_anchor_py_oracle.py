"""Pinned Python oracle for the channel-skeleton PAD-ANCHORING migration.

DO NOT EDIT -- THIS IS THE REFERENCE.
=====================================
``extract_channel_skeleton`` below is a **verbatim** ``git show``
extraction from commit ``19ddbbbc8079641edbfd9fc1270a568ca54843d3``
(``origin/main`` at the time this migration branched) of
``temper_placer/router_v6/channel_skeleton.py``.

Nothing has been cleaned up, refactored, or fixed *by this file*.
``test_channel_skeleton_pad_anchor_rust_differential.py::test_oracle_is_verbatim_copy``
re-extracts the definition from the pinned commit and compares the source
text character for character.

Why this function, and why now
---------------------------------
The sibling oracle ``_channel_skeleton_py_oracle.py`` pinned the
medial-axis compute and explicitly listed this function's pad-anchoring
block as NOT migrated, on the grounds that it is "dict/list bookkeeping
over ``ParsedPCB.components``/``pins``, orchestration".

That classification was wrong on cost, and a cProfile of a full production
route (301.04s wall, board digest ``6d4e17337bcf2633``, 4553 segments)
measured why:

* ``channel_skeleton.py:56`` (``extract_channel_skeleton``) --- 22.3s
  SELF time, 80.5s cumulative, from **six** calls. The self time is the
  nearest-skeleton-node scan at the pinned source's inner ``for node in
  skeleton_nodes`` loop, which is inline in this function and therefore
  attributed to it.
* ``channel_skeleton.py:159`` ``<genexpr>`` --- 15.2s over
  **97,412,627** evaluations. That is the ``any(...)`` pad-dedup scan.

Both are O(pads x skeleton_nodes) brute-force scans over Python tuples
(~41k nodes per outer layer). The "bookkeeping" framing described the
list/dict handling around them accurately and missed that the two nested
scans in the middle are the single largest line-item in the whole route.

What the migration preserves, exactly
----------------------------------------
This is search-and-classification code, not an emitted pour outline: two
different answers can both be "legal" and only equality reveals a change.
So the Rust port is a **verbatim brute-force transcription**, not a
spatially-indexed rewrite --- no KD-tree, no pruning, no early exit that
could reorder a tie. Specifically preserved:

* ``skeleton_nodes`` is snapshotted BEFORE the pad loop, so pads added
  during the loop are invisible to both later dedup checks and later
  nearest-node searches.
* The dedup predicate is a strict, axis-aligned box test
  (``abs(dx) < 0.1 and abs(dy) < 0.1``), not a radius test.
* The nearest-node search uses strict ``<``, so ties resolve to the
  EARLIEST node in ``skeleton_nodes`` order.
* ``math.sqrt((dx) ** 2 + (dy) ** 2)`` is libm ``pow`` twice followed by
  libm ``sqrt`` --- NOT ``dx * dx``, and NOT ``hypot``. The Rust arm goes
  through ``host_math::pow`` for exactly this reason.
* A pad whose position duplicates an earlier pad's still contributes its
  own ``total_length += min_dist`` and its own ``pads_added`` increment,
  even though ``add_node``/``add_edge`` dedupe it away in the graph. That
  double-count is preserved deliberately.

Not pinned here (imported LIVE by the differential, unchanged by this
migration): ``_extract_medial_axis`` / ``_extract_medial_axis_single``
(already Rust, pinned by the sibling oracle),
``_ensure_skeleton_connectivity``, and ``ChannelSkeleton`` /
``SkeletonGraph``. Both arms feed through the same instances of these, so
the differential isolates the pad-anchoring scan and nothing else.
"""

from __future__ import annotations

from temper_placer.core.pin_geometry import pin_world_position
from temper_placer.router_v6.channel_skeleton import (
    ChannelSkeleton,
    SkeletonGraph,
    _ensure_skeleton_connectivity,
    _extract_medial_axis,
)

# Imported only to satisfy the pinned body's annotation. The pinned function
# is copied verbatim and carries `routing_space: RoutingSpace`; the original
# module resolves that name from its own imports, which are NOT part of the
# pin. `from __future__ import annotations` makes it a string at runtime
# either way -- this import exists so a linter reading the file statically
# sees a defined name, WITHOUT touching a character of the pinned text and
# without a `# noqa`, which would have been a silenced check rather than a
# satisfied one.
from temper_placer.router_v6.routing_space import RoutingSpace

# ===========================================================================
# VERBATIM from channel_skeleton.py @ 19ddbbbc8079641edbfd9fc1270a568ca54843d3
# ===========================================================================


def extract_channel_skeleton(
    routing_space: RoutingSpace,
    simplify_tolerance: float = 0.5,
    pcb=None,  # Optional ParsedPCB for pad anchoring
) -> ChannelSkeleton:
    """
    Extract routing channel skeleton using medial axis approximation.

    If pcb is provided, adds component pad positions as anchor nodes
    connected to nearest skeleton nodes. This ensures routes connect
    to actual pad centers, not approximated skeleton positions.

    Args:
        routing_space: Routing space from Stage 2.2
        simplify_tolerance: Tolerance for simplifying skeleton (mm)
        pcb: Optional ParsedPCB for adding pad anchor nodes

    Returns:
        ChannelSkeleton with graph representation

    Example:
        >>> skeleton = extract_channel_skeleton(routing_space, pcb=pcb)
        >>> skeleton.is_connected
        True
    """
    # Create graph
    G = SkeletonGraph()

    # Get available routing area
    available_area = routing_space.available_area

    if available_area.is_empty:
        # No routing space available
        return ChannelSkeleton(
            graph=G,
            layer_name=routing_space.layer_name,
            total_length=0.0,
        )

    # Extract skeleton using Voronoi-based medial axis approximation
    skeleton_lines = _extract_medial_axis(available_area, simplify_tolerance)

    total_length = 0.0

    # Build graph from skeleton lines
    for line in skeleton_lines:
        coords = list(line.coords)

        for i in range(len(coords) - 1):
            p1 = coords[i]
            p2 = coords[i + 1]

            # Add nodes (use tuple for hashability)
            G.add_node(p1, pos=p1)
            G.add_node(p2, pos=p2)

            # Calculate edge weight (length)
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            length = (dx**2 + dy**2) ** 0.5

            # Add edge with length weight (deduped in Rust -- the
            # duplicate add_edge call from the original code is now
            # a no-op on the second call, matching networkx behaviour).
            G.add_edge(p1, p2, weight=length)
            total_length += length

    # Ensure connectivity by bridging islands. ``available_area`` (obstacles
    # already subtracted) is passed through so every bridge is validated to
    # lie entirely within routable copper -- see _ensure_skeleton_connectivity's
    # docstring for why this check exists and did not before.
    G = _ensure_skeleton_connectivity(
        G, max_bridge_distance=10.0, available_area=available_area
    )

    # **OPTION F FIX**: Add component pad positions as anchor nodes
    if pcb and hasattr(pcb, "components") and G.number_of_nodes() > 0:
        import math

        # Extract all pad positions
        pad_positions = []
        for comp in pcb.components:
            if not comp.initial_position or not hasattr(comp, "pins"):
                continue

            # A rotation-in-degrees expression and an initial_side lookup
            # used to be computed here and discarded -- dead code, found
            # 2026-08-13 auditing initial_rotation_quadrant read sites.
            # Neither fed anything: pad positions below come from
            # `pin_world_position`, which already applies rotation and side
            # correctly.

            for pin in comp.pins:
                if pin.net:
                    abs_pos = pin_world_position(pin, comp)
                    pad_positions.append(abs_pos)

        # Add pads as anchor nodes, connected to nearest skeleton node
        skeleton_nodes = list(G.nodes)
        pads_added = 0

        for pad_pos in pad_positions:
            # Skip if pad already exists in skeleton (within 0.1mm)
            if any(
                abs(pad_pos[0] - n[0]) < 0.1 and abs(pad_pos[1] - n[1]) < 0.1
                for n in skeleton_nodes
            ):
                continue

            # Find nearest skeleton node
            nearest_node = None
            min_dist = float("inf")
            for node in skeleton_nodes:
                dist = math.sqrt((pad_pos[0] - node[0]) ** 2 + (pad_pos[1] - node[1]) ** 2)
                if dist < min_dist:
                    min_dist = dist
                    nearest_node = node

            # Add pad as new node with edge to nearest skeleton node
            if nearest_node and min_dist < 50.0:  # Only connect if within 50mm
                G.add_node(pad_pos, pos=pad_pos)
                G.add_edge(pad_pos, nearest_node, weight=min_dist)
                total_length += min_dist
                pads_added += 1

        if pads_added > 0:
            pass

    return ChannelSkeleton(
        graph=G,
        layer_name=routing_space.layer_name,
        total_length=total_length,
    )
