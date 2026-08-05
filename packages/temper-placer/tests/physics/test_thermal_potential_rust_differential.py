"""R1a differential: temper-thermal's thermal-potential kernels vs the
pinned pure-Python/numpy oracle (Wave 4, Phase 4).

The pre-migration implementation is pinned **verbatim** in
`_thermal_potential_py_oracle.py`; nothing in this file may relax it.
Every float is compared through `float.hex()` (never a tolerance) and
every leaf carries its concrete type and dtype (see `_leafcmp`), so an
f32/f64 or int/float drift cannot hide behind numeric equality.

Covered divergence classes from the Wave-4 bit-exactness catalog:

* **B1** host-runtime libm — `np.exp`/`np.cos`/`np.sin` vs the Rust
  kernel's `dlsym`-resolved symbols.  Measured on this runtime
  (CPython 3.12, numpy 2.3.5, macOS/arm64): numpy's float64 loops are
  bit-identical to the host libm at every array length the module uses,
  so one resolution serves the scalar and array call sites alike; the
  `phi_*` pins below re-measure that on every run.
* **B2** `np.radians(d)` == `d * (PI / 180.0)` (the division).
* **B5** three distinct NaN semantics: CPython `max(power, 1e-6)`
  (first argument wins), `np.maximum` (propagates), `np.clip`
  (propagates).
* **B7** operation order — `x ** 2` is libm `pow`, not `x * x`;
  `(...) ** 0.5` is libm `pow`, not `sqrt`.
* **B8** denormals are preserved, never flushed.
"""

from __future__ import annotations

import math
import random

import numpy as np
import pytest
import temper_thermal as _tt

from temper_placer.physics import thermal_potential as mod
from tests.physics._leafcmp import assert_same, leaf_signature
from tests.physics._thermal_potential_py_oracle import (
    ThermalPotentialConfig as OracleConfig,
)
from tests.physics._thermal_potential_py_oracle import (
    assign_thermal_anchors as oracle_assign,
)
from tests.physics._thermal_potential_py_oracle import (
    build_potential_grid as oracle_grid,
)
from tests.physics._thermal_potential_py_oracle import (
    phi_convection as oracle_convection,
)
from tests.physics._thermal_potential_py_oracle import (
    phi_copper as oracle_copper,
)
from tests.physics._thermal_potential_py_oracle import (
    phi_coupling as oracle_coupling,
)
from tests.physics._thermal_potential_py_oracle import (
    phi_edge as oracle_edge,
)
from tests.physics._thermal_potential_py_oracle import (
    phi_exclusion as oracle_exclusion,
)
from tests.physics._thermal_potential_py_oracle import (
    superpose_fields as oracle_superpose,
)

EDGES = ("TOP", "BOTTOM", "LEFT", "RIGHT")
_EDGE_CODES = {"TOP": 0, "BOTTOM": 1, "LEFT": 2, "RIGHT": 3}


# ---------------------------------------------------------------------------
# Direct Rust callers (mirroring what the delegating module does)
# ---------------------------------------------------------------------------


def _edge_code(edge: str) -> int:
    return _EDGE_CODES.get(edge.upper().strip(), 4)


def _b(a) -> bytes:
    return np.ascontiguousarray(a, dtype=np.float64).tobytes()


def _unpack(raw: bytes, shape) -> np.ndarray:
    return np.frombuffer(raw, dtype=np.float64).reshape(shape).copy()


def _rust_grid(bounds, resolution):
    xb, yb = _tt.thermal_potential_build_grid_py(*bounds, resolution)
    shape = (resolution, resolution)
    return _unpack(xb, shape), _unpack(yb, shape)


def _rust_edge(x, y, bounds, edge, decay):
    raw = _tt.thermal_potential_phi_edge_py(
        _b(x), _b(y), *bounds, _edge_code(edge), decay
    )
    return _unpack(raw, np.shape(x))


def _rust_copper(bounds, zone_count, zones):
    rows, cols, raw = _tt.thermal_potential_phi_copper_py(
        *bounds, zone_count, [tuple(z) for z in zones]
    )
    return _unpack(raw, (rows, cols))


