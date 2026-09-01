"""R1a: behavioural A/B of the Wave-4 Phase 2 contract layer.

Every assertion compares the *production* module (now delegating to
``temper-io-types``) against ``_core_py_oracle``, the verbatim
pre-migration Python pinned at ``origin/main`` (``facaed149``), through
the type-carrying signature in ``_sig``. There is no tolerance anywhere:
floats compare by ``float.hex()``, arrays additionally by ``dtype`` and
``shape``, and every other leaf by its concrete type name. Raised
exceptions are compared by type *and* message, because both are contract.

The corpora below are deliberately adversarial rather than
representative -- signed zeros, denormals, infinities, NaN, values
straddling every branch threshold, ints as well as floats, and (for the
string predicates) embedded newlines and non-ASCII case-folding.

Coverage note for the PR-#714 lesson: the perf harness in
``test_core_contracts_perf.py`` exercises 4 000-name classification runs,
600-pin DRC scans and 400-component/1200-net adjacency builds. Every one
of those parameters is covered *here* at an equal or larger size (see
``test_perf_harness_parameters_are_covered``), so no benchmark runs at a
scale the differential has not measured.
"""

from __future__ import annotations

import math
import random

import numpy as np
import pytest

from temper_placer.core import manufacturing as prod_mf
from temper_placer.core import net_classification as prod_nc
from temper_placer.core import units as prod_units
from temper_placer.core.board import Rect as ProdRect
from temper_placer.core.netlist import build_adjacency_matrix as prod_adjacency
from tests.wave4_phase2 import _core_py_oracle as oracle
from tests.wave4_phase2._sig import assert_same, call

# ---------------------------------------------------------------------------
# corpora
# ---------------------------------------------------------------------------

#: Floats chosen to hit every classifiable case: signed zeros, denormals,
#: the f32/f64 boundaries, exact powers of two, the non-finites, and
#: values whose decimal expansion forces a rounding decision.
EDGE_FLOATS: tuple[float, ...] = (
    0.0,
    -0.0,
    1.0,
    -1.0,
    0.1,
    -0.1,
    0.5,
    2.675,
    0.0005,
    0.0015,
    -0.0004,
    1e-5,
    1e-4,
    1e15,
    1e16,
    1e300,
    -1e300,
    5e-324,
    2.2250738585072014e-308,
    1.7976931348623157e308,
    math.pi,
    math.e,
    180.0,
    360.0,
    90.0,
    float("inf"),
    float("-inf"),
    float("nan"),
)

EDGE_INTS: tuple[int, ...] = (0, 1, -1, 2, 3, 4, 5, 105, -105, 2**31, -(2**31), 2**53, 2**63)


def _random_floats(n: int, seed: int, lo: float = -1e6, hi: float = 1e6) -> list[float]:
    rng = random.Random(seed)
    return [rng.uniform(lo, hi) for _ in range(n)]


#: Net/pin names: every literal pattern from every set, plus the
#: word-boundary near-misses the module's own bug history names, plus
#: newline and Unicode case-folding cases.
def _name_corpus() -> list[str]:
    names: list[str] = []
    for patterns in (
        oracle.GROUND_NET_PATTERNS,
        oracle.POWER_NET_PATTERNS,
        oracle.HV_NET_PATTERNS,
        oracle.GROUND_PIN_PATTERNS,
        oracle.POWER_PIN_PATTERNS,
        oracle.HV_PIN_PATTERNS,
        oracle.CLOCK_PIN_PATTERNS,
    ):
        for p in sorted(patterns):
            names += [
                p,
                p.lower(),
                f"{p}_1",
                f"{p}1",
                f"X_{p}",
                f"X{p}",
                f"{p}X",
                f"{p}\n",
                f"{p}\n\n",
                f"{p}\nX",
                f"\n{p}",
                f"{p}_",
                f"_{p}",
            ]
    # Names that match MORE THAN ONE pattern set, so the precedence order
    # (ground > power > hv > signal) is actually exercised. Without these
    # a port that checks power before ground is indistinguishable --
    # mutant M11 survived the corpus until they were added.
    names += [
        "GND_VCC",
        "VCC_GND",
        "AGND_VDD",
        "GND_AC_L",
        "VCC_AC_L",
        "X_VSS_VBUS",
        "PGND_VBUS_1",
        "AC_L_GND",
        "VDD_PE",
        "CLK_GND",
    ]
    names += [
        "",
        "\n",
        "_",
        "SPEED",
        "TYPE",
        "OPEN",
        "TYPE_PE",
        "SDA",
        "SCL",
        "Net-(U1-Pad1)",
        "ß_gnd",
        "ı_gnd",
        "gndı",
        "GnD",
        "+3v3",
        "DC_BUS+FOO",
        "X_DC_BUS+FOO",
        "VCC/VDD",
        "A" * 200,
        "GND" * 50,
    ]
    rng = random.Random(20260804)
    alphabet = "ABCDEGLNPSUVWX_+-0123456789\n"
    for _ in range(4500):
        length = rng.randint(0, 12)
        names.append("".join(rng.choice(alphabet) for _ in range(length)))
    return names


