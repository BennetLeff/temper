"""R1a differential: ``router_v6/path_simplify`` vs its pinned oracle.

**THIS SUITE IS DELIBERATELY RED.** Gate G1 (``docs/wave4-discipline-contract.md``)
requires the differential that pins the pre-migration implementation
verbatim to exist and fail *before* the Rust exists; every comparison
resolves its Rust arm through ``tests/router_v6/_pending_rust.rust`` and
fails with a named ``PendingRustError`` until the migration supplies the
pyfunction.

Arms
----
* **oracle** -- ``tests/router_v6/_path_simplify_py_oracle.py``, a verbatim
  ``git show`` copy of ``path_simplify.py`` at
  ``550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5`` (``origin/main``).
* **rust** -- the pyfunctions the migration adds, listed in
  :data:`REQUIRED_RUST_SYMBOLS` and bound in the adapter block below.
  Resolved from ``temper_geometry`` (``via_clearance.rs``), the Wave-4
  home crate for router_v6 geometry; the duplicate ``temper-rust-router``
  copies were deleted in the cross-crate kernel dedupe.

Comparison is by type-carrying signature (``tests/router_v6/_signature``).
**No tolerance anywhere.** Both arms are compared at the wire-tuple level
(``(x, y, layer)`` int triples) because that is the shape the Rust kernel
actually accepts and returns; ``GridCell`` reconstruction from that tuple is
a lossless, un-interesting bijection asserted once in
``test_wire_tuples_round_trip_through_gridcell``.

Why this module has no float/hash traps (see the oracle module's own
docstring for the full argument): ``GridCell`` is all-``int`` fields, so
every comparison is exact; the one thing a Rust port must still get right is
iterating ``cells`` in order and never reordering into a set.
"""

from __future__ import annotations

import ast
import subprocess

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import tests.router_v6._path_simplify_py_oracle as ORACLE
from temper_placer.router_v6.grid_types import GridCell
from tests.router_v6._pending_rust import missing_symbols, rust
from tests.router_v6._signature import sig

# ===========================================================================
# ADAPTER BLOCK -- the ONLY part of this file that knows the Rust arm exists.
# Phase B binds these; no assertion and no corpus row below changes.
# ===========================================================================

_RUST_MODULE = "temper_geometry"

REQUIRED_RUST_SYMBOLS: tuple[str, ...] = (
    "is_collinear_py",
    "simplify_path_py",
    "estimate_segment_count_py",
)


def _rust(symbol: str):
    return rust(_RUST_MODULE, symbol)


# ===========================================================================
# END ADAPTER BLOCK
# ===========================================================================

_ORACLE_PIN_SHA = "550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5"
_ORACLE_NAMES: tuple[str, ...] = ("is_collinear", "simplify_path", "estimate_segment_count")


def _capture(fn):
    try:
        return fn()
    except BaseException as exc:  # noqa: BLE001 - error parity is the point
        return exc


def _cell_tuple(c: GridCell) -> tuple[int, int, int]:
    return (c.x, c.y, c.layer)


def _cells_to_tuples(cells: list[GridCell]) -> tuple[tuple[int, int, int], ...]:
    return tuple(_cell_tuple(c) for c in cells)


def _assert_same(label: str, oracle_fn, symbol: str, rust_fn):
    """The oracle arm runs first, so a broken oracle fails with its own error."""
    a = _capture(oracle_fn)
    fn = _rust(symbol)  # RED until the Rust arm lands
    b = _capture(lambda: rust_fn(fn))
    assert sig(a) == sig(b), f"{label}: oracle={a!r} rust={b!r}"


# ---------------------------------------------------------------------------
# G1 evidence: the oracle is a verbatim pin
# ---------------------------------------------------------------------------


def _segments_from_source(src: str, names: tuple[str, ...]) -> dict[str, str]:
    tree = ast.parse(src)
    lines = src.splitlines()
    out: dict[str, str] = {}
    for node in tree.body:
        nm = getattr(node, "name", None)
        if nm in names:
            decos = getattr(node, "decorator_list", [])
            start = (min(d.lineno for d in decos) if decos else node.lineno) - 1
            out[nm] = "\n".join(lines[start : node.end_lineno])
    return out


