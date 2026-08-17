"""Differential tests: ``channel_skeleton._radius_pairs`` (Rust ``rstar``
R*-tree, via ``temper_geometry.radius_pairs_transform``) vs
``scipy.spatial.cKDTree.query_pairs``, the pre-migration oracle pinned here
per R19 (see ``docs/wave4-discipline-contract.md`` and mirroring
``test_routability_check_cc_rust_differential.py``'s structure).

Three things this suite verifies, matching the task's determinism
requirements for ``_ensure_skeleton_connectivity``'s content-addressed
output:

1. **Pair-set agreement**: the Rust radius query returns exactly the same
   unordered pair SET as scipy's ``query_pairs`` (pair ORDER is explicitly
   not part of either backend's contract -- see ``radius_pairs.rs``'s module
   doc -- so this compares as sets, not sequences).
2. **MST-edge agreement**: feeding either backend's candidate pairs through
   the *same* canonical ``(distance, i, j)`` tie-break and Kruskal loop
   ``_ensure_skeleton_connectivity`` actually uses produces the identical
   resulting edge set -- the property that actually matters for the router's
   output, not just the intermediate candidate set.
3. **Cross-process byte-identical determinism**: two separate Python
   processes given the same input produce byte-identical
   ``radius_pairs_transform`` output -- the property the content-addressing
   work this migration must not regress actually depends on.

This module (``channel_skeleton.py``) no longer imports ``scipy`` for its
island-bridging candidate generation; ``scipy.spatial.cKDTree`` is retained,
unused there, only as the oracle pinned in this file.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

import tests.graph_fixtures as nx
import numpy as np
import pytest

from temper_placer.router_v6.channel_skeleton import (
    _ensure_skeleton_connectivity,
    _radius_pairs,
)

# ---------------------------------------------------------------------------
# Oracle: the pre-migration scipy call, pinned verbatim (R19).
# ---------------------------------------------------------------------------


def _scipy_query_pairs(positions: np.ndarray, radius: float) -> np.ndarray:
    """Pre-migration oracle: this is exactly what ``_ensure_skeleton_connectivity``
    computed before the Rust ``radius_pairs`` migration."""
    from scipy.spatial import cKDTree

    if len(positions) < 2:
        return np.empty((0, 2), dtype=np.int64)
    tree = cKDTree(positions)
    return tree.query_pairs(r=radius, output_type="ndarray")


def _pair_set(pairs: np.ndarray) -> set[tuple[int, int]]:
    return {(int(a), int(b)) for a, b in pairs}


def _mst_edges(positions: np.ndarray, pairs: np.ndarray) -> set[tuple[int, int]]:
    """Reproduce ``_ensure_skeleton_connectivity``'s Kruskal-over-radius-pairs
    logic (no obstacle geometry -- this isolates the spatial-index +
    tie-break + union-find behavior from the separate, already-tested
    ``_bridge_validity_mask`` geometry gate) on a single connected component
    (every node its own component), so every candidate pair is a genuine
    cross-"component" candidate and the MST spans the point set.

    Uses the exact canonical ``(distance, i, j)`` tie-break
    ``_ensure_skeleton_connectivity`` itself uses, so this function's only
    remaining degree of freedom is which pair SET it started from -- which
    is exactly what this differential suite is isolating.
    """
    n = len(positions)
    if n < 2 or len(pairs) == 0:
        return set()
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> bool:
        ra, rb = find(a), find(b)
        if ra == rb:
            return False
        parent[ra] = rb
        return True

    dist = np.linalg.norm(positions[pairs[:, 0]] - positions[pairs[:, 1]], axis=1)
    order = np.lexsort((pairs[:, 1], pairs[:, 0], dist))
    edges = set()
    for pos in order:
        i, j = int(pairs[pos, 0]), int(pairs[pos, 1])
        if union(i, j):
            edges.add((i, j))
    return edges


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------


def _curated_cases() -> list[tuple[np.ndarray, float]]:
    cases: list[tuple[np.ndarray, float]] = []

    cases.append((np.empty((0, 2), dtype=np.float64), 5.0))
    cases.append((np.array([[0.0, 0.0]]), 5.0))
    cases.append((np.array([[0.0, 0.0], [3.0, 4.0]]), 5.0))  # exact boundary
    cases.append((np.array([[0.0, 0.0], [3.0, 4.0]]), 4.999))  # just under

    # Coincident points (real skeleton nodes can share exact coordinates,
    # e.g. mirrored/symmetric board layouts, or pad-anchor nodes -- see
    # ChannelSkeletonStage's "Added N pad anchor nodes to skeleton").
    coincident = np.array(
        [[0.0, 0.0]] * 5 + [[2.0, 2.0]] * 3 + [[100.0, 100.0]],
        dtype=np.float64,
    )
    for r in (0.0, 0.1, 2.83, 3.0, 200.0):
        cases.append((coincident, r))

    # Regular grid: many exact-distance ties by construction -- the sharpest
    # discriminator for the tie-breaking contract this migration must
    # preserve (see channel_skeleton.py's "Spatial-index migration" doc).
    grid = np.array(
        [[float(x), float(y)] for x in range(10) for y in range(10)],
        dtype=np.float64,
    )
    for r in (1.0, 1.5, 2.0, 3.0):
        cases.append((grid, r))

    # Random point clouds at varying density (radius relative to spacing).
    rng = np.random.default_rng(20260807)
    for n in (20, 100, 400):
        for extent in (5.0, 50.0, 500.0):
            positions = rng.random((n, 2)) * extent
            for radius in (0.5, 2.0, 8.0):
                cases.append((positions, radius))

    return cases


# ---------------------------------------------------------------------------
# 1. Pair-set agreement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case_idx", range(len(_curated_cases())))
def test_radius_pairs_matches_scipy_pair_set(case_idx: int) -> None:
    positions, radius = _curated_cases()[case_idx]
    got = _pair_set(_radius_pairs(positions, radius))
    want = _pair_set(_scipy_query_pairs(positions, radius))
    assert got == want, (
        f"pair set mismatch at n={len(positions)}, radius={radius}: "
        f"only-in-rust={got - want}, only-in-scipy={want - got}"
    )


def test_radius_pairs_result_dtype_and_shape() -> None:
    positions = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=np.float64)
    out = _radius_pairs(positions, 5.0)
    assert out.dtype == np.int64
    assert out.ndim == 2
    assert out.shape[1] == 2


def test_radius_pairs_i_less_than_j_always() -> None:
    rng = np.random.default_rng(7)
    positions = rng.random((200, 2)) * 20.0
    out = _radius_pairs(positions, 5.0)
    assert np.all(out[:, 0] < out[:, 1])


# ---------------------------------------------------------------------------
# 2. MST-edge agreement (the property that actually matters downstream)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case_idx", range(len(_curated_cases())))
def test_mst_edges_match_scipy_oracle(case_idx: int) -> None:
    positions, radius = _curated_cases()[case_idx]
    rust_pairs = _radius_pairs(positions, radius)
    scipy_pairs = _scipy_query_pairs(positions, radius)
    got = _mst_edges(positions, rust_pairs)
    want = _mst_edges(positions, scipy_pairs)
    assert got == want, (
        f"MST edge mismatch at n={len(positions)}, radius={radius}: "
        f"only-in-rust={got - want}, only-in-scipy={want - got}"
    )


def test_full_bridging_matches_between_backends_on_grid_islands() -> None:
    """End-to-end: build a fragmented skeleton graph (several disjoint
    islands, no obstacle geometry) and confirm
    ``_ensure_skeleton_connectivity`` -- the actual production function,
    unmodified except for its already-migrated spatial-index call --
    produces a graph whose edge set does not depend on whether the
    candidate pairs happened to come from scipy or Rust. Since production
    code now always uses Rust, this is exercised by re-deriving what the
    scipy-backed answer *would have been* via the same tie-break/Kruskal
    logic (`_mst_edges`) and comparing against the real function's output.
    """
    G = nx.Graph()
    rng = np.random.default_rng(42)
    island_positions: list[tuple[float, float]] = []
    for k in range(12):
        cx, cy = (k % 4) * 3.0, (k // 4) * 3.0
        pts = rng.random((5, 2)) * 0.4 + np.array([cx, cy])
        for a, b in zip(pts, pts[1:]):
            G.add_edge(tuple(a), tuple(b), weight=float(np.linalg.norm(a - b)))
        island_positions.extend(tuple(p) for p in pts)

    result = _ensure_skeleton_connectivity(G.copy(), max_bridge_distance=5.0)
    assert nx.is_connected(result)

    nodes = list(G.nodes())
    node_index = {node: i for i, node in enumerate(nodes)}
    positions = np.asarray(nodes, dtype=float)
    scipy_pairs = _scipy_query_pairs(positions, 5.0)

    # Reproduce the ACTUAL cross-component Kruskal `_ensure_skeleton_connectivity`
    # runs (union-find pre-seeded with the graph's existing connected
    # components, not one singleton per node -- `_mst_edges` above
    # deliberately does the simpler singleton-per-node MST for the isolated
    # radius-pairs-vs-Kruskal unit tests, which is a different scenario from
    # this end-to-end islands-already-connected-internally case).
    components = list(nx.connected_components(G))
    comp_of = {}
    for cid, comp in enumerate(components):
        for node in comp:
            comp_of[node_index[node]] = cid
    parent = list(range(len(components)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> bool:
        ra, rb = find(a), find(b)
        if ra == rb:
            return False
        parent[ra] = rb
        return True

    dist = np.linalg.norm(positions[scipy_pairs[:, 0]] - positions[scipy_pairs[:, 1]], axis=1)
    order = np.lexsort((scipy_pairs[:, 1], scipy_pairs[:, 0], dist))
    expected_added = set()
    for pos in order:
        i, j = int(scipy_pairs[pos, 0]), int(scipy_pairs[pos, 1])
        ci, cj = comp_of[i], comp_of[j]
        if ci == cj:
            continue
        if union(ci, cj):
            expected_added.add(frozenset((i, j)))

    original_edges = {
        frozenset((node_index[a], node_index[b])) for a, b in G.edges()
    }
    result_edges = {
        frozenset((node_index[a], node_index[b])) for a, b in result.edges()
    }
    added_edges = result_edges - original_edges
    assert added_edges == expected_added


# ---------------------------------------------------------------------------
# 3. Cross-process byte-identical determinism
# ---------------------------------------------------------------------------


def test_radius_pairs_transform_byte_identical_across_processes() -> None:
    """The content-addressing requirement this migration must not regress:
    the same input must produce byte-identical
    ``temper_geometry.radius_pairs_transform`` output whether called again
    in this process or from a freshly started one (different PID,
    different ``PYTHONHASHSEED`` unless pinned, different malloc arena
    layout) -- i.e. the result must not depend on anything process-local.
    """
    script = textwrap.dedent(
        """
        import numpy as np
        import temper_geometry as tg

        rng = np.random.default_rng(20260807)
        positions = np.ascontiguousarray(rng.random((300, 2)) * 40.0, dtype=np.float64)
        out = tg.radius_pairs_transform(positions.tobytes(), len(positions), 3.0)
        import sys
        sys.stdout.buffer.write(out)
        """
    )
    results = []
    for _ in range(2):
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            check=True,
        )
        results.append(proc.stdout)
    assert len(results[0]) > 0, "expected at least one pair in this fixed corpus"
    assert results[0] == results[1], "radius_pairs_transform output differs across processes"


def test_radius_pairs_transform_byte_identical_same_process_repeated_calls() -> None:
    rng = np.random.default_rng(123)
    positions = np.ascontiguousarray(rng.random((150, 2)) * 25.0, dtype=np.float64)
    import temper_geometry as tg

    first = tg.radius_pairs_transform(positions.tobytes(), len(positions), 4.0)
    for _ in range(5):
        again = tg.radius_pairs_transform(positions.tobytes(), len(positions), 4.0)
        assert again == first
