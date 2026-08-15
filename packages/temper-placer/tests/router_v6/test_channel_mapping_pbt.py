"""Property-based tests for the Rust-backed channel-mapping kernels
(``temper_placer/router_v6/channel_mapping.py``, delegating to
``temper-geometry``'s ``channel_mapping.rs``).

Six non-vacuous properties over randomized finite-coordinate fixtures, all
exercised through the production shim functions:

- P1 ``_calculate_path_length``: non-negative; a single segment equals the
  reference ``(dx**2 + dy**2) ** 0.5`` form exactly; zero iff every
  consecutive pair coincides
- P2 ``_nearest_skeleton_node``: returns a member of the node set and its
  ``(n - coord)**2`` key is no larger than any other node's (argmin)
- P3 ``_is_near_skeleton``: exactly the existential ``dx*dx + dy*dy <=
  tolerance*tolerance`` scan
- P4 ``_nearest_terminal_order``: a permutation of the de-duplicated pads
- P5 ``_nearest_terminal_order``: each chosen pad is the Manhattan-nearest
  of the remaining (greedy step, reference key form)
- P6 ``_calculate_path_length``: monotone non-decreasing under appending a
  waypoint

Metamorphic relations (G5), exactness claims stated per relation:

- M1 translation invariance of path length / nearest node / near-skeleton
  (exact: integer coordinates + power-of-two offset)
- M2 ``_nearest_terminal_order`` input-order permutation invariance (exact:
  each greedy step's argmin key is unique)
- M3 path length is additive under append (exact monotonicity, P6 restated
  as a relation)
- M4 ``_is_near_skeleton`` monotone in tolerance (exact boolean)

Every property carries a ``test_pN_fails_for_<mutant>`` companion proving a
degenerate kernel violates it (G4 vacuity guard).
"""

from __future__ import annotations

import random

import tests.graph_fixtures as nx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6 import channel_mapping as cm
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton

_COORD = st.floats(
    min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False
).filter(lambda x: abs(x) >= 1e-3 or x == 0.0)
_POINT = st.tuples(_COORD, _COORD)
_INT_POINT = st.tuples(st.integers(min_value=-40, max_value=40), st.integers(min_value=-40, max_value=40))


@st.composite
def waypoints(draw):
    n = draw(st.integers(min_value=0, max_value=8))
    return [draw(_POINT) for _ in range(n)]


@st.composite
def node_set(draw):
    n = draw(st.integers(min_value=0, max_value=10))
    return [draw(_POINT) for _ in range(n)]


@st.composite
def pad_list(draw):
    n = draw(st.integers(min_value=0, max_value=8))
    return [draw(_POINT) for _ in range(n)]


def _skeleton(nodes):
    g = nx.Graph()
    for n in nodes:
        g.add_node(n)
    return ChannelSkeleton(g, "F.Cu", 0.0)


def _ref_seg_len(a, b):
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    return (dx**2 + dy**2) ** 0.5


def _ref_key(node, coord):
    return (node[0] - coord[0]) ** 2 + (node[1] - coord[1]) ** 2


def _ref_manhattan(current, pad):
    return abs(pad[0] - current[0]) + abs(pad[1] - current[1])


# ---------------------------------------------------------------------------
# P1 — path length: non-negative, exact single segment, zero-iff-coincide
# ---------------------------------------------------------------------------


@given(waypoints())
@settings(max_examples=200, deadline=60000)
def test_p1_path_length_basic(wps) -> None:
    total = cm._calculate_path_length(wps)
    assert total >= 0.0
    if len(wps) == 2:
        assert total == _ref_seg_len(wps[0], wps[1])
    if len(wps) >= 2 and all(wps[i] == wps[i + 1] for i in range(len(wps) - 1)):
        assert total == 0.0


# ---------------------------------------------------------------------------
# P2 — nearest skeleton node is the argmin of the (n - coord)**2 key
# ---------------------------------------------------------------------------


@given(_POINT, node_set())
@settings(max_examples=200, deadline=60000)
def test_p2_nearest_skeleton_node_is_argmin(coord, nodes) -> None:
    sk = _skeleton(nodes)
    got = cm._nearest_skeleton_node(coord, sk)
    if not nodes:
        assert got is None
        return
    assert got in nodes  # membership: exactly one of the input nodes
    got_key = _ref_key(got, coord)
    for n in nodes:
        assert got_key <= _ref_key(n, coord)


