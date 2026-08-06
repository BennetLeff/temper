"""R1a differential: ``router_v6/net_ordering`` vs its pinned oracle (cluster G, split).

**THIS SUITE IS DELIBERATELY RED.**  Gate G1 requires the differential that
pins the pre-migration implementation verbatim to exist and fail *before* the
Rust exists; every comparison resolves its Rust arm through
``tests/router_v6/_pending_rust.rust`` and fails with a named
``PendingRustError`` until Phase B supplies the pyfunction.

Arms
----
* **oracle** -- ``tests/router_v6/_net_ordering_py_oracle.py``, a verbatim
  ``git show`` copy of ``net_ordering.py`` at
  ``15110feccc6ec9389f0777d3cff1ce9f81b11068`` (``origin/main``).
* **rust** -- the pyfunctions Phase B will add, listed in
  :data:`REQUIRED_RUST_SYMBOLS` and bound in the adapter block below.

Comparison is by type-carrying signature (``tests/router_v6/_signature``).
**No tolerance anywhere** -- gate G2.  Exceptions are compared as values.

What this module's contract actually is
---------------------------------------
A **total-order comparator**, not geometry.  The sharpest thing that can be
asserted about it is that ``order_nets`` is invariant under permutation of
``netlist.nets``, and it **holds**: measured over all 24 permutations of a
4-net design and all 6 of a 3-net design tied on every field except ``name``,
**0 mismatches** (:func:`test_order_nets_is_permutation_invariant`).  There is
no PYTHONHASHSEED-class determinism bug here of the kind PR #730 fixed.

It stops holding when a pin coordinate is NaN: ``compute_hpwl`` returns NaN,
the 6-tuple key stops being a total order, and ``list.sort``'s output becomes
a function of input order -- measured, **4 distinct orderings** across 6
permutations.  That is pinned as a fact
(:func:`test_nan_wirelength_breaks_the_total_order`), not weakened away, and
it is gated on a NaN input rather than on interpreter state.

Traps this file pins explicitly
-------------------------------
``max``/``min`` over an *iterable* containing NaN is neither ``f64::max``'s
discard nor a clean propagate: it is whatever survives a left-to-right scan,
so ``max([nan, 5.0])`` is ``nan`` while ``max([5.0, nan])`` is ``5.0``
(:func:`test_trap_iterable_max_is_a_left_to_right_scan`) (B5).

``compute_hpwl`` and ``compute_bbox_area`` differ by **one operator** --
``width + height`` vs ``width * height`` -- over identical bounding-box code
(:func:`test_trap_hpwl_and_area_share_everything_but_one_operator`) (B7).

The net-class table is an **exact-match dict**, not a case-insensitive or
prefix lookup; 17 near-miss spellings fall through to ``SIGNAL``
(:func:`test_net_class_near_misses_fall_through`).
"""

from __future__ import annotations

import ast
import itertools
import math
import subprocess

import pytest

import tests.router_v6._net_ordering_py_oracle as ORACLE
from tests.router_v6._net_ordering_builders import (
    build_loops,
    build_netlist,
    build_order_netlist,
)
from tests.router_v6._net_ordering_cases import (
    BENCH_HPWL_DESIGNS,
    BENCH_ORDER_DESIGNS,
    HPWL_DESIGNS,
    LOOP_CASES,
    NET_CLASS_STRINGS,
    ORDER_DESIGNS,
    PRIORITY_KEYS,
    random_order_designs,
)
from tests.router_v6._pending_rust import missing_symbols, rust
from tests.router_v6._signature import sig

# ===========================================================================
# ADAPTER BLOCK -- the ONLY part of this file that knows the Rust arm exists.
# Phase B binds these; no assertion and no corpus row below changes.
# ===========================================================================

#: Migration target.  ``net_ordering`` is net-level router logic, not
#: geometry, so ``temper-rust-router`` (whose ``types.rs``/``loop_extractor``
#: already carry nets and loops) is the crate named here rather than
#: ``temper-geometry``, which is where cluster E points.  If Phase B picks
#: differently, this one constant moves.
_RUST_MODULE = "temper_rust_router"

