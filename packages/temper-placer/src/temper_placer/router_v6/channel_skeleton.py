"""
Router V6 Stage 2.3: Extract Channel Skeleton

Extracts channel centerlines using medial axis transform to find routing paths.
Part of temper-h6t7 (Stage 2 - Channel Analysis)
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import shapely
import temper_design_bundle_python as _tdb
import temper_geometry as _tg
from shapely.geometry import LineString, MultiPolygon, Polygon

from temper_placer.core.pin_geometry import pin_world_position
from temper_placer.deterministic.stages.base import Stage
from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.routing_space import RoutingSpace
from temper_placer.router_v6.stage0_data import ParsedPCB
from temper_placer.router_v6.stage_validators import (
    StageDRCFailure,
    register_validator,
)

# Re-export the Rust pyclass under its public name.
SkeletonGraph = _tdb.channel_skeleton_contracts.SkeletonGraph


@dataclass
class ChannelSkeleton:
    """Skeleton graph representing routing channels."""

    graph: SkeletonGraph  # Nodes are (x, y) positions, edges are channel segments
    layer_name: str
    total_length: float  # Total channel length in mm

    @property
    def is_connected(self) -> bool:
        """Check if the channel graph is fully connected."""
        return self.graph.is_connected() if self.graph.number_of_nodes() > 0 else True

    @property
    def node_count(self) -> int:
        """Number of nodes in the skeleton."""
        return self.graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        """Number of edges in the skeleton."""
        return self.graph.number_of_edges()


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

        # Add pads as anchor nodes, connected to nearest skeleton node.
        #
        # The dedup scan and the nearest-node scan that used to be written
        # out here now run in Rust
        # (``temper_geometry.pad_anchor_plan_py``, see
        # ``packages/temper-geometry/src/channel_skeleton.rs``). They were
        # the single largest line-item in a full production route: a
        # cProfile (301.04s wall, board digest ``6d4e17337bcf2633``, 4553
        # segments) charged 22.3s of SELF time to this function -- the
        # ``for node in skeleton_nodes`` loop, inline here and so attributed
        # here -- plus 15.2s to the ``any(...)`` dedup generator over
        # **97,412,627** evaluations. Both were brute-force
        # O(pads x skeleton_nodes) sweeps over Python coordinate tuples, and
        # this board's outer layers carry ~41k skeleton nodes each.
        #
        # ``pad_anchor_plan_py`` is a verbatim transcription of those two
        # loops, deliberately still brute force: it is an argmin over
        # distances, and the Python resolves ties to the earliest node in
        # ``skeleton_nodes`` order via a strict ``<``, which a spatial
        # index's own tie-breaking would not reproduce. See that module's
        # comment for the full list of preserved behaviours -- including
        # that ``skeleton_nodes`` is a snapshot (pads anchored earlier are
        # invisible to later pads) and that a duplicated pad position still
        # contributes its own ``total_length`` increment.
        skeleton_nodes = list(G.nodes)
        pads_added = 0

        pads_arr = np.ascontiguousarray(pad_positions, dtype=np.float64)
        nodes_arr = np.ascontiguousarray(skeleton_nodes, dtype=np.float64)
        plan = _tg.pad_anchor_plan_py(
            pads_arr.tobytes(),
            len(pad_positions),
            nodes_arr.tobytes(),
            len(skeleton_nodes),
            0.1,  # dedup half-width (mm) -- literal from the pinned Python
            50.0,  # "only connect if within 50mm" -- literal from the pinned Python
        )

        # Replay the plan in pad order. The order is part of the contract:
        # float addition is not associative, so ``total_length`` must
        # accumulate in exactly the original sequence.
        for pad_idx, node_idx, min_dist in plan:
            pad_pos = pad_positions[pad_idx]
            nearest_node = skeleton_nodes[node_idx]
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


def _extract_medial_axis(
    polygon_or_multipolygon,
    simplify_tolerance: float = 0.5,
) -> list[LineString]:
    """
    Extract medial axis using Voronoi diagram approach.

    Args:
        polygon_or_multipolygon: Available routing area
        simplify_tolerance: Simplification tolerance

    Returns:
        List of LineStrings representing skeleton
    """
    from shapely.geometry import MultiPolygon, Polygon

    # Handle MultiPolygon
    if isinstance(polygon_or_multipolygon, MultiPolygon):
        all_lines = []

        if hasattr(polygon_or_multipolygon, "geoms"):
            polys = list(polygon_or_multipolygon.geoms)
        else:
            polys = [polygon_or_multipolygon]

        # Combine skeletons from all polygons
        for p in polys:
            lines = _extract_medial_axis_single(p, simplify_tolerance)
            all_lines.extend(lines)
        return all_lines
    elif isinstance(polygon_or_multipolygon, Polygon):
        return _extract_medial_axis_single(polygon_or_multipolygon, simplify_tolerance)
    else:
        return []


def _extract_medial_axis_single(
    polygon: Polygon,
    simplify_tolerance: float = 0.5,
) -> list[LineString]:
    """
    Extract medial axis for a single polygon via an independent (non-GEOS)
    Voronoi diagram, computed in Rust.

    Delegates the full pipeline -- boundary sampling, Voronoi, the
    interior-edge filter, and both fallback branches (degenerate <3-point
    input, and Voronoi-yields-nothing) -- to
    ``temper_geometry.extract_medial_axis_single_py``. See
    ``packages/temper-geometry/src/channel_skeleton.rs`` for the port.

    Why an independent (spade, not GEOS) Voronoi is safe here: SAT
    channel-edge identity (``constraint_model.py::canonical_channel_edges``)
    is built from endpoints quantised to 1e-6 mm and ordered by that
    quantised key -- not from Voronoi emission order or raw float ``repr()``
    (fixed on ``fix/constraint-model-edge-identity``, the blocker recorded
    in three prior triage documents, most recently
    ``docs/evidence/2026-08-07-channel-skeleton-triage-no-port.md``). The
    2026-08-04 spike
    (``docs/evidence/2026-08-04-shapely-voronoi-channel-skeleton-spike.md``)
    measured an independent (Qhull) Voronoi reproducing the GEOS skeleton to
    <1e-9 mm on 12/12 boards -- three orders of magnitude finer than the
    1e-6 mm quantum -- and this migration re-verified the claim (12/12
    boards, both at the 1e-6 mm node-set level and directly on
    ``canonical_channel_edges()``-style ids) before porting.

    ``simplify_tolerance`` is threaded through for signature parity; it is
    a documented no-op on this path (spike §8: GEOS's Voronoi edges here
    are always exactly 2 coordinates, and Douglas-Peucker simplification of
    a 2-point line is the identity -- spade's undirected Voronoi edges are
    likewise always two circumcenters, so the same holds structurally).

    Args:
        polygon: Single polygon
        simplify_tolerance: Simplification tolerance (no-op; see above)

    Returns:
        List of LineStrings
    """
    outer = list(polygon.exterior.coords)
    holes = [list(interior.coords) for interior in polygon.interiors]
    segments = _tg.extract_medial_axis_single_py(outer, holes, simplify_tolerance)
    return [LineString([p1, p2]) for p1, p2 in segments]


class _UnionFind:
    """Disjoint-set over small integer labels (component ids), path-compressed
    with union-by-rank. Used to track which islands have merged without
    re-running ``connected_components`` (an O(V+E) pass) after every edge."""

    __slots__ = ("parent", "rank")

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1
        return True


def _bridge_validity_mask(
    available_area: Polygon | MultiPolygon | None,
    coords_a: np.ndarray,
    coords_b: np.ndarray,
) -> np.ndarray:
    """Validate, in one vectorized batch, that every candidate bridge segment
    ``(coords_a[k], coords_b[k])`` lies entirely inside the routable region.

    Returns a boolean array aligned with the input rows (all True when
    ``available_area`` is None -- e.g. synthetic graphs built without
    routing-space geometry, matching the legacy no-check behavior).

    Why vectorized rather than a per-candidate ``PreparedGeometry.contains``
    call: measured on pcb/temper.kicad_pcb, an individually-prepared
    predicate (``shapely.prepared.prep(area).contains(line)`` called once
    per candidate) costs ~13us/call in Python-loop overhead; batching the
    same predicate through ``shapely.prepare`` (in-place, vectorized) plus
    the ``shapely.contains`` ufunc over a numpy array of geometries costs
    ~1us/call -- roughly 13x faster because the per-call Python/GIL
    overhead is paid once for the whole batch instead of once per candidate.
    At O(10^6) candidates (2.6M on F.Cu within a 10mm bridging radius) that
    difference is the gap between this stage costing single-digit seconds
    and costing nearly a minute. A tiny buffer absorbs floating point noise
    where a skeleton node sits exactly on the routable-region boundary
    (common -- skeleton nodes are themselves derived from that boundary's
    medial axis).
    """
    if available_area is None or available_area.is_empty or len(coords_a) == 0:
        return np.ones(len(coords_a), dtype=bool)

    coord_pairs = np.stack([coords_a, coords_b], axis=1)  # (N, 2, 2)
    line_arr = shapely.linestrings(coord_pairs)

    buffered = available_area.buffer(1e-6)
    shapely.prepare(buffered)
    return shapely.contains(buffered, line_arr)


def _radius_pairs(positions: np.ndarray, radius: float) -> np.ndarray:
    """All unordered index pairs ``(i, j)``, ``i < j``, within ``radius`` of
    each other, delegating to ``temper_geometry.radius_pairs_transform``
    (Rust, ``rstar`` R*-tree).

    Matches the pair SET ``scipy.spatial.cKDTree(positions).query_pairs(r=radius,
    output_type="ndarray")`` computes -- exactly (see
    ``packages/temper-geometry/src/radius_pairs.rs``'s differential-corpus
    tests and ``tests/router_v6/test_channel_skeleton_radius_pairs_rust_differential.py``).
    This function's own pair ORDER is not part of its contract and is not
    guaranteed to match scipy's: the caller (``_ensure_skeleton_connectivity``)
    sorts candidates by an explicit ``(distance, i, j)`` key before consuming
    them, precisely so that which spatial-index implementation produced the
    unordered candidate set never affects the resulting MST -- see that
    function's docstring, "Spatial-index migration" section, for why this
    matters.

    ``positions`` must be ``(N, 2)`` float64. Returns an ``(P, 2)`` int64
    array (``P`` = number of pairs found), empty (shape ``(0, 2)``) when
    there are none.

    R19: the pre-migration ``scipy.spatial.cKDTree.query_pairs`` call is
    retained, unused here, as the differential's pinned oracle in
    ``tests/router_v6/test_channel_skeleton_radius_pairs_rust_differential.py``.
    """
    n = len(positions)
    if n < 2:
        return np.empty((0, 2), dtype=np.int64)
    positions_c = np.ascontiguousarray(positions, dtype=np.float64)
    out_bytes = _tg.radius_pairs_transform(positions_c.tobytes(), n, float(radius))
    if len(out_bytes) == 0:
        return np.empty((0, 2), dtype=np.int64)
    return np.frombuffer(out_bytes, dtype="<i8").reshape(-1, 2)


def _ensure_skeleton_connectivity(
    G,
    max_bridge_distance: float = 5.0,
    available_area: Polygon | MultiPolygon | None = None,
):
    """
    Ensure skeleton graph is fully connected by adding bridge edges.

    Args:
        G: Potentially fragmented skeleton graph
        max_bridge_distance: Maximum distance (mm) to bridge between islands
        available_area: Routable region (obstacles already subtracted). When
            given, every candidate bridge is validated to lie entirely
            inside it before being added -- bridging through an obstacle
            would silently create a route where copper actually is. When
            None (e.g. synthetic graphs built without routing-space
            geometry), bridges are not geometry-checked, matching the
            legacy behavior.

    Returns:
        Connected graph (or as connected as ``max_bridge_distance`` and
        obstacle geometry allow -- islands with no valid bridge within
        that distance are left unconnected, same as before).

    Algorithm (replaces an O(components^2 * nodes_per_component^2)
    brute-force nearest-pair search that did not complete in practical
    time on production geometry -- a single outer-loop pass did not finish
    in 79s of pure-Python CPU time on pcb/temper.kicad_pcb's 153-island
    F.Cu skeleton):

    The old code's "always bridge the globally closest cross-island node
    pair, recompute components, repeat" is exactly Kruskal's MST algorithm
    run over the complete graph of all skeleton nodes, restricted to
    cross-component edges and thresholded at ``max_bridge_distance``: both
    add the cheapest available edge that connects two different components,
    in ascending distance order, and stop when nothing eligible remains
    under the threshold. That equivalence is what licenses replacing the
    brute-force distance computation with a spatial index without changing
    which components end up merged (it is the same MST-with-cutoff, just
    computed without enumerating pairs that were never going to be the
    answer).

    Implementation:
      - ``_radius_pairs`` (``temper_geometry.radius_pairs_transform``, Rust
        ``rstar`` R*-tree -- see ``packages/temper-geometry/src/radius_pairs.rs``)
        finds *every* node pair within the bridging radius in one call --
        O(N log N + P) where P is the number of pairs within the radius
        (output-sensitive: bounded by local point density around each
        node, not by N^2; measured 44.1M pairs for N=41,271 nodes in 1.2s
        on F.Cu using the pre-migration ``scipy.spatial.cKDTree.query_pairs``
        -- this call was migrated off scipy after that measurement, same
        asymptotic bound). This is deliberately exact, not a
        K-nearest-neighbour approximation: an approximate top-K
        candidate set was tried first and rejected -- see "Rejected
        alternatives" below.
      - Pairs are filtered to cross-component ones (O(P)), distances
        computed vectorized (O(P)), then sorted ascending by an explicit
        ``(distance, i, j)`` key (O(P log P)) -- the tie-break is
        index-based rather than relying on whichever order the candidate
        pairs originally arrived in, so which spatial-index backend
        produced the set never affects the resulting MST.
      - Every cross-component candidate's geometry is validated against
        ``available_area`` in **one vectorized batch call**
        (``_bridge_validity_mask``: ``shapely.linestrings`` to construct
        all P candidate segments at once, ``shapely.prepare`` +
        ``shapely.contains`` to test all of them against the routable
        region in a single C-level loop) rather than one Python-level
        ``shapely`` call per candidate -- measured ~13x faster per
        predicate (~1us/candidate vectorized vs ~13us/candidate through an
        individually-prepared-geometry Python call), because the
        candidate-pair count in practice is dominated by genuinely
        obstacle-separated islands where most candidates are invalid (see
        "Upstream finding" below), so a real fraction of P gets checked
        either way.
      - Kruskal via union-find then consumes the sorted candidates using
        the precomputed boolean mask (a cheap array lookup, not a shapely
        call): for each valid candidate that would connect two different
        (super)components, the bridge is added and the components merged.
        The loop exits as soon as every component has merged (union-find
        count reaches 1).

    Total: O(N log N + P log P) where P is the number of node pairs within
    the bridging radius (query-pairs output size, output-sensitive in local
    point density -- not the O(components^2 * nodes^2) term that made the
    original implementation intractable). Measured on pcb/temper.kicad_pcb:
    ~10s wall time per layer including the vectorized geometry pass over
    ~2.6M candidates (see the perf evidence doc for full wall-time/RSS
    tables) versus not completing in 79s of pure-Python CPU for one
    outer-loop pass before.

    Rejected alternatives:
      - K-nearest-neighbour candidate generation (query each node's K
        nearest neighbours, K fixed, e.g. 16) was implemented and measured
        first. It is asymptotically cheaper per query but is an
        *approximation*: a component's true nearest cross-component point
        can be crowded out of any fixed K by same-component neighbours in
        a dense island (the two ~20,000-node F.Cu islands are exactly this
        case), silently under-connecting relative to the exact algorithm
        it replaces. Patching that with a second fallback phase (exact
        nearest-neighbour search only over the few components K-NN missed)
        was also implemented and measured -- and was *slower* than the
        exact radius query on this board (roughly 57s for B.Cu alone),
        because a large fraction of candidates near real-world zone-pour
        geometry are geometrically invalid (obstacle-crossing) and get
        rejected, pushing many components into that fallback path, whose
        cost is quadratic in how many components still need it (a fresh
        O(remaining_components^2) tree-query sweep per single merge). The
        exact radius query has no such failure mode: it enumerates every
        candidate within the threshold once.
      - Per-candidate (non-vectorized) geometry validation, called lazily
        inside the Kruskal loop and skipping remaining candidates for a
        pair once it exceeded an attempt cap, was implemented and measured
        as an intermediate step: it worked (F.Cu ~54s, B.Cu ~48s) but was
        still dominated by ~13us/call Python-level ``shapely`` overhead at
        the P ~ 10^6 scale this board exhibits, and traded away exactness
        (a capped pair could in principle have had a valid bridge past the
        cap). Batching the *entire* candidate set through one vectorized
        ``shapely.contains`` call (~1us/candidate) removed both problems at
        once -- it is both faster in aggregate and exact, so the attempt
        cap was deleted rather than kept as a secondary safeguard.
      - A Euclidean-MST-over-island-*centroids* formulation (bridge
        component A to component B via their centroids) was rejected: a
        component's centroid is not guaranteed to be a real skeleton node,
        and worse, a centroid-to-centroid line is far more likely to cross
        an obstacle than a line between the two islands' actual nearest
        boundary nodes -- exactly the geometric-validity failure mode this
        function must avoid.
      - An R-tree over per-node bounding boxes (e.g. via shapely's STRtree)
        was rejected in favor of a KD-tree: candidates here are point-to-
        point nearest-neighbour queries, which is what a KD-tree is built
        for; an R-tree earns its keep over 2D *regions* with extent, which
        skeleton nodes do not have.

    Upstream finding (not fixed here, out of scope -- reported instead):
    the 153/225-island fragmentation this function bridges is itself
    downstream of a documented obstacle-map defect, not primarily a medial-
    axis artifact. F.Cu/B.Cu measure ~25% available area versus ~98% on the
    inner layers on pcb/temper.kicad_pcb, matching the ~24.7% figure in
    docs/solutions/best-practices/correct-diagnosis-unsafe-change-2026-07-28.md's
    2026-07-29 update: ``obstacle_map.py``'s zone loop unions every zone on
    a layer into that layer's obstacle polygon net-blind (regardless of
    which net the pour belongs to), so outer-layer pours the router will
    never actually route through still carve the medial axis into many
    small, often genuinely wall-separated pockets. The inner layers, with
    real pour-free area, produce only 3 islands. A correct fast bridging
    algorithm over spurious islands is still bridging the wrong problem;
    the durable fix is the already-scoped, not-yet-implemented "pours
    become derived output" project
    (docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md).
    """
    if G.number_of_nodes() == 0:
        return G

    components = G.connected_components()
    n_components = len(components)
    if n_components <= 1:
        return G  # Already connected

    # Wave 4: G.nodes is a property on SkeletonGraph (was list(G.nodes()) on nx.Graph).
    nodes = list(G.nodes)
    positions = np.asarray(nodes, dtype=float)
    node_index = {node: i for i, node in enumerate(nodes)}

    comp_id = np.empty(len(nodes), dtype=np.int64)
    for cid, comp in enumerate(components):
        for node in comp:
            comp_id[node_index[node]] = cid

    uf = _UnionFind(n_components)
    merges = 0

    pairs = _radius_pairs(positions, max_bridge_distance)

    if len(pairs) > 0:
        ci_all = comp_id[pairs[:, 0]]
        cj_all = comp_id[pairs[:, 1]]
        cross_mask = ci_all != cj_all
        cross_pairs = pairs[cross_mask]

        if len(cross_pairs) > 0:
            cand_dist = np.linalg.norm(
                positions[cross_pairs[:, 0]] - positions[cross_pairs[:, 1]], axis=1
            )
            # Canonical tie-break: sort by (distance, i, j), not distance
            # alone. `_radius_pairs` already guarantees i < j per pair (see
            # its own docstring), so this is a total order with no ties --
            # deterministic and independent of which spatial-index backend
            # produced the candidate set.
            order = np.lexsort((cross_pairs[:, 1], cross_pairs[:, 0], cand_dist))
            cross_pairs = cross_pairs[order]
            cand_dist = cand_dist[order]

            # Validate every candidate's geometry in one vectorized batch
            # up front (see _bridge_validity_mask's docstring for why this
            # beats a per-candidate check by ~13x) -- the Kruskal loop below
            # then does a plain boolean-array lookup per candidate instead
            # of a shapely call, so it stays cheap even at O(10^6)
            # candidates with no need to bound how many are attempted per
            # component pair.
            valid_mask = _bridge_validity_mask(
                available_area,
                positions[cross_pairs[:, 0]],
                positions[cross_pairs[:, 1]],
            )

            for pos in range(len(cross_pairs)):
                if not valid_mask[pos]:
                    continue
                i, j = int(cross_pairs[pos, 0]), int(cross_pairs[pos, 1])
                ci, cj = uf.find(comp_id[i]), uf.find(comp_id[j])
                if ci == cj:
                    continue
                d = float(cand_dist[pos])
                a, b = nodes[i], nodes[j]
                G.add_edge(a, b, weight=d)
                uf.union(ci, cj)
                merges += 1
                if merges == n_components - 1:
                    break

    if merges < n_components - 1:
        n_remaining = len({uf.find(c) for c in comp_id})
    return G


class ChannelSkeletonStage(Stage):
    """Stage 2.3: Extract channel skeletons from routing spaces."""

    @property
    def name(self) -> str:
        return "ChannelSkeleton"

    def run(self, state: BoardState) -> BoardState:
        assert state._parsed_pcb is not None
        pcb: ParsedPCB = state._parsed_pcb
        routing_spaces = state.routing_spaces
        skeletons: dict[str, ChannelSkeleton] = {}
        # Was hardcoded to the two literal outer-copper layer names only --
        # a hardcode present since this stage's original implementation
        # (4bf34600), predating this board having a 4-layer stackup with
        # named inner routable layers. Once RoutingSpaceStage
        # (routing_space.py:85) already restricts `routing_spaces` to
        # routable layers, filtering again here to two hardcoded names
        # silently drops every other routable layer from ever getting a
        # channel skeleton -- regardless of whether it is present and
        # usable. Combined with the plane-condemnation quantifier bug (see
        # the use_declared_layer_roles=True comment in _pipeline_core.py),
        # this left state.channel_skeletons == {} even when routing_spaces
        # was non-empty (see
        # docs/evidence/2026-08-07-router-silent-noop-diagnosis.md, "Bug
        # B"). A 4-layer board should be able to use its inner layers, so
        # build a skeleton for every routable layer routing_spaces
        # actually contains.
        for layer_name, routing_space in routing_spaces.items():  # type: ignore[union-attr]
            skeleton = extract_channel_skeleton(routing_space, pcb=pcb)
            skeletons[layer_name] = skeleton
        return replace(state, channel_skeletons=skeletons)


@register_validator("ChannelSkeleton")
def validate_channel_skeleton(state: BoardState) -> list[StageDRCFailure]:
    """Validate channel skeleton invariants."""
    failures: list[StageDRCFailure] = []
    if state.channel_skeletons is None:
        failures.append(
            StageDRCFailure(
                field="channel_skeletons",
                value=None,
                reason="Channel skeletons not computed",
                stage="ChannelSkeleton",
            )
        )
        return failures

    for layer_name, skeleton in state.channel_skeletons.items():
        if skeleton.node_count == 0 and state.routing_spaces:
            rs = state.routing_spaces.get(layer_name)
            if rs and rs.routing_area > 0:
                failures.append(
                    StageDRCFailure(
                        field="channel_skeletons",
                        value=layer_name,
                        reason="Zero nodes on layer with positive routing area",
                        stage="ChannelSkeleton",
                    )
                )

    return failures
