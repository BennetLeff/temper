"""Differential tests: Rust channel-mapping kernels vs the pre-migration
pure-Python reference (``temper_placer/router_v6/channel_mapping.py``, Wave 4).

The four pure-geometry kernels migrated to
``packages/temper-geometry/src/channel_mapping.rs`` are pinned bit-exactly
against a VERBATIM copy of the pre-migration implementations (the
``_oracle_*`` block below, ``git show 47349a50:.../channel_mapping.py``):

- ``_calculate_path_length`` — naive ``+=`` fold (NOT builtin ``sum()``) of
  ``(dx**2 + dy**2) ** 0.5`` segment lengths.  ``x**2`` / ``x**0.5`` are
  CPython ``float_pow`` = host-libm ``pow`` (resolved via ``dlsym`` in
  ``host_math``, contract class B1/B7/B13), NOT ``x*x`` / ``sqrt`` and NOT
  ``math.hypot``.
- ``_nearest_skeleton_node`` — argmin over the node set by the key
  ``((n - coord)**2, n)`` (tuple key with the node's own coordinates as the
  tie-break).  The argmin is unique for distinct nodes, so the result is
  independent of node-set iteration order.
- ``_is_near_skeleton`` — existential ``dx*dx + dy*dy <= tolerance*tolerance``
  (multiplication, not pow), order-independent.
- ``_nearest_terminal_order`` — greedy nearest-by-Manhattan ``abs`` ordering
  over ``set(pads)`` (which de-duplicates), key ``(manhattan, pad)`` unique
  per remaining pad, so each step's argmin is order-independent.

The orchestration these feed (``map_topology_to_channels``,
``_extract_waypoints``, ``expand_channel_path_terminals``, layer assignment,
networkx graph traversal) stays in Python; only the four kernels cross the
boundary.
"""

from __future__ import annotations

import math
import random

import networkx as nx
import pytest

from temper_placer.router_v6 import channel_mapping as cm
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton

# ---------------------------------------------------------------------------
# Verbatim pre-migration oracles (copied from the module AS COMMITTED at
# 47349a50 before the Wave 4 migration; do not edit — they are the
# reference).  Only the ``_oracle_`` name prefix differs from the committed
# file.
# ---------------------------------------------------------------------------


def _oracle_calculate_path_length(waypoints: list[tuple[float, float]]) -> float:
    """
    Calculate total path length from waypoints.

    Args:
        waypoints: List of (x, y) coordinates

    Returns:
        Total length in mm
    """
    if len(waypoints) < 2:
        return 0.0

    total_length = 0.0
    for i in range(len(waypoints) - 1):
        x1, y1 = waypoints[i]
        x2, y2 = waypoints[i + 1]
        dx = x2 - x1
        dy = y2 - y1
        length = (dx**2 + dy**2) ** 0.5
        total_length += length

    return total_length


def _oracle_nearest_skeleton_node(
    coord: tuple[float, float],
    nodes,
) -> tuple[float, float] | None:
    """Return the skeleton node closest to ``coord``, or ``None`` if empty.

    Ties are broken by the node's own coordinate, so the result depends only on
    the node *set* and ``coord`` -- never on iteration or insertion order.
    """
    if not nodes:
        return None
    return min(
        nodes,
        key=lambda n: ((n[0] - coord[0]) ** 2 + (n[1] - coord[1]) ** 2, n),
    )


def _oracle_is_near_skeleton(
    coord: tuple[float, float],
    nodes,
    tolerance: float = 5.0,
) -> bool:
    """Check if a coordinate is near any skeleton node."""
    if len(nodes) == 0:
        return False
    for node in nodes:
        dx = node[0] - coord[0]
        dy = node[1] - coord[1]
        if (dx * dx + dy * dy) <= tolerance * tolerance:
            return True
    return False