def _rust_coupling(x, y, positions, powers, sigma_factor=50.0):
    pairs = [((float(p[0]), float(p[1])), float(w)) for p, w in zip(positions, powers)]
    raw = _tt.thermal_potential_phi_coupling_py(_b(x), _b(y), pairs, sigma_factor)
    return _unpack(raw, np.shape(x))


def _rust_exclusion(x, y, anchors, radius, barrier, steepness):
    raw = _tt.thermal_potential_phi_exclusion_py(
        _b(x), _b(y), [(float(a), float(bb)) for a, bb in anchors], radius, barrier, steepness
    )
    return _unpack(raw, np.shape(x))


def _rust_convection(x, y, airflow):
    raw = _tt.thermal_potential_phi_convection_py(
        _b(x), _b(y), None if airflow is None else (float(airflow[0]), float(airflow[1]))
    )
    return _unpack(raw, np.shape(x))


# ---------------------------------------------------------------------------
# Random input generators
# ---------------------------------------------------------------------------


def _random_bounds(rng):
    x_min = rng.choice([0.0, rng.uniform(-200.0, 200.0)])
    y_min = rng.choice([0.0, rng.uniform(-200.0, 200.0)])
    return (
        x_min,
        y_min,
        x_min + rng.uniform(1.0, 400.0),
        y_min + rng.uniform(1.0, 400.0),
    )


def _random_config(rng) -> dict:
    return {
        "edge_weight": rng.choice([0.0, 1.0, rng.uniform(0.1, 5.0)]),
        "copper_weight": rng.choice([0.0, 1.0, rng.uniform(0.1, 5.0)]),
        "coupling_weight": rng.choice([0.0, 1.0, rng.uniform(0.1, 5.0)]),
        "exclusion_weight": rng.choice([0.0, 1.0, rng.uniform(0.1, 5.0)]),
        "convection_weight": rng.choice([0.0, 1.0, rng.uniform(0.1, 5.0)]),
        "edge_decay_length_mm": rng.choice([10.0, rng.uniform(0.5, 60.0)]),
        "thermal_exclusion_radius_mm": rng.choice([10.0, rng.uniform(1.0, 40.0)]),
        "exclusion_barrier_height": rng.choice([1e6, rng.uniform(1.0, 1e9)]),
        "exclusion_steepness": rng.choice([20.0, rng.uniform(0.5, 60.0)]),
    }


# ---------------------------------------------------------------------------
# Direct Rust pins — grid
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(12))
def test_direct_build_grid_bit_exact(seed):
    """`np.linspace` + `np.meshgrid` replicated exactly, including the
    assigned (not computed) endpoint and the `step == 0` branch."""
    rng = random.Random(seed)
    for _ in range(15):
        bounds = _random_bounds(rng)
        resolution = rng.choice([0, 1, 2, 3, 7, 20, 50])
        got = _rust_grid(bounds, resolution)
        want = oracle_grid(bounds, resolution)
        assert_same(got, want, f"build_potential_grid({bounds}, {resolution})")


def test_direct_build_grid_degenerate_and_denormal():
    """B8: a zero-extent axis takes numpy's `step == 0` branch, and a
    denormal-band extent must not flush to zero."""
    for bounds, res in [
        ((5.0, 5.0, 5.0, 5.0), 7),
        ((0.0, 0.0, 1e-320, 1e-320), 5),
        ((-1e-310, 0.0, 1e-310, 1.0), 4),
    ]:
        assert_same(_rust_grid(bounds, res), oracle_grid(bounds, res), f"{bounds} @ {res}")


def test_direct_build_grid_rejects_negative_resolution():
    """`np.linspace` raises ValueError for a negative sample count; the
    Rust bridge must raise the same exception type."""
    with pytest.raises(ValueError):
        oracle_grid((0.0, 0.0, 1.0, 1.0), -1)
    with pytest.raises(ValueError):
        _rust_grid((0.0, 0.0, 1.0, 1.0), -1)