# ---------------------------------------------------------------------------
# P3 — near-skeleton is the existential dx*dx + dy*dy <= tol*tol scan
# ---------------------------------------------------------------------------


@given(_POINT, node_set(), st.floats(min_value=0.1, max_value=20.0, allow_nan=False, allow_infinity=False))
@settings(max_examples=200, deadline=60000)
def test_p3_is_near_skeleton_matches_existential_scan(coord, nodes, tolerance) -> None:
    sk = _skeleton(nodes)
    got = cm._is_near_skeleton(coord, sk, tolerance=tolerance)
    expected = any(
        ((n[0] - coord[0]) * (n[0] - coord[0]) + (n[1] - coord[1]) * (n[1] - coord[1]))
        <= tolerance * tolerance
        for n in nodes
    )
    assert got == expected


# ---------------------------------------------------------------------------
# P4 — terminal order is a permutation of the de-duplicated pads
# ---------------------------------------------------------------------------


@given(_POINT, pad_list())
@settings(max_examples=200, deadline=60000)
def test_p4_terminal_order_is_permutation_of_deduped_pads(start, pads) -> None:
    ordered = cm._nearest_terminal_order(start, pads)
    assert set(ordered) == set(pads)
    assert len(ordered) == len(set(pads))


# ---------------------------------------------------------------------------
# P5 — terminal order greedy step: each pick is the Manhattan-nearest of
# the remaining
# ---------------------------------------------------------------------------


@given(_POINT, pad_list())
@settings(max_examples=200, deadline=60000)
def test_p5_terminal_order_greedy_steps(start, pads) -> None:
    ordered = cm._nearest_terminal_order(start, pads)
    remaining = list(ordered)  # order of play
    for i in range(len(remaining)):
        current = start if i == 0 else remaining[i - 1]
        chosen = remaining[i]
        rest = remaining[i:]
        for other in rest:
            if other == chosen:
                continue
            chosen_key = (_ref_manhattan(current, chosen), chosen)
            other_key = (_ref_manhattan(current, other), other)
            assert chosen_key <= other_key


# ---------------------------------------------------------------------------
# P6 — path length monotone under appending a waypoint
# ---------------------------------------------------------------------------


@given(waypoints(), _POINT)
@settings(max_examples=200, deadline=60000)
def test_p6_path_length_monotone_under_append(wps, extra) -> None:
    before = cm._calculate_path_length(wps)
    after = cm._calculate_path_length([*wps, extra])
    # naive `+=` fold of non-negative segment lengths is exact-monotone
    assert after >= before - 1e-12


# ---------------------------------------------------------------------------
# Metamorphic relations (G5)
# ---------------------------------------------------------------------------


def _shift(points, offset):
    return [(x + offset, y + offset) for x, y in points]


@given(_INT_POINT, _INT_POINT, _INT_POINT, _INT_POINT)
@settings(max_examples=200, deadline=60000)
def test_m1_translation_invariance_integer_coords(a, b, c, d) -> None:
    """Exact: integer coordinates translated by a power-of-two offset keep
    every difference bit-identical."""
    offset = 2.0**20
    pts = [tuple(float(v) for v in p) for p in (a, b, c, d)]
    a, b, c, d = pts
    poly = [a, b, c]
    a_s, b_s, c_s, d_s = _shift(pts, offset)
    assert cm._calculate_path_length(poly) == cm._calculate_path_length([a_s, b_s, c_s])
    # the nearest node translates with the frame: the translated result is
    # the shift of the original result (both are exactly-determined argmins)
    orig_nearest = cm._nearest_skeleton_node(a, _skeleton([b, c]))
    trans_nearest = cm._nearest_skeleton_node(a_s, _skeleton([b_s, c_s]))
    assert trans_nearest == (
        _shift([orig_nearest], offset)[0] if orig_nearest is not None else None
    )
    assert cm._is_near_skeleton(a, _skeleton([b, c]), tolerance=5.0) == cm._is_near_skeleton(
        a_s, _skeleton([b_s, c_s]), tolerance=5.0
    )