REQUIRED_RUST_SYMBOLS: tuple[str, ...] = (
    "net_class_from_string_py",
    "net_loop_criticality_py",
    "net_compute_hpwl_py",
    "net_compute_bbox_area_py",
    "net_priority_key_py",
    "net_priority_lt_py",
    "order_nets_py",
)


def _rust(symbol: str):
    return rust(_RUST_MODULE, symbol)


# ===========================================================================
# END ADAPTER BLOCK
# ===========================================================================

_ORACLE_PIN_SHA = "15110feccc6ec9389f0777d3cff1ce9f81b11068"
_ORACLE_NAMES: tuple[str, ...] = (
    "NetClass",
    "NetPriority",
    "get_net_class_from_string",
    "get_loop_criticality",
    "compute_hpwl",
    "compute_bbox_area",
    "order_nets",
)


def _capture(fn):
    try:
        return fn()
    except BaseException as exc:  # noqa: BLE001 - error parity is the point
        return exc


def _assert_same(label: str, oracle_fn, symbol: str, rust_fn):
    """The oracle arm runs first, so a broken oracle fails with its own error."""
    a = _capture(oracle_fn)
    fn = _rust(symbol)  # RED until Phase B lands
    b = _capture(lambda: rust_fn(fn))
    assert sig(a) == sig(b), f"{label}: oracle={a!r} rust={b!r}"


def _priority(key: tuple):
    cp, lc, nc, pc, wl, name = key
    return ORACLE.NetPriority(
        config_priority=cp,
        loop_criticality=lc,
        net_class=ORACLE.NetClass(nc),
        pin_count=pc,
        estimated_wirelength=wl,
        name=name,
    )


# ---------------------------------------------------------------------------
# G1 evidence
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
    rel = "packages/temper-placer/src/temper_placer/router_v6/net_ordering.py"
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
        assert name in original, f"{name} missing from net_ordering.py at the pin"
        assert copied[name] == original[name], (
            f"net_ordering.py::{name} in the oracle is NOT verbatim -- "
            f"the pin is broken and the differential proves nothing"
        )


def test_rust_symbols_exist():
    """The Phase-B checklist.  RED until every kernel is ported."""
    missing = missing_symbols(_RUST_MODULE, REQUIRED_RUST_SYMBOLS)
    assert not missing, (
        f"{_RUST_MODULE} is missing {len(missing)} of {len(REQUIRED_RUST_SYMBOLS)} "
        f"net_ordering kernels: {missing}"
    )


def test_bench_corpus_is_covered_by_differential():
    """Every benchmark row is a row the differential already compares."""
    assert BENCH_HPWL_DESIGNS, "BENCH_HPWL_DESIGNS is empty -- vacuous containment"
    assert BENCH_ORDER_DESIGNS, "BENCH_ORDER_DESIGNS is empty -- vacuous containment"
    hpwl_labels = {d[0] for d in HPWL_DESIGNS}
    order_labels = {d[0] for d in ORDER_DESIGNS}
    assert {d[0] for d in BENCH_HPWL_DESIGNS} <= hpwl_labels
    assert {d[0] for d in BENCH_ORDER_DESIGNS} <= order_labels
    for d in BENCH_HPWL_DESIGNS:
        assert d in HPWL_DESIGNS
    for d in BENCH_ORDER_DESIGNS:
        assert d in ORDER_DESIGNS


# ---------------------------------------------------------------------------
# get_net_class_from_string
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("net_class_str", NET_CLASS_STRINGS)
def test_net_class_from_string_bit_exact(net_class_str):
    _assert_same(
        f"get_net_class_from_string({net_class_str!r})",
        lambda: ORACLE.get_net_class_from_string(net_class_str).value,
        "net_class_from_string_py",
        lambda fn: fn(net_class_str),
    )


