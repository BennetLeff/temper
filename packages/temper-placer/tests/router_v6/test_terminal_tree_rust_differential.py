"""R1a differential: ``router_v6/terminal_tree`` vs its pinned oracle.

**THIS SUITE IS DELIBERATELY RED.** Gate G1 (``docs/wave4-discipline-contract.md``)
requires the differential that pins the pre-migration implementation
verbatim to exist and fail *before* the Rust exists; every comparison
resolves its Rust arm through ``tests/router_v6/_pending_rust.rust`` and
fails with a named ``PendingRustError`` until the migration supplies the
pyfunction.

Arms
----
* **oracle** -- ``tests/router_v6/_terminal_tree_py_oracle.py``, a verbatim
  ``git show`` copy of ``terminal_tree.py`` at
  ``550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5`` (``origin/main``).
* **rust** -- the ``plan_terminal_tree_py`` pyfunction the migration adds,
  bound in the adapter block below.

Comparison is by type-carrying signature (``tests/router_v6/_signature``).
**No tolerance anywhere.** Both arms compare at the wire-tuple level: a pad
is ``(component_ref, pad, net, x, y, layers_list, center_x, center_y)``, a
plan is ``(root_wire, [(source_wire, target_wire), ...])`` -- exactly the
shape ``plan_terminal_tree_py`` is expected to accept and return, matching
pyo3's ``Vec`` -> ``list`` / Rust-tuple -> Python-tuple conversion so
``sig()`` (which discriminates ``list`` from ``tuple``) cannot pass on a
container-type mismatch that would be invisible to a plain ``==``.

Why the ``connected``/``remaining`` sets in the oracle do not need to be
reproduced (see the oracle module's own docstring for the full argument):
the ``min(..., key=...)`` tie-break key includes the candidate
``PadIdentity`` values themselves, not just their hash-derived position, and
``terminals`` is deduped by identity first -- so for any two distinct
candidate pairs the key differs by construction, and CPython's ``set``
iteration order (salted per process) never has a tie to resolve. A Rust port
using plain ascending-index iteration reproduces the oracle exactly.
"""

from __future__ import annotations

import ast
import subprocess

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import tests.router_v6._terminal_tree_py_oracle as ORACLE
from temper_placer.router_v6.connectivity import CopperPad, PadIdentity
from temper_placer.router_v6.constraints_geometry import Point
from tests.router_v6._pending_rust import missing_symbols, rust
from tests.router_v6._signature import sig

# ===========================================================================
# ADAPTER BLOCK -- the ONLY part of this file that knows the Rust arm exists.
# Phase B binds these; no assertion and no corpus row below changes.
# ===========================================================================

_RUST_MODULE = "temper_rust_router"

REQUIRED_RUST_SYMBOLS: tuple[str, ...] = ("plan_terminal_tree_py",)


def _rust(symbol: str):
    return rust(_RUST_MODULE, symbol)


# ===========================================================================
# END ADAPTER BLOCK
# ===========================================================================

_ORACLE_PIN_SHA = "550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5"
_ORACLE_NAMES: tuple[str, ...] = (
    "TreeTerminal",
    "TerminalTreeEdge",
    "TerminalTreePlan",
    "plan_terminal_tree",
    "_manhattan",
)


def _capture(fn):
    try:
        return fn()
    except BaseException as exc:  # noqa: BLE001 - error parity is the point
        return exc


def _identity_wire(ident: PadIdentity) -> tuple:
    return (ident.component_ref, ident.pad, ident.net, ident.x, ident.y, list(ident.layers))


def _pad_wire(pad: CopperPad) -> tuple:
    return (*_identity_wire(pad.identity), pad.center.x, pad.center.y)


def _plan_wire(plan) -> tuple:
    return (
        _identity_wire(plan.root),
        [(_identity_wire(e.source), _identity_wire(e.target)) for e in plan.edges],
    )


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
    rel = "packages/temper-placer/src/temper_placer/router_v6/terminal_tree.py"
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
        assert name in original, f"{name} missing from terminal_tree.py at the pin"
        assert copied[name] == original[name], (
            f"terminal_tree.py::{name} in the oracle is NOT verbatim -- "
            f"the pin is broken and the differential proves nothing"
        )


def test_rust_symbols_exist():
    """The migration checklist. RED until every kernel is ported."""
    missing = missing_symbols(_RUST_MODULE, REQUIRED_RUST_SYMBOLS)
    assert not missing, (
        f"{_RUST_MODULE} is missing {len(missing)} of {len(REQUIRED_RUST_SYMBOLS)} "
        f"terminal_tree kernels: {missing}"
    )


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------


