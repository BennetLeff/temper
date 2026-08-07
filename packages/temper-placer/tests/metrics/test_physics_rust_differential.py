"""Differential tests: temper-thermal Rust geometric/thermal metric kernels
vs the pinned pre-migration Python (``metrics/physics.py``, Wave 4).

The pre-migration implementation is pinned in ``_physics_py_oracle.py`` (a
verbatim ``git show`` extraction of ``measure_geometric``/``measure_thermal``
at ``550cab2a3`` -- see that file's module docstring for the full B-class
catalog and the measured NEP-50 findings this suite pins).

Every assertion is **bit-exact**: floats compared through ``float.hex()``
(never a tolerance), ints/bools compared with their concrete type so
``0 == 0.0`` cannot hide a type change (mirrors
``tests/metrics/test_quality_rust_differential.py``'s ``key()`` helper).

Scope: only ``measure_geometric`` and ``measure_thermal``. ``measure_emi``
and ``measure_routability`` are deliberately NOT pinned here -- see
``packages/temper-thermal/src/geometric_metrics.rs`` / ``thermal_edges.rs``
module docs for why.
"""

from __future__ import annotations

import math
import random

import numpy as np
import pytest
from tests.metrics._physics_py_oracle import (
    _oracle_measure_geometric,
    _oracle_measure_thermal,
)

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.core.state import PlacementState

# ---------------------------------------------------------------------------
# Bit-exact comparison helpers (mirrors test_quality_rust_differential.py)
# ---------------------------------------------------------------------------


def key(value):
    if isinstance(value, float):
        if math.isnan(value):
            return ("float", "nan", math.copysign(1.0, value))
        return ("float", value.hex())
    if isinstance(value, bool):
        return ("bool", value)
    return (type(value).__name__, value)


def assert_metrics_bit_identical(got, expected) -> None:
    for field in (
        "overlap_count",
        "overlap_area_mm2",
        "zone_violation_count",
        "zone_violation_max_mm",
        "boundary_violation_count",
        "min_hv_lv_clearance_mm",
    ):
        if not hasattr(expected, field):
            continue
        g = getattr(got, field)
        e = getattr(expected, field)
        assert key(g) == key(e), f"{field}: rust={g!r} ({key(g)}) oracle={e!r} ({key(e)})"


def assert_thermal_bit_identical(got, expected) -> None:
    for field in ("max_junction_temp_c", "thermal_margin_c", "edge_distance_avg_mm"):
        g = getattr(got, field)
        e = getattr(expected, field)
        assert key(g) == key(e), f"{field}: rust={g!r} ({key(g)}) oracle={e!r} ({key(e)})"


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def make_netlist(n, bounds=None, net_classes=None, zones=None):
    comps = [
        Component(
            ref=f"U{i}",
            footprint="FP",
            bounds=(bounds[i] if bounds else (2.5, 1.25)),
            net_class=(net_classes[i] if net_classes else "Signal"),
            zone=(zones[i] if zones else None),
        )
        for i in range(n)
    ]
    nets = [Net(name="N1", pins=[])]
    return Netlist(components=comps, nets=nets)


def make_state(positions, dtype=np.float32):
    """Positions always float32 in production -- every ``core/state.py``
    factory hardcodes ``dtype=np.float32`` (verified: ``from_positions``,
    ``from_positions_dict``, ``from_netlist_and_board``)."""
    return PlacementState.from_positions(np.array(positions, dtype=dtype))


def make_board(width=100.0, height=80.0, origin=(0.0, 0.0), zones=None):
    return Board(width=width, height=height, origin=origin, zones=zones or [])


def random_positions(rng, n, lo=-50.0, hi=250.0):
    return [[rng.uniform(lo, hi), rng.uniform(lo, hi)] for _ in range(n)]


def random_bounds(rng, n, lo=0.5, hi=20.0):
    return [(rng.uniform(lo, hi), rng.uniform(lo, hi)) for _ in range(n)]


# ---------------------------------------------------------------------------
# Marshalling helpers -- extract the primitive arrays the Rust kernel takes.
# These mirror (and, once wired, are shared with) the delegation in
# ``temper_placer.metrics.physics``.
# ---------------------------------------------------------------------------