def test_net_class_near_misses_fall_through():
    """The mapping is an exact-match dict, not a fuzzy lookup.

    Green today: this is a property of the *oracle*, so it is asserted here
    rather than deferred to the Rust arm.  A Rust mirror built on
    ``eq_ignore_ascii_case`` or ``starts_with`` fails every row below.
    """
    exact_keys = {
        "HighVoltage",
        "highvoltage",
        "HV",
        "Differential",
        "differential",
        "DiffPair",
        "Power",
        "power",
        "GateDrive",
        "gatedrive",
        "Gate",
        "GateDriveHV",
        "gatedrivehv",
        "GateDriveSELV",
        "gatedriveselv",
        "Signal",
        "signal",
        "FinePitch",
        "finepitch",
        "Ground",
        "ground",
        "GND",
    }
    near_misses = [s for s in NET_CLASS_STRINGS if s not in exact_keys]
    assert len(near_misses) >= 15, "the corpus lost its near-miss coverage"
    for s in near_misses:
        assert ORACLE.get_net_class_from_string(s) is ORACLE.NetClass.SIGNAL, (
            f"{s!r} unexpectedly resolved to a non-SIGNAL class"
        )
    # ... and every exact key resolves to something, so the test is not
    # vacuously satisfied by a constant-SIGNAL implementation
    resolved = {ORACLE.get_net_class_from_string(k) for k in exact_keys}
    assert len(resolved) == 6, f"expected all six NetClass members, got {resolved}"


# ---------------------------------------------------------------------------
# get_loop_criticality
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", LOOP_CASES, ids=lambda c: c[0])
def test_loop_criticality_bit_exact(case):
    label, loop_specs, net = case
    _assert_same(
        f"get_loop_criticality[{label}]",
        lambda: ORACLE.get_loop_criticality(net, build_loops(loop_specs)),
        "net_loop_criticality_py",
        lambda fn: fn(net, loop_specs),
    )


# ---------------------------------------------------------------------------
# compute_hpwl / compute_bbox_area
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", HPWL_DESIGNS, ids=lambda c: c[0])
def test_compute_hpwl_bit_exact(case):
    label, components, net = case
    _assert_same(
        f"compute_hpwl[{label}]",
        lambda: ORACLE.compute_hpwl(net, build_netlist(components)),
        "net_compute_hpwl_py",
        lambda fn: fn(net, components),
    )


@pytest.mark.parametrize("case", HPWL_DESIGNS, ids=lambda c: c[0])
def test_compute_bbox_area_bit_exact(case):
    label, components, net = case
    _assert_same(
        f"compute_bbox_area[{label}]",
        lambda: ORACLE.compute_bbox_area(net, build_netlist(components)),
        "net_compute_bbox_area_py",
        lambda fn: fn(net, components),
    )


# ---------------------------------------------------------------------------
# NetPriority
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("left,right", PRIORITY_KEYS)
def test_priority_key_bit_exact(left, right):
    _assert_same(
        f"NetPriority._key({left})",
        lambda: _priority(left)._key(),
        "net_priority_key_py",
        lambda fn: fn(left),
    )


@pytest.mark.parametrize("left,right", PRIORITY_KEYS)
def test_priority_ordering_bit_exact(left, right):
    def _oracle():
        a, b = _priority(left), _priority(right)
        # `<`, `==`, and the `@total_ordering`-derived `>`/`<=`/`>=`, plus
        # the NotImplemented path for a non-NetPriority operand
        return (
            a < b,
            b < a,
            a == b,
            a > b,
            a <= b,
            a >= b,
            a.__lt__("not a NetPriority") is NotImplemented,
            a.__eq__("not a NetPriority") is NotImplemented,
        )

    _assert_same(
        f"NetPriority ordering({left} vs {right})",
        _oracle,
        "net_priority_lt_py",
        lambda fn: fn(left, right),
    )


# ---------------------------------------------------------------------------
# order_nets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", ORDER_DESIGNS, ids=lambda c: c[0])
def test_order_nets_bit_exact(case):
    label, components, nets, loop_specs, config = case
    _assert_same(
        f"order_nets[{label}]",
        lambda: ORACLE.order_nets(
            build_order_netlist(components, nets), build_loops(loop_specs), config
        ),
        "order_nets_py",
        lambda fn: fn(components, nets, loop_specs, config),
    )


