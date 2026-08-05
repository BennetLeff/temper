"""Self-test for the Wave 4 Phase 5 comparator (``_heuristic_canon.canon``).

A differential is only worth what its comparator can *see*. #724's
differential was green across 941 assertions while ``pickle``/``deepcopy``
were broken, and a comparator that folds ``True`` into ``1`` or ``float32``
into ``float64`` produces exactly that kind of vacuous green.

Every assertion below is of the form "these two values are DIFFERENT, and
the comparator says so" for the specific confusions a Rust port introduces:

* ``float32`` vs ``float64`` (numpy dtype widening)
* ``bool`` array vs ``uint8`` array (the keepout mask's dtype)
* ``int`` vs ``float`` (a dataclass field that did no coercion)
* ``True`` vs ``1`` (bool is an int subclass)
* ``0.0`` vs ``-0.0`` (``==`` says equal; the bit patterns are not)
* 1 ULP (no tolerance, ever)
* ``np.float64`` scalar vs Python ``float`` (a leaked numpy scalar)
* list order (the hash-order drift this phase is built around)
* dict insertion order
* exception type and message
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from tests.heuristics._heuristic_canon import canon, canon_call


def test_float32_and_float64_arrays_differ():
    a = np.array([1.0, 2.0], dtype=np.float32)
    b = np.array([1.0, 2.0], dtype=np.float64)
    assert (a == b).all(), "precondition: numpy == cannot see the dtype"
    assert canon(a) != canon(b)


def test_bool_and_uint8_arrays_differ():
    # `create_keepout_mask` returns `dtype=np.bool_`. A Rust port that
    # produced uint8 would compare equal elementwise and be wrong.
    a = np.array([[True, False]], dtype=np.bool_)
    b = np.array([[1, 0]], dtype=np.uint8)
    assert (a == b).all(), "precondition: numpy == cannot see the dtype"
    assert canon(a) != canon(b)


def test_array_shape_is_carried():
    a = np.array([True, False, True, False], dtype=np.bool_)
    b = a.reshape(2, 2)
    assert a.tobytes() == b.tobytes(), "precondition: same bytes"
    assert canon(a) != canon(b)


def test_int_and_float_differ():
    assert 1 == 1.0, "precondition: Python == cannot see the type"
    assert canon(1) != canon(1.0)


def test_true_and_one_differ():
    assert True == 1, "precondition: bool is an int subclass"  # noqa: E712
    assert canon(True) != canon(1)
    assert canon(False) != canon(0)


def test_positive_and_negative_zero_differ():
    assert 0.0 == -0.0, "precondition: == says equal"
    assert canon(0.0) != canon(-0.0)


def test_one_ulp_differs():
    x = 0.2513272
    y = math.nextafter(x, math.inf)
    assert x != y
    assert abs(x - y) < 1e-16, "precondition: 1 ULP apart"
    assert canon(x) != canon(y)


def test_one_ulp_differs_on_a_measured_real_divergence():
    # Not synthetic: this is the exact numpy-vs-Rust `sin` divergence measured
    # for this phase at angle 2*3.14159*1/25, which is why the port calls
    # numpy's `sin` rather than Rust's `f64::sin`. The comparator must be able
    # to see it, or the decision would be untestable.
    np_val = float(np.sin(0.2513272))
    rust_val = math.nextafter(np_val, math.inf)
    assert canon(np_val) != canon(rust_val)


def test_numpy_scalar_and_python_float_differ():
    # `float(np.cos(a))` vs a leaked `np.float64`.
    assert np.float64(0.5) == 0.5, "precondition: == says equal"
    assert canon(np.float64(0.5)) != canon(0.5)


def test_nan_normalises_but_is_not_confused_with_a_number():
    assert canon(float("nan")) == canon(float("nan"))
    assert canon(float("nan")) != canon(0.0)
    assert canon(float("nan")) != canon(float("inf"))


def test_list_order_is_significant():
    # The whole point of this phase's order discipline.
    assert canon(["A", "B"]) != canon(["B", "A"])
    assert sorted(["A", "B"]) == sorted(["B", "A"]), "precondition: same contents"


def test_list_and_tuple_differ():
    assert canon(["A"]) != canon(("A",))


def test_dict_insertion_order_is_significant():
    a = {"x": 1, "y": 2}
    b = {"y": 2, "x": 1}
    assert a == b, "precondition: dict == ignores order"
    assert canon(a) != canon(b)


def test_set_contents_compare_order_insensitively():
    # Sets are the ONE place order is folded away -- deliberately, because a
    # public `set` return has no CPython order guarantee to begin with.
    assert canon({"A", "B"}) == canon({"B", "A"})
    assert canon({"A", "B"}) != canon({"A", "C"})
    assert canon({"A"}) != canon(frozenset({"A"}))


def test_str_and_bytes_differ():
    assert canon("A") != canon(b"A")


def test_none_is_distinguished_from_falsy_values():
    assert canon(None) != canon(False)
    assert canon(None) != canon(0)
    assert canon(None) != canon("")


def test_canon_call_sees_exception_type_and_message():
    def raises_value():
        raise ValueError("boom")

    def raises_type():
        raise TypeError("boom")

    def raises_other_message():
        raise ValueError("bang")

    assert canon_call(raises_value) != canon_call(raises_type)
    assert canon_call(raises_value) != canon_call(raises_other_message)
    assert canon_call(raises_value) == canon_call(raises_value)


def test_canon_call_distinguishes_raise_from_return():
    def returns_none():
        return None

    def raises():
        raise ValueError("x")

    assert canon_call(returns_none) != canon_call(raises)


def test_canon_refuses_unknown_types_rather_than_silently_passing():
    class Opaque:
        pass

    with pytest.raises(TypeError):
        canon(Opaque())