def marshal_geometric_args(state, netlist, board, min_separation=0.5):
    positions = np.asarray(state.positions)
    xs = [float(v) for v in positions[:, 0]]
    ys = [float(v) for v in positions[:, 1]]
    widths = [float(c.bounds[0]) for c in netlist.components]
    heights = [float(c.bounds[1]) for c in netlist.components]
    zone_lookup = {z.name: tuple(float(v) for v in z.bounds) for z in board.zones}
    zone_bounds = [
        zone_lookup.get(c.zone) if (c.zone and c.zone in zone_lookup) else None
        for c in netlist.components
    ]
    is_hv = [c.net_class == "HighVoltage" for c in netlist.components]
    return (
        xs,
        ys,
        widths,
        heights,
        float(min_separation),
        zone_bounds,
        (float(board.origin[0]), float(board.origin[1])),
        float(board.width),
        float(board.height),
        is_hv,
    )


def marshal_thermal_args(state, netlist, board, power_dissipation, ambient_temp_c=40.0):
    positions = np.asarray(state.positions)
    xs, ys, powers = [], [], []
    for ref, power in power_dissipation.items():
        try:
            idx = netlist.get_component_index(ref)
        except KeyError:
            continue
        xs.append(float(positions[idx, 0]))
        ys.append(float(positions[idx, 1]))
        powers.append(float(power))
    return (
        xs,
        ys,
        powers,
        (float(board.origin[0]), float(board.origin[1])),
        float(board.width),
        float(board.height),
        float(ambient_temp_c),
    )


# ---------------------------------------------------------------------------
# Direct Rust kernel pins -- these fail at collection/call time until the
# Rust kernels exist (the RED state this migration's process requires).
# ---------------------------------------------------------------------------


class TestDirectRustKernelPins:
    """Calls straight into ``temper_thermal``'s new kernels, bypassing the
    Python delegation entirely -- proves the KERNEL is bit-exact,
    independent of whether ``metrics/physics.py`` has been wired to call
    it. (The wiring itself -- that the shipped ``measure_geometric`` /
    ``measure_thermal`` genuinely reach these kernels -- was proven by
    making the kernel raise and observing the exception propagate through
    the public entry point; see the PR description for that evidence,
    since a proof-by-raise is a one-time demonstration, not a standing
    test.)"""

    @pytest.mark.parametrize("seed", range(15))
    def test_direct_geometric_kernel_bit_exact(self, seed):
        import temper_thermal as _tt

        rng = random.Random(seed)
        n = rng.randint(2, 10)
        positions = random_positions(rng, n)
        bounds = random_bounds(rng, n)
        net_classes = [rng.choice(["Signal", "HighVoltage"]) for _ in range(n)]
        zone_assign = [rng.choice(["Z", None]) for _ in range(n)]
        board_zones = [Zone(name="Z", bounds=(0.0, 0.0, 100.0, 100.0))]
        netlist = make_netlist(n, bounds=bounds, net_classes=net_classes, zones=zone_assign)
        state = make_state(positions)
        board = make_board(width=200.0, height=180.0, origin=(-10.0, -10.0), zones=board_zones)

        expected = _oracle_measure_geometric(state, netlist, board)
        args = marshal_geometric_args(state, netlist, board)
        got = _tt.measure_geometric_py(*args)

        got_fields = (
            got[0],
            got[1],
            got[2],
            got[3],
            got[4],
            got[5],
        )
        exp_fields = (
            expected.overlap_count,
            expected.overlap_area_mm2,
            expected.zone_violation_count,
            expected.zone_violation_max_mm,
            expected.boundary_violation_count,
            expected.min_hv_lv_clearance_mm,
        )
        for g, e in zip(got_fields, exp_fields):
            assert key(g) == key(e), f"rust={g!r} oracle={e!r}"

    @pytest.mark.parametrize("seed", range(10))
    def test_direct_thermal_kernel_bit_exact(self, seed):
        import temper_thermal as _tt

        rng = random.Random(4000 + seed)
        n = rng.randint(1, 9)
        positions = random_positions(rng, n, lo=0.0, hi=150.0)
        netlist = make_netlist(n)
        state = make_state(positions)
        board = make_board(width=150.0, height=120.0, origin=(0.0, 0.0))
        power = {f"U{i}": rng.uniform(0.1, 30.0) for i in range(n)}

        expected = _oracle_measure_thermal(state, netlist, board, power_dissipation=power)
        args = marshal_thermal_args(state, netlist, board, power)
        max_tj, edge_avg = _tt.measure_thermal_edges_py(*args)

        assert key(max_tj) == key(expected.max_junction_temp_c)
        assert key(edge_avg) == key(expected.edge_distance_avg_mm)