@pytest.mark.parametrize("seed", [101, 102, 103])
def test_order_nets_random_sweep(seed):
    for components, nets in random_order_designs(seed, 30):
        _assert_same(
            f"random order_nets seed={seed}",
            lambda c=components, n=nets: ORACLE.order_nets(
                build_order_netlist(c, n), build_loops([]), None
            ),
            "order_nets_py",
            lambda fn, c=components, n=nets: fn(c, n, [], None),
        )


# ---------------------------------------------------------------------------
# The determinism question, answered
# ---------------------------------------------------------------------------


def test_order_nets_is_permutation_invariant():
    """P: the output does not depend on the order of ``netlist.nets``.

    Green today.  This is the sharpest property the module has, and the
    survey/brief flagged it as the one that would expose a real determinism
    bug if it failed.  It does not fail: over all 24 permutations of a
    4-net design and all 6 of a 3-net design that ties on every key field
    except ``name``, there are **0 mismatches**.  Recorded here rather than
    only in prose so a future change that breaks it is caught.
    """
    for label in ("tie_broken_by_wirelength", "full_tie_name_only"):
        _lbl, components, nets, loop_specs, config = next(d for d in ORDER_DESIGNS if d[0] == label)
        loops = build_loops(loop_specs)
        base = ORACLE.order_nets(build_order_netlist(components, list(nets)), loops, config)
        mismatches = [
            perm
            for perm in itertools.permutations(nets)
            if ORACLE.order_nets(build_order_netlist(components, list(perm)), loops, config) != base
        ]
        assert not mismatches, (
            f"[{label}] order_nets is NOT permutation invariant: "
            f"{len(mismatches)} of {math.factorial(len(nets))} permutations differ. "
            f"That is a real determinism bug -- report it, do not weaken this test."
        )
        # non-vacuity: the design must actually have more than one net, and
        # the base ordering must not be the input order by accident
        assert len(nets) >= 3
        assert len(set(base)) == len(base)


def test_duplicate_net_names_are_a_stable_tie():
    """Two nets with the same name tie on all six key fields.

    ``list.sort`` is stable, so the output is the input order.  Green today;
    a Rust mirror using an unstable sort produces a different answer only
    when the payloads differ, which is exactly when it matters.
    """
    _lbl, components, nets, loop_specs, config = next(
        d for d in ORDER_DESIGNS if d[0] == "duplicate_names"
    )
    loops = build_loops(loop_specs)
    forward = ORACLE.order_nets(build_order_netlist(components, list(nets)), loops, config)
    reverse = ORACLE.order_nets(
        build_order_netlist(components, list(reversed(nets))), loops, config
    )
    assert forward == ["D", "D"]
    assert reverse == ["D", "D"]
    # the keys really are equal -- otherwise this would be testing nothing
    keys = {
        ORACLE.NetPriority(
            config_priority=5,
            loop_criticality=3,
            net_class=ORACLE.NetClass.SIGNAL,
            pin_count=len(pins),
            estimated_wirelength=ORACLE.compute_hpwl(name, build_netlist(components)),
            name=name,
        )._key()
        for (name, pins, _cls) in nets
    }
    assert len(keys) == 1, f"the duplicate-name case is no longer a full tie: {keys}"


