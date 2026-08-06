"""Anti-vacuity self-test for the R1a comparator in ``_pclsig.py``.

A differential is only as strong as its comparator. If ``signature()``
collapsed ``True`` into ``1``, or f32 into f64, then every differential
built on it would pass vacuously. These tests prove the comparator
*distinguishes* each class of near-miss the Wave-4 program has actually
been bitten by, and that it *identifies* values that really are the same.

Required discriminations (from the Wave-4 R1a gate):
  f32 vs f64, int vs float, True vs 1, 0.0 vs -0.0, and 1 ulp.
"""

from __future__ import annotations

import enum
import math

import numpy as np
import pytest
from tests.pcl._pclsig import assert_same, call_signature, signature

# ---------------------------------------------------------------------------
# The five mandated discriminations.
# ---------------------------------------------------------------------------


def test_discriminates_f32_from_f64():
    """np.float32(0.1) and np.float64(0.1) must not share a signature."""
    a = np.float32(0.1)
    b = np.float64(0.1)
    assert signature(a) != signature(b)
    # ...and the dtype is what makes it legible, not just the widened value.
    assert "float32" in repr(signature(a))
    assert "float64" in repr(signature(b))
    # Even at a value both dtypes represent exactly, the dtype still splits them.
    assert signature(np.float32(0.5)) != signature(np.float64(0.5))


def test_discriminates_int_from_float():
    """1 and 1.0 are numerically equal but are different concrete types."""
    assert 1 == 1.0  # the trap: bare == cannot tell these apart
    assert signature(1) != signature(1.0)
    assert signature(0) != signature(0.0)
    # And inside containers, recursively.
    assert signature([1, 2]) != signature([1.0, 2.0])
    assert signature({"a": 3}) != signature({"a": 3.0})


def test_discriminates_true_from_one():
    """bool is a subclass of int; True == 1 must still fail the comparator."""
    assert True == 1  # noqa: E712 - the trap being defended against
    assert signature(True) != signature(1)
    assert signature(False) != signature(0)
    assert signature(True) != signature(1.0)
    assert signature([True, False]) != signature([1, 0])


def test_discriminates_positive_from_negative_zero():
    """0.0 == -0.0 in IEEE-754; float.hex() keeps the sign bit."""
    assert 0.0 == -0.0
    assert signature(0.0) != signature(-0.0)
    assert signature(0.0) == ("float", "0x0.0p+0")
    assert signature(-0.0) == ("float", "-0x0.0p+0")


def test_discriminates_one_ulp():
    """A single ulp of difference must fail -- there is no tolerance."""
    x = 1.0
    y = math.nextafter(1.0, math.inf)
    assert y != x
    assert abs(y - x) < 1e-15  # any tolerance-based comparator would pass
    assert signature(x) != signature(y)
    # Also at a magnitude where the absolute gap is enormous...
    big = 1e300
    assert signature(big) != signature(math.nextafter(big, math.inf))
    # ...and at a magnitude where it is subnormal-small.
    tiny = 5e-324
    assert signature(tiny) != signature(math.nextafter(tiny, math.inf))


# ---------------------------------------------------------------------------
# NaN: reflexive under the comparator even though NaN != NaN, and the
# *payload sign* is kept (the program has been bitten by -nan vs nan).
# ---------------------------------------------------------------------------


def test_nan_is_reflexive_and_signed():
    nan = float("nan")
    assert nan != nan  # the trap
    assert signature(nan) == signature(float("nan"))
    assert signature(nan) != signature(-nan)
    assert signature(float("inf")) != signature(float("-inf"))
    assert signature(float("inf")) != signature(1e308)


# ---------------------------------------------------------------------------
# Enum leaves: compared by owning class + member name, not by value.
# ---------------------------------------------------------------------------


class _AlphaEnum(enum.Enum):
    X = "x"


class _BetaEnum(enum.Enum):
    X = "x"


def test_discriminates_enum_classes_sharing_names_and_values():
    """Two enums with identical member names and values are not the same type."""
    assert _AlphaEnum.X.value == _BetaEnum.X.value
    assert signature(_AlphaEnum.X) != signature(_BetaEnum.X)


def test_discriminates_enum_member_from_its_value():
    assert signature(_AlphaEnum.X) != signature("x")


# ---------------------------------------------------------------------------
# Containers: type-carrying, and order-carrying where order is observable.
# ---------------------------------------------------------------------------


def test_discriminates_list_from_tuple():
    assert signature([1, 2]) != signature((1, 2))


def test_discriminates_set_from_frozenset():
    assert signature({1, 2}) != signature(frozenset({1, 2}))


def test_sets_compare_by_content_not_order():
    """Set iteration order is not observable, so it must not affect the token."""
    a = {"alpha", "beta", "gamma", "delta"}
    b = {"delta", "gamma", "beta", "alpha"}
    assert signature(a) == signature(b)
    assert signature(a) != signature({"alpha", "beta", "gamma"})


def test_dicts_compare_by_order_because_dict_order_is_observable():
    """CPython dicts are insertion-ordered and callers iterate them."""
    assert signature({"a": 1, "b": 2}) != signature({"b": 2, "a": 1})
    assert signature({"a": 1, "b": 2}) == signature({"a": 1, "b": 2})


def test_discriminates_nested_type_change_deep_in_a_structure():
    """A single int->float swap five levels down still fails."""
    deep_a = {
        "k": [
            (
                1,
                {"j": frozenset({2})},
            )
        ]
    }
    deep_b = {
        "k": [
            (
                1,
                {"j": frozenset({2.0})},
            )
        ]
    }
    assert signature(deep_a) != signature(deep_b)


# ---------------------------------------------------------------------------
# Identity direction: values that really are equal must compare equal, or the
# differential would fail for the wrong reason.
# ---------------------------------------------------------------------------


def test_identical_values_compare_equal():
    assert_same(1.5, 1.5)
    assert_same([1, "a", None, (2.5,)], [1, "a", None, (2.5,)])
    assert_same({"x": frozenset({"p", "q"})}, {"x": frozenset({"q", "p"})})
    assert_same(_AlphaEnum.X, _AlphaEnum.X)


def test_unhandled_leaf_type_is_an_error_not_a_silent_pass():
    """An unmodelled type must raise, never compare-equal-by-accident."""

    class Opaque:
        pass

    with pytest.raises(AssertionError, match="unhandled leaf type"):
        signature(Opaque())


# ---------------------------------------------------------------------------
# call_signature: exceptions are part of the migrated API surface.
# ---------------------------------------------------------------------------


class _ErrA(Exception):
    pass


class _ErrB(Exception):
    pass


def test_call_signature_distinguishes_exception_class():
    def raise_a():
        raise _ErrA("boom")

    def raise_b():
        raise _ErrB("boom")

    assert call_signature(raise_a) != call_signature(raise_b)


def test_call_signature_distinguishes_exception_message():
    def raise_1():
        raise _ErrA("boom 1")

    def raise_2():
        raise _ErrA("boom 2")

    assert call_signature(raise_1) != call_signature(raise_2)


def test_call_signature_distinguishes_raise_from_return():
    def raiser():
        raise _ErrA("x")

    assert call_signature(raiser) != call_signature(lambda: "x")


def test_call_signature_matches_for_identical_behaviour():
    def a():
        raise _ErrA("same")

    def b():
        raise _ErrA("same")

    assert call_signature(a) == call_signature(b)