# ---------------------------------------------------------------------------
# measure_geometric -- randomized differential
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(30))
def test_measure_geometric_random_no_zones(seed):
    """No zones, no HV/LV split -- exercises overlap + boundary only."""
    rng = random.Random(seed)
    n = rng.randint(2, 12)
    positions = random_positions(rng, n)
    bounds = random_bounds(rng, n)
    netlist = make_netlist(n, bounds=bounds)
    state = make_state(positions)
    board = make_board(width=200.0, height=180.0, origin=(-10.0, -10.0))

    expected = _oracle_measure_geometric(state, netlist, board)

    from temper_placer.metrics.physics import measure_geometric

    got = measure_geometric(state, netlist, board)
    assert_metrics_bit_identical(got, expected)


@pytest.mark.parametrize("seed", range(20))
def test_measure_geometric_random_with_zones_and_hv(seed):
    """Zones + HV/LV split exercised together."""
    rng = random.Random(1000 + seed)
    n = rng.randint(3, 15)
    positions = random_positions(rng, n)
    bounds = random_bounds(rng, n)
    net_classes = [rng.choice(["Signal", "HighVoltage", "Power"]) for _ in range(n)]
    zone_names = ["ZoneA", "ZoneB", None]
    zones_for_comps = [rng.choice(zone_names) for _ in range(n)]

    board_zones = [
        Zone(name="ZoneA", bounds=(0.0, 0.0, 60.0, 60.0)),
        Zone(name="ZoneB", bounds=(40.0, 40.0, 120.0, 120.0)),
    ]
    netlist = make_netlist(n, bounds=bounds, net_classes=net_classes, zones=zones_for_comps)
    state = make_state(positions)
    board = make_board(width=200.0, height=180.0, origin=(-10.0, -10.0), zones=board_zones)

    expected = _oracle_measure_geometric(state, netlist, board, min_separation=0.75)

    from temper_placer.metrics.physics import measure_geometric

    got = measure_geometric(state, netlist, board, min_separation=0.75)
    assert_metrics_bit_identical(got, expected)


def test_measure_geometric_empty_netlist():
    netlist = make_netlist(0)
    state = make_state([])
    board = make_board()

    expected = _oracle_measure_geometric(state, netlist, board)

    from temper_placer.metrics.physics import measure_geometric

    got = measure_geometric(state, netlist, board)
    assert_metrics_bit_identical(got, expected)


def test_measure_geometric_single_component():
    netlist = make_netlist(1, bounds=[(5.0, 5.0)])
    state = make_state([[10.0, 10.0]])
    board = make_board(width=50.0, height=50.0)

    expected = _oracle_measure_geometric(state, netlist, board)

    from temper_placer.metrics.physics import measure_geometric

    got = measure_geometric(state, netlist, board)
    assert_metrics_bit_identical(got, expected)


def test_measure_geometric_exact_touching_overlap_boundary():
    """Two components exactly ``min_separation`` apart -- pins the ``> 0``
    (not ``>= 0``) branch."""
    netlist = make_netlist(2, bounds=[(4.0, 4.0), (4.0, 4.0)])
    # centers 4.5mm apart on x: hw+hw+sep = 2+2+0.5 = 4.5 -> ox == 0.0 exactly
    state = make_state([[0.0, 0.0], [4.5, 0.0]])
    board = make_board(width=100.0, height=100.0, origin=(-50.0, -50.0))

    expected = _oracle_measure_geometric(state, netlist, board, min_separation=0.5)

    from temper_placer.metrics.physics import measure_geometric

    got = measure_geometric(state, netlist, board, min_separation=0.5)
    assert_metrics_bit_identical(got, expected)
    assert got.overlap_count == 0  # ox == 0.0 fails the strict `> 0`


def test_measure_geometric_all_hv():
    """hv_indices non-empty, lv_indices empty -- min_hv_lv_clearance_mm
    stays the 1000.0 default (the ``if hv_indices and lv_indices`` guard)."""
    netlist = make_netlist(3, net_classes=["HighVoltage"] * 3)
    state = make_state(random_positions(random.Random(5), 3))
    board = make_board()

    expected = _oracle_measure_geometric(state, netlist, board)

    from temper_placer.metrics.physics import measure_geometric

    got = measure_geometric(state, netlist, board)
    assert_metrics_bit_identical(got, expected)
    assert got.min_hv_lv_clearance_mm == 1000.0