@given(_POINT, pad_list())
@settings(max_examples=200, deadline=60000)
def test_m2_terminal_order_input_permutation_invariant(start, pads) -> None:
    """Exact: each greedy step's argmin key ``(manhattan, pad)`` is unique,
    so shuffling the input order never changes the output sequence."""
    rng = random.Random(1234)
    expected = cm._nearest_terminal_order(start, pads)
    shuffled = pads[:]
    rng.shuffle(shuffled)
    assert cm._nearest_terminal_order(start, shuffled) == expected


@given(waypoints(), _POINT)
@settings(max_examples=200, deadline=60000)
def test_m3_path_length_additive_under_append(start_wps, extra) -> None:
    """Exact: a naive fold of non-negative segment lengths is monotone, so
    the appended path is never shorter (restated additive relation)."""
    before = cm._calculate_path_length(start_wps)
    after = cm._calculate_path_length([*start_wps, extra])
    assert after >= before - 1e-12


@given(_POINT, node_set())
@settings(max_examples=200, deadline=60000)
def test_m4_near_skeleton_monotone_in_tolerance(coord, nodes) -> None:
    """Exact boolean: a larger tolerance never turns a near-coordinate into
    a far one."""
    sk = _skeleton(nodes)
    t1 = 5.0
    t2 = 7.0
    near1 = cm._is_near_skeleton(coord, sk, tolerance=t1)
    near2 = cm._is_near_skeleton(coord, sk, tolerance=t2)
    assert near2 >= near1


# ---------------------------------------------------------------------------
# Vacuity guards (G4): every property fails against a degenerate kernel
# ---------------------------------------------------------------------------


@pytest.fixture
def _restore_kernels():
    saved = {
        name: getattr(cm, name)
        for name in (
            "_calculate_path_length",
            "_nearest_skeleton_node",
            "_is_near_skeleton",
            "_nearest_terminal_order",
        )
    }
    yield
    for name, fn in saved.items():
        setattr(cm, name, fn)


def test_p1_fails_for_constant_path_length(_restore_kernels) -> None:
    cm._calculate_path_length = lambda wps: 5.0
    with pytest.raises(AssertionError):
        test_p1_path_length_basic.hypothesis.inner_test([(0.0, 0.0), (1.0, 0.0)])


def test_p2_fails_for_first_node_mutant(_restore_kernels) -> None:
    cm._nearest_skeleton_node = lambda coord, sk: next(iter(list(sk.graph.nodes())), None)
    # the first node (0,0) is NOT the argmin for coord (5,5) when (6,6) is
    # present (key 50 vs 2), so a first-node mutant violates the property
    with pytest.raises(AssertionError):
        test_p2_nearest_skeleton_node_is_argmin.hypothesis.inner_test(
            (5.0, 5.0), [(0.0, 0.0), (6.0, 6.0)]
        )


def test_p3_fails_for_always_false_mutant(_restore_kernels) -> None:
    cm._is_near_skeleton = lambda coord, sk, tolerance=5.0: False
    with pytest.raises(AssertionError):
        test_p3_is_near_skeleton_matches_existential_scan.hypothesis.inner_test(
            (0.0, 0.0), [(0.0, 0.0)], 5.0
        )


def test_p4_fails_for_dropping_a_pad_mutant(_restore_kernels) -> None:
    cm._nearest_terminal_order = lambda start, pads: list(set(pads))[:-1]
    with pytest.raises(AssertionError):
        test_p4_terminal_order_is_permutation_of_deduped_pads.hypothesis.inner_test(
            (0.0, 0.0), [(1.0, 1.0), (2.0, 2.0), (3.0, 3.0)]
        )


def test_p5_fails_for_reversed_order_mutant(_restore_kernels) -> None:
    cm._nearest_terminal_order = lambda start, pads: list(reversed(list(set(pads))))
    with pytest.raises(AssertionError):
        test_p5_terminal_order_greedy_steps.hypothesis.inner_test(
            (0.0, 0.0), [(1.0, 1.0), (2.0, 2.0), (3.0, 3.0)]
        )


def test_p6_fails_for_negative_mutant(_restore_kernels) -> None:
    cm._calculate_path_length = lambda wps: -1.0 if len(wps) > 2 else 0.0
    with pytest.raises(AssertionError):
        test_p6_path_length_monotone_under_append.hypothesis.inner_test(
            [(0.0, 0.0), (1.0, 0.0)], (2.0, 0.0)
        )
