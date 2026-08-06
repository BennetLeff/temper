"""Self-test for the R1a comparator (``tests/router_v6/_signature.py``).

A differential suite is only as strong as the comparator it uses.  This file
proves the comparator actually *distinguishes* the pairs the Wave-4 gate
requires: f32 vs f64, int vs float, ``True`` vs ``1``, ``0.0`` vs ``-0.0``,
and a 1-ulp difference.  Every assertion below is a pair the naive ``==``
comparison would call equal (or would call unequal for the wrong reason);
if any of them starts passing as "equal", the differential suites that
depend on this module have gone vacuous.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from tests.router_v6._signature import sig, sigs_equal


def test_distinguishes_f32_from_f64_arrays():
    a = np.array([1.0, 2.0], dtype=np.float32)
    b = np.array([1.0, 2.0], dtype=np.float64)
    assert (a == b).all()  # naive comparison says "equal"
    assert not sigs_equal(a, b)


def test_distinguishes_f32_from_f64_scalars():
    a = np.float32(0.25)
    b = np.float64(0.25)
    assert a == b  # naive comparison says "equal"
    assert not sigs_equal(a, b)


def test_distinguishes_numpy_float64_from_builtin_float():
    a = np.float64(0.25)
    b = 0.25
    assert a == b  # naive comparison says "equal"
    assert not sigs_equal(a, b)


def test_distinguishes_int_from_float():
    assert 1 == 1.0  # noqa: PLR0133 - the point of the test
    assert not sigs_equal(1, 1.0)


def test_distinguishes_true_from_one():
    assert True == 1  # noqa: E712 - the point of the test
    assert not sigs_equal(True, 1)
    assert not sigs_equal(np.bool_(True), 1)


def test_distinguishes_positive_and_negative_zero():
    assert 0.0 == -0.0
    assert not sigs_equal(0.0, -0.0)
    # ... and inside containers / arrays / dataclasses
    assert not sigs_equal((0.0,), (-0.0,))
    assert not sigs_equal(np.array([0.0]), np.array([-0.0]))


def test_distinguishes_one_ulp():
    x = 1.0
    y = math.nextafter(1.0, 2.0)
    assert x != y
    assert abs(x - y) < 1e-15  # any tolerance-based check would call these equal
    assert not sigs_equal(x, y)


def test_distinguishes_tuple_from_list():
    assert not sigs_equal((1.0, 2.0), [1.0, 2.0])


def test_distinguishes_shape():
    assert not sigs_equal(np.array([[1.0, 2.0]]), np.array([1.0, 2.0]))


def test_nan_is_self_equal_under_sig():
    # `nan != nan`, so a raw `==` differential silently passes on any pair
    # of NaN results.  The signature makes NaN compare equal to NaN (so a
    # genuine NaN-vs-NaN match is asserted, not skipped) while still
    # separating NaN from every non-NaN value.
    assert float("nan") != float("nan")
    assert sigs_equal(float("nan"), float("nan"))
    assert not sigs_equal(float("nan"), float("inf"))
    assert not sigs_equal(float("inf"), float("-inf"))


def test_identical_values_are_equal():
    assert sigs_equal(1.5, 1.5)
    assert sigs_equal(np.array([1.0, 2.0]), np.array([1.0, 2.0]))
    assert sigs_equal((1, "a", None, [2.0]), (1, "a", None, [2.0]))


def test_unknown_type_raises_rather_than_degrading():
    class Weird:
        pass

    with pytest.raises(TypeError):
        sig(Weird())


def test_dict_order_is_part_of_the_signature():
    # Sorting keys to "make the arms agree" would be an undetectable
    # behaviour change; the comparator refuses to do it.
    assert {"a": 1, "b": 2} == {"b": 2, "a": 1}
    assert not sigs_equal({"a": 1, "b": 2}, {"b": 2, "a": 1})