NAME_CORPUS: list[str] = _name_corpus()


# ---------------------------------------------------------------------------
# units
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", EDGE_FLOATS + tuple(EDGE_INTS))
def test_deg_to_rad_edges(value):
    assert_same(
        call(prod_units.deg_to_rad, value),
        call(oracle.deg_to_rad, value),
        f"deg_to_rad({value!r})",
    )


@pytest.mark.parametrize("value", EDGE_FLOATS + tuple(EDGE_INTS))
def test_rad_to_deg_edges(value):
    assert_same(
        call(prod_units.rad_to_deg, value),
        call(oracle.rad_to_deg, value),
        f"rad_to_deg({value!r})",
    )


def test_deg_to_rad_random_sweep():
    """The associativity trap: ~30% of these differ from `math.radians`."""
    diverged_from_math = 0
    for v in _random_floats(20000, seed=1):
        got, want = prod_units.deg_to_rad(v), oracle.deg_to_rad(v)
        assert_same(got, want, f"deg_to_rad({v!r})")
        if want != math.radians(v):
            diverged_from_math += 1
    # Anti-vacuity: if this ever drops to zero the trap has gone away and
    # the Rust may as well use `to_radians()` -- which would then need
    # re-measuring, not silently accepting.
    assert diverged_from_math > 1000, (
        f"only {diverged_from_math}/20000 inputs distinguish (x*pi)/180 from "
        "math.radians; the trap this port guards against may have changed"
    )


def test_rad_to_deg_random_sweep():
    diverged_from_math = 0
    for v in _random_floats(20000, seed=2, lo=-1e4, hi=1e4):
        got, want = prod_units.rad_to_deg(v), oracle.rad_to_deg(v)
        assert_same(got, want, f"rad_to_deg({v!r})")
        if want != math.degrees(v):
            diverged_from_math += 1
    assert diverged_from_math > 1000


@pytest.mark.parametrize(
    "arr",
    [
        np.array([1, 2, 3], dtype=np.int32),
        np.array([1, 2, 3], dtype=np.int64),
        np.array([1.0, 2.0], dtype=np.float32),
        np.array([1.0, 2.0], dtype=np.float64),
        np.array([], dtype=np.float32),
        np.array([[0.0, 90.0], [180.0, 360.0]], dtype=np.float32),
    ],
)
def test_deg_to_rad_array_dtypes_are_unchanged(arr):
    """NEP 50: float32 in, float32 out -- and computed in float32."""
    assert_same(prod_units.deg_to_rad(arr), oracle.deg_to_rad(arr), f"deg_to_rad({arr.dtype})")
    assert_same(prod_units.rad_to_deg(arr), oracle.rad_to_deg(arr), f"rad_to_deg({arr.dtype})")


@pytest.mark.parametrize(
    "scalar", [np.float32(1.0), np.float64(1.0), np.int32(1), np.int64(1), np.bool_(True)]
)
def test_deg_to_rad_numpy_scalars_keep_their_type(scalar):
    assert_same(prod_units.deg_to_rad(scalar), oracle.deg_to_rad(scalar), "numpy scalar")