def test_nan_wirelength_breaks_the_total_order():
    """A NaN HPWL makes ``order_nets`` order-dependent.  Pinned, not hidden.

    NaN is unordered against everything, so the 6-tuple comparison stops
    being a total order and timsort's output becomes a function of input
    order.  Measured: **4 distinct orderings** across the 6 permutations of a
    3-net design with one NaN pin coordinate.

    This is a real order-dependence and it is reported rather than papered
    over -- but note what it is *not*: it is gated on a NaN **input**, not on
    ``PYTHONHASHSEED`` or dict iteration, so it is not the class of bug
    PR #730 fixed.  A Rust mirror must reproduce CPython's timsort placement
    or reject NaN keys; it may not silently pick its own order.
    """
    _lbl, components, nets, loop_specs, config = next(
        d for d in ORDER_DESIGNS if d[0] == "nan_wirelength"
    )
    loops = build_loops(loop_specs)

    # the premise: at least one HPWL really is NaN
    hpwls = [ORACLE.compute_hpwl(name, build_netlist(components)) for (name, _p, _c) in nets]
    assert any(math.isnan(h) for h in hpwls), f"no NaN HPWL in the corpus case: {hpwls}"

    orderings = {
        tuple(ORACLE.order_nets(build_order_netlist(components, list(perm)), loops, config))
        for perm in itertools.permutations(nets)
    }
    assert len(orderings) > 1, (
        "the NaN case no longer produces order-dependence -- either the "
        "corpus changed or CPython's sort did; re-measure before editing"
    )
    assert len(orderings) == 4, (
        f"expected 4 distinct orderings over 6 permutations, measured "
        f"{len(orderings)}: {sorted(orderings)}"
    )


# ---------------------------------------------------------------------------
# Traps
# ---------------------------------------------------------------------------


def test_trap_iterable_max_is_a_left_to_right_scan():
    """``max(iterable)`` with a NaN is position-dependent (B5).

    ``compute_hpwl``/``compute_bbox_area`` use ``max(xs)``/``min(xs)`` over
    lists built in pin-iteration order, so *where* a NaN sits in the list
    changes the answer.  A Rust ``iter().fold(f64::NEG_INFINITY, f64::max)``
    discards NaN entirely and gets both cases wrong.
    """
    nan = float("nan")
    assert math.isnan(max([nan, 5.0, 1.0]))
    assert max([5.0, nan, 1.0]) == 5.0
    assert max([1.0, nan, 5.0]) == 5.0
    assert math.isnan(min([nan, 5.0]))
    assert min([5.0, nan]) == 5.0
    # ... and the module's own reduction inherits it
    nan_first = next(d for d in HPWL_DESIGNS if d[0] == "nan_first")
    nan_last = next(d for d in HPWL_DESIGNS if d[0] == "nan_last")
    a = ORACLE.compute_hpwl(nan_first[2], build_netlist(nan_first[1]))
    b = ORACLE.compute_hpwl(nan_last[2], build_netlist(nan_last[1]))
    assert math.isnan(a) or math.isnan(b), "neither NaN corpus case produced a NaN HPWL"
    assert sig(a) != sig(b), (
        "NaN-first and NaN-last produced the same HPWL -- the corpus stopped "
        "discriminating the position-dependence"
    )


def test_trap_hpwl_and_area_share_everything_but_one_operator():
    """``compute_hpwl`` is ``w + h``; ``compute_bbox_area`` is ``w * h``.

    Same bounding-box code, one operator apart.  A Rust mirror that shares an
    implementation and parameterizes the operator is fine; one that computes
    the area as ``hpwl * hpwl / 4`` or similar is not, and the corpus rows
    where ``w + h != w * h`` are what catch it.
    """
    differing: list[str] = []
    coincide: list[str] = []
    for label, components, net in HPWL_DESIGNS:
        netlist = build_netlist(components)
        hpwl = ORACLE.compute_hpwl(net, netlist)
        area = ORACLE.compute_bbox_area(net, netlist)
        if math.isnan(hpwl) or math.isnan(area):
            continue
        (differing if hpwl != area else coincide).append(label)
    assert len(differing) >= 5, (
        f"only {len(differing)} corpus rows separate hpwl from area -- the "
        f"corpus no longer discriminates the operator: {differing}"
    )
    # Rows where they coincide (zero-span boxes, absent nets) are present on
    # purpose: an implementation returning the area for both would pass THOSE
    # rows, which is why the count above is what the assertion rests on.
    assert coincide, "expected at least the zero-span rows to coincide"
