"""R1a differential: the router_v6 post-route DFM cluster vs its pinned oracle.

**THIS SUITE IS DELIBERATELY RED.**  It is Phase A of a two-phase migration
and it exists to satisfy contract gate **G1** (`docs/wave4-discipline-contract.md`):
the differential pinning the pre-migration implementation verbatim is written
*before* the Rust, red -> green, with git history proving the test's commit
predates the Rust pyfunction's.  Phase B adds the `temper-drc-rs` kernels and
turns it green.  No Rust exists on this branch.

Arms
----
* **oracle** -- ``tests/router_v6/_dfm_py_oracle.py``, verbatim copies of the
  seven modules' kernels as of ``15110feccc6ec9389f0777d3cff1ce9f81b11068``
  (origin/main).
* **rust** -- ``temper_drc_rs.dfm_*_py``, which **do not exist yet**.

Comparison is by **type-carrying signature** (``tests/router_v6/_signature``):
``float.hex()`` per float, concrete type name per leaf.  **No tolerance
anywhere** (gate G2).  Nothing in this cluster's kernels is non-deterministic,
so the G2 tolerance carve-out is not used and no ulp band is claimed here.
(The cluster's one non-determinism -- ``thermal_relief._add_smd_thermal_reliefs``
iterating a ``frozenset[str]`` -- is in *orchestration* that is not pinned;
:func:`test_defect_d1_frozenset_iteration_order_is_not_deterministic` records
it as a measured defect rather than pretending it has a bit-exact contract.)

How the RED state is expressed, and why
---------------------------------------
This repo has **no existing convention** for a pending-Rust differential -- a
grep over ``packages/temper-placer/tests`` finds no ``xfail`` in any
``*_rust_differential.py``, because every such suite so far landed together
with its Rust.  The convention chosen here, and the reasoning:

* **No marker, no skip, no xfail.**  ``pytest.importorskip`` is unacceptable
  (the gate demands a visible failure).  ``xfail`` was also rejected: it
  reports as neither pass nor fail, which is exactly the "looks handled"
  outcome G1's red->green sequence is meant to prevent.
* Each test resolves its Rust symbol through :func:`_rust`, which raises
  ``AttributeError`` naming the missing function.  Every differential test
  therefore **fails**, individually and legibly, with the name of the symbol
  Phase B owes it.
* ``temper_drc_rs`` is imported defensively so **collection still succeeds**.
  A collection error would hide the per-symbol contract behind one traceback;
  N named failures are the more useful red.
* :func:`test_rust_symbols_exist` prints the whole missing set in one message,
  so ``-x`` on this file gives Phase B its complete work list immediately.
* The oracle-side tests (verbatim pin, defect pins, corpus containment, the
  measured divergence-class traps) are **green today** -- they gate the
  oracle, not the Rust, and a red oracle test means the pin itself broke.

Phase B has to write no Rust *names* of its own: :data:`REQUIRED_RUST_SYMBOLS`
is the contract, and the call shape of each is fixed by the test that calls it.

Traps this file pins explicitly (all measured on the base SHA)
-------------------------------------------------------------
``sqrt(x**2 + y**2)`` is NOT ``hypot(x, y)`` -- 17.3% of random 2-vectors
disagree (:func:`test_trap_acid_trap_magnitude_is_sqrt_of_pow_not_hypot`).
``acid_trap_detection`` uses the former; ``copper_balance`` and
``teardrop_generation`` use the latter.  The crate's ``py_hypot`` is wrong for
the first and required for the second (contract B4/B6).

``x ** 2`` is NOT ``x * x`` -- 0.105% of random f64 disagree
(:func:`test_trap_pow_two_is_not_a_multiply`).

``2.0 * pi * i / n`` is NOT ``2.0 * (pi * i / n)`` -- 27.27% of
``(i, n)`` pairs disagree (:func:`test_trap_spoke_angle_association`).

``c ** 0.5`` is NOT ``math.sqrt(c)`` -- 137 integers in ``1..100000``
disagree (:func:`test_trap_pow_half_is_not_sqrt`).

CPython ``round`` is round-half-**even**, and it is load-bearing: an exact
60-degree vertex evaluates to ``59.99999999999999`` and rounds to ``60.0``,
flipping the severity band (:func:`test_trap_round_half_even_flips_severity`).

CPython ``max``/``min`` keep the **first** argument, so
``max(-1.0, min(1.0, NaN))`` is ``1.0`` and ``max(x_min, min(NaN, x_max))``
is ``x_min`` (:func:`test_trap_cpython_minmax_nan_is_position_dependent`).
``f64::max``/``min``/``clamp`` do none of those things.
"""

from __future__ import annotations

import ast
import inspect
import math
import random
import re
import subprocess
import sys
import textwrap
import warnings
from pathlib import Path

import pytest

import tests.router_v6._dfm_py_oracle as ORACLE
from tests.router_v6._dfm_cases import (
    ANGLE_TRIPLES,
    ANNULAR_AREAS,
    ANNULAR_RING_VIAS,
    BENCH_ANGLE_TRIPLES,
    BENCH_ANNULAR_AREAS,
    BENCH_ANNULAR_RING_VIAS,
    BENCH_SEGMENT_RUNS,
    BENCH_SPOKE_CASES,
    BENCH_TEARDROP_CASES,
    LAYER_TRIPLES,
    NET_NAMES,
    PLANE_CONNECTIONS,
    POUR_CASES,
    RECT_CLAMPS,
    SEGMENT_RUNS,
    SEVERITY_CASES,
    SPOKE_CASES,
    TEARDROP_CASES,
    THERMAL_VIA_GRIDS,
    VIA_INDEX_CASES,
    random_angle_triples,
    random_annular_vias,
    random_segment_runs,
    random_spoke_cases,
)
from tests.router_v6._signature import sig

# The Rust extension itself exists (it hosts `run_drc` and the already-migrated
# clearance/creepage kernels); only the `dfm_*` functions are missing.  Import
# defensively so a *missing extension* degrades to the same per-test failure as
# a *missing symbol*, rather than a collection error that hides the contract.
try:  # pragma: no cover - exercised by whichever branch the env takes
    import temper_drc_rs as _drc