# ---------------------------------------------------------------------------
# Direct Rust pins — field components
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(12))
def test_direct_phi_edge_bit_exact(seed):
    """B1: `1 - np.exp(-d / lambda)` elementwise, host-libm exact."""
    rng = random.Random(100 + seed)
    for _ in range(12):
        bounds = _random_bounds(rng)
        resolution = rng.choice([2, 5, 20])
        x, y = oracle_grid(bounds, resolution)
        edge = rng.choice([*EDGES, "top", "  BOTTOM ", "DIAGONAL"])
        decay = rng.choice([10.0, rng.uniform(0.1, 100.0)])
        assert_same(
            _rust_edge(x, y, bounds, edge, decay),
            oracle_edge(x, y, bounds, edge, decay),
            f"phi_edge({edge!r}, decay={decay!r})",
        )


def test_direct_phi_edge_exact_zero_on_the_edge():
    """`d == 0` gives `1 - exp(-0.0) == 0.0` exactly in both — a value a
    tolerance-based check could never distinguish from 1e-17."""
    bounds = (0.0, 0.0, 100.0, 150.0)
    x, y = oracle_grid(bounds, 5)
    got = _rust_edge(x, y, bounds, "TOP", 10.0)
    want = oracle_edge(x, y, bounds, "TOP", 10.0)
    assert_same(got, want, "phi_edge on-edge")
    assert float(want[-1, 0]).hex() == 0.0.hex()


@pytest.mark.parametrize("seed", range(10))
def test_direct_phi_copper_bit_exact(seed):
    """The zone rasterisation, the transposed `[gx, gy]` indexing quirk,
    and the `1 / (clip(c, 0, None) + 1e-12)` reciprocal."""
    rng = random.Random(200 + seed)
    for _ in range(12):
        bounds = _random_bounds(rng)
        n_zones = rng.choice([0, 1, 2, 5])
        zones = []
        for _ in range(n_zones):
            zx0 = rng.uniform(bounds[0] - 20, bounds[2] + 20)
            zy0 = rng.uniform(bounds[1] - 20, bounds[3] + 20)
            zones.append((zx0, zy0, zx0 + rng.uniform(0.0, 80.0), zy0 + rng.uniform(0.0, 80.0)))
        oracle_zones = [_ZoneStub(z) for z in zones]
        x, y = oracle_grid(bounds, 50)
        assert_same(
            _rust_copper(bounds, len(zones), zones),
            oracle_copper(x, y, bounds, copper_zones=oracle_zones or None),
            f"phi_copper({bounds}, {len(zones)} zones)",
        )


class _ZoneStub:
    """Minimal duck-typed copper zone (`.bounds`), as the reference reads it."""

    def __init__(self, bounds):
        self.bounds = bounds


def test_direct_phi_copper_uniform_and_degenerate():
    """No zones -> `np.ones((1,1)) * 0.5`; a non-positive board extent
    takes the same early return even with zones present."""
    bounds = (0.0, 0.0, 100.0, 150.0)
    x, y = oracle_grid(bounds, 8)
    assert_same(
        _rust_copper(bounds, 0, []),
        oracle_copper(x, y, bounds, copper_zones=None),
        "phi_copper no zones",
    )
    degenerate = (10.0, 0.0, 10.0, 150.0)
    assert_same(
        _rust_copper(degenerate, 1, [(0.0, 0.0, 5.0, 5.0)]),
        oracle_copper(x, y, degenerate, copper_zones=[_ZoneStub((0.0, 0.0, 5.0, 5.0))]),
        "phi_copper degenerate board",
    )


def test_direct_phi_copper_non_finite_zone_bounds_raise_alike():
    """CPython's `int(nan)` is a ValueError and `int(inf)` an
    OverflowError; the Rust bridge must raise the same classes."""
    bounds = (0.0, 0.0, 100.0, 150.0)
    x, y = oracle_grid(bounds, 50)
    with pytest.raises(ValueError):
        oracle_copper(x, y, bounds, copper_zones=[_ZoneStub((float("nan"), 0.0, 5.0, 5.0))])
    with pytest.raises(ValueError):
        _rust_copper(bounds, 1, [(float("nan"), 0.0, 5.0, 5.0)])
    with pytest.raises(OverflowError):
        oracle_copper(x, y, bounds, copper_zones=[_ZoneStub((float("inf"), 0.0, 5.0, 5.0))])
    with pytest.raises(OverflowError):
        _rust_copper(bounds, 1, [(float("inf"), 0.0, 5.0, 5.0)])