@pytest.mark.parametrize("mm", EDGE_FLOATS + tuple(EDGE_INTS))
@pytest.mark.parametrize("cell", [0.1, 1.0, 0.05, -1.0, 0.0])
def test_mm_to_cell(mm, cell):
    assert_same(
        call(prod_units.mm_to_cell, mm, cell),
        call(oracle.mm_to_cell, mm, cell),
        f"mm_to_cell({mm!r}, {cell!r})",
    )


@pytest.mark.parametrize("cell", EDGE_INTS)
@pytest.mark.parametrize("size", [0.1, 1.0, 0.05])
def test_cell_to_mm(cell, size):
    assert_same(
        call(prod_units.cell_to_mm, cell, size),
        call(oracle.cell_to_mm, cell, size),
        f"cell_to_mm({cell!r}, {size!r})",
    )


def test_distance_and_manhattan_random_sweep():
    xs = _random_floats(8000, seed=3)
    for i in range(0, len(xs) - 3, 4):
        a, b, c, d = xs[i : i + 4]
        assert_same(prod_units.distance_mm(a, b, c, d), oracle.distance_mm(a, b, c, d), "distance")
        assert_same(
            prod_units.manhattan_distance_mm(a, b, c, d),
            oracle.manhattan_distance_mm(a, b, c, d),
            "manhattan",
        )


@pytest.mark.parametrize("a", EDGE_FLOATS)
@pytest.mark.parametrize("b", (0.0, -0.0, 1.0, float("inf"), float("nan")))
def test_distance_and_manhattan_edges(a, b):
    assert_same(prod_units.distance_mm(a, b, b, a), oracle.distance_mm(a, b, b, a), "distance")
    assert_same(
        prod_units.manhattan_distance_mm(a, b, b, a),
        oracle.manhattan_distance_mm(a, b, b, a),
        "manhattan",
    )


@pytest.mark.parametrize("layer", EDGE_INTS + (-2, 7))
@pytest.mark.parametrize("max_layers", [0, 1, 4, 8])
def test_is_valid_layer(layer, max_layers):
    assert_same(
        call(prod_units.is_valid_layer, layer, max_layers),
        call(oracle.is_valid_layer, layer, max_layers),
        "is_valid_layer",
    )


def test_is_valid_layer_default_max_layers_is_four():
    for layer in (-1, 0, 3, 4):
        assert_same(
            call(prod_units.is_valid_layer, layer),
            call(oracle.is_valid_layer, layer),
            "is_valid_layer default",
        )


@pytest.mark.parametrize("net_id", EDGE_INTS + (-2, -1))
def test_is_valid_net_id(net_id):
    assert_same(
        call(prod_units.is_valid_net_id, net_id),
        call(oracle.is_valid_net_id, net_id),
        "is_valid_net_id",
    )


# ---------------------------------------------------------------------------
# net classification
# ---------------------------------------------------------------------------

_NC_PREDICATES = (
    "is_ground_net",
    "is_power_net",
    "is_hv_net",
    "is_signal_net",
    "classify_net_type",
    "is_ground_pin",
    "is_power_pin",
    "is_hv_pin",
    "is_clock_pin",
)


@pytest.mark.parametrize("fn_name", _NC_PREDICATES)
def test_net_classification_full_corpus(fn_name):
    prod_fn = getattr(prod_nc, fn_name)
    oracle_fn = getattr(oracle, fn_name)
    for name in NAME_CORPUS:
        assert_same(call(prod_fn, name), call(oracle_fn, name), f"{fn_name}({name!r})")


def test_net_classification_corpus_is_not_degenerate():
    """Anti-vacuity: the corpus must exercise every outcome."""
    outcomes = {oracle.classify_net_type(n) for n in NAME_CORPUS}
    assert outcomes == {"ground", "power", "hv", "signal"}

    # ... and must contain names that match more than one set, or the
    # precedence order is untested (mutant M11).
    multi = [
        n
        for n in NAME_CORPUS
        if sum(
            (
                oracle.is_ground_net(n),
                oracle.is_power_net(n),
                oracle.is_hv_net(n),
            )
        )
        > 1
    ]
    assert multi, "corpus contains no name matching two pattern sets"
    for pair in (("is_ground_net", "is_power_net"), ("is_ground_net", "is_hv_net")):
        assert any(
            getattr(oracle, pair[0])(n) and getattr(oracle, pair[1])(n) for n in NAME_CORPUS
        ), f"corpus never exercises the {pair[0]} vs {pair[1]} precedence edge"
    for fn_name in _NC_PREDICATES:
        if fn_name == "classify_net_type":
            continue
        fn = getattr(oracle, fn_name)
        results = {fn(n) for n in NAME_CORPUS}
        assert results == {True, False}, f"{fn_name} never returned both outcomes"