@pytest.mark.parametrize("seed", range(10))
def test_measure_geometric_adversarial_magnitudes(seed):
    """Extreme-magnitude positions/bounds -- exercises the pow()-not-x*x
    (B1/B7) and f32 NEP-50 widening paths at scale."""
    rng = random.Random(5000 + seed)
    n = 6
    positions = [
        [rng.choice([1e-6, 1e6, -1e6, rng.uniform(-1e4, 1e4)]) for _ in range(2)] for _ in range(n)
    ]
    bounds = [
        (
            rng.choice([1e-3, 1e5, rng.uniform(0.1, 50.0)]),
            rng.choice([1e-3, 1e5, rng.uniform(0.1, 50.0)]),
        )
        for _ in range(n)
    ]
    net_classes = [rng.choice(["Signal", "HighVoltage"]) for _ in range(n)]
    zones = [
        Zone(name="Z", bounds=(-1e5, -1e5, 1e5, 1e5)),
    ]
    zone_assign = [rng.choice(["Z", None]) for _ in range(n)]
    netlist = make_netlist(n, bounds=bounds, net_classes=net_classes, zones=zone_assign)
    state = make_state(positions)
    board = make_board(width=1e6, height=1e6, origin=(-5e5, -5e5), zones=zones)

    expected = _oracle_measure_geometric(state, netlist, board)

    from temper_placer.metrics.physics import measure_geometric

    got = measure_geometric(state, netlist, board)
    assert_metrics_bit_identical(got, expected)


# ---------------------------------------------------------------------------
# measure_thermal -- randomized differential
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(25))
def test_measure_thermal_random(seed):
    rng = random.Random(2000 + seed)
    n = rng.randint(1, 10)
    positions = random_positions(rng, n, lo=0.0, hi=150.0)
    netlist = make_netlist(n)
    state = make_state(positions)
    board = make_board(width=150.0, height=120.0, origin=(0.0, 0.0))

    power = {f"U{i}": rng.uniform(0.1, 30.0) for i in range(n) if rng.random() > 0.2}
    if not power:
        power = {"U0": 5.0}

    expected = _oracle_measure_thermal(state, netlist, board, power_dissipation=power)

    from temper_placer.metrics.physics import measure_thermal

    got = measure_thermal(state, netlist, board, power_dissipation=power)
    assert_thermal_bit_identical(got, expected)


def test_measure_thermal_empty_power_dissipation():
    netlist = make_netlist(2)
    state = make_state([[1.0, 1.0], [2.0, 2.0]])
    board = make_board()

    expected = _oracle_measure_thermal(state, netlist, board, power_dissipation=None)

    from temper_placer.metrics.physics import measure_thermal

    got = measure_thermal(state, netlist, board, power_dissipation=None)
    assert_thermal_bit_identical(got, expected)


def test_measure_thermal_all_refs_missing():
    """Every ref misses ``get_component_index`` -- edge_dists stays empty."""
    netlist = make_netlist(2)
    state = make_state([[1.0, 1.0], [2.0, 2.0]])
    board = make_board()

    power = {"NOPE1": 5.0, "NOPE2": 3.0}
    expected = _oracle_measure_thermal(state, netlist, board, power_dissipation=power)

    from temper_placer.metrics.physics import measure_thermal

    got = measure_thermal(state, netlist, board, power_dissipation=power)
    assert_thermal_bit_identical(got, expected)
    assert got.edge_distance_avg_mm == 0.0


def test_measure_thermal_partial_refs_missing():
    netlist = make_netlist(3)
    state = make_state([[10.0, 10.0], [20.0, 20.0], [30.0, 30.0]])
    board = make_board(width=100.0, height=100.0)

    power = {"U0": 10.0, "NOPE": 99.0, "U2": 5.0}
    expected = _oracle_measure_thermal(state, netlist, board, power_dissipation=power)

    from temper_placer.metrics.physics import measure_thermal

    got = measure_thermal(state, netlist, board, power_dissipation=power)
    assert_thermal_bit_identical(got, expected)


