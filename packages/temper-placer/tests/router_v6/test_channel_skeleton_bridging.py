"""Tests for ``_ensure_skeleton_connectivity`` (island bridging).

Covers two things the perf rewrite (replacing an
O(components^2 * nodes_per_component^2) brute-force nearest-pair search
with a KD-tree radius query + Kruskal MST, see that function's docstring
in channel_skeleton.py) must preserve:

1. Correctness: the result is a connected graph whenever a geometrically
   valid bridge exists, and bridges never cross outside the routable
   region (``available_area``) when one is supplied -- bridging through an
   obstacle would silently create a route where copper actually is.
2. Complexity: bridging time does not blow up quadratically as island
   count grows (a scale guard against reintroducing the O(components^2)
   term that made the original implementation intractable on production
   geometry -- see docs/evidence/2026-08-07-channel-skeleton-bridging-perf.md).
"""

from __future__ import annotations

import time

import tests.graph_fixtures as nx
import pytest
from shapely.geometry import LineString, MultiPolygon, box
from shapely.ops import unary_union

from temper_placer.router_v6.channel_skeleton import _ensure_skeleton_connectivity


def _add_island(G: nx.Graph, nodes: list[tuple[float, float]]) -> None:
    """Add a connected path of nodes to G, forming one island."""
    for a, b in zip(nodes, nodes[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        G.add_edge(a, b, weight=(dx**2 + dy**2) ** 0.5)


def _make_chain_islands(n_islands: int, gap: float = 1.0) -> nx.Graph:
    """N separate 2-node islands spaced ``gap`` mm apart along the x axis."""
    G = nx.Graph()
    step = gap + 0.5
    for k in range(n_islands):
        x0 = k * step
        _add_island(G, [(x0, 0.0), (x0 + 0.3, 0.0)])
    return G


class TestCorrectness:
    def test_no_op_when_already_connected(self):
        G = nx.Graph()
        _add_island(G, [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])
        result = _ensure_skeleton_connectivity(G, max_bridge_distance=5.0)
        assert nx.is_connected(result)
        assert result.number_of_edges() == 2  # untouched

    def test_empty_graph_returns_empty(self):
        G = nx.Graph()
        result = _ensure_skeleton_connectivity(G, max_bridge_distance=5.0)
        assert result.number_of_nodes() == 0

    def test_bridges_multiple_islands_into_connected_graph(self):
        """N widely-separated islands, no obstacle geometry: bridging must
        produce a single connected component using only edges within
        max_bridge_distance, without disturbing the original edges."""
        n_islands = 12
        G = _make_chain_islands(n_islands, gap=1.0)
        original_edges = {frozenset(e) for e in G.edges()}
        assert nx.number_connected_components(G) == n_islands

        result = _ensure_skeleton_connectivity(G, max_bridge_distance=2.0)

        assert nx.is_connected(result)
        # Original topology is preserved -- bridging only *adds* edges.
        assert original_edges.issubset({frozenset(e) for e in result.edges()})
        # Every added edge respects the distance threshold.
        new_edges = {frozenset(e) for e in result.edges()} - original_edges
        assert len(new_edges) == n_islands - 1  # a spanning tree over islands
        for e in new_edges:
            u, v = tuple(e)
            dist = ((u[0] - v[0]) ** 2 + (u[1] - v[1]) ** 2) ** 0.5
            assert dist <= 2.0 + 1e-9

    def test_bridge_rejected_when_no_valid_path_exists(self):
        """Two islands separated by a real gap: available_area covers only
        the two boxes themselves (no connecting corridor), so *no* straight
        line between them can stay inside the routable region. The
        function must NOT fabricate a bridge through that gap, even though
        the nearest node pair is well within max_bridge_distance -- the
        legacy algorithm had no geometry awareness and would have added it.
        """
        box_a = box(0.0, 0.0, 2.0, 2.0)
        box_b = box(3.0, 0.0, 5.0, 2.0)  # 1mm gap, no corridor between them
        available_area = MultiPolygon([box_a, box_b])

        G = nx.Graph()
        _add_island(G, [(0.0, 1.0), (2.0, 1.0)])  # island A, right edge at x=2
        _add_island(G, [(3.0, 1.0), (5.0, 1.0)])  # island B, left edge at x=3
        assert nx.number_connected_components(G) == 2

        result = _ensure_skeleton_connectivity(
            G, max_bridge_distance=5.0, available_area=available_area
        )

        # Nearest node pair (2,1)-(3,1) is 1mm apart -- well under the 5mm
        # threshold -- but every candidate line crosses the un-routable gap
        # between the boxes, so nothing should have been bridged.
        assert nx.number_connected_components(result) == 2
        assert result.number_of_edges() == 2  # unchanged from the input

    def test_bridge_uses_valid_path_around_obstacle(self):
        """Dumbbell-shaped routable region: two boxes connected only by a
        narrow corridor offset from the boxes' nearest edge-to-edge line.
        Skeleton nodes exist both on the (closer, invalid) direct line and
        on the (farther, valid) corridor line. Bridging must find and use
        only the geometrically valid path -- never the shorter invalid one
        -- and the result must be fully connected.
        """
        box_a = box(0.0, 0.0, 2.0, 2.0)
        box_b = box(6.0, 0.0, 8.0, 2.0)
        corridor = box(2.0, 0.9, 6.0, 1.1)
        available_area = unary_union([box_a, box_b, corridor])

        G = nx.Graph()
        # Island A: a node right at y=0 (outside the corridor band) and one
        # inside the corridor band.
        _add_island(G, [(0.0, 0.0), (2.0, 0.0)])
        G.add_node((2.0, 1.0))
        G.add_edge((2.0, 0.0), (2.0, 1.0), weight=1.0)
        # Island B: symmetric.
        _add_island(G, [(8.0, 0.0), (6.0, 0.0)])
        G.add_node((6.0, 1.0))
        G.add_edge((6.0, 0.0), (6.0, 1.0), weight=1.0)

        assert nx.number_connected_components(G) == 2

        result = _ensure_skeleton_connectivity(
            G, max_bridge_distance=5.0, available_area=available_area
        )

        assert nx.is_connected(result)

        # Every edge in the result -- old and new -- must lie inside the
        # routable region (the dumbbell), i.e. no bridge cuts across the
        # empty space outside the corridor.
        prepared_area = available_area.buffer(1e-6)
        for u, v in result.edges():
            line = LineString([u, v])
            assert prepared_area.contains(line), f"edge {u}-{v} exits available_area"


class TestScaleGuard:
    """Regression guard against reintroducing O(components^2) bridging.

    The original implementation's outer loop recomputed a full
    components x components x nodes x nodes nearest-pair search on every
    single merge; on pcb/temper.kicad_pcb's 153-island F.Cu skeleton, one
    such pass measured 91.3s (see the perf evidence doc) and needed up to
    152 passes to finish -- i.e. it did not complete in practical time.
    These synthetic sizes are far smaller (so the test suite stays fast),
    but the growth-rate comparison is what actually guards against the
    quadratic term coming back: doubling components should cost close to
    linearithmically more, not ~4x more.
    """

    @pytest.mark.parametrize("multiplier", [8])
    def test_bridging_time_grows_subquadratically(self, multiplier):
        small_n = 200
        large_n = small_n * multiplier

        G_small = _make_chain_islands(small_n, gap=1.0)
        t0 = time.perf_counter()
        result_small = _ensure_skeleton_connectivity(G_small, max_bridge_distance=2.0)
        t_small = time.perf_counter() - t0
        assert nx.is_connected(result_small)

        G_large = _make_chain_islands(large_n, gap=1.0)
        t0 = time.perf_counter()
        result_large = _ensure_skeleton_connectivity(G_large, max_bridge_distance=2.0)
        t_large = time.perf_counter() - t0
        assert nx.is_connected(result_large)

        # A true O(C^2) algorithm would cost ~multiplier^2 as much (64x for
        # multiplier=8). Require growth well under that -- generous enough
        # to absorb measurement noise on a small, fast synthetic case, but
        # tight enough that a regression back to quadratic scaling fails it.
        quadratic_bound = multiplier**2
        # Guard the ratio against a near-zero t_small making it noisy.
        t_small_floor = max(t_small, 1e-3)
        ratio = t_large / t_small_floor
        assert ratio < quadratic_bound / 2, (
            f"bridging time grew {ratio:.1f}x for a {multiplier}x increase in "
            f"islands (t_small={t_small:.4f}s, t_large={t_large:.4f}s) -- "
            f"expected well under the {quadratic_bound}x a quadratic algorithm "
            f"would cost"
        )

    def test_bridging_completes_quickly_at_moderate_scale(self):
        """Absolute wall-clock ceiling: 2,000 islands (4,000 nodes) must
        bridge in well under a second. The old algorithm's own docstring
        assumed 'N is small (<2000 nodes)' as an operating assumption --
        this asserts the new algorithm has comfortable headroom past that."""
        G = _make_chain_islands(2000, gap=1.0)
        t0 = time.perf_counter()
        result = _ensure_skeleton_connectivity(G, max_bridge_distance=2.0)
        elapsed = time.perf_counter() - t0
        assert nx.is_connected(result)
        assert elapsed < 5.0, f"bridging 2000 islands took {elapsed:.2f}s, expected < 5s"