def test_pattern_constants_did_not_drift_from_rust():
    """The Rust holds its own copy of the seven pattern sets."""
    import temper_io_types as rs

    # Rust matches exactly the names the Python constants say it should,
    # for a probe built from the constants themselves.
    for patterns, predicate in (
        (prod_nc.GROUND_NET_PATTERNS, rs.is_ground_net),
        (prod_nc.POWER_NET_PATTERNS, rs.is_power_net),
        (prod_nc.HV_NET_PATTERNS, rs.is_hv_net),
        (prod_nc.GROUND_PIN_PATTERNS, rs.is_ground_pin),
        (prod_nc.POWER_PIN_PATTERNS, rs.is_power_pin),
        (prod_nc.HV_PIN_PATTERNS, rs.is_hv_pin),
        (prod_nc.CLOCK_PIN_PATTERNS, rs.is_clock_pin),
    ):
        for p in patterns:
            assert predicate(p), f"Rust does not recognise declared pattern {p!r}"


# ---------------------------------------------------------------------------
# manufacturing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nominal", EDGE_FLOATS)
@pytest.mark.parametrize("tolerance", (0.0, -0.0, 0.1, 1.0, float("nan"), float("inf")))
def test_inflated_clearance_and_width(nominal, tolerance):
    assert_same(
        call(prod_mf.inflated_clearance, nominal, tolerance),
        call(oracle.inflated_clearance, nominal, tolerance),
        f"inflated_clearance({nominal!r}, {tolerance!r})",
    )
    assert_same(
        call(prod_mf.inflated_width, nominal, tolerance),
        call(oracle.inflated_width, nominal, tolerance),
        f"inflated_width({nominal!r}, {tolerance!r})",
    )


@pytest.mark.parametrize("nominal", EDGE_FLOATS)
def test_inflated_defaults(nominal):
    assert_same(
        call(prod_mf.inflated_clearance, nominal),
        call(oracle.inflated_clearance, nominal),
        "default tolerance",
    )
    assert_same(
        call(prod_mf.inflated_width, nominal),
        call(oracle.inflated_width, nominal),
        "default tolerance",
    )


def test_inflated_clearance_random_sweep():
    xs = _random_floats(10000, seed=4, lo=-1.0, hi=1.0)
    for i in range(0, len(xs) - 1, 2):
        a, b = xs[i], xs[i + 1]
        assert_same(prod_mf.inflated_clearance(a, b), oracle.inflated_clearance(a, b), "sweep")
        assert_same(prod_mf.inflated_width(a, b), oracle.inflated_width(a, b), "sweep")


@pytest.mark.parametrize("name", ["jlcpcb_standard", "jlcpcb_hdi", "oshpark"])
def test_fab_presets_match_field_for_field(name):
    assert_same(
        getattr(prod_mf.FabPreset, name)(),
        getattr(oracle.FabPreset, name)(),
        f"FabPreset.{name}()",
    )


def test_get_fab_presets_keys_and_order():
    got, want = prod_mf.get_fab_presets(), oracle.get_fab_presets()
    assert list(got) == list(want)
    assert_same(got, want, "get_fab_presets")


def test_fab_preset_constructor_defaults_and_repr():
    assert_same(prod_mf.FabPreset("x"), oracle.FabPreset("x"), "FabPreset('x')")
    assert repr(prod_mf.FabPreset("x")) == repr(oracle.FabPreset("x"))
    assert repr(prod_mf.FabPreset.oshpark()) == repr(oracle.FabPreset.oshpark())


def test_fab_preset_is_mutable_and_unhashable_like_the_dataclass():
    p, o = prod_mf.FabPreset("x"), oracle.FabPreset("x")
    p.min_trace_mm = 0.9
    o.min_trace_mm = 0.9
    assert_same(p, o, "after mutation")
    for obj in (p, o):
        with pytest.raises(TypeError, match="unhashable type: 'FabPreset'"):
            hash(obj)


