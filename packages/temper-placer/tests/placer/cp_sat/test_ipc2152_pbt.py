"""Property-based tests for the Rust IPC-2152 ampacity model (Wave 2).

Five invariants (per the migration roadmap's R6 gate):

1. Forward capacity is monotonic non-decreasing in trace width
2. Forward capacity is monotonic in temperature rise
3. Internal layers never carry more than external (0.65 derate)
4. Minimum width is monotonic non-decreasing in current
5. Roundtrip: the minimum width for a current carries at least that
   current within one rounding step

The properties exercise the wrapper (``temper_placer.placer.cp_sat.
gates``), the consumer surface the StackupGate sees.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.placer.cp_sat.gates import _ipc2152_forward, _min_width_ipc2152

MAX_EXAMPLES = 150

_width = st.floats(min_value=0.01, max_value=50.0, allow_nan=False, allow_infinity=False)
_current = st.floats(min_value=0.1, max_value=40.0, allow_nan=False, allow_infinity=False)
_oz = st.floats(min_value=0.5, max_value=4.0, allow_nan=False, allow_infinity=False)
_rise = st.floats(min_value=5.0, max_value=60.0, allow_nan=False, allow_infinity=False)


@given(_width, _width, _oz, _rise, st.booleans())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_forward_monotonic_in_width(w1: float, w2: float, oz: float, rise: float, internal: bool):
    lo, hi = min(w1, w2), max(w1, w2)
    assert _ipc2152_forward(lo, oz, rise, internal) <= _ipc2152_forward(hi, oz, rise, internal)


@given(_width, _oz, _rise, _rise, st.booleans())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_forward_monotonic_in_rise(w: float, oz: float, r1: float, r2: float, internal: bool):
    lo, hi = min(r1, r2), max(r1, r2)
    assert _ipc2152_forward(w, oz, lo, internal) <= _ipc2152_forward(w, oz, hi, internal)


@given(_width, _oz, _rise)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_internal_never_exceeds_external(w: float, oz: float, rise: float):
    ext = _ipc2152_forward(w, oz, rise, False)
    internal = _ipc2152_forward(w, oz, rise, True)
    assert internal <= ext
    assert internal == ext * 0.65


@given(_current, _current, _oz, _rise, st.booleans())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_min_width_monotonic_in_current(c1: float, c2: float, oz: float, rise: float, internal: bool):
    lo, hi = min(c1, c2), max(c1, c2)
    assert _min_width_ipc2152(lo, oz, rise, internal) <= _min_width_ipc2152(hi, oz, rise, internal)


@given(_current, _oz, _rise, st.booleans())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_roundtrip_within_rounding_step(current: float, oz: float, rise: float, internal: bool):
    w = _min_width_ipc2152(current, oz, rise, internal)
    cap = _ipc2152_forward(w, oz, rise, internal)
    if w == 50.0:
        # Root at/above the bisection search bound: the reference pins
        # hi=50 and returns it, correctly flagging an unroutable-width
        # violation.
        assert cap < current
        return
    # The 3-decimal rounding can undershoot by up to one 0.0005 mm step;
    # capacity scales ~w^0.725, so the relative undershoot bound scales
    # with 1/w (6.6% at w=0.0055, the smallest in-range root).
    rel_step = 0.725 * 0.0005 / w
    assert cap >= current * (1.0 - rel_step - 1e-9), f"cap {cap} vs current {current} at w {w}"
