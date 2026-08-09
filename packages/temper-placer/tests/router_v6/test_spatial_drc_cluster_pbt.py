"""Property-based tests for the Wave 4 spatial-DRC cluster (resource_bound,
power_plane, diff_pair_inference, trace_width_assignment,
dense_package_detection).

Seven properties (>= 5) over randomized inputs, one per module reached
(G4 cluster-unit ruling: the module-to-property map is listed below so a
reviewer can check reachability without reading the kernels):

- P1 resource_bound — conflict clusters are a partition, and fully
  overlapping (identical, positive-area) bboxes always merge into one
  cluster.
- P2 resource_bound — ``max_routable_nets`` is bounded by the net count and
  monotone non-increasing as cells become blocked.
- P3 power_plane — pour strips are ordered, positive-width, lie inside the
  board, partition the width (within a stated tolerance; the exact first-
  strip anchor is pinned bit-for-bit).
- P4 power_plane — the thermal-via array has exactly ``count`` points and,
  at unit pitch on integer coordinates, is the exact centred square lattice
  {(cx+d, cy+e) : d,e in {-1,0,1}}.
- P5 diff_pair — every returned pair has distinct nets drawn from the input,
  and no net is used by two pairs.
- P6 trace_width — the width is bijectively determined by the reason (gate
  width = power*0.6, HV width = hv, power width = power, default width =
  default).
- P7 dense_package — the pitch estimate is positive, finite, and for a
  footprint that parses a pitch it is exactly the parsed value regardless of
  pin positions.

Non-vacuity: each property has a mutation test below proving a degenerate
kernel violates it (the ``test_pN_fails_for_<mutant>`` pattern).

Metamorphic relations (>= 3) — M1..M5, each naming its module and exactness
claim (power-of-two / integer arithmetic is bit-exact by construction):

- M1 resource_bound — conflict clusters are invariant under integer
  translation of every bbox (exact: small integer coordinates make every
  overlap operation exact).
- M2 diff_pair — appending nets that cannot pair (no +/P/DP/_DP suffix and
  no matching counterpart) leaves the existing pair list unchanged (exact).
- M3 power_plane — scaling the via-grid centre and pitch by 2.0 scales every
  via position by 2.0 (exact: multiplication by a power of two commutes with
  rounding).
- M4 dense_package — a footprint-parsed pitch is unchanged by adding
  arbitrarily many pins (exact: parsing precedes the pin fallback).
- M5 trace_width — doubling all three width parameters doubles the assigned
  width for every net (exact: every output is a parameter or a 0.6 multiple
  of one, and doubling commutes with rounding).
"""

from __future__ import annotations

import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6 import (
    dense_package_detection as dpd,
    diff_pair_inference as dpi,
    power_plane as pp,
    resource_bound as rb,
    trace_width_assignment as twa,
)
from temper_placer.router_v6.diff_pair_inference import infer_differential_pairs
from temper_placer.router_v6.trace_width_assignment import _determine_trace_width