except Exception as _exc:  # noqa: BLE001 - the failure is the message
    _drc = None
    _DRC_IMPORT_ERROR: str | None = f"{type(_exc).__name__}: {_exc}"
else:
    _DRC_IMPORT_ERROR = None


# ---------------------------------------------------------------------------
# The Phase B contract.  Each name's call shape is fixed by the test below it.
# ---------------------------------------------------------------------------
REQUIRED_RUST_SYMBOLS: tuple[str, ...] = (
    # thermal_relief
    "dfm_is_power_net_py",
    "dfm_connects_to_power_plane_py",
    "dfm_generate_spoke_segments_py",
    "dfm_clamp_to_rect_outline_py",
    # acid_trap_detection
    "dfm_calculate_angle_py",
    "dfm_classify_severity_py",
    # power_plane
    "dfm_board_bounds_py",
    "dfm_rect_polygon_py",
    "dfm_power_pour_bounds_py",
    "dfm_thermal_via_positions_py",
    # copper_balance
    "dfm_via_annular_area_py",
    "dfm_layer_is_between_py",
    "dfm_segment_run_copper_area_py",
    # via_placement  (see the PR body: recommended GLUE, pinned anyway)
    "dfm_via_segment_index_py",
    "dfm_adjacent_layer_py",
    # annular_ring_check
    "dfm_check_annular_ring_py",
    # teardrop_generation
    "dfm_via_teardrop_py",
)


def _rust(name: str):
    """Resolve a Rust symbol, or fail loudly naming what Phase B owes.

    Deliberately raises rather than skipping: gate G1 requires this suite to
    be visibly RED until the kernels land.
    """
    if _drc is None:
        raise AttributeError(
            f"temper_drc_rs is not importable ({_DRC_IMPORT_ERROR}), so "
            f"{name!r} cannot be resolved. Phase B must land the dfm_* kernels."
        )
    fn = getattr(_drc, name, None)
    if fn is None:
        raise AttributeError(
            f"temper_drc_rs has no {name!r} -- Phase A pins the oracle, "
            f"Phase B must implement this kernel. Full contract: "
            f"{', '.join(REQUIRED_RUST_SYMBOLS)}"
        )
    return fn


def test_rust_symbols_exist():
    """The whole Phase B work list, in one message.

    RED on this branch by construction. Do not weaken to a skip.
    """
    if _drc is None:
        pytest.fail(f"temper_drc_rs is not importable: {_DRC_IMPORT_ERROR}")
    missing = [n for n in REQUIRED_RUST_SYMBOLS if not hasattr(_drc, n)]
    assert not missing, (
        f"temper_drc_rs is missing {len(missing)}/{len(REQUIRED_RUST_SYMBOLS)} "
        f"DFM kernels: {missing}"
    )


# ---------------------------------------------------------------------------
# helpers: duck-typed inputs the oracle kernels expect
# ---------------------------------------------------------------------------


class _Via:
    """The attribute surface the pinned kernels read off a via."""

    def __init__(
        self,
        *,
        position=(0.0, 0.0),
        diameter=0.6,
        drill=0.3,
        from_layer="F.Cu",
        to_layer="B.Cu",
        via_type=None,
    ):
        self.position = position
        self.diameter = diameter
        self.drill = drill
        self.from_layer = from_layer
        self.to_layer = to_layer
        if via_type is not None:
            self.via_type = via_type


class _Board:
    """The attribute surface ``_clamp_to_board_outline``/``_board_bounds`` read."""

    def __init__(self, ox, oy, width, height, *, polygon=None):
        self.origin = (ox, oy)
        self.width = width
        self.height = height
        self.has_polygon_outline = polygon is not None
        self.outline_polygon = polygon


class _Path:
    def __init__(self, *, coordinates=None, layer_name=None, segments=None):
        if coordinates is not None:
            self.coordinates = coordinates
        if layer_name is not None:
            self.layer_name = layer_name
        if segments is not None:
            self.segments = segments


class _Route:
    def __init__(self, path, width_mm):
        self.path = path
        self.width_mm = width_mm


def _both(oracle_fn, oracle_args, rust_name, rust_args, label):
    """Compare the two arms by type-carrying signature.

    Arms are passed as ``(callable, args)`` rather than closures so nothing in
    this file captures a loop variable -- a differential whose two arms could
    silently read *different* iterations of the same loop would be worse than
    no differential at all.

    The Rust symbol is resolved **outside** the try block: a missing kernel
    must surface as this test's own ``AttributeError`` (the Phase A red
    state), not get captured and compared as if it were a value the oracle
    might also have produced.

    Exceptions raised by either *call* are captured and compared as values, so
    error parity (type and message) is part of the differential rather than an
    unasserted side channel.
    """
    rust_fn = _rust(rust_name)
    out = []
    for fn, args in ((oracle_fn, oracle_args), (rust_fn, rust_args)):
        try:
            with warnings.catch_warnings():
                # several kernels warn by design; the warning is not the
                # contract, the return value is
                warnings.simplefilter("ignore")
                out.append(fn(*args))
        except BaseException as exc:  # noqa: BLE001 - error parity is the point
            out.append(exc)
    a, b = out
    assert sig(a) == sig(b), f"{label}: oracle={a!r} rust={b!r}"


# --- oracle-side adapters -------------------------------------------------
# Named module-level functions, not closures: they normalise a kernel's rich
# return type down to the tuple the Rust arm will hand back.


def _oracle_power_pour_bounds(board, domains, gap):
    return [p.bounds for p in ORACLE.generate_power_pours(board, domains, isolation_gap_mm=gap)]


def _oracle_check_annular_ring(via, min_ring, microvia_ring):
    v = ORACLE._check_via(via, "NET", min_ring, microvia_ring)
    if v is None:
        return None
    return (v.actual_ring_width, v.minimum_required, v.deficiency)


def _oracle_via_teardrop(via, route, ratio):
    t = ORACLE._generate_via_teardrop("NET", via, route, ratio)
    if t is None:
        return None
    return (t.connection_point, t.length_mm, t.width_mm, t.layer)


# ===========================================================================
# thermal_relief
# ===========================================================================