@pytest.mark.parametrize("seed", range(12))
def test_direct_phi_coupling_bit_exact(seed):
    """B1/B5/B7: `sqrt(max(power, 1e-6)) * sigma_factor`, the
    `(2.0 * sigma) * sigma` chain, and `exp(-dist_sq / sigma_sq)`."""
    rng = random.Random(300 + seed)
    for _ in range(12):
        bounds = _random_bounds(rng)
        resolution = rng.choice([2, 5, 15])
        x, y = oracle_grid(bounds, resolution)
        n = rng.choice([0, 1, 3, 6])
        positions = [
            (rng.uniform(bounds[0], bounds[2]), rng.uniform(bounds[1], bounds[3]))
            for _ in range(n)
        ]
        powers = [rng.choice([0.0, 1e-9, rng.uniform(0.1, 200.0)]) for _ in range(n)]
        assert_same(
            _rust_coupling(x, y, positions, powers),
            oracle_coupling(x, y, positions, powers),
            f"phi_coupling({n} devices)",
        )


def test_direct_phi_coupling_nan_power_keeps_the_first_max_argument():
    """B5: `max(NaN, 1e-6)` is NaN in CPython (first argument wins), so
    sigma is NaN and the whole field is NaN.  `f64::max` would have
    silently returned 1e-6 and produced finite numbers."""
    bounds = (0.0, 0.0, 100.0, 150.0)
    x, y = oracle_grid(bounds, 4)
    got = _rust_coupling(x, y, [(50.0, 75.0)], [float("nan")])
    want = oracle_coupling(x, y, [(50.0, 75.0)], [float("nan")])
    assert_same(got, want, "phi_coupling NaN power")
    assert np.all(np.isnan(want)), "the oracle must actually go NaN here"


def test_direct_phi_coupling_zip_truncates_to_the_shorter_sequence():
    """`zip(positions, powers)` stops at the shorter list."""
    bounds = (0.0, 0.0, 100.0, 150.0)
    x, y = oracle_grid(bounds, 4)
    positions = [(10.0, 10.0), (20.0, 20.0), (30.0, 30.0)]
    powers = [5.0]
    assert_same(
        _rust_coupling(x, y, positions, powers),
        oracle_coupling(x, y, positions, powers),
        "phi_coupling ragged zip",
    )


@pytest.mark.parametrize("seed", range(12))
def test_direct_phi_exclusion_bit_exact(seed):
    """B5/B7: `np.maximum` accumulation and the
    `(-steepness) * (dist - radius)` sigmoid argument."""
    rng = random.Random(400 + seed)
    for _ in range(12):
        bounds = _random_bounds(rng)
        resolution = rng.choice([2, 5, 15])
        x, y = oracle_grid(bounds, resolution)
        n = rng.choice([0, 1, 2, 4])
        anchors = [
            (rng.uniform(bounds[0], bounds[2]), rng.uniform(bounds[1], bounds[3]))
            for _ in range(n)
        ]
        radius = rng.choice([10.0, rng.uniform(0.1, 50.0)])
        barrier = rng.choice([1e6, rng.uniform(1.0, 1e9)])
        steep = rng.choice([20.0, rng.uniform(0.1, 100.0)])
        assert_same(
            _rust_exclusion(x, y, anchors, radius, barrier, steep),
            oracle_exclusion(x, y, anchors, radius, barrier, steep),
            f"phi_exclusion({n} anchors)",
        )


def test_direct_phi_exclusion_nan_propagates_like_np_maximum():
    """B5: `np.maximum(field, NaN)` is NaN, unlike `f64::max`, which
    would keep the finite operand and silently disagree."""
    bounds = (0.0, 0.0, 100.0, 150.0)
    x, y = oracle_grid(bounds, 4)
    got = _rust_exclusion(x, y, [(50.0, 75.0)], float("nan"), 1e6, 20.0)
    want = oracle_exclusion(x, y, [(50.0, 75.0)], float("nan"), 1e6, 20.0)
    assert_same(got, want, "phi_exclusion NaN radius")
    assert np.all(np.isnan(want)), "the oracle must actually go NaN here"