def test_oracle_is_verbatim_copy():
    """Every definition in the oracle is character-identical to the pin."""
    rel = "packages/temper-placer/src/temper_placer/router_v6/path_simplify.py"
    try:
        src = subprocess.run(
            ["git", "show", f"{_ORACLE_PIN_SHA}:{rel}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):  # pragma: no cover
        pytest.skip(f"pinned commit {_ORACLE_PIN_SHA} not present in this clone")

    original = _segments_from_source(src, _ORACLE_NAMES)
    with open(ORACLE.__file__, encoding="utf-8") as fh:
        copied = _segments_from_source(fh.read(), _ORACLE_NAMES)

    for name in _ORACLE_NAMES:
        assert name in copied, f"{name} missing from the oracle module"
        assert name in original, f"{name} missing from path_simplify.py at the pin"
        assert copied[name] == original[name], (
            f"path_simplify.py::{name} in the oracle is NOT verbatim -- "
            f"the pin is broken and the differential proves nothing"
        )


def test_rust_symbols_exist():
    """The migration checklist. RED until every kernel is ported."""
    missing = missing_symbols(_RUST_MODULE, REQUIRED_RUST_SYMBOLS)
    assert not missing, (
        f"{_RUST_MODULE} is missing {len(missing)} of {len(REQUIRED_RUST_SYMBOLS)} "
        f"path_simplify kernels: {missing}"
    )


def test_wire_tuples_round_trip_through_gridcell():
    """The (x, y, layer) tuple <-> GridCell mapping is lossless -- asserted
    once so the comparisons below can work at the tuple level without
    re-litigating this every case."""
    c = GridCell(3, -7, 2)
    assert _cell_tuple(c) == (3, -7, 2)
    assert GridCell(*_cell_tuple(c)) == c


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------

STRAIGHT_LINE = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)]
L_SHAPE = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(1, 1, 0)]
LAYER_CHANGE = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(1, 0, 1)]
EMPTY: list[GridCell] = []
SINGLE = [GridCell(5, 5, 0)]
TWO_POINTS = [GridCell(0, 0, 0), GridCell(9, 9, 3)]
ZIGZAG = [
    GridCell(0, 0, 0),
    GridCell(1, 0, 0),
    GridCell(1, 1, 0),
    GridCell(2, 1, 0),
    GridCell(2, 2, 0),
]
DUPLICATE_POINTS = [GridCell(0, 0, 0), GridCell(0, 0, 0), GridCell(0, 0, 0)]
LAYER_FLAP = [
    GridCell(0, 0, 0),
    GridCell(1, 0, 1),
    GridCell(1, 0, 0),
    GridCell(2, 0, 0),
]
LONG_STRAIGHT_THEN_TURN = [GridCell(i, 0, 0) for i in range(10)] + [
    GridCell(9, 1, 0),
    GridCell(9, 2, 0),
]
NEGATIVE_COORDS = [GridCell(-5, -5, 0), GridCell(-3, -5, 0), GridCell(-1, -5, 0)]
MULTI_LAYER_VIA_CHAIN = [
    GridCell(0, 0, 0),
    GridCell(0, 0, 1),
    GridCell(0, 0, 2),
    GridCell(0, 0, 3),
]

CASES: tuple[tuple[str, list[GridCell]], ...] = (
    ("straight_line", STRAIGHT_LINE),
    ("l_shape", L_SHAPE),
    ("layer_change", LAYER_CHANGE),
    ("empty", EMPTY),
    ("single", SINGLE),
    ("two_points", TWO_POINTS),
    ("zigzag", ZIGZAG),
    ("duplicate_points", DUPLICATE_POINTS),
    ("layer_flap", LAYER_FLAP),
    ("long_straight_then_turn", LONG_STRAIGHT_THEN_TURN),
    ("negative_coords", NEGATIVE_COORDS),
    ("multi_layer_via_chain", MULTI_LAYER_VIA_CHAIN),
)

TRIPLES: tuple[tuple[str, GridCell, GridCell, GridCell], ...] = (
    ("horizontal", GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)),
    ("vertical", GridCell(0, 0, 0), GridCell(0, 1, 0), GridCell(0, 2, 0)),
    ("corner", GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(1, 1, 0)),
    ("layer_mismatch_p1", GridCell(0, 0, 1), GridCell(1, 0, 0), GridCell(2, 0, 0)),
    ("layer_mismatch_p3", GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 1)),
    ("coincident", GridCell(3, 3, 0), GridCell(3, 3, 0), GridCell(3, 3, 0)),
)


# ---------------------------------------------------------------------------
# is_collinear
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", TRIPLES, ids=lambda c: c[0])
def test_is_collinear_bit_exact(case):
    _label, p1, p2, p3 = case
    _assert_same(
        f"is_collinear[{_label}]",
        lambda: ORACLE.is_collinear(p1, p2, p3),
        "is_collinear_py",
        lambda fn: fn(_cell_tuple(p1), _cell_tuple(p2), _cell_tuple(p3)),
    )


# ---------------------------------------------------------------------------
# simplify_path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES, ids=lambda c: c[0])
def test_simplify_path_bit_exact(case):
    _label, cells = case
    _assert_same(
        f"simplify_path[{_label}]",
        lambda: _cells_to_tuples(ORACLE.simplify_path(cells)),
        "simplify_path_py",
        lambda fn: tuple(fn(_cells_to_tuples(cells))),
    )


# ---------------------------------------------------------------------------
# estimate_segment_count
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES, ids=lambda c: c[0])
def test_estimate_segment_count_bit_exact(case):
    _label, cells = case
    _assert_same(
        f"estimate_segment_count[{_label}]",
        lambda: ORACLE.estimate_segment_count(cells),
        "estimate_segment_count_py",
        lambda fn: fn(_cells_to_tuples(cells)),
    )


# ---------------------------------------------------------------------------
# Property-based sweep
# ---------------------------------------------------------------------------

_cell_strategy = st.tuples(
    st.integers(-50, 50), st.integers(-50, 50), st.integers(0, 5)
).map(lambda t: GridCell(*t))


@given(st.lists(_cell_strategy, min_size=0, max_size=25))
@settings(max_examples=200, deadline=30_000)
def test_simplify_path_random_sweep(cells):
    _assert_same(
        "simplify_path[random]",
        lambda: _cells_to_tuples(ORACLE.simplify_path(cells)),
        "simplify_path_py",
        lambda fn: tuple(fn(_cells_to_tuples(cells))),
    )


@given(st.lists(_cell_strategy, min_size=0, max_size=25))
@settings(max_examples=200, deadline=30_000)
def test_estimate_segment_count_random_sweep(cells):
    _assert_same(
        "estimate_segment_count[random]",
        lambda: ORACLE.estimate_segment_count(cells),
        "estimate_segment_count_py",
        lambda fn: fn(_cells_to_tuples(cells)),
    )