def _oracle_nearest_terminal_order(
    start: tuple[float, float], pads: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    """Deterministically extend an existing copper component one pad at a time."""
    remaining = set(pads)
    ordered: list[tuple[float, float]] = []
    current = start
    while remaining:
        next_pad = min(
            remaining,
            key=lambda pad: (abs(pad[0] - current[0]) + abs(pad[1] - current[1]), pad),
        )
        ordered.append(next_pad)
        remaining.remove(next_pad)
        current = next_pad
    return ordered


def test_oracle_is_verbatim_semantics() -> None:
    assert _oracle_calculate_path_length([(0.0, 0.0), (3.0, 4.0)]) == 5.0
    assert _oracle_calculate_path_length([(0.0, 0.0)]) == 0.0
    assert _oracle_nearest_skeleton_node((5.0, 5.0), {(0.0, 0.0), (6.0, 6.0)}) == (6.0, 6.0)
    assert _oracle_nearest_skeleton_node((5.0, 5.0), set()) is None
    assert _oracle_is_near_skeleton((5.0, 5.0), {(0.0, 0.0), (6.0, 6.0)}, tolerance=2.0)
    assert not _oracle_is_near_skeleton((50.0, 50.0), {(0.0, 0.0)}, tolerance=2.0)
    assert _oracle_nearest_terminal_order((0.0, 0.0), [(3.0, 0.0), (3.0, 4.0)]) == [
        (3.0, 0.0),
        (3.0, 4.0),
    ]


# ---------------------------------------------------------------------------
# Bit-exact comparison helpers
# ---------------------------------------------------------------------------


def key(value):
    if isinstance(value, float):
        if math.isnan(value):
            return ("float", "nan", math.copysign(1.0, value))
        return ("float", value.hex())
    if isinstance(value, bool):
        return ("bool", value)
    return (type(value).__name__, value)


def assert_bits(got, expected, label: str) -> None:
    assert key(got) == key(expected), f"{label}: rust={got!r} ({key(got)}) oracle={expected!r} ({key(expected)})"


def flatten(points):
    out = []
    for x, y in points:
        out.append(x)
        out.append(y)
    return out


def rng_point(rng, lo=-20.0, hi=50.0):
    return (rng.uniform(lo, hi), rng.uniform(lo, hi))


def make_skeleton(nodes, rng=None):
    g = nx.Graph()
    for n in nodes:
        g.add_node(n)
    return ChannelSkeleton(g, "F.Cu", 0.0)


# ---------------------------------------------------------------------------
# _calculate_path_length
# ---------------------------------------------------------------------------


class TestCalculatePathLength:
    @pytest.mark.parametrize("seed", range(30))
    def test_random_waypoints(self, seed):
        rng = random.Random(seed)
        n = rng.randint(1, 10)
        waypoints = [rng_point(rng) for _ in range(n)]
        expected = _oracle_calculate_path_length(waypoints)
        import temper_geometry as tg

        got = tg.channel_path_length_py(flatten(waypoints))
        assert_bits(got, expected, f"pathlen {waypoints}")
        assert_bits(cm._calculate_path_length(waypoints), expected, f"shim pathlen {waypoints}")

    @pytest.mark.parametrize("seed", range(10))
    def test_adversarial_magnitudes(self, seed):
        rng = random.Random(3000 + seed)
        n = rng.randint(2, 8)
        waypoints = [
            (rng.choice([1e-6, 1e6, -1e6, rng.uniform(-1e4, 1e4)]), rng.uniform(-1e4, 1e4))
            for _ in range(n)
        ]
        expected = _oracle_calculate_path_length(waypoints)
        import temper_geometry as tg

        got = tg.channel_path_length_py(flatten(waypoints))
        assert_bits(got, expected, f"pathlen {waypoints}")

    def test_degenerate_and_nan(self):
        import temper_geometry as tg

        cases = [
            [],
            [(0.0, 0.0)],
            [(0.0, 0.0), (0.0, 0.0)],
            [(0.0, 0.0), (float("nan"), 1.0)],
            [(0.0, 0.0), (float("inf"), 1.0)],
            [(0.0, 0.0), (1e308, 1e308)],
            [(0.0, 0.0), (3.0, 4.0), (6.0, 8.0), (9.0, 12.0)],
        ]
        for wps in cases:
            expected = _oracle_calculate_path_length(wps)
            got = tg.channel_path_length_py(flatten(wps))
            assert_bits(got, expected, f"pathlen {wps}")
            assert_bits(cm._calculate_path_length(wps), expected, f"shim pathlen {wps}")

    def test_pow_not_sqrt_discriminator(self):
        """The reference is ``(dx**2 + dy**2) ** 0.5`` = host-libm pow, not
        ``math.hypot`` and not ``sqrt(dx*dx + dy*dy)``.  Assert the Rust
        kernel agrees with the reference on inputs where those differ, and
        that this platform actually distinguishes pow-form from hypot-form
        (else the mitigation is untested here)."""
        import temper_geometry as tg

        rng = random.Random(99)
        differ = 0
        for _ in range(5000):
            a = rng_point(rng)
            b = rng_point(rng)
            dx, dy = b[0] - a[0], b[1] - a[1]
            pow_form = (dx**2 + dy**2) ** 0.5
            if pow_form.hex() != math.hypot(dx, dy).hex():
                differ += 1
            if differ >= 1 and differ:
                waypoints = [a, b]
                expected = _oracle_calculate_path_length(waypoints)
                got = tg.channel_path_length_py(flatten(waypoints))
                assert_bits(got, expected, "pow-vs-hypot")
                break
        assert differ > 0, (
            "pow-form and hypot never differed on this platform; the "
            "host_math::pow mitigation is untested here"
        )


# ---------------------------------------------------------------------------
# _nearest_skeleton_node
# ---------------------------------------------------------------------------


class TestNearestSkeletonNode:
    @pytest.mark.parametrize("seed", range(30))
    def test_random(self, seed):
        rng = random.Random(1000 + seed)
        coord = rng_point(rng)
        nodes = {rng_point(rng) for _ in range(rng.randint(0, 12))}
        expected = _oracle_nearest_skeleton_node(coord, nodes)
        import temper_geometry as tg

        got = tg.nearest_skeleton_node_py(coord[0], coord[1], flatten(nodes))
        assert key(got) == key(expected)
        sk = make_skeleton(nodes)
        assert key(cm._nearest_skeleton_node(coord, sk)) == key(expected)

    def test_empty_and_ties(self):
        import temper_geometry as tg

        assert tg.nearest_skeleton_node_py(5.0, 5.0, []) is None
        sk = make_skeleton(set())
        assert cm._nearest_skeleton_node((5.0, 5.0), sk) is None
        # exact-tie distance -> tie-break by node coordinate
        nodes = {(0.0, 10.0), (10.0, 0.0)}  # both 50 from (0,10)
        coord = (0.0, 0.0)
        expected = _oracle_nearest_skeleton_node(coord, nodes)
        got = tg.nearest_skeleton_node_py(0.0, 0.0, flatten(nodes))
        assert got == expected
        assert got == (0.0, 10.0)

    def test_insertion_order_independent(self):
        """The argmin key is unique for distinct nodes, so the result must
        not depend on node iteration/insertion order."""
        import temper_geometry as tg

        rng = random.Random(77)
        nodes = list({rng_point(rng) for _ in range(10)})
        coord = rng_point(rng)
        expected = _oracle_nearest_skeleton_node(coord, set(nodes))
        for _ in range(20):
            shuffled = nodes[:]
            rng.shuffle(shuffled)
            got = tg.nearest_skeleton_node_py(coord[0], coord[1], flatten(shuffled))
            assert got == expected

    def test_nan_coordinate_node(self):
        """A NaN-coordinate node's squared-distance key is NaN and never
        wins against a finite key; with only NaN nodes the result is
        iteration-order-dependent, so only the mixed case is pinned."""
        import temper_geometry as tg

        nodes = [(float("nan"), 0.0), (1.0, 1.0), (3.0, 3.0)]
        coord = (2.0, 2.0)
        expected = _oracle_nearest_skeleton_node(coord, set(nodes))
        assert expected == (1.0, 1.0)
        got = tg.nearest_skeleton_node_py(2.0, 2.0, flatten(nodes))
        assert got == expected


# ---------------------------------------------------------------------------
# _is_near_skeleton
# ---------------------------------------------------------------------------


class TestIsNearSkeleton:
    @pytest.mark.parametrize("seed", range(30))
    def test_random(self, seed):
        rng = random.Random(2000 + seed)
        coord = rng_point(rng)
        nodes = {rng_point(rng) for _ in range(rng.randint(0, 10))}
        tolerance = rng.choice([0.5, 1.0, 5.0, 10.0])
        expected = _oracle_is_near_skeleton(coord, nodes, tolerance=tolerance)
        import temper_geometry as tg

        got = tg.is_near_skeleton_py(coord[0], coord[1], flatten(nodes), tolerance)
        assert got == expected
        sk = make_skeleton(nodes)
        assert cm._is_near_skeleton(coord, sk, tolerance=tolerance) == expected

    def test_empty_and_boundary(self):
        import temper_geometry as tg

        assert tg.is_near_skeleton_py(0.0, 0.0, [], 5.0) is False
        sk = make_skeleton(set())
        assert cm._is_near_skeleton((0.0, 0.0), sk) is False
        # exactly at tolerance boundary: dx*dx + dy*dy == tol*tol
        assert tg.is_near_skeleton_py(0.0, 0.0, flatten([(3.0, 4.0)]), 5.0)
        # just outside
        assert not tg.is_near_skeleton_py(0.0, 0.0, flatten([(3.0, 4.1)]), 5.0)
        assert tg.is_near_skeleton_py(0.0, 0.0, flatten([(float("nan"), 4.0)]), 5.0) is False


# ---------------------------------------------------------------------------
# _nearest_terminal_order
# ---------------------------------------------------------------------------


class TestNearestTerminalOrder:
    @pytest.mark.parametrize("seed", range(30))
    def test_random(self, seed):
        rng = random.Random(4000 + seed)
        start = rng_point(rng)
        n = rng.randint(0, 8)
        pads = [rng_point(rng) for _ in range(n)]
        expected = _oracle_nearest_terminal_order(start, pads)
        import temper_geometry as tg

        got = tg.nearest_terminal_order_py(start[0], start[1], flatten(pads))
        assert got == expected
        assert cm._nearest_terminal_order(start, pads) == expected

    def test_duplicates_are_deduped(self):
        """``set(pads)`` de-duplicates; the kernel must too."""
        import temper_geometry as tg

        pads = [(1.0, 1.0), (1.0, 1.0), (2.0, 0.0), (2.0, 0.0), (0.0, 5.0)]
        expected = _oracle_nearest_terminal_order((0.0, 0.0), pads)
        got = tg.nearest_terminal_order_py(0.0, 0.0, flatten(pads))
        assert got == expected
        assert got == [(1.0, 1.0), (2.0, 0.0), (0.0, 5.0)]

    def test_empty_and_single(self):
        import temper_geometry as tg

        assert tg.nearest_terminal_order_py(0.0, 0.0, []) == []
        assert cm._nearest_terminal_order((0.0, 0.0), []) == []
        assert tg.nearest_terminal_order_py(0.0, 0.0, flatten([(3.0, 4.0)])) == [(3.0, 4.0)]

    def test_manhattan_tie_break_by_coordinate(self):
        """Two pads at equal Manhattan distance -> smaller (x, y) tuple
        wins, independent of input order."""
        import temper_geometry as tg

        pads = [(0.0, 5.0), (5.0, 0.0)]  # both manhattan 5 from origin
        expected = _oracle_nearest_terminal_order((0.0, 0.0), pads)
        got = tg.nearest_terminal_order_py(0.0, 0.0, flatten(pads))
        assert got == expected
        assert got == [(0.0, 5.0), (5.0, 0.0)]
        # reversed input order must give the same result
        got2 = tg.nearest_terminal_order_py(0.0, 0.0, flatten(list(reversed(pads))))
        assert got2 == got

    @pytest.mark.parametrize("seed", range(10))
    def test_input_order_independent(self, seed):
        import temper_geometry as tg

        rng = random.Random(5000 + seed)
        pads = list({rng_point(rng) for _ in range(rng.randint(2, 7))})
        start = rng_point(rng)
        expected = _oracle_nearest_terminal_order(start, pads)
        for _ in range(15):
            shuffled = pads[:]
            rng.shuffle(shuffled)
            got = tg.nearest_terminal_order_py(start[0], start[1], flatten(shuffled))
            assert got == expected