def test_fab_preset_equality_semantics():
    assert prod_mf.FabPreset("x") == prod_mf.FabPreset("x")
    assert prod_mf.FabPreset("x") != prod_mf.FabPreset("y")
    assert (prod_mf.FabPreset("x") == "x") is (oracle.FabPreset("x") == "x")


# ---------------------------------------------------------------------------
# Rect
# ---------------------------------------------------------------------------

_RECT_ARGS = [
    (0.0, 0.0, 50.0, 80.0),
    (0, 0, 50, 80),
    (-1.5, -2.5, 1.5, 2.5),
    (1, 2, 3, 4),
    (0.0, 0.0, 5e-324, 5e-324),
    (-1e300, -1e300, 1e300, 1e300),
    (0.1, 0.2, 0.30000000000000004, 0.4),
    (-0.0, -0.0, 1.0, 1.0),
    (2**53, 2**53, 2**53 + 4, 2**53 + 4),
]

_RECT_BAD_ARGS = [
    (5, 0, 1, 1),
    (0, 5, 1, 1),
    (0.0, 0.0, 0.0, 1.0),
    (0.0, 0.0, 1.0, 0.0),
    (float("nan"), 0.0, 1.0, 1.0),
    (0.0, 0.0, float("nan"), 1.0),
    (0.0, 0.0, float("inf"), float("inf")),
]


@pytest.mark.parametrize("args", _RECT_ARGS)
def test_rect_construction_and_attributes(args):
    got, want = ProdRect(*args), oracle.Rect(*args)
    assert_same(got, want, f"Rect{args}")
    assert_same(got.width, want.width, "width")
    assert_same(got.height, want.height, "height")
    assert repr(got) == repr(want)
    assert_same(list(got), list(want), "iteration")
    assert len(got) == len(want)
    assert hash(got) == hash(want)


@pytest.mark.parametrize("args", _RECT_BAD_ARGS)
def test_rect_invariant_errors_match_exactly(args):
    assert_same(call(ProdRect, *args), call(oracle.Rect, *args), f"Rect{args}")


@pytest.mark.parametrize("args", _RECT_ARGS)
def test_rect_alternate_constructors(args):
    assert_same(call(ProdRect.from_xyxy, *args), call(oracle.Rect.from_xyxy, *args), "from_xyxy")
    x, y = args[0], args[1]
    w, h = 3.0, 4.0
    assert_same(
        call(ProdRect.from_xywh, x, y, w, h),
        call(oracle.Rect.from_xywh, x, y, w, h),
        "from_xywh",
    )


@pytest.mark.parametrize(
    "value",
    [
        (0, 0, 50, 80),
        [0.0, 0.0, 50.0, 80.0],
        (0.5, 1.5, 2.5, 3.5),
        (1, 2, 3),
        (1, 2, 3, 4, 5),
        "abcd",
        42,
    ],
)
def test_rect_coerce(value):
    assert_same(call(ProdRect.coerce, value), call(oracle.Rect.coerce, value), f"coerce({value!r})")


def test_rect_coerce_is_identity_for_an_existing_rect():
    r = ProdRect(0.0, 0.0, 1.0, 1.0)
    assert ProdRect.coerce(r) is r
    o = oracle.Rect(0.0, 0.0, 1.0, 1.0)
    assert oracle.Rect.coerce(o) is o


@pytest.mark.parametrize(
    "other",
    [
        (0.0, 0.0, 50.0, 80.0),
        [0.0, 0.0, 50.0, 80.0],
        (0.0, 0.0, 50.0, 81.0),
        (0, 0, 50, 80),
        (0.0, 0.0, 50.0),
        (0.0, 0.0, 50.0, 80.0, 1.0),
        "not a rect",
        None,
        42,
    ],
)
def test_rect_equality_against_every_operand_kind(other):
    got = ProdRect(0.0, 0.0, 50.0, 80.0)
    want = oracle.Rect(0.0, 0.0, 50.0, 80.0)
    assert (got == other) == (want == other), f"== {other!r}"
    assert (got != other) == (want != other), f"!= {other!r}"