@pytest.mark.parametrize("seed", range(8))
def test_measure_thermal_many_devices_crosses_pairwise_blocksize(seed):
    """n >= 8 crosses numpy's pairwise-sum unrolled-block threshold for
    ``np.mean(edge_dists)`` -- and edge_dists is float32 (NEP-50 narrowing),
    so this also exercises the pairwise algorithm run in float32."""
    rng = random.Random(3000 + seed)
    n = rng.choice([8, 9, 15, 129, 200])
    positions = random_positions(rng, n, lo=0.0, hi=150.0)
    netlist = make_netlist(n)
    state = make_state(positions)
    board = make_board(width=150.0, height=150.0, origin=(0.0, 0.0))
    power = {f"U{i}": rng.uniform(0.1, 20.0) for i in range(n)}

    expected = _oracle_measure_thermal(state, netlist, board, power_dissipation=power)

    from temper_placer.metrics.physics import measure_thermal

    got = measure_thermal(state, netlist, board, power_dissipation=power)
    assert_thermal_bit_identical(got, expected)


def test_measure_thermal_narrowing_is_real_on_this_input():
    """Pins that the NEP-50 narrowing this module is measured against
    actually manifests here (not merely theoretical) -- a naive
    whole-computation-in-float64 reimplementation of the edge-distance
    formula disagrees with the real (float32-narrowed) oracle output on
    this exact fixture."""
    netlist = make_netlist(1)
    pos = [12.345678, 7.654321]
    state = make_state([pos])
    board = make_board(width=137.777, height=91.333, origin=(3.14159, 2.71828))
    power = {"U0": 10.0}

    expected = _oracle_measure_thermal(state, netlist, board, power_dissipation=power)

    ox = board.origin[0]
    w = board.width

    # Reconstruct what the real (float32-narrowed) dist must have been from
    # the pinned Tj: not directly observable, so instead assert the two
    # candidate float64 sub-terms are not both exactly representable in
    # float32 without rounding (i.e. the narrowing step is not a no-op).
    import numpy as _np

    # NEP-50 comparison narrowing means `np.float32(v) == v` is trivially
    # True (v itself narrows for the comparison) -- widen back explicitly
    # to detect real precision loss.
    assert float(_np.float32(ox + w - pos[0])) != (ox + w - pos[0]) or float(
        _np.float32(pos[0] - ox)
    ) != (pos[0] - ox), "fixture does not actually exercise float32 rounding"
    assert expected.max_junction_temp_c != 0.0  # sanity: computation ran


# ---------------------------------------------------------------------------
# Bit-exactness catalog pins -- prove the traps bite on THIS machine
# ---------------------------------------------------------------------------


class TestBitExactnessCatalogPins:
    def test_square_is_not_interchangeable_with_multiplication(self):
        """B1/B7: `x ** 2` (CPython/numpy libm pow) differs from `x * x`."""
        rng = random.Random(11)
        diffs = sum(
            1
            for _ in range(200_000)
            if (lambda x: (x**2).hex() != (x * x).hex())(rng.uniform(0, 1e6))
        )
        assert diffs > 0, (
            "x ** 2 == x * x for every sampled input on this platform; the "
            "hostmath::pow mitigation in geometric_metrics.rs is untested here"
        )

    def test_numpy_float64_pow_matches_cpython_pow_not_multiplication(self):
        """The ``dist_x**2`` in the zone-violation/HV-LV-clearance arms
        operates on a numpy float64 scalar (the output of the ``max()``
        builtin fold over numpy floats) -- confirm numpy's scalar `**`
        matches CPython's (both go through the same libm `pow`), not
        `x * x`."""
        rng = random.Random(12)
        diffs_vs_mul = 0
        diffs_vs_cpython = 0
        for _ in range(50_000):
            x = rng.uniform(0, 1e6)
            nx = np.float64(x)
            if (nx**2).tobytes() != (nx * nx).tobytes():
                diffs_vs_mul += 1
            if (nx**2).tobytes() != np.float64(x**2).tobytes():
                diffs_vs_cpython += 1
        assert diffs_vs_mul > 0
        assert diffs_vs_cpython == 0

    def test_nep50_positions_are_float32_in_every_state_factory(self):
        state = PlacementState.from_positions(np.array([[1.0, 2.0]], dtype=np.float32))
        assert state.positions.dtype == np.float32
        state2 = PlacementState.from_positions_dict({"U0": (1.0, 2.0)}, component_order=["U0"])
        assert state2.positions.dtype == np.float32