def test_direct_phi_exclusion_denormal_barrier_is_not_flushed():
    """B8: a denormal barrier height stays denormal on both sides."""
    bounds = (0.0, 0.0, 100.0, 150.0)
    x, y = oracle_grid(bounds, 4)
    got = _rust_exclusion(x, y, [(50.0, 75.0)], 10.0, 1e-320, 20.0)
    want = oracle_exclusion(x, y, [(50.0, 75.0)], 10.0, 1e-320, 20.0)
    assert_same(got, want, "phi_exclusion denormal barrier")
    assert 0.0 < float(want.max()) < 1e-300, "expected a denormal result, not 0.0"


@pytest.mark.parametrize("seed", range(10))
def test_direct_phi_convection_bit_exact(seed):
    """B1/B2: `np.radians` then `cos`/`sin` then the ramp."""
    rng = random.Random(500 + seed)
    for _ in range(12):
        bounds = _random_bounds(rng)
        resolution = rng.choice([2, 5, 15])
        x, y = oracle_grid(bounds, resolution)
        airflow = rng.choice(
            [
                None,
                (0.0, 45.0),
                (-1.0, 45.0),
                (rng.uniform(0.01, 20.0), rng.uniform(-720.0, 720.0)),
            ]
        )
        assert_same(
            _rust_convection(x, y, airflow),
            oracle_convection(x, y, airflow),
            f"phi_convection({airflow!r})",
        )


def test_direct_phi_convection_nan_magnitude_falls_through():
    """`NaN <= 0` is False, so the reference computes the ramp anyway."""
    bounds = (0.0, 0.0, 100.0, 150.0)
    x, y = oracle_grid(bounds, 4)
    assert_same(
        _rust_convection(x, y, (float("nan"), 30.0)),
        oracle_convection(x, y, (float("nan"), 30.0)),
        "phi_convection NaN magnitude",
    )


def test_direct_phi_convection_radians_is_the_division_form():
    """B2: `np.radians(d)` must be reproduced as `d * (PI / 180.0)`.
    Pin an angle where the reassociated `(d * PI) / 180.0` differs."""
    bad = [d for d in np.linspace(-720.0, 720.0, 4001) if np.radians(d) != (d * math.pi) / 180.0]
    assert bad, "no discriminating angle found -- the pin would be vacuous"
    bounds = (0.0, 0.0, 100.0, 150.0)
    x, y = oracle_grid(bounds, 4)
    for deg in bad[:8]:
        assert_same(
            _rust_convection(x, y, (2.0, float(deg))),
            oracle_convection(x, y, (2.0, float(deg))),
            f"phi_convection radians @ {deg}",
        )


# ---------------------------------------------------------------------------
# Module-level pins — the delegating public API
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(10))
def test_module_superpose_fields_bit_exact(seed):
    """The full weighted superposition through the delegating module."""
    rng = random.Random(600 + seed)
    for _ in range(10):
        bounds = _random_bounds(rng)
        resolution = 50  # the only resolution phi_copper's 50x50 broadcasts onto
        x, y = mod.build_potential_grid(bounds, resolution)
        edge = rng.choice(EDGES)
        params = _random_config(rng)
        n = rng.choice([0, 2, 4])
        positions = [
            (rng.uniform(bounds[0], bounds[2]), rng.uniform(bounds[1], bounds[3]))
            for _ in range(n)
        ]
        powers = [rng.uniform(0.5, 120.0) for _ in range(n)]
        anchors = positions[: rng.choice([0, n])]
        zones = [(bounds[0], bounds[1], bounds[0] + 20.0, bounds[1] + 20.0)]
        use_zones = rng.choice([True, False])
        airflow = rng.choice([None, (rng.uniform(0.1, 10.0), rng.uniform(0.0, 360.0))])

        got = mod.superpose_fields(
            x, y, bounds, edge,
            mod.ThermalPotentialConfig(**params, grid_resolution=resolution),
            device_positions=positions or None,
            device_powers=powers or None,
            anchor_positions=anchors or None,
            copper_zones=[_ZoneStub(z) for z in zones] if use_zones else None,
            airflow_vector=airflow,
        )
        want = oracle_superpose(
            x, y, bounds, edge,
            OracleConfig(**params, grid_resolution=resolution),
            device_positions=positions or None,
            device_powers=powers or None,
            anchor_positions=anchors or None,
            copper_zones=[_ZoneStub(z) for z in zones] if use_zones else None,
            airflow_vector=airflow,
        )
        assert_same(got, want, f"superpose_fields(edge={edge}, {params})")