def test_rect_equality_between_rects():
    a, b = ProdRect(0.0, 0.0, 1.0, 1.0), ProdRect(0.0, 0.0, 1.0, 1.0)
    oa, ob = oracle.Rect(0.0, 0.0, 1.0, 1.0), oracle.Rect(0.0, 0.0, 1.0, 1.0)
    assert (a == b) == (oa == ob)
    assert (a == ProdRect(0.0, 0.0, 1.0, 2.0)) == (oa == oracle.Rect(0.0, 0.0, 1.0, 2.0))


@pytest.mark.parametrize("index", [0, 1, 2, 3, -1, -4, 4, -5, slice(0, 2), slice(None, None, -1)])
def test_rect_indexing_including_negatives_and_slices(index):
    got = ProdRect(0.0, 1.0, 2.0, 3.0)
    want = oracle.Rect(0.0, 1.0, 2.0, 3.0)
    assert_same(call(got.__getitem__, index), call(want.__getitem__, index), f"[{index!r}]")


def test_rect_is_frozen_with_the_same_exception():
    got, want = ProdRect(0.0, 0.0, 1.0, 1.0), oracle.Rect(0.0, 0.0, 1.0, 1.0)
    for obj in (got, want):
        with pytest.raises(Exception) as exc:  # noqa: PT011 -- type is the assertion
            obj.x_min = 5.0
        assert type(exc.value).__name__ == "FrozenInstanceError"
        assert str(exc.value) == "cannot assign to field 'x_min'"


def test_rect_unpacks_positionally():
    a, b, c, d = ProdRect(1.0, 2.0, 3.0, 4.0)
    oa, ob, oc, od = oracle.Rect(1.0, 2.0, 3.0, 4.0)
    assert_same([a, b, c, d], [oa, ob, oc, od], "unpack")


def test_rect_random_sweep():
    rng = random.Random(5)
    for _ in range(4000):
        x0 = rng.uniform(-1e4, 1e4)
        y0 = rng.uniform(-1e4, 1e4)
        w = rng.uniform(1e-9, 1e4)
        h = rng.uniform(1e-9, 1e4)
        args = (x0, y0, x0 + w, y0 + h)
        got, want = call(ProdRect, *args), call(oracle.Rect, *args)
        assert_same(got, want, f"Rect{args}")
        if not isinstance(want, BaseException):
            assert_same(got.width, want.width, "width")
            assert_same(got.height, want.height, "height")
            assert hash(got) == hash(want)
            assert repr(got) == repr(want)


@pytest.mark.parametrize("args", _RECT_ARGS)
def test_rect_survives_pickle_copy_and_deepcopy(args):
    """A pyclass is unpicklable by default; the dataclass was not.

    This was a real regression, caught after the first differential was
    already green: `copy.deepcopy(zone)` and `pickle.dumps(board)` both
    reach a `Rect` through `Zone.bounds` and raised `TypeError: cannot
    pickle 'temper_io_types.Rect' object`. `__reduce__` fixes it; this
    test is what would have caught it.
    """
    import copy
    import pickle

    got, want = ProdRect(*args), oracle.Rect(*args)
    for label, roundtrip in (
        ("pickle", lambda o: pickle.loads(pickle.dumps(o))),
        ("deepcopy", copy.deepcopy),
        ("copy", copy.copy),
    ):
        assert_same(roundtrip(got), roundtrip(want), f"Rect{args} via {label}")
        # ... and the round-tripped object is still the same class and
        # still equal to the original, including field types.
        assert type(roundtrip(got)) is type(got)
        assert roundtrip(got) == got


def test_zone_and_board_survive_pickle_and_deepcopy():
    """The regression's actual blast radius: Zone.bounds is a Rect."""
    import copy
    import pickle

    from temper_placer.core.board import Board, Zone

    z = Zone("Z", (0, 0, 10, 10))
    for roundtrip in (lambda o: pickle.loads(pickle.dumps(o)), copy.deepcopy):
        assert roundtrip(z).bounds == (0.0, 0.0, 10.0, 10.0)
        board = Board(width=10, height=10, zones=[Zone("A", (0, 0, 5, 5))])
        assert roundtrip(board).zones[0].bounds == (0.0, 0.0, 5.0, 5.0)


