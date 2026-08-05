"""Supplemental pins for the `net_ordering` Rust arm.

This file exists because of specific **mutation survivors**: mutants of the
Rust kernel that ``test_net_ordering_rust_differential.py`` could not kill,
because the pinned corpus does not reach the behaviour they change.  The
differential and its corpus are the pinned reference and are NOT edited to
close a gap; the gap is closed here instead.

Nothing in this file weakens or restates a differential assertion -- every
test below is about an input shape the corpus does not contain.

Survivors closed here
---------------------
``M24`` -- ``parse_key_tuple``'s ``bool``/``int`` distinction erased.
  ``PRIORITY_KEYS`` carries the ``True`` config-priority row, but
  ``test_priority_key_bit_exact`` only ever passes the pair's **left**
  element to ``net_priority_key_py`` and ``True`` sits on the right.  So the
  key builder is never called with a ``bool`` and the mutant survives 145/145.
  ``True == 1`` in Python, and only the concrete type separates them.

``M09`` -- the ``< 2``-pin guard relaxed to ``< 1``.
  Equivalent on the corpus (a one-pin box gives ``x - x == 0.0``), but NOT
  equivalent when that single coordinate is NaN: ``NaN - NaN`` is NaN, while
  the guard returns ``0.0``.  The corpus has no single-pin NaN row.
"""

from __future__ import annotations

import copy
import pickle

import pytest

import tests.router_v6._net_ordering_py_oracle as ORACLE
from tests.router_v6._net_ordering_builders import build_netlist
from tests.router_v6._pending_rust import rust
from tests.router_v6._signature import sig

_RUST_MODULE = "temper_rust_router"

NAN = float("nan")


def _rust(symbol: str):
    return rust(_RUST_MODULE, symbol)


def _priority_key(key: tuple) -> tuple:
    cp, lc, nc, pc, wl, name = key
    return ORACLE.NetPriority(
        config_priority=cp,
        loop_criticality=lc,
        net_class=ORACLE.NetClass(nc),
        pin_count=pc,
        estimated_wirelength=wl,
        name=name,
    )._key()


# ---------------------------------------------------------------------------
# M24: bool is not int, even though True == 1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        (True, 3, 4, 2, 1.0, "N"),
        (False, 3, 4, 2, 1.0, "N"),
        (1, 3, 4, 2, 1.0, "N"),
        (0, 3, 4, 2, 1.0, "N"),
        (True, 3, 0, 2, -0.0, "é"),
    ],
)
def test_priority_key_preserves_bool_vs_int(key):
    """A ``bool`` config priority must come back a ``bool``, not an ``int``.

    ``sig()`` is what separates them; ``==`` cannot, because ``True == 1``.
    """
    a = _priority_key(key)
    b = _rust("net_priority_key_py")(key)
    assert sig(a) == sig(b), f"oracle={a!r} rust={b!r}"
    # ... and the discrimination is real, not accidental: on the bool rows the
    # int-valued twin must compare EQUAL and sign DIFFERENTLY, or the
    # assertion above is satisfied by any implementation at all.
    if isinstance(key[0], bool):
        int_key = (int(key[0]), *key[1:])
        assert _priority_key(key) == _priority_key(int_key), "premise: they compare equal"
        assert sig(_priority_key(key)) != sig(_priority_key(int_key)), (
            "premise: sig() separates bool from int -- if this fails the test above is vacuous"
        )


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
    """The Rust arm hands back plain ``list``/``tuple``/``float``/``str``/``int``.

    No pyclass is introduced, so nothing stored on another object can change
    identity, and ``pickle``/``deepcopy`` behaviour is the builtins'.
    """
    key = _rust("net_priority_key_py")((5, 3, 4, 2, 1.0, "N"))
    assert type(key) is tuple
    assert [type(x).__name__ for x in key] == ["int", "int", "int", "int", "float", "str"]

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


@pytest.mark.parametrize(
    "value",
    [
        (5, 3, 4, 2, 1.0, "N"),
        (True, 3, 4, 2, -0.0, "é"),
    ],
)
def test_rust_results_round_trip_pickle_and_deepcopy(value):
    """Explicit, because a sibling slice's differential was green across 941
    assertions while both arms were broken: `==` on the round-tripped value is
    not enough, the signature has to survive too."""
    key = _rust("net_priority_key_py")(value)
    assert sig(pickle.loads(pickle.dumps(key))) == sig(key)
    assert sig(copy.deepcopy(key)) == sig(key)


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