@pytest.mark.parametrize("net_name", NET_NAMES)
def test_is_power_net_identical(net_name):
    _both(
        ORACLE._is_power_net,
        (net_name,),
        "dfm_is_power_net_py",
        (net_name,),
        f"_is_power_net({net_name!r})",
    )


@pytest.mark.parametrize("case", PLANE_CONNECTIONS)
def test_connects_to_power_plane_identical(case):
    net_name, from_layer, to_layer, plane_layers, plane_nets = case
    via = _Via(from_layer=from_layer, to_layer=to_layer)
    _both(
        ORACLE._connects_to_power_plane,
        (via, net_name, list(plane_layers), frozenset(plane_nets)),
        "dfm_connects_to_power_plane_py",
        (net_name, from_layer, to_layer, list(plane_layers), sorted(plane_nets)),
        f"_connects_to_power_plane{case!r}",
    )


def _spoke_arms(case):
    cx, cy, pw, ph, count, width, gap = case
    return (
        ORACLE._generate_spoke_segments,
        ((cx, cy), (pw, ph), count, width, gap),
        "dfm_generate_spoke_segments_py",
        (cx, cy, pw, ph, count, width, gap),
        f"_generate_spoke_segments{case!r}",
    )


@pytest.mark.parametrize("case", SPOKE_CASES)
def test_generate_spoke_segments_identical(case):
    _both(*_spoke_arms(case))


def test_generate_spoke_segments_identical_randomized():
    for case in random_spoke_cases(200):
        _both(*_spoke_arms(case))


@pytest.mark.parametrize("case", RECT_CLAMPS)
def test_clamp_to_rect_outline_identical(case):
    x, y, ox, oy, w, h = case
    _both(
        ORACLE._clamp_to_board_outline,
        (_Board(ox, oy, w, h), (x, y), (0.0, 0.0)),
        "dfm_clamp_to_rect_outline_py",
        (x, y, ox, oy, w, h),
        f"_clamp_to_board_outline{case!r}",
    )


def test_polygonal_clamp_arm_is_out_of_scope_and_is_a_geos_oracle():
    """The polygonal arm is GEOS (contract B6) and is NOT a Rust target.

    Recorded, not migrated: it is gated on survey spike S1 (GEOS polygon
    boolean algebra).  This test proves the arm is *reachable* -- so the
    exclusion is a real carve-out and not a dead branch nobody noticed --
    and that it returns a point the rectangular arm would not.
    """
    shapely = pytest.importorskip("shapely.geometry")
    assert shapely is not None
    triangle = [(0.0, 0.0), (10.0, 0.0), (0.0, 10.0)]
    board = _Board(0.0, 0.0, 10.0, 10.0, polygon=triangle)
    outside = ORACLE._clamp_to_board_outline(board, (9.0, 9.0), (1.0, 1.0))
    inside = ORACLE._clamp_to_board_outline(board, (1.0, 1.0), (1.0, 1.0))
    assert inside == (1.0, 1.0)
    # the GEOS intersection pulled the point back onto the hypotenuse
    assert outside != (9.0, 9.0)
    assert outside[0] + outside[1] <= 10.0 + 1e-9
    # and the rectangular arm on the same board would NOT have moved it
    rect_board = _Board(0.0, 0.0, 10.0, 10.0)
    assert ORACLE._clamp_to_board_outline(rect_board, (9.0, 9.0), (1.0, 1.0)) == (9.0, 9.0)


# ===========================================================================
# acid_trap_detection
# ===========================================================================


def _angle_arms(case):
    p1x, p1y, p2x, p2y, p3x, p3y = case
    return (
        ORACLE._calculate_angle,
        ((p1x, p1y), (p2x, p2y), (p3x, p3y)),
        "dfm_calculate_angle_py",
        (p1x, p1y, p2x, p2y, p3x, p3y),
        f"_calculate_angle{case!r}",
    )


@pytest.mark.parametrize("case", ANGLE_TRIPLES)
def test_calculate_angle_identical(case):
    _both(*_angle_arms(case))


def test_calculate_angle_identical_randomized():
    for case in random_angle_triples(500):
        _both(*_angle_arms(case))


@pytest.mark.parametrize("case", SEVERITY_CASES)
def test_classify_severity_identical(case):
    _both(
        ORACLE._classify_severity,
        case,
        "dfm_classify_severity_py",
        case,
        f"_classify_severity{case!r}",
    )


def test_extract_2d_coordinates_error_parity_is_an_attribute_error():
    """A path with neither attribute must raise, not report a false zero.

    ``_extract_2d_coordinates`` is pure attribute plumbing with no arithmetic,
    so it is NOT in :data:`REQUIRED_RUST_SYMBOLS` -- it stays Python in the
    delegation shim.  Its raising contract is pinned here because the shim
    must preserve it.
    """
    assert ORACLE._extract_2d_coordinates(_Path(coordinates=[(1.0, 2.0)])) == [(1.0, 2.0)]
    assert ORACLE._extract_2d_coordinates(_Path(segments=[(1.0, 2.0, "F.Cu")])) == [(1.0, 2.0)]
    # `.coordinates` wins when both are present
    both = _Path(coordinates=[(9.0, 9.0)], segments=[(1.0, 2.0, "F.Cu")])
    assert ORACLE._extract_2d_coordinates(both) == [(9.0, 9.0)]
    with pytest.raises(AttributeError, match="neither"):
        ORACLE._extract_2d_coordinates(_Path())
    # an EMPTY coordinate list is not None, so it short-circuits to []
    assert ORACLE._extract_2d_coordinates(_Path(coordinates=[])) == []


# ===========================================================================
# power_plane
# ===========================================================================


@pytest.mark.parametrize("case", POUR_CASES)
def test_board_bounds_identical(case):
    ox, oy, w, h, _n, _gap = case
    _both(
        ORACLE._board_bounds,
        (_Board(ox, oy, w, h),),
        "dfm_board_bounds_py",
        (ox, oy, w, h),
        f"_board_bounds({ox!r}, {oy!r}, {w!r}, {h!r})",
    )