def test_contract_objects_survive_pickle_and_deepcopy():
    """Same for FabPreset."""
    import copy
    import pickle

    subjects = [
        (prod_mf.FabPreset.oshpark(), oracle.FabPreset.oshpark()),
        # Every field non-default, so a `__reduce__` that silently drops
        # one is caught. The three named presets all leave
        # `drill_tolerance_mm` at its default, which is why dropping it
        # from the reduce tuple survived (mutant M39) until this case.
        (
            prod_mf.FabPreset("custom", 0.11, 0.22, 0.33, 0.44, 0.55, 0.66),
            oracle.FabPreset("custom", 0.11, 0.22, 0.33, 0.44, 0.55, 0.66),
        ),
    ]
    for got, want in subjects:
        for label, roundtrip in (
            ("pickle", lambda o: pickle.loads(pickle.dumps(o))),
            ("deepcopy", copy.deepcopy),
        ):
            assert_same(roundtrip(got), roundtrip(want), f"{type(got).__name__} via {label}")


def test_rect_subclassing_still_works():
    """The dataclass was subclassable, so the pyclass must be too."""

    class MyRect(ProdRect):
        pass

    class MyOracleRect(oracle.Rect):
        pass

    m, o = MyRect(0.0, 0.0, 1.0, 1.0), MyOracleRect(0.0, 0.0, 1.0, 1.0)
    # Compared through the unpacked fields rather than `assert_same`,
    # because the signature keys on the concrete type name and these two
    # subclasses deliberately have different ones.
    assert_same(list(m), list(o), "subclass fields")
    assert repr(m).startswith("MyRect(") or repr(m).startswith("Rect(")
    # `coerce` returns a subclass instance unchanged, and `from_xyxy`
    # constructs the subclass -- both because they dispatch on `cls`.
    assert ProdRect.coerce(m) is m
    assert oracle.Rect.coerce(o) is o
    assert type(MyRect.from_xyxy(0.0, 0.0, 2.0, 2.0)) is MyRect
    assert type(MyOracleRect.from_xyxy(0.0, 0.0, 2.0, 2.0)) is MyOracleRect

    # A subclass must survive copy/deepcopy AS the subclass -- i.e.
    # `__reduce__` has to reconstruct through `type(self)`, not through
    # the concrete `Rect`. (Mutant M36 survived until this was added; a
    # locally-defined class cannot be pickled, so copy is the vehicle.)
    import copy

    assert type(copy.copy(m)) is MyRect
    assert type(copy.deepcopy(m)) is MyRect
    assert type(copy.deepcopy(o)) is MyOracleRect
    assert_same(list(copy.deepcopy(m)), list(copy.deepcopy(o)), "subclass deepcopy")


def test_rect_keeps_the_dataclass_protocol_and_asdict_shape():
    """The migration's one API delta was CLOSED; this pins the parity.

    This test used to pin the delta in the other direction:
    `dataclasses.is_dataclass(Rect)` had become `False`, so `asdict()` on a
    dataclass *containing* a `Rect` stopped recursing into it and deep-copied
    the `Rect` instead::

        before:  {'bounds': {'x_min': 0.0, 'y_min': 0.0, ...}}
        after:   {'bounds': Rect(x_min=0.0, y_min=0.0, ...)}

    That delta was judged acceptable because none of the four `asdict` call
    sites was reachable from a `Rect`. It was then closed anyway by
    `b5d472865` ("restore the dataclass protocol on the migrated contracts"),
    which put `__dataclass_fields__` back on the pyclass. Measured here: the
    nested-dict shape is what `asdict` produces again.

    So the assertion is inverted relative to its old self ON PURPOSE. Left as
    it was, it asserted the absence of a property that a later commit
    deliberately restored -- a test pinning a fact that had stopped being
    true. It still bites: lose the protocol again and both halves fail.
    """
    import dataclasses

    assert dataclasses.is_dataclass(ProdRect), (
        "Rect lost __dataclass_fields__ -- b5d472865 restored it deliberately, "
        "and asdict() on anything containing a Rect silently changes shape "
        "when it goes missing"
    )
    assert dataclasses.is_dataclass(oracle.Rect)

    from temper_placer.core.board import Zone

    z = Zone("Z", (0, 0, 1, 1))
    assert dataclasses.is_dataclass(z.bounds)

    @dataclasses.dataclass
    class _Holder:
        bounds: object

    prod = dataclasses.asdict(_Holder(bounds=ProdRect(0.0, 0.0, 1.0, 1.0)))
    orac = dataclasses.asdict(_Holder(bounds=oracle.Rect(0.0, 0.0, 1.0, 1.0)))
    assert prod == orac, f"asdict shape diverged from the oracle: {prod} != {orac}"
    assert prod == {"bounds": {"x_min": 0.0, "y_min": 0.0, "x_max": 1.0, "y_max": 1.0}}