@pytest.mark.parametrize("seed", range(14))
def test_module_assign_thermal_anchors_bit_exact(seed):
    """The two-pass greedy assignment end to end, including insertion
    order, the min-separation rejection, the clamp and the uniqueness
    offset."""
    rng = random.Random(700 + seed)
    for _ in range(6):
        bounds = _random_bounds(rng)
        edge = rng.choice(EDGES)
        n = rng.choice([1, 2, 3, 5])
        devices = [(f"Q{i}", rng.uniform(0.0, 150.0)) for i in range(n)]
        resolution = rng.choice([6, 12, 20])
        params = _random_config(rng)
        params["copper_weight"] = 0.0 if rng.random() < 0.5 else params["copper_weight"]
        config_kwargs = dict(params, grid_resolution=resolution)
        zones = None
        if rng.random() < 0.4:
            zones = {
                d[0]: (
                    bounds[0],
                    bounds[1],
                    bounds[0] + rng.uniform(5.0, (bounds[2] - bounds[0])),
                    bounds[1] + rng.uniform(5.0, (bounds[3] - bounds[1])),
                )
                for d in devices
            }
        keepouts = None
        if rng.random() < 0.4:
            keepouts = [
                (
                    bounds[0],
                    bounds[1] + (bounds[3] - bounds[1]) * 0.5,
                    bounds[0] + (bounds[2] - bounds[0]) * 0.5,
                    bounds[3],
                )
            ]
        airflow = rng.choice([None, (rng.uniform(0.1, 5.0), rng.uniform(0.0, 360.0))])
        min_sep = rng.choice([2.0, 0.0, rng.uniform(0.1, 30.0)])

        got = mod.assign_thermal_anchors(
            bounds, edge, devices,
            zones=zones, keepouts=keepouts,
            config=mod.ThermalPotentialConfig(**config_kwargs),
            airflow_vector=airflow, min_separation_mm=min_sep,
        )
        want = oracle_assign(
            bounds, edge, devices,
            zones=zones, keepouts=keepouts,
            config=OracleConfig(**config_kwargs),
            airflow_vector=airflow, min_separation_mm=min_sep,
        )
        assert_same(
            got, want,
            f"assign_thermal_anchors(edge={edge}, res={resolution}, n={n}, "
            f"min_sep={min_sep}, zones={zones is not None}, keepouts={keepouts is not None})",
        )


def test_module_assign_anchors_edge_cases():
    """Degenerate shapes the random sweep is unlikely to hit."""
    bounds = (0.0, 0.0, 100.0, 150.0)
    cfg = {"grid_resolution": 8}
    cases = [
        ("empty devices", [], "TOP", {}),
        ("unknown edge", [("Q1", 10.0)], "DIAGONAL", {}),
        ("duplicate refs", [("Q1", 10.0), ("Q1", 5.0)], "TOP", {}),
        ("zero power", [("Q1", 0.0), ("Q2", 0.0)], "BOTTOM", {}),
        ("huge separation", [("Q1", 10.0), ("Q2", 5.0)], "LEFT", {"min_separation_mm": 1e6}),
        (
            "everything keeps out",
            [("Q1", 10.0)],
            "RIGHT",
            {"keepouts": [(-1e9, -1e9, 1e9, 1e9)]},
        ),
        (
            "empty zone",
            [("Q1", 10.0)],
            "TOP",
            {"zones": {"Q1": (1e6, 1e6, 1e6 + 1.0, 1e6 + 1.0)}},
        ),
        # Inverted zone bounds (zx0 > zx1).  `np.clip` returns the UPPER
        # bound for an inverted interval; Rust's `f64::clamp` *panics*
        # ("min > max"), so this case is what separates a faithful
        # `np_clip` mirror from the obvious `clamp` substitution.
        (
            "inverted zone bounds",
            [("Q1", 10.0)],
            "TOP",
            {"zones": {"Q1": (90.0, 140.0, 10.0, 20.0)}},
        ),
        (
            "inverted board-relative zone on both axes",
            [("Q1", 10.0), ("Q2", 4.0)],
            "BOTTOM",
            {"zones": {"Q1": (80.0, 100.0, 5.0, 5.0), "Q2": (60.0, 90.0, 1.0, 2.0)}},
        ),
        (
            "NaN zone bound",
            [("Q1", 10.0)],
            "TOP",
            {"zones": {"Q1": (float("nan"), 0.0, 50.0, 150.0)}},
        ),
    ]
    for label, devices, edge, extra in cases:
        got = mod.assign_thermal_anchors(
            bounds, edge, devices,
            config=mod.ThermalPotentialConfig(**cfg), **extra,
        )
        want = oracle_assign(
            bounds, edge, devices,
            config=OracleConfig(**cfg), **extra,
        )
        assert_same(got, want, f"assign_thermal_anchors [{label}]")