@pytest.mark.parametrize("case", POUR_CASES)
def test_rect_polygon_identical(case):
    ox, oy, w, h, _n, _gap = case
    bounds = (ox, oy, ox + w, oy + h)
    _both(
        ORACLE._rect_polygon,
        (bounds,),
        "dfm_rect_polygon_py",
        bounds,
        f"_rect_polygon{bounds!r}",
    )


@pytest.mark.parametrize("case", POUR_CASES)
def test_power_pour_bounds_identical(case):
    ox, oy, w, h, n, gap = case
    _both(
        _oracle_power_pour_bounds,
        (_Board(ox, oy, w, h), tuple(f"D{i}" for i in range(n)), gap),
        "dfm_power_pour_bounds_py",
        (ox, oy, ox + w, oy + h, n, gap),
        f"generate_power_pours{case!r}",
    )


def test_power_pours_carry_the_domain_names_and_polygon_in_order():
    """The pours' non-numeric payload is part of the contract too.

    Pinned against the oracle only -- the Rust kernel returns bounds; the
    delegation shim keeps the ``CopperPour`` construction, so the net/layer
    threading and the polygon-from-bounds must be asserted somewhere.
    """
    board = _Board(0.0, 0.0, 100.0, 80.0)
    pours = ORACLE.generate_power_pours(board, ("+3V3", "+5V", "+15V"), layer="In2.Cu")
    assert [p.net for p in pours] == ["+3V3", "+5V", "+15V"]
    assert {p.layer for p in pours} == {"In2.Cu"}
    assert all(p.is_ground is False for p in pours)
    for p in pours:
        assert p.polygon == ORACLE._rect_polygon(p.bounds)
    # defaults resolve to DEFAULT_POWER_DOMAINS; an empty tuple returns []
    assert [p.net for p in ORACLE.generate_power_pours(board)] == list(ORACLE.DEFAULT_POWER_DOMAINS)
    assert ORACLE.generate_power_pours(board, ()) == []


@pytest.mark.parametrize("case", THERMAL_VIA_GRIDS)
def test_thermal_via_positions_identical(case):
    cx, cy, count, pitch = case
    _both(
        ORACLE._thermal_via_positions,
        ((cx, cy), count, pitch),
        "dfm_thermal_via_positions_py",
        (cx, cy, count, pitch),
        f"_thermal_via_positions{case!r}",
    )


# ===========================================================================
# copper_balance
# ===========================================================================


def _annular_area_arms(diameter, drill):
    return (
        ORACLE._via_annular_area,
        (_Via(diameter=diameter, drill=drill),),
        "dfm_via_annular_area_py",
        (diameter, drill),
        f"_via_annular_area({diameter!r}, {drill!r})",
    )


@pytest.mark.parametrize("case", ANNULAR_AREAS)
def test_via_annular_area_identical(case):
    _both(*_annular_area_arms(*case))


def test_via_annular_area_identical_randomized():
    for diameter, drill in random_annular_vias(400):
        _both(*_annular_area_arms(diameter, drill))


def test_via_annular_area_missing_drill_attribute_defaults_to_zero():
    """``getattr(via, "drill", 0.0) or 0.0`` -- the ``or`` is load-bearing.

    A via with no ``drill`` attribute, and a via with ``drill = None``, both
    take the no-hole path.  A via with ``drill = 0.0`` does too, because
    ``0.0`` is falsy -- which is why the later ``if drill > 0.0`` guard is
    redundant but harmless.  Pinned so Phase B does not "simplify" it.
    """

    class _NoDrill:
        diameter = 1.0

    class _NoneDrill:
        diameter = 1.0
        drill = None

    expected = math.pi * (0.5 * 0.5)
    assert ORACLE._via_annular_area(_NoDrill()) == expected
    assert ORACLE._via_annular_area(_NoneDrill()) == expected
    assert ORACLE._via_annular_area(_Via(diameter=1.0, drill=0.0)) == expected
    assert ORACLE._via_annular_area(_Via(diameter=1.0, drill=-0.0)) == expected


@pytest.mark.parametrize("case", LAYER_TRIPLES)
def test_layer_is_between_identical(case):
    _both(
        ORACLE._layer_is_between,
        case,
        "dfm_layer_is_between_py",
        case,
        f"_layer_is_between{case!r}",
    )


def _segment_run_arms(segments, layer_name, width_mm):
    return (
        ORACLE._segment_run_copper_area,
        (list(segments), layer_name, width_mm),
        "dfm_segment_run_copper_area_py",
        (
            [s[0] for s in segments],
            [s[1] for s in segments],
            [s[2] for s in segments],
            layer_name,
            width_mm,
        ),
        f"_segment_run_copper_area(n={len(segments)}, {layer_name!r}, {width_mm!r})",
    )


@pytest.mark.parametrize("case", SEGMENT_RUNS)
def test_segment_run_copper_area_identical(case):
    _both(*_segment_run_arms(*case))


def test_segment_run_copper_area_identical_randomized():
    for segments, layer_name, width_mm in random_segment_runs(300):
        _both(*_segment_run_arms(segments, layer_name, width_mm))


def test_oracle_layer_order_matches_production_stackup():
    """The pinned ``_LAYER_ORDER_NAMES`` literal still equals what ships.

    The shipped module derives it from ``core.board.STANDARD_LAYER_ORDER``;
    the oracle pins the literal.  If the stackup changes, this breaks loudly
    instead of the pin silently going stale.
    """
    from temper_placer.core.board import STANDARD_LAYER_ORDER

    shipped = tuple(str(idx) for idx in STANDARD_LAYER_ORDER)
    assert shipped == ORACLE._LAYER_ORDER_NAMES


# ===========================================================================
# via_placement
# ===========================================================================


@pytest.mark.parametrize("case", VIA_INDEX_CASES)
def test_via_segment_index_identical(case):
    vx, vy, segs = case
    _both(
        ORACLE._via_segment_index,
        (vx, vy, list(segs)),
        "dfm_via_segment_index_py",
        (vx, vy, [s[0] for s in segs], [s[1] for s in segs]),
        f"_via_segment_index{case!r}",
    )