def _pad(ref: str, index: int, x: float, y: float, layers: tuple[int, ...] = (0,)) -> CopperPad:
    # x/y are coerced to float: PadIdentity.x/y and Point.x/y are typed
    # `float` (`connectivity.py`/`core/geometry_types.py`), and real pad
    # positions are always the float output of pin_world_position -- an
    # int literal here would be an unrealistic fixture, and would also
    # trip `sig()`'s deliberate int/float discrimination against a Rust
    # arm that (correctly) always returns f64.
    x, y = float(x), float(y)
    return CopperPad(PadIdentity(ref, str(index), "NET", x, y, layers), Point(x, y), "rect", (1, 1))


THREE_PAD_LINE = [_pad("U1", 2, 10, 0), _pad("U1", 1, 0, 0), _pad("U1", 3, 0, 10)]
SINGLE_PAD = [_pad("U1", 1, 5, 5)]
TWO_PADS = [_pad("U1", 1, 0, 0), _pad("U1", 2, 3, 4)]
STAR = [
    _pad("U1", 0, 0, 0),
    _pad("U1", 1, 10, 0),
    _pad("U1", 2, -10, 0),
    _pad("U1", 3, 0, 10),
    _pad("U1", 4, 0, -10),
]
MULTI_COMPONENT = [
    _pad("U1", 1, 0, 0),
    _pad("J1", 1, 20, 0),
    _pad("R1", 1, 20, 20),
    _pad("C1", 1, 0, 20),
]
TIED_DISTANCES = [
    _pad("A", 1, 0, 0),
    _pad("B", 1, 5, 0),
    _pad("C", 1, 0, 5),
]  # B and C are both distance 5 from A -- identity breaks the tie.
NEGATIVE_AND_FRACTIONAL = [
    _pad("U1", 1, -1.5, -2.25),
    _pad("U1", 2, 3.75, 0.5),
    _pad("U1", 3, -0.25, 4.0),
]
MULTI_LAYER_IDENTITY = [
    _pad("U1", 1, 0, 0, layers=(0, 31)),
    _pad("U1", 2, 5, 0, layers=(0,)),
    _pad("U1", 3, 0, 5, layers=(31,)),
]
DUPLICATE_IDENTITY = [
    _pad("U1", 1, 0, 0),
    _pad("U1", 1, 0, 0),  # exact duplicate identity+center -- dedups to one
    _pad("U1", 2, 10, 0),
]

CASES: tuple[tuple[str, list[CopperPad]], ...] = (
    ("three_pad_line", THREE_PAD_LINE),
    ("single_pad", SINGLE_PAD),
    ("two_pads", TWO_PADS),
    ("star", STAR),
    ("multi_component", MULTI_COMPONENT),
    ("tied_distances", TIED_DISTANCES),
    ("negative_and_fractional", NEGATIVE_AND_FRACTIONAL),
    ("multi_layer_identity", MULTI_LAYER_IDENTITY),
    ("duplicate_identity", DUPLICATE_IDENTITY),
)


# ---------------------------------------------------------------------------
# plan_terminal_tree
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", CASES, ids=lambda c: c[0])
def test_plan_terminal_tree_bit_exact(case):
    _label, pads = case
    _assert_same(
        f"plan_terminal_tree[{_label}]",
        lambda: _plan_wire(ORACLE.plan_terminal_tree(pads)),
        "plan_terminal_tree_py",
        lambda fn: fn([_pad_wire(p) for p in pads]),
    )


def test_plan_terminal_tree_empty_raises():
    _assert_same(
        "plan_terminal_tree[empty]",
        lambda: ORACLE.plan_terminal_tree([]),
        "plan_terminal_tree_py",
        lambda fn: fn([]),
    )


# ---------------------------------------------------------------------------
# Property-based sweep
# ---------------------------------------------------------------------------

_point_strategy = st.tuples(
    st.floats(-100, 100, allow_nan=False, allow_infinity=False),
    st.floats(-100, 100, allow_nan=False, allow_infinity=False),
)


@given(
    st.lists(_point_strategy, min_size=1, max_size=8, unique=True),
)
@settings(max_examples=100, deadline=30_000)
def test_plan_terminal_tree_random_sweep(points):
    pads = [_pad("U1", i, x, y) for i, (x, y) in enumerate(points)]
    _assert_same(
        "plan_terminal_tree[random]",
        lambda: _plan_wire(ORACLE.plan_terminal_tree(pads)),
        "plan_terminal_tree_py",
        lambda fn: fn([_pad_wire(p) for p in pads]),
    )