def test_module_assign_anchors_with_a_nan_board_bound():
    """`np.clip(nan, 0.0, nan)` is `nan`; Rust's `f64::clamp` *panics* on a
    NaN upper bound (`min <= max` fails).  A degenerate board therefore
    discriminates a faithful `np_clip` mirror from the obvious `clamp`
    substitution — and the reference really does return a NaN coordinate
    here rather than raising, so the migration must too."""
    bounds = (0.0, 0.0, float("nan"), 150.0)
    devices = [("Q1", 10.0)]
    got = mod.assign_thermal_anchors(
        bounds, "TOP", devices, config=mod.ThermalPotentialConfig(grid_resolution=6)
    )
    want = oracle_assign(
        bounds, "TOP", devices, config=OracleConfig(grid_resolution=6)
    )
    assert_same(got, want, "assign_thermal_anchors [NaN board bound]")
    assert any(math.isnan(x) for x, _ in want.values()), (
        "the oracle must actually produce a NaN coordinate here"
    )


def test_module_assign_anchors_copper_zone_shape_mismatch_raises_alike():
    """`phi_copper` hard-codes a 50x50 grid, so a non-50 resolution with
    copper zones cannot broadcast.  The reference raises `ValueError`;
    the migration must not quietly succeed."""
    bounds = (0.0, 0.0, 100.0, 150.0)
    zones = [_ZoneStub((0.0, 140.0, 100.0, 150.0))]
    with pytest.raises(ValueError):
        oracle_assign(
            bounds, "TOP", [("Q1", 10.0)],
            config=OracleConfig(grid_resolution=8), copper_zones=zones,
        )
    with pytest.raises(ValueError):
        mod.assign_thermal_anchors(
            bounds, "TOP", [("Q1", 10.0)],
            config=mod.ThermalPotentialConfig(grid_resolution=8), copper_zones=zones,
        )


def test_module_assign_anchors_with_copper_zones_at_the_matching_resolution():
    """At resolution 50 the copper field does broadcast; pin that path."""
    bounds = (0.0, 0.0, 100.0, 150.0)
    raw = [(0.0, 140.0, 100.0, 150.0), (20.0, 100.0, 60.0, 150.0)]
    got = mod.assign_thermal_anchors(
        bounds, "TOP", [("Q1", 40.0), ("Q2", 12.0)],
        config=mod.ThermalPotentialConfig(grid_resolution=50),
        copper_zones=[_ZoneStub(z) for z in raw],
    )
    want = oracle_assign(
        bounds, "TOP", [("Q1", 40.0), ("Q2", 12.0)],
        config=OracleConfig(grid_resolution=50),
        copper_zones=[_ZoneStub(z) for z in raw],
    )
    assert_same(got, want, "assign_thermal_anchors with copper zones @ 50")


# ---------------------------------------------------------------------------
# R1h / R24 — BMC-exhaustive validation on small N
# ---------------------------------------------------------------------------