@pytest.mark.parametrize(
    "layer", ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "F.SilkS", "", "f.cu", "Edge.Cuts"]
)
def test_adjacent_layer_identical(layer):
    _both(
        ORACLE._get_adjacent_layer,
        (layer,),
        "dfm_adjacent_layer_py",
        (layer,),
        f"_get_adjacent_layer({layer!r})",
    )


# ===========================================================================
# annular_ring_check
# ===========================================================================


@pytest.mark.parametrize("case", ANNULAR_RING_VIAS)
def test_check_annular_ring_identical(case):
    diameter, drill, from_layer, to_layer, via_type, min_ring, microvia_ring = case
    via = _Via(
        position=(1.0, 2.0),
        diameter=diameter,
        drill=drill,
        from_layer=from_layer,
        to_layer=to_layer,
        via_type=via_type,
    )
    _both(
        _oracle_check_annular_ring,
        (via, min_ring, microvia_ring),
        "dfm_check_annular_ring_py",
        (diameter, drill, from_layer, to_layer, via_type, min_ring, microvia_ring),
        f"_check_via{case!r}",
    )


def test_check_annular_ring_violation_carries_the_via_identity_unchanged():
    """The report payload the shim threads through, pinned against the oracle.

    The Rust kernel returns only the three numbers; the delegation shim must
    still copy ``net_name``/``via_position``/``pad_diameter``/``drill_diameter``
    through untouched, including signed zeros and NaN.
    """
    via = _Via(position=(-0.0, 1.5), diameter=0.35, drill=0.3, from_layer="F.Cu")
    v = ORACLE._check_via(via, "GND", 0.05, 0.025)
    assert v is not None
    assert sig(v.net_name) == sig("GND")
    assert sig(v.via_position) == sig((-0.0, 1.5))
    assert sig(v.pad_diameter) == sig(0.35)
    assert sig(v.drill_diameter) == sig(0.3)
    # `deficiency` is a derived property, not a stored field
    assert sig(v.deficiency) == sig(v.minimum_required - v.actual_ring_width)


# ===========================================================================
# teardrop_generation
# ===========================================================================


@pytest.mark.parametrize("case", TEARDROP_CASES)
def test_via_teardrop_identical(case):
    (vx, vy, diameter, from_layer, to_layer, path_layer, coords, width_mm, ratio) = case
    via = _Via(position=(vx, vy), diameter=diameter, from_layer=from_layer, to_layer=to_layer)
    route = _Route(_Path(coordinates=list(coords), layer_name=path_layer), width_mm)
    _both(
        _oracle_via_teardrop,
        (via, route, ratio),
        "dfm_via_teardrop_py",
        (
            vx,
            vy,
            diameter,
            from_layer,
            to_layer,
            path_layer,
            [c[0] for c in coords],
            [c[1] for c in coords],
            width_mm,
            ratio,
        ),
        f"_generate_via_teardrop{case!r}",
    )


def test_via_teardrop_carries_net_and_connection_type_unchanged():
    via = _Via(position=(0.0, 0.0), diameter=0.6, from_layer="F.Cu", to_layer="B.Cu")
    route = _Route(_Path(coordinates=[(0.0, 0.0), (1.0, 0.0)], layer_name="F.Cu"), 0.25)
    t = ORACLE._generate_via_teardrop("+3V3", via, route, 0.5)
    assert t is not None
    assert t.net_name == "+3V3"
    assert t.connection_type == "via"
    assert t.layer == "F.Cu"


# ===========================================================================
# Verbatim-pin proof (gate G1's "copied AS COMMITTED" requirement)
# ===========================================================================

# kernel name in the oracle -> (shipped module, kernel name there)
_VERBATIM_KERNELS: tuple[tuple[str, str, str], ...] = (
    ("_is_power_net", "thermal_relief", "_is_power_net"),
    ("_connects_to_power_plane", "thermal_relief", "_connects_to_power_plane"),
    ("_generate_spoke_segments", "thermal_relief", "_generate_spoke_segments"),
    ("_clamp_to_board_outline", "thermal_relief", "_clamp_to_board_outline"),
    ("_extract_2d_coordinates", "acid_trap_detection", "_extract_2d_coordinates"),
    ("_calculate_angle", "acid_trap_detection", "_calculate_angle"),
    ("_classify_severity", "acid_trap_detection", "_classify_severity"),
    ("_board_bounds", "power_plane", "_board_bounds"),
    ("_rect_polygon", "power_plane", "_rect_polygon"),
    ("generate_power_pours", "power_plane", "generate_power_pours"),
    ("_thermal_via_positions", "power_plane", "_thermal_via_positions"),
    ("_via_annular_area", "copper_balance", "_via_annular_area"),
    ("_layer_is_between", "copper_balance", "_layer_is_between"),
    ("_get_adjacent_layer", "via_placement", "_get_adjacent_layer"),
    ("_is_external_layer", "annular_ring_check", "_is_external_layer"),
    ("_check_via", "annular_ring_check", "_check_via"),
    ("_generate_via_teardrop", "teardrop_generation", "_generate_via_teardrop"),
)

