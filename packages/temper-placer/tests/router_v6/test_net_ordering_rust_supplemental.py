"""Supplemental pins for the `net_ordering` Rust arm.

This file exists because of specific **mutation survivors**: mutants of the
Rust kernel that ``test_net_ordering_rust_differential.py`` could not kill,
because the pinned corpus does not reach the behaviour they change.  The
differential and its corpus are the pinned reference and are NOT edited to
close a gap; the gap is closed here instead.

Nothing in this file weakens or restates a differential assertion -- every
test below is about an input shape the corpus does not contain.

Survivor closed here
--------------------
``M09`` -- the ``< 2``-pin guard relaxed to ``< 1``.
  Equivalent on the corpus (a one-pin box gives ``x - x == 0.0``), but NOT
  equivalent when that single coordinate is NaN: ``NaN - NaN`` is NaN, while
  the guard returns ``0.0``.  The corpus has no single-pin NaN row.
"""

from __future__ import annotations

import pytest

import tests.router_v6._net_ordering_py_oracle as ORACLE
from tests.router_v6._net_ordering_builders import build_netlist
from tests.router_v6._pending_rust import rust
from tests.router_v6._signature import sig

_RUST_MODULE = "temper_rust_router"

NAN = float("nan")


def _rust(symbol: str):
    return rust(_RUST_MODULE, symbol)


# ---------------------------------------------------------------------------
# M09: the <2-pin guard, on a NaN single pin
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,components",
    [
        ("single_nan_pin", [("U1", (NAN, NAN), 0, [("1", (0.0, 0.0), "N1")])]),
        ("single_inf_pin", [("U1", (float("inf"), 0.0), 0, [("1", (0.0, 0.0), "N1")])]),
        ("zero_pins", [("U1", (NAN, NAN), 0, [("1", (0.0, 0.0), "OTHER")])]),
    ],
)
def test_short_net_guard_returns_zero_not_nan(label, components):
    """Fewer than two pins returns ``0.0`` before any arithmetic happens.

    A guard relaxed to ``< 1`` would compute ``NaN - NaN`` here and answer
    NaN, which no corpus row can see.
    """
    for name, fn in (
        ("compute_hpwl", "net_compute_hpwl_py"),
        ("compute_bbox_area", "net_compute_bbox_area_py"),
    ):
        a = getattr(ORACLE, name)("N1", build_netlist(components))
        b = _rust(fn)("N1", components)
        assert sig(a) == sig(b), f"[{label}] {name}: oracle={a!r} rust={b!r}"
        assert sig(a) == sig(0.0), f"[{label}] {name}: premise -- the guard should return 0.0"


# ---------------------------------------------------------------------------
# Public API / value plumbing
# ---------------------------------------------------------------------------


def test_rust_arm_returns_only_builtin_types():
    """The Rust arm hands back plain ``list``/``float``/``str``/``int``."""
    order = _rust("order_nets_py")(
        [("U0", (0.0, 0.0), 0, [("1", (0.0, 0.0), "A"), ("2", (1.0, 0.0), "A")])],
        [("A", [("U0", "1"), ("U0", "2")], None)],
        [],
        None,
    )
    assert type(order) is list
    assert all(type(x) is str for x in order)

    hp = _rust("net_compute_hpwl_py")(
        "A", [("U0", (0.0, 0.0), 0, [("1", (0.0, 0.0), "A"), ("2", (1.0, 0.0), "A")])]
    )
    assert type(hp) is float

    cls = _rust("net_class_from_string_py")("HighVoltage")
    assert type(cls) is int


def test_production_module_is_untouched_by_this_migration():
    """Phase B adds a Rust arm; it does not yet re-point the Python module.

    ``router_v6/net_ordering.py`` must still be the pinned implementation --
    if a later change delegates it to Rust, this test is the reminder that the
    oracle pin and this assertion both have to move deliberately.
    """
    import temper_placer.router_v6.net_ordering as prod

    assert not hasattr(prod, "temper_rust_router")
    assert prod.get_net_class_from_string("HighVoltage") is prod.NetClass.HIGH_VOLTAGE
    # and the production module still agrees with the oracle it was pinned from
    components = [
        ("U1", (1.0, 2.0), 0, [("1", (0.0, 0.0), "N1")]),
        ("U2", (11.0, 7.0), 0, [("1", (0.0, 0.0), "N1")]),
    ]
    assert sig(prod.compute_hpwl("N1", build_netlist(components))) == sig(
        ORACLE.compute_hpwl("N1", build_netlist(components))
    )


# ---------------------------------------------------------------------------
# Migration-narrowing regression: fractional `initial_rotation_quadrant`
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rotation", [0.5, 1.5, -0.5, 2.25])
def test_fractional_rotation_agrees_with_the_oracle(rotation):
    """A non-integral rotation must produce an angle, not a ``TypeError``.

    Found by ``scripts/check_migration_narrowing.py`` (Check B): the Rust
    kernel bound ``rotation`` as ``Option<i64>`` while the Python path does
    ``float(comp.initial_rotation_quadrant) * math.pi / 2.0``. pyo3 REJECTS a
    non-integral float on an ``i64`` extract rather than truncating, so this
    input raised ``TypeError`` on the Rust arm and returned an angle on the
    Python arm -- the exact shape of the already-fixed ``escape_via.rs``
    defect, which the corpus cannot reach because every pinned row uses an
    integer rotation index.

    Asserting agreement with the oracle rather than just "does not raise" is
    deliberate: widening the binding to ``f64`` would also be satisfied by a
    kernel that silently truncated to the integer index, and that would be a
    different, quieter version of the same bug.
    """
    components = [
        ("U0", (0.0, 0.0), rotation, [("1", (1.0, 0.5), "A"), ("2", (2.0, 0.5), "A")])
    ]

    rust_hpwl = _rust("net_compute_hpwl_py")("A", components)
    oracle_hpwl = ORACLE.compute_hpwl("A", build_netlist(components))

    assert type(rust_hpwl) is float
    assert sig(rust_hpwl) == sig(oracle_hpwl)


def test_integer_rotation_is_unchanged_by_the_widening(): 
    """The widening must not perturb the integer-index path it inherited.

    ``Option<i64>`` -> ``Option<f64>`` changes the multiply from
    ``(r as f64) * PI / 2.0`` to ``r * PI / 2.0``. For an integral ``r`` the
    two are the same value, and this pins that rather than assuming it --
    every pinned corpus row depends on it.
    """
    for rotation in (0, 1, 2, 3, 5, -1):
        components = [
            ("U0", (0.0, 0.0), rotation, [("1", (1.0, 0.5), "A"), ("2", (2.0, 0.5), "A")])
        ]
        rust_hpwl = _rust("net_compute_hpwl_py")("A", components)
        oracle_hpwl = ORACLE.compute_hpwl("A", build_netlist(components))
        assert sig(rust_hpwl) == sig(oracle_hpwl), f"diverged at rotation={rotation}"