# adjacency
# ---------------------------------------------------------------------------


def _netlists(component_refs, net_pin_refs):
    """A production Netlist and the oracle's projection of the same data."""
    from temper_placer.core.netlist import Component, Net, Netlist

    prod = Netlist(
        components=[Component(ref=r, footprint="F", bounds=(1.0, 1.0)) for r in component_refs],
        nets=[
            Net(name=f"N{i}", pins=[(r, "1") for r in pins]) for i, pins in enumerate(net_pin_refs)
        ],
    )
    return prod, oracle.make_oracle_netlist(component_refs, net_pin_refs)


@pytest.mark.parametrize(
    ("refs", "nets"),
    [
        ([], []),
        (["U1"], []),
        (["U1", "U2"], [["U1", "U2"]]),
        (["U1", "U2"], [["U1", "U1", "U1", "U2"]]),
        (["U1", "U2"], [["U1", "U2"], ["U2", "U1"]]),
        (["U1"], [["U1", "MISSING"]]),
        (["U1", "U1", "U2"], [["U1", "U2"]]),
        (["U1", "U2", "U3", "U4"], [["U1", "U2", "U3", "U4"]]),
        (["U1", "U2", "U3"], [[], ["U1"], ["U1", "U2", "U3"]]),
    ],
)
def test_build_adjacency_matrix_cases(refs, nets):
    prod, orc = _netlists(refs, nets)
    assert_same(prod_adjacency(prod), oracle.build_adjacency_matrix(orc), f"{refs} {nets}")


@pytest.mark.parametrize("n_components", [1, 5, 40, 400])
def test_build_adjacency_matrix_random(n_components):
    """`n=400`/1200 nets matches the perf harness's largest netlist."""
    rng = random.Random(9000 + n_components)
    refs = [f"U{i}" for i in range(n_components)]
    nets = []
    for _ in range(min(3 * n_components, 1200)):
        k = rng.randint(0, min(8, n_components))
        nets.append([rng.choice(refs) for _ in range(k)])
    prod, orc = _netlists(refs, nets)
    assert_same(prod_adjacency(prod), oracle.build_adjacency_matrix(orc), f"n={n_components}")


def test_build_adjacency_matrix_random_is_not_all_zeros():
    prod, orc = _netlists(
        [f"U{i}" for i in range(40)],
        [[f"U{i}", f"U{(i + 1) % 40}"] for i in range(40)],
    )
    assert oracle.build_adjacency_matrix(orc).sum() > 0


def test_empty_netlist_dtype_is_float64_not_float32():
    prod, orc = _netlists([], [])
    assert prod_adjacency(prod).dtype == np.float64
    assert_same(prod_adjacency(prod), oracle.build_adjacency_matrix(orc), "empty")


# ---------------------------------------------------------------------------
# benchmark-parameter coverage (the PR #714 lesson)
# ---------------------------------------------------------------------------


def test_perf_harness_parameters_are_covered():
    """Every size the perf harness runs is measured by a test above.

    PR #714 verified parity at iteration counts its own benchmark then
    exceeded, and failed on Linux CI. This asserts the coverage relation
    directly rather than trusting a reading of both files.
    """
    from tests.wave4_phase2 import test_core_contracts_perf as perf

    assert len(NAME_CORPUS) >= perf.PERF_NAME_COUNT
    assert perf.PERF_PIN_COUNT <= 600
    assert perf.PERF_COMPONENT_COUNT <= 400
    assert perf.PERF_NET_COUNT <= 1200
    assert perf.PERF_RECT_COUNT <= 4000