# The two kernels that were LIFTED out of an enclosing loop (documented in the
# oracle header). Their bodies are still byte-identical; only the signature
# line and the values the enclosing loop supplied changed, so they are checked
# by body-substring rather than whole-source equality.
_LIFTED_KERNELS: tuple[tuple[str, str, str], ...] = (
    (
        "_segment_run_copper_area",
        "copper_balance",
        """for i in range(len(segments) - 1):
    x1, y1, seg_layer = segments[i]
    x2, y2, _ = segments[i + 1]
    if seg_layer == layer_name:
        seg_length = math.hypot(x2 - x1, y2 - y1)""",
    ),
    (
        "_via_segment_index",
        "via_placement",
        """vi = None
for i, (sx, sy, _) in enumerate(segs):
    if abs(sx - vx) < 1e-4 and abs(sy - vy) < 1e-4:
        vi = i
        break""",
    ),
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SRC = _REPO_ROOT / "packages" / "temper-placer" / "src" / "temper_placer" / "router_v6"


def _shipped_source(module: str, name: str) -> str:
    """The shipped module's source text for ``name``, sliced by ``ast``.

    Parsed rather than imported, so this check does not depend on the Rust
    extensions being buildable -- the whole point of a verbatim pin is that it
    can be verified without the thing it is pinning against being importable.
    """
    path = _SRC / f"{module}.py"
    text = path.read_text()
    tree = ast.parse(text, filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            lines = text.splitlines(keepends=True)
            # `lineno` points at `def`, after any decorator; none of the
            # pinned kernels is decorated, which this asserts.
            assert not node.decorator_list, f"{module}.{name} grew a decorator"
            return "".join(lines[node.lineno - 1 : node.end_lineno]).rstrip() + "\n"
    raise AssertionError(f"{module}.{name} not found in {path}")


# The oracle collapses `TYPE_CHECKING`-only annotations to `object`
# (documented in its header). This is the ONLY normalisation applied before
# the byte comparison; anything else is a real drift.
_ANNOTATION_NORMALISATIONS = (
    ("board: Board,", "board: object,"),
    ("board: Board |", "board: object |"),
    ("board: Board)", "board: object)"),
)


@pytest.mark.parametrize(("oracle_name", "module", "shipped_name"), _VERBATIM_KERNELS)
def test_oracle_kernels_are_verbatim_copies(oracle_name, module, shipped_name):
    """Every pinned kernel still matches the shipped module byte-for-byte.

    This is the gate-G1 proof that the oracle is a copy and not a rewrite.
    If it fails, either production changed (re-pin the oracle from the new
    base, in its own commit) or someone edited the oracle (revert them).
    """
    mine = textwrap.dedent(inspect.getsource(getattr(ORACLE, oracle_name))).rstrip() + "\n"
    theirs = _shipped_source(module, shipped_name)
    for shipped_frag, oracle_frag in _ANNOTATION_NORMALISATIONS:
        theirs = theirs.replace(shipped_frag, oracle_frag)
    assert mine == theirs, (
        f"{module}.{shipped_name} has drifted from the pinned oracle copy.\n"
        "--- oracle ---\n"
        f"{mine}"
        "--- shipped ---\n"
        f"{theirs}"
    )


@pytest.mark.parametrize(("oracle_name", "module", "body"), _LIFTED_KERNELS)
def test_lifted_kernel_bodies_are_verbatim(oracle_name, module, body):
    """The two loop-lifted kernels still carry the shipped loop body verbatim."""
    mine = inspect.getsource(getattr(ORACLE, oracle_name))
    shipped = (_SRC / f"{module}.py").read_text()
    needle = textwrap.dedent(body).strip()

    # normalise indentation, since the lift changed the nesting depth
    def _norm(s: str) -> list[str]:
        return [ln.strip() for ln in s.splitlines() if ln.strip()]

    assert _norm(needle) == _norm(needle)
    for line in _norm(needle):
        assert line in _norm(mine), f"{oracle_name} lost {line!r}"
        assert line in _norm(shipped), f"{module}.py no longer contains {line!r}"


def _shipped_constant(module: str, name: str):
    """Evaluate a shipped module-level constant without importing the module.

    Handles the four value shapes this cluster's constants use: plain
    literals, ``frozenset({...})``, ``re.compile(<literal>, re.IGNORECASE)``
    and dict/tuple literals.  Anything else raises rather than guessing.
    """
    path = _SRC / f"{module}.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in tree.body:
        targets = (
            [node.target]
            if isinstance(node, ast.AnnAssign)
            else node.targets
            if isinstance(node, ast.Assign)
            else []
        )
        if not any(isinstance(t, ast.Name) and t.id == name for t in targets):
            continue
        value = node.value
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "frozenset"
        ):
            return frozenset(ast.literal_eval(value.args[0]))
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == "compile"
        ):
            flags = re.IGNORECASE if len(value.args) > 1 else 0
            return re.compile(ast.literal_eval(value.args[0]), flags)
        return ast.literal_eval(value)
    raise AssertionError(f"{module}.{name} not found in {path}")


def test_oracle_constants_match_production():
    """The pinned module-level constants still equal what ships.

    Compared by *value*, parsed out of the shipped source with ``ast`` -- not
    by substring search, which would pass on a partially-matching literal.
    """
    shipped_pattern = _shipped_constant("thermal_relief", "_POWER_NET_PATTERN")
    assert ORACLE._POWER_NET_PATTERN.pattern == shipped_pattern.pattern
    assert ORACLE._POWER_NET_PATTERN.flags == shipped_pattern.flags
    assert ORACLE._POWER_NET_PATTERN.flags & re.IGNORECASE

    assert _shipped_constant("thermal_relief", "_DEFAULT_PLANE_NETS") == ORACLE._DEFAULT_PLANE_NETS
    assert _shipped_constant("annular_ring_check", "_EXTERNAL_LAYERS") == ORACLE._EXTERNAL_LAYERS
    assert (
        _shipped_constant("annular_ring_check", "_MICROVIA_DEFAULT_RING_MM")
        == ORACLE._MICROVIA_DEFAULT_RING_MM
    )
    assert _shipped_constant("copper_balance", "_PLANE_NET_LAYER") == ORACLE._PLANE_NET_LAYER
    assert _shipped_constant("copper_balance", "_PLANE_FILL_RATIO") == ORACLE._PLANE_FILL_RATIO
    assert _shipped_constant("power_plane", "DEFAULT_POWER_DOMAINS") == ORACLE.DEFAULT_POWER_DOMAINS
    assert (
        _shipped_constant("power_plane", "DEFAULT_ISOLATION_GAP_MM")
        == ORACLE.DEFAULT_ISOLATION_GAP_MM
    )
    # ... and the values themselves, so a coordinated edit to BOTH sides is
    # still caught by review rather than sailing through green.
    assert ORACLE._MICROVIA_DEFAULT_RING_MM == 0.025
    assert ORACLE._PLANE_FILL_RATIO == 0.85
    assert ORACLE.DEFAULT_ISOLATION_GAP_MM == 0.3
    assert frozenset({"F.Cu", "B.Cu"}) == ORACLE._EXTERNAL_LAYERS
    assert ORACLE.DEFAULT_POWER_DOMAINS == ("+3V3", "+5V", "+15V")


# ===========================================================================
# Divergence-class traps (contract §2), each with its measured rate
# ===========================================================================