_BBOX = st.tuples(
    st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
)
_BBOXES = st.dictionaries(
    keys=st.text(min_size=1, max_size=6, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    values=_BBOX,
    min_size=0,
    max_size=8,
)

_NEUTRAL_NETS = ("SIG1", "GND", "3V3", "ZZZ", "AUDIO_L", "CLK")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _grid(rows: int, cols: int, blocked_cells: set[tuple[int, int]]) -> rb.OccupancyGrid:
    from temper_placer.router_v6.occupancy_grid import OccupancyGrid

    import numpy as np

    grid = np.zeros((rows, cols), dtype=np.int8)
    for (r, c) in blocked_cells:
        if 0 <= r < rows and 0 <= c < cols:
            grid[r, c] = 1
    return OccupancyGrid(
        layer_name="F.Cu",
        grid=grid,
        origin=(0.0, 0.0),
        cell_size=1.0,
        width_cells=cols,
        height_cells=rows,
    )


def _cluster_map(clusters: list[list[str]]) -> dict[str, int]:
    """Map each net to its cluster index; nets in the same cluster get the
    same id (ids are assigned by first occurrence)."""
    mapping: dict[str, int] = {}
    for i, cluster in enumerate(clusters):
        for net in cluster:
            mapping[net] = i
    return mapping


def _area(bbox: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = bbox
    return max((x2 - x1) * (y2 - y1), 0.0)


def _same_cluster(bboxes, a, b) -> bool:
    """Are two nets in the same conflict cluster (per the migrated kernel)?"""
    clusters = rb._compute_conflict_clusters(bboxes)
    m = _cluster_map(clusters)
    return m.get(a) == m.get(b)


# ---------------------------------------------------------------------------
# P1 — conflict clusters partition + full-overlap merge
# ---------------------------------------------------------------------------


@given(_BBOXES)
@settings(max_examples=100, deadline=60000)
def test_p1_conflict_clusters_partition_and_full_overlap_merge(bboxes) -> None:
    clusters = rb._compute_conflict_clusters(bboxes)
    members = [n for c in clusters for n in c]
    # partition: cover + disjoint
    assert sorted(members) == sorted(bboxes.keys())
    assert len(members) == len(set(members))
    # soundness: two identical positive-area (valid) bboxes always share a
    # cluster.  "Valid" means x1 < x2 and y1 < y2: an inverted bbox
    # (x2 < x1) has positive squared area but zero axis-aligned overlap, so
    # the kernel correctly leaves inverted twins unmerged.
    names = list(bboxes.keys())
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            ba = bboxes[a]
            if (
                bboxes[a] == bboxes[b]
                and _area(ba) > 0
                and ba[0] < ba[2]
                and ba[1] < ba[3]
            ):
                assert _same_cluster(bboxes, a, b), f"identical bboxes {a}/{b} not merged"


# ---------------------------------------------------------------------------
# P2 — max_routable monotone in free cells, bounded by net count
# ---------------------------------------------------------------------------


@given(
    bboxes=st.dictionaries(
        keys=st.text(min_size=1, max_size=6, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
        values=st.tuples(
            st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
            st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
            st.floats(min_value=5.0, max_value=12.0, allow_nan=False, allow_infinity=False),
            st.floats(min_value=5.0, max_value=12.0, allow_nan=False, allow_infinity=False),
        ),
        min_size=0,
        max_size=8,
    ),
    tw=st.floats(min_value=0.1, max_value=0.6, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100, deadline=60000)
def test_p2_max_routable_monotone_and_bounded(bboxes, tw) -> None:
    rows = cols = 12
    rng = random.Random(hash((tuple(sorted(bboxes.items())), tw)) & 0xFFFFFFFF)
    n_block = rng.randrange(0, rows * cols // 2)
    blocked: set[tuple[int, int]] = set()
    while len(blocked) < n_block:
        blocked.add((rng.randrange(rows), rng.randrange(cols)))
    # dense: same cells plus 10 more; sparse: the original set
    extra: set[tuple[int, int]] = set()
    while len(extra) < 10:
        extra.add((rng.randrange(rows), rng.randrange(cols)))
    blocked_extra = blocked | extra
    dense = _grid(rows, cols, blocked_extra)
    sparse = _grid(rows, cols, blocked)

    r_dense = rb.max_routable_nets(dense, bboxes, tw)
    r_sparse = rb.max_routable_nets(sparse, bboxes, tw)
    assert 0 <= r_dense <= len(bboxes)
    assert 0 <= r_sparse <= len(bboxes)
    # more free cells never reduces the bound
    assert r_dense <= r_sparse, f"dense={r_dense} sparse={r_sparse}"


# ---------------------------------------------------------------------------
# P3 — pour strips partition the board
# ---------------------------------------------------------------------------


@given(
    x_min=st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    width=st.floats(min_value=5.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    n=st.integers(min_value=1, max_value=6),
    gap=st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100, deadline=60000)
def test_p3_power_pour_strips_partition(x_min, width, n, gap) -> None:
    x_max = x_min + width
    total_gap = gap * (n - 1)
    strip_width = (width - total_gap) / n
    if strip_width <= 0:
        # degenerate board: the kernel raises; anything else is a violation
        with pytest.raises(ValueError):
            pp._tg.power_pour_strips_py(x_min, 0.0, x_max, 1.0, n, gap)
        return
    strips = pp._tg.power_pour_strips_py(x_min, 0.0, x_max, 1.0, n, gap)
    assert len(strips) == n
    widths = [x2 - x1 for (x1, x2) in strips]
    assert all(x1 < x2 for (x1, x2) in strips)
    assert all(strips[i][0] < strips[i + 1][0] for i in range(n - 1))
    # first strip is anchored exactly at x_min
    assert strips[0][0] == x_min
    # ordered, inside the board, and the partition is complete up to the
    # float rounding of the reference's own strip_width chain
    assert all(x_min <= x1 and x2 <= x_max + 1e-9 for (x1, x2) in strips)
    assert abs(sum(widths) + total_gap - width) < 1e-9


# ---------------------------------------------------------------------------
# P4 — thermal via array is the centred square lattice
# ---------------------------------------------------------------------------


@given(
    cx=st.integers(min_value=-100, max_value=100).map(lambda i: i / 2.0),
    cy=st.integers(min_value=-100, max_value=100).map(lambda i: i / 2.0),
)
@settings(max_examples=50, deadline=60000)
def test_p4_thermal_via_grid_count_and_unit_lattice(cx, cy) -> None:
    count = 9
    vias = pp._tg.thermal_via_positions_py(cx, cy, count, 1.0)
    assert len(vias) == count
    # unit pitch, integer centre offsets -> the exact centred 3x3 lattice
    # (all arithmetic on dyadic values is exact)
    for v in vias:
        assert v[0] in (cx - 1.0, cx, cx + 1.0)
        assert v[1] in (cy - 1.0, cy, cy + 1.0)
    assert set(vias) == {
        (cx + d, cy + e) for d in (-1.0, 0.0, 1.0) for e in (-1.0, 0.0, 1.0)
    }


# ---------------------------------------------------------------------------
# P5 — diff pairs are valid
# ---------------------------------------------------------------------------


@given(
    st.lists(
        st.sampled_from(
            [
                "USB_D+", "USB_D-", "CLK_P", "CLK_N", "TX+", "TX-", "USB_DP", "USB_DN",
                "USBDP", "USBDN", "ETH_P", "ETH_N", "GND", "3V3", "SIG1", "DIGP", "DIGN",
                "A+", "A-", "B+", "B-",
            ]
        ),
        min_size=0,
        max_size=12,
    )
)
@settings(max_examples=100, deadline=60000)
def test_p5_diff_pairs_are_valid(net_names) -> None:
    pairs = infer_differential_pairs(net_names)
    upper_inputs = {n.upper() for n in net_names}
    members = [m for p in pairs for m in (p.p_net, p.n_net)]
    # no net is used by two pairs
    assert len(members) == len(set(members))
    for p in pairs:
        assert p.p_net != p.n_net
        assert p.p_net.upper() in upper_inputs
        assert p.n_net.upper() in upper_inputs


# ---------------------------------------------------------------------------
# P6 — trace width is bijectively determined by its reason
# ---------------------------------------------------------------------------


# Widths chosen so the four candidate widths (d, p, h, p*0.6) are pairwise
# distinct — otherwise "width == h" is satisfied by two different reasons
# and the bijection is ill-formed.
_P6_WIDTHS = st.tuples(
    st.floats(min_value=0.05, max_value=0.5, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.2, max_value=2.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.3, max_value=3.0, allow_nan=False, allow_infinity=False),
).filter(lambda t: len({t[0], t[1], t[2], t[1] * 0.6}) == 4)


@given(
    net_name=st.text(min_size=1, max_size=14, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ_+0123456789"),
    widths=_P6_WIDTHS,
)
@settings(max_examples=100, deadline=60000)
def test_p6_trace_width_reason_width_bijection(net_name, widths) -> None:
    d, p, h = widths
    w = _determine_trace_width(net_name, d, p, h)
    assert w.width_mm in (d, p, h, p * 0.6)
    assert (w.reason == "High voltage net requires wider trace") == (w.width_mm == h)
    assert (w.reason == "Power net requires wider trace for current capacity") == (w.width_mm == p)
    assert (w.reason == "Gate drive signal requires medium-width trace") == (
        w.width_mm == p * 0.6
    )
    assert (w.reason == "Standard signal trace") == (w.width_mm == d)


# ---------------------------------------------------------------------------
# P7 — pitch is positive; a parseable footprint pins it exactly
# ---------------------------------------------------------------------------


@given(
    footprint=st.sampled_from(["CUSTOM", "X_0.5", "QFN-48_0.5mm", "BGA-256_0.8mm", "X_50"]),
    positions=st.lists(
        st.tuples(
            st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
            st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
        ),
        min_size=0,
        max_size=8,
    ),
)
@settings(max_examples=100, deadline=60000)
def test_p7_estimate_pitch_positive_and_parsed(footprint, positions) -> None:
    flat = [c for pos in positions for c in pos]
    pitch = dpd._tg.estimate_pitch_py(footprint, flat)
    assert pitch > 0 and pitch != float("inf")
    # a footprint that parses a pitch pins it exactly, independent of pins
    parsed = {
        "X_0.5": 0.5,
        "QFN-48_0.5mm": 0.5,
        "BGA-256_0.8mm": 0.8,
        "X_50": 50.0 * 0.0254,
    }
    if footprint in parsed:
        assert pitch == parsed[footprint]


# ---------------------------------------------------------------------------
# Non-vacuity: each property fails against a mutated (degenerate) kernel
# ---------------------------------------------------------------------------


@pytest.fixture
def _restore_kernels():
    rb_tg = rb._tg
    pp_tg = pp._tg
    dpi_tg = dpi._tg
    twa_tg = twa._tg
    dpd_tg = dpd._tg
    yield
    rb._tg = rb_tg
    pp._tg = pp_tg
    dpi._tg = dpi_tg
    twa._tg = twa_tg
    dpd._tg = dpd_tg


def test_p1_fails_for_empty_clusters(_restore_kernels) -> None:
    """A kernel that reports no clusters violates the partition."""
    rb._tg = type("T", (), {"conflict_clusters_py": lambda *a, **k: []})
    with pytest.raises(AssertionError):
        test_p1_conflict_clusters_partition_and_full_overlap_merge.hypothesis.inner_test(
            {"A": (0.0, 0.0, 1.0, 1.0), "B": (0.0, 0.0, 1.0, 1.0)}
        )


def test_p2_fails_for_unbounded_result(_restore_kernels) -> None:
    """A kernel claiming an absurdly high bound violates max_routable <= n."""
    rb._tg = type("T", (), {"max_routable_py": lambda *a, **k: (10**9, 0.5, 1)})
    with pytest.raises(AssertionError):
        test_p2_max_routable_monotone_and_bounded.hypothesis.inner_test(
            {"A": (0.0, 0.0, 2.0, 2.0)}, 0.2
        )


def test_p3_fails_for_degenerate_strips(_restore_kernels) -> None:
    """Zero-width strips violate the ordered-positive-width partition."""
    pp._tg = type("T", (), {"power_pour_strips_py": lambda *a, **k: [(0.0, 0.0), (1.0, 1.0)]})
    with pytest.raises(AssertionError):
        test_p3_power_pour_strips_partition.hypothesis.inner_test(0.0, 10.0, 2, 0.0)


def test_p4_fails_for_single_point(_restore_kernels) -> None:
    """A kernel collapsing the array to one point violates the count."""
    pp._tg = type("T", (), {"thermal_via_positions_py": lambda *a, **k: [(0.0, 0.0)]})
    with pytest.raises(AssertionError):
        test_p4_thermal_via_grid_count_and_unit_lattice.hypothesis.inner_test(0.0, 0.0)


def test_p5_fails_for_reused_net(_restore_kernels) -> None:
    """A kernel emitting a net twice violates the distinctness invariant."""
    dpi._tg = type(
        "T",
        (),
        {
            "infer_differential_pairs_py": lambda *a, **k: [
                ("A", "A+", "A-"),
                ("A", "A+", "A-"),
            ]
        },
    )
    with pytest.raises(AssertionError):
        test_p5_diff_pairs_are_valid.hypothesis.inner_test(["A+", "A-"])


def test_p6_fails_for_inconsistent_width_reason(_restore_kernels) -> None:
    """A kernel returning a width not matching its own reason breaks the
    bijection."""
    twa._tg = type(
        "T",
        (),
        {"determine_trace_width_py": lambda *a, **k: (0.7, "Standard signal trace")},
    )
    with pytest.raises(AssertionError):
        test_p6_trace_width_reason_width_bijection.hypothesis.inner_test("SIG1", (0.1, 0.5, 0.6))


def test_p7_fails_for_zero_pitch(_restore_kernels) -> None:
    """A kernel reporting zero pitch violates positivity."""
    dpd._tg = type("T", (), {"estimate_pitch_py": lambda *a, **k: 0.0})
    with pytest.raises(AssertionError):
        test_p7_estimate_pitch_positive_and_parsed.hypothesis.inner_test("CUSTOM", [])


# sanity: the real kernels satisfy the properties on the vacuity examples
def test_sanity_real_kernels_pass_vacuity_examples() -> None:
    assert rb._compute_conflict_clusters({"A": (0.0, 0.0, 1.0, 1.0), "B": (0.0, 0.0, 1.0, 1.0)}) == [
        ["A", "B"]
    ]
    assert rb.max_routable_nets(
        _grid(2, 2, set()), {"A": (0.0, 0.0, 2.0, 2.0)}, 0.2
    ) == 1
    assert pp._tg.thermal_via_positions_py(0.0, 0.0, 9, 1.0) == [
        (-1.0, -1.0),
        (0.0, -1.0),
        (1.0, -1.0),
        (-1.0, 0.0),
        (0.0, 0.0),
        (1.0, 0.0),
        (-1.0, 1.0),
        (0.0, 1.0),
        (1.0, 1.0),
    ]
    pairs = infer_differential_pairs(["A+", "A-"])
    assert len(pairs) == 1 and pairs[0].p_net != pairs[0].n_net
    assert _determine_trace_width("HV_MAINS", 0.1, 0.5, 0.6).width_mm == 0.6
    assert dpd._tg.estimate_pitch_py("CUSTOM", []) == 0.65


# ---------------------------------------------------------------------------
# Metamorphic relations (M1..M5)
# ---------------------------------------------------------------------------


@given(
    bboxes=st.dictionaries(
        keys=st.text(min_size=1, max_size=6, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
        values=st.tuples(
            st.integers(min_value=0, max_value=20),
            st.integers(min_value=0, max_value=20),
            st.integers(min_value=20, max_value=40),
            st.integers(min_value=20, max_value=40),
        ),
        min_size=2,
        max_size=8,
    ),
    dx=st.integers(min_value=1, max_value=10),
    dy=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=60, deadline=60000)
def test_m1_conflict_clusters_invariant_under_integer_translation(bboxes, dx, dy) -> None:
    """M1 (resource_bound): translating every bbox by (dx, dy) — all
    operations exact on small integers — leaves the conflict clusters
    (normalized) unchanged."""
    shifted = {n: (x1 + dx, y1 + dy, x2 + dx, y2 + dy) for n, (x1, y1, x2, y2) in bboxes.items()}
    before = sorted(sorted(c) for c in rb._compute_conflict_clusters(bboxes))
    after = sorted(sorted(c) for c in rb._compute_conflict_clusters(shifted))
    assert before == after


@given(
    st.lists(
        st.sampled_from(
            ["USB_D+", "USB_D-", "CLK_P", "CLK_N", "TX+", "TX-", "USB_DP", "USB_DN", "ETH_P", "ETH_N"]
        ),
        min_size=0,
        max_size=8,
    )
)
@settings(max_examples=60, deadline=60000)
def test_m2_diff_pairs_invariant_under_neutral_addition(net_names) -> None:
    """M2 (diff_pair): appending nets that cannot pair (no +/P/DP suffix and
    no counterpart) leaves the existing pair list unchanged."""
    base = infer_differential_pairs(net_names)
    extended = infer_differential_pairs([*net_names, *_NEUTRAL_NETS])
    assert [(p.base_name, p.p_net, p.n_net) for p in extended] == [
        (p.base_name, p.p_net, p.n_net) for p in base
    ]


@given(
    cx=st.floats(min_value=-30.0, max_value=30.0, allow_nan=False, allow_infinity=False),
    cy=st.floats(min_value=-30.0, max_value=30.0, allow_nan=False, allow_infinity=False),
    pitch=st.floats(min_value=0.1, max_value=3.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=60, deadline=60000)
def test_m3_power_plane_via_grid_scale_by_two(cx, cy, pitch) -> None:
    """M3 (power_plane): scaling centre and pitch by 2.0 scales every via
    position by 2.0 exactly (multiplication by a power of two commutes with
    rounding)."""
    small = pp._tg.thermal_via_positions_py(cx, cy, 9, pitch)
    big = pp._tg.thermal_via_positions_py(2.0 * cx, 2.0 * cy, 9, 2.0 * pitch)
    assert big == [(2.0 * x, 2.0 * y) for (x, y) in small]


@given(
    footprint=st.sampled_from(["X_0.5", "QFN-48_0.5mm", "BGA-256_0.8mm"]),
    positions=st.lists(
        st.tuples(
            st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False),
            st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False),
        ),
        min_size=0,
        max_size=10,
    ),
)
@settings(max_examples=60, deadline=60000)
def test_m4_dense_package_parsed_pitch_invariant_to_pins(footprint, positions) -> None:
    """M4 (dense_package): for a parseable footprint, the pitch estimate is
    unchanged by the number/position of pins (parsing precedes the fallback).
    """
    base = dpd._tg.estimate_pitch_py(footprint, [])
    with_pins = dpd._tg.estimate_pitch_py(footprint, [c for pos in positions for c in pos])
    assert with_pins == base


@given(
    net_name=st.text(min_size=1, max_size=14, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ_+0123456789"),
    d=st.floats(min_value=0.05, max_value=0.5, allow_nan=False, allow_infinity=False),
    p=st.floats(min_value=0.2, max_value=2.0, allow_nan=False, allow_infinity=False),
    h=st.floats(min_value=0.3, max_value=3.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=60, deadline=60000)
def test_m5_trace_width_scale_by_two(net_name, d, p, h) -> None:
    """M5 (trace_width): doubling all three width parameters doubles the
    assigned width exactly (every output is a parameter or 0.6 of one)."""
    w1 = _determine_trace_width(net_name, d, p, h).width_mm
    w2 = _determine_trace_width(net_name, 2.0 * d, 2.0 * p, 2.0 * h).width_mm
    assert w2 == 2.0 * w1