def test_bmc_exhaustive_small_n_anchor_assignment():
    """**BMC-exhaustive (R24.2).** On grids small enough to enumerate,
    check EVERY combination of edge, resolution, device count, zone
    presence and keepout presence against the oracle -- no sampling.

    4 edges x 3 resolutions x 3 device counts x 2 zone states x
    2 keepout states x 2 airflow states = 288 configurations, each
    compared leaf-by-leaf with `float.hex()`.
    """
    bounds = (0.0, 0.0, 20.0, 20.0)
    zone = {"Q0": (0.0, 0.0, 12.0, 20.0), "Q1": (4.0, 0.0, 20.0, 20.0), "Q2": None}
    checked = 0
    for edge in EDGES:
        for resolution in (2, 3, 5):
            for n_devices in (1, 2, 3):
                devices = [(f"Q{i}", 10.0 * (n_devices - i)) for i in range(n_devices)]
                for use_zones in (False, True):
                    zones = (
                        {k: v for k, v in zone.items() if v is not None and k in dict(devices)}
                        if use_zones
                        else None
                    )
                    for use_keepout in (False, True):
                        keepouts = [(0.0, 0.0, 8.0, 8.0)] if use_keepout else None
                        for airflow in (None, (2.0, 30.0)):
                            cfg = {
                                "grid_resolution": resolution,
                                "copper_weight": 0.0,
                            }
                            got = mod.assign_thermal_anchors(
                                bounds, edge, devices,
                                zones=zones, keepouts=keepouts,
                                config=mod.ThermalPotentialConfig(**cfg),
                                airflow_vector=airflow,
                            )
                            want = oracle_assign(
                                bounds, edge, devices,
                                zones=zones, keepouts=keepouts,
                                config=OracleConfig(**cfg),
                                airflow_vector=airflow,
                            )
                            assert_same(
                                got, want,
                                f"BMC[{edge},{resolution},{n_devices},{use_zones},"
                                f"{use_keepout},{airflow}]",
                            )
                            checked += 1
    assert checked == 4 * 3 * 3 * 2 * 2 * 2, f"BMC sweep was truncated at {checked}"


def test_bmc_exhaustive_small_n_field_components():
    """**BMC-exhaustive (R24.2).** Every cell of a 3x3 board, every edge,
    every field component, compared bit-for-bit."""
    bounds = (0.0, 0.0, 3.0, 3.0)
    x, y = oracle_grid(bounds, 3)
    for edge in (*EDGES, "NOT_AN_EDGE"):
        for decay in (1.0, 10.0):
            assert_same(
                _rust_edge(x, y, bounds, edge, decay),
                oracle_edge(x, y, bounds, edge, decay),
                f"BMC phi_edge[{edge},{decay}]",
            )
    for power in (0.0, 1e-9, 1.0, 100.0):
        for px in (0.0, 1.5, 3.0):
            assert_same(
                _rust_coupling(x, y, [(px, 1.5)], [power]),
                oracle_coupling(x, y, [(px, 1.5)], [power]),
                f"BMC phi_coupling[{power},{px}]",
            )
    for radius in (0.5, 1.0, 5.0):
        for steep in (1.0, 20.0):
            assert_same(
                _rust_exclusion(x, y, [(1.5, 1.5)], radius, 1e6, steep),
                oracle_exclusion(x, y, [(1.5, 1.5)], radius, 1e6, steep),
                f"BMC phi_exclusion[{radius},{steep}]",
            )
    for magnitude in (0.0, 1.0, 7.5):
        for direction in (0.0, 90.0, 180.0, 270.0, 45.0):
            assert_same(
                _rust_convection(x, y, (magnitude, direction)),
                oracle_convection(x, y, (magnitude, direction)),
                f"BMC phi_convection[{magnitude},{direction}]",
            )


# ---------------------------------------------------------------------------
# Anti-vacuity: the comparison must be able to fail
# ---------------------------------------------------------------------------


def test_leaf_signature_discriminates_float_from_int_and_f32_from_f64():
    """The differential's own discriminating power (G4 vacuity guard):
    equal *numbers* with different types must produce different
    signatures, or every assertion above is weaker than it claims."""
    assert leaf_signature(1) != leaf_signature(1.0)
    assert leaf_signature(np.float32(0.1)) != leaf_signature(np.float64(0.1))
    assert leaf_signature(np.arange(3, dtype=np.float32)) != leaf_signature(
        np.arange(3, dtype=np.float64)
    )
    assert leaf_signature(0.0) != leaf_signature(-0.0)
    assert leaf_signature(True) != leaf_signature(1)
    # ... and a 1-ulp difference is caught, which a tolerance would miss.
    assert leaf_signature(1.0) != leaf_signature(np.nextafter(1.0, 2.0))