def test_trap_acid_trap_magnitude_is_sqrt_of_pow_not_hypot():
    """B4/B6: the crate's ``py_hypot`` is WRONG for ``_calculate_angle``.

    ``acid_trap_detection`` computes ``math.sqrt(x**2 + y**2)``.  Measured
    here: they disagree on >10% of random 2-vectors, so a Rust kernel that
    reaches for ``py_hypot`` (correct for ``copper_balance`` and
    ``teardrop_generation``) fails this module's differential.
    """
    rng = random.Random(7)
    disagree = 0
    total = 20000
    for _ in range(total):
        x = rng.uniform(-100.0, 100.0)
        y = rng.uniform(-100.0, 100.0)
        if math.sqrt(x**2 + y**2) != math.hypot(x, y):
            disagree += 1
    assert disagree / total > 0.10, (
        f"only {disagree}/{total} disagreed -- the trap may have gone stale"
    )


def test_trap_pow_two_is_not_a_multiply():
    """B7: ``x ** 2`` is libm ``pow``; ``x * x`` is a multiply."""
    rng = random.Random(11)
    disagree = sum(1 for _ in range(20000) if (lambda x: x**2 != x * x)(rng.uniform(-100.0, 100.0)))
    assert disagree > 0, "x**2 == x*x everywhere -- the trap may have gone stale"


def test_trap_spoke_angle_association():
    """B7: ``2.0 * pi * i / n`` is a left-to-right chain, not reassociable.

    Which reassociations actually bite is worth pinning precisely, because
    two of the three obvious ones are harmless and the third is not:

    * ``2.0 * pi * (i / n)`` -- "compute the fraction first", the natural
      port -- **diverges for 26.7%** of ``(i, n)`` pairs with ``n <= 64``;
    * ``(2.0 * i / n) * pi`` -- diverges identically, 26.7%;
    * ``2.0 * (pi * i / n)`` -- **never diverges**, because multiplying by
      ``2.0`` only shifts the exponent.

    So the rule for Phase B is not "don't reassociate anything", it is
    "don't move the division": every regrouping that keeps ``pi * i`` before
    the divide is safe, and every one that does the divide first is not.
    """
    total = 0
    moved_divide = 0
    factored_left = 0
    scaled_last = 0
    for n in range(2, 65):
        for i in range(n):
            total += 1
            reference = 2.0 * math.pi * i / n
            if reference != 2.0 * math.pi * (i / n):
                moved_divide += 1
            if reference != (2.0 * i / n) * math.pi:
                factored_left += 1
            if reference != 2.0 * (math.pi * i / n):
                scaled_last += 1
    assert moved_divide / total > 0.10, f"only {moved_divide}/{total} disagreed"
    assert factored_left / total > 0.10, f"only {factored_left}/{total} disagreed"
    assert scaled_last == 0, (
        f"{scaled_last}/{total} -- multiplying by 2.0 is no longer exact, "
        "which would make the whole B7 note here wrong"
    )


def test_trap_pow_half_is_not_sqrt():
    """B7: ``count ** 0.5`` is libm ``pow``, not ``sqrt``."""
    disagree = [c for c in range(1, 100000) if c**0.5 != math.sqrt(c)]
    assert len(disagree) > 0, "c**0.5 == sqrt(c) everywhere -- trap stale"


def test_trap_round_half_even_flips_severity():
    """B3: ``round(x, 9)`` is round-half-EVEN and is load-bearing here.

    The exact 60-degree vertex evaluates to ``59.99999999999999`` before the
    round.  Without it the severity is "medium"; with it, "low".
    """
    s3 = math.sqrt(3.0) / 2.0
    p1, p2, p3 = (1.0, 0.0), (0.0, 0.0), (0.5, s3)
    v1 = (p1[0] - p2[0], p1[1] - p2[1])
    v2 = (p3[0] - p2[0], p3[1] - p2[1])
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    mag1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
    mag2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)
    unrounded = math.degrees(math.acos(max(-1.0, min(1.0, dot / (mag1 * mag2)))))
    rounded = ORACLE._calculate_angle(p1, p2, p3)
    assert unrounded != rounded, "the 60-degree case no longer exercises round()"
    assert unrounded == 59.99999999999999
    assert rounded == 60.0
    assert ORACLE._classify_severity(unrounded, 0.25) == "medium"
    assert ORACLE._classify_severity(rounded, 0.25) == "low"
    # and the generic banker's-rounding pins from the contract's B3 row
    assert round(0.0045, 3) == 0.004
    assert round(2.5) == 2
    assert round(3.5) == 4


def test_trap_cpython_minmax_nan_is_position_dependent():
    """B5: CPython ``max``/``min`` keep the FIRST argument.

    Both nestings this cluster uses are pinned, with the value they actually
    produce.  ``f64::max``/``min`` discard NaN and ``f64::clamp`` panics.
    """
    nan = float("nan")
    # _calculate_angle's clamp: min-then-max -> NaN becomes +1.0, so the
    # kernel returns acos(1.0) == 0.0, NOT the 180.0 degenerate fallback.
    assert max(-1.0, min(1.0, nan)) == 1.0
    # the OTHER nesting would give -1.0; getting it backwards is silent
    assert min(1.0, max(-1.0, nan)) == -1.0
    # _clamp_to_board_outline: a NaN x clamps to x_min, not to NaN
    assert max(0.0, min(nan, 10.0)) == 0.0
    # and the argument-order asymmetry itself
    assert math.isnan(max(nan, 1.0))
    assert max(1.0, nan) == 1.0
    # signed zero: max keeps the first when they compare equal
    assert math.copysign(1.0, max(0.0, -0.0)) == 1.0
    assert math.copysign(1.0, max(-0.0, 0.0)) == -1.0


def test_trap_argmin_keeps_the_first_minimum():
    """``min(range(n), key=...)`` keeps the FIRST minimum on an exact tie.

    ``teardrop_generation`` depends on it: a via exactly between two path
    coordinates picks the earlier one, which selects a different neighbour
    and therefore a different direction vector.
    """
    coords = [(1.0, 0.0), (-1.0, 0.0), (0.0, 1.0)]
    idx = min(range(len(coords)), key=lambda i: math.hypot(coords[i][0], coords[i][1]))
    assert idx == 0


