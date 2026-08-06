"""Anti-vacuity proof for the R1a comparator itself.

A differential is only as strong as the comparator behind it. Every
assertion here shows the comparator *distinguishes* a pair that a naive
``==`` would call equal -- so a green differential in
``test_core_contracts_differential.py`` is evidence, not an artefact of a
comparator that says yes to everything.
"""

from __future__ import annotations

import numpy as np
import pytest

from tests.wave4_phase2._sig import assert_same, signature


def _distinct(a, b) -> None:
    assert signature(a) != signature(b), (
        f"comparator failed to distinguish {a!r} from {b!r}: both -> {signature(a)!r}"
    )


def test_distinguishes_f32_from_f64():
    _distinct(np.float32(0.1), np.float64(0.1))
    _distinct(np.zeros(3, dtype=np.float32), np.zeros(3, dtype=np.float64))
    # ... which `==` does not.
    assert np.float32(0.1) == np.float32(np.float64(0.1))


def test_distinguishes_int_from_float():
    _distinct(1, 1.0)
    _distinct(np.int64(1), np.float64(1.0))
    assert 1 == 1.0


def test_distinguishes_true_from_one():
    _distinct(True, 1)
    _distinct(np.bool_(True), np.int64(1))
    assert True == 1  # noqa: E712


def test_distinguishes_positive_from_negative_zero():
    _distinct(0.0, -0.0)
    _distinct(np.array([0.0]), np.array([-0.0]))
    assert 0.0 == -0.0


def test_distinguishes_one_ulp():
    x = 1.0
    y = np.nextafter(x, 2.0)
    assert x != y
    _distinct(x, y)
    # And the same at a magnitude where a naive relative tolerance would
    # certainly pass.
    big = 1e300
    _distinct(big, np.nextafter(big, np.inf))


def test_distinguishes_nan_payload_free_but_type_carrying():
    # NaN != NaN, so `==` cannot even assert equality; the signature can.
    assert_same(float("nan"), float("nan"))
    _distinct(float("nan"), float("inf"))


def test_distinguishes_shape_and_dtype_before_values():
    _distinct(np.zeros((2, 2)), np.zeros((4,)))
    _distinct(np.zeros((0, 0)), np.zeros((0,)))
    # The empty-adjacency contract: (0, 0) float64, not float32.
    _distinct(
        np.array([]).reshape(0, 0),
        np.zeros((0, 0), dtype=np.float32),
    )


def test_distinguishes_tuple_from_list():
    _distinct((1.0, 2.0), [1.0, 2.0])


def test_distinguishes_exception_type_and_message():
    _distinct(ValueError("a"), TypeError("a"))
    _distinct(ValueError("a"), ValueError("b"))


def test_rejects_an_unhandled_leaf_rather_than_passing_it():
    class Opaque:
        pass

    with pytest.raises(AssertionError, match="unhandled leaf type"):
        signature(Opaque())