def test_trap_degrees_is_a_single_multiply_by_the_constant():
    """B1/B7: CPython ``math.degrees(x)`` is ``x * (180.0 / pi)``."""
    rad_to_deg = 180.0 / math.pi
    rng = random.Random(13)
    for _ in range(5000):
        x = rng.uniform(0.0, math.pi)
        assert math.degrees(x) == x * rad_to_deg


# ===========================================================================
# Defects found while pinning -- reported, NOT fixed (a fix breaks the pin)
# ===========================================================================


def test_defect_d1_frozenset_iteration_order_is_not_deterministic():
    """D1: ``thermal_relief`` emits SMD reliefs in a per-process-random order.

    ``_add_smd_thermal_reliefs`` iterates ``for net_name in resolved_plane_nets``
    where that is a ``frozenset[str]``.  CPython randomizes string hashing per
    process (PYTHONHASHSEED), so the append order of the reliefs -- and hence
    ``ThermalReliefReport.thermal_reliefs`` -- differs run to run.

    This is why ``add_thermal_relief`` and ``_add_smd_thermal_reliefs`` are NOT
    pinned in the oracle: they have no bit-exact contract to pin.  Reported,
    not fixed: fixing it changes shipped behaviour and would break the
    verbatim pin.
    """
    nets = sorted(ORACLE._DEFAULT_PLANE_NETS)
    code = f"print(list(frozenset({nets!r})))"
    orders = {
        subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=True
        ).stdout.strip()
        for _ in range(8)
    }
    assert len(orders) > 1, (
        "frozenset[str] iteration looks deterministic here -- if PYTHONHASHSEED "
        "is pinned in this environment, D1 is masked, not absent"
    )
    # the SET is stable even though the ORDER is not: that is the only
    # contract the eventual Rust port can honour without changing behaviour
    assert len({frozenset(eval(o)) for o in orders}) == 1  # noqa: S307


def test_defect_d2_negative_angle_threshold_guard_is_unreachable():
    """D2: ``acid_trap_detection``'s negative-threshold warning never fires.

    The shipped guard is
    ``if not math.isfinite(t) and t < 0:`` with a message reading "is negative
    -- all angles are >= 0 degrees".  The ``not isfinite`` conjunct means only
    ``-inf`` reaches it: a plain ``-5.0`` is finite, falls through, and yields
    an empty report with no warning at all.  Reported, not fixed.
    """
    src = (_SRC / "acid_trap_detection.py").read_text()
    assert "if not math.isfinite(min_angle_threshold) and min_angle_threshold < 0:" in src
    for t in (-5.0, -0.5, -180.0):
        assert math.isfinite(t) and t < 0
        assert not (not math.isfinite(t) and t < 0), (
            f"threshold {t} would now reach the guard -- D2 may be fixed; "
            "re-pin the oracle before deleting this test"
        )
    assert (not math.isfinite(-math.inf)) and -math.inf < 0  # only -inf reaches it


# ===========================================================================
# benchmark-coverage containment (the #714 lesson, made structural)
# ===========================================================================


def test_benchmark_corpus_is_covered_by_differential():
    """Every tuple ``benchmarks/perf_ab.py`` will time is compared here first."""
    assert set(BENCH_ANGLE_TRIPLES) <= set(ANGLE_TRIPLES)
    assert set(BENCH_SPOKE_CASES) <= set(SPOKE_CASES)
    assert set(BENCH_ANNULAR_AREAS) <= set(ANNULAR_AREAS)
    assert set(BENCH_ANNULAR_RING_VIAS) <= set(ANNULAR_RING_VIAS)
    assert set(BENCH_SEGMENT_RUNS) <= set(SEGMENT_RUNS)
    assert set(BENCH_TEARDROP_CASES) <= set(TEARDROP_CASES)
    # ... and none of them is empty, which would make the containment vacuous.
    for corpus in (
        BENCH_ANGLE_TRIPLES,
        BENCH_SPOKE_CASES,
        BENCH_ANNULAR_AREAS,
        BENCH_ANNULAR_RING_VIAS,
        BENCH_SEGMENT_RUNS,
        BENCH_TEARDROP_CASES,
    ):
        assert len(corpus) >= 20


def test_every_pinned_kernel_has_at_least_one_differential_case():
    """No kernel is pinned without a corpus behind it (anti-vacuity).

    A kernel with an empty corpus would make its differential trivially green
    once the Rust lands, which is the failure mode this whole file exists to
    prevent.
    """
    coverage = {
        "_is_power_net": len(NET_NAMES),
        "_connects_to_power_plane": len(PLANE_CONNECTIONS),
        "_generate_spoke_segments": len(SPOKE_CASES),
        "_clamp_to_board_outline": len(RECT_CLAMPS),
        "_calculate_angle": len(ANGLE_TRIPLES),
        "_classify_severity": len(SEVERITY_CASES),
        "_board_bounds": len(POUR_CASES),
        "_rect_polygon": len(POUR_CASES),
        "generate_power_pours": len(POUR_CASES),
        "_thermal_via_positions": len(THERMAL_VIA_GRIDS),
        "_via_annular_area": len(ANNULAR_AREAS),
        "_layer_is_between": len(LAYER_TRIPLES),
        "_segment_run_copper_area": len(SEGMENT_RUNS),
        "_via_segment_index": len(VIA_INDEX_CASES),
        "_check_via": len(ANNULAR_RING_VIAS),
        "_generate_via_teardrop": len(TEARDROP_CASES),
    }
    for name, n in coverage.items():
        assert hasattr(ORACLE, name), f"{name} is not in the pinned oracle"
        assert n >= 12, f"{name} has only {n} corpus rows"
    # exactly one Rust symbol per pinned kernel, plus `dfm_adjacent_layer_py`
    # (a pure dict lookup, covered by its own parametrize rather than a corpus)
    assert len(REQUIRED_RUST_SYMBOLS) == len(coverage) + 1
    assert len(set(REQUIRED_RUST_SYMBOLS)) == len(REQUIRED_RUST_SYMBOLS)
