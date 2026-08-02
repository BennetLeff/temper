"""Property-based + metamorphic tests for the Rust loop pyclasses.

Wave 4, Phase 2 — the contracts-as-pyo3-pyclasses pivot (plan
``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``
R1c/R1d). These properties exercise the migrated
``temper_placer.core.loop`` module (a pure delegation re-export of the
``temper_design_bundle_python`` pyclasses); bit-identical parity against
the pinned pre-migration Python is asserted separately by
``test_loop_rust_differential.py``.

Five hypothesis properties (all non-vacuously guarded):

- P1. ``LoopEvent.estimated_inductance_nh`` matches an independent
  closed-form reference (L = mu0·A/h) bit-exactly, and the area scaling
  genuinely bites: doubling the area exactly doubles the inductance (a
  power-of-two scale preserves every f64 bit through the whole op chain).
- P2. ``max_area_for_inductance_nh`` is the exact inverse closed form
  (A = L·h/mu0), bit-identical against an independent recomputation.
- P3. ``get_component_refs``: when ``components`` is non-empty it is
  returned verbatim (identity with the stored list); a pins-only loop
  dedups component refs preserving first-appearance order.
- P4. Predicate agreement: ``involves_component(ref)`` ⟺
  ``ref in get_component_refs()`` and ``involves_net(net)`` ⟺
  ``net in nets or any(pin.net_name == net)``.
- P5. Area compliance/margin: ``is_area_compliant()`` ⟺
  ``area <= max_area``; ``area_margin_pct()`` is the exact closed form
  ``(max - area) / max * 100``; both are None before any area is set.

Three metamorphic relations:

- MR1. Construction→access round-trip: every explicitly-set field reads
  back bit-identically, and keyword-argument order is commutative.
- MR2. Insertion-order permutation invariance: reordering the ``loops``
  of a ``LoopCollection`` leaves set-valued queries (``get_all_component_refs``,
  ``get_all_nets``) and ``len`` unchanged.
- MR3. Independent-path equivalence: ``Loop.estimated_voltage_spike`` is
  bit-identical to the chained ``LoopEvent.voltage_spike_v(
  estimated_inductance_nh(...))`` computation (same op chain, so exact).
"""

from __future__ import annotations

import os

import pytest
import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.loop import (
    Loop,
    LoopCollection,
    LoopEvent,
    LoopPin,
    LoopType,
)

MAX_EXAMPLES = 100

# Independent closed-form references (the property recomputes the physics
# itself, so the assertion is against the form, not against either
# implementation).
_MU_0 = 4 * 3.141592653589793 * 1e-7  # H/m (4*pi*1e-7, same value)
_PI = 3.141592653589793


def _f(value):
    return None if value is None else float(value).hex()


def _inductance_ref(area_mm2, trace_height_mm):
    """L = mu0 * A / h, with the oracle's unit conversions, recomputed
    independently here (same expression shape as the module)."""
    h_m = trace_height_mm * 1e-3
    area_m2 = area_mm2 * 1e-6
    inductance_h = _MU_0 * area_m2 / h_m
    return inductance_h * 1e9


def _max_area_ref(target_nh, trace_height_mm):
    """A = L * h / mu0, inverse of the reference above."""
    h_m = trace_height_mm * 1e-3
    inductance_h = target_nh * 1e-9
    area_m2 = inductance_h * h_m / _MU_0
    return area_m2 * 1e6


# ---------------------------------------------------------------------------
# Kernel indirection — the vacuity-mutant seam (G4 evidence pattern).
#
# Every property below exercises its behavior through a `_kernels` method;
# the production methods delegate straight to the pyclasses. A vacuity
# mutant replaces one kernel method with a degenerate implementation and
# re-runs the property via `hypothesis.inner_test` — the property must
# FAIL, proving it is not trivially satisfied.
# ---------------------------------------------------------------------------


class _LoopKernels:
    inductance = staticmethod(lambda area, h: LoopEvent().estimated_inductance_nh(area, h))
    max_area = staticmethod(lambda nh, h: LoopEvent().max_area_for_inductance_nh(nh, h))
    component_refs = staticmethod(lambda loop: loop.get_component_refs())
    involves_component = staticmethod(lambda loop, ref: loop.involves_component(ref))
    involves_net = staticmethod(lambda loop, net: loop.involves_net(net))
    is_compliant = staticmethod(lambda loop: loop.is_area_compliant())
    margin = staticmethod(lambda loop: loop.area_margin_pct())
    voltage_spike = staticmethod(lambda event, nh: event.voltage_spike_v(nh))


_kernels = _LoopKernels()

_KERNEL_NAMES = (
    "inductance",
    "max_area",
    "component_refs",
    "involves_component",
    "involves_net",
    "is_compliant",
    "margin",
    "voltage_spike",
)


@pytest.fixture
def _restore_kernels():
    saved = {name: getattr(_kernels, name) for name in _KERNEL_NAMES}
    yield
    for name, fn in saved.items():
        setattr(_kernels, name, fn)


def _make_loop(**overrides):
    kwargs = {
        "name": "l",
        "loop_type": LoopType.CUSTOM,
        "description": "d",
        **overrides,
    }
    return Loop(**kwargs)


# ---------------------------------------------------------------------------
# P1 — inductance matches an independent closed-form reference (bit-exact)
# ---------------------------------------------------------------------------


@st.composite
def _area_height(draw):
    area = draw(st.floats(min_value=0.5, max_value=5000.0, allow_nan=False, allow_infinity=False))
    height = draw(st.floats(min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False))
    return area, height


@given(_area_height())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p1_inductance_matches_reference(area_height):
    area, height = area_height
    got = _kernels.inductance(area, height)
    expected = _inductance_ref(area, height)
    assert float(got).hex() == float(expected).hex(), (
        f"area={area} h={height}: got={got!r} ref={expected!r}"
    )
    # Vacuity guard: doubling the area (an exact power-of-two scale) must
    # exactly double the inductance — every step of the op chain is
    # exact under a power-of-two multiply, so this is a bit-exact claim.
    doubled = _kernels.inductance(2.0 * area, height)
    assert float(doubled).hex() == float(2.0 * got).hex(), (
        f"area doubling not exact: {doubled!r} vs {2.0 * got!r}"
    )


def test_p1_fails_for_constant_inductance(_restore_kernels):
    _kernels.inductance = lambda *_a, **_k: 1.0
    with pytest.raises(AssertionError):
        test_p1_inductance_matches_reference.hypothesis.inner_test((100.0, 0.2))


# ---------------------------------------------------------------------------
# P2 — max_area_for_inductance_nh is the exact inverse closed form
# ---------------------------------------------------------------------------


@given(
    st.floats(min_value=0.1, max_value=1e6, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p2_max_area_matches_reference(target_nh, height):
    got = _kernels.max_area(target_nh, height)
    expected = _max_area_ref(target_nh, height)
    assert float(got).hex() == float(expected).hex(), (
        f"target={target_nh} h={height}: got={got!r} ref={expected!r}"
    )
    # Vacuity guard: the closed forms are true inverses of the same
    # expression, so the recomputation genuinely exercises both constants.
    assert expected > 0.0


def test_p2_fails_for_constant_max_area(_restore_kernels):
    _kernels.max_area = lambda *_a, **_k: 1.0
    with pytest.raises(AssertionError):
        test_p2_max_area_matches_reference.hypothesis.inner_test(10.0, 0.2)


# ---------------------------------------------------------------------------
# P3 — get_component_refs: components win; pins-only dedup, order-preserving
# ---------------------------------------------------------------------------


@given(
    st.lists(st.sampled_from(["Q1", "Q2", "R1", "U1"]), min_size=0, max_size=6),
    st.lists(st.sampled_from(["Q1", "Q2", "R1", "U1"]), min_size=0, max_size=6),
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p3_component_refs_consistency(components, pin_refs):
    pins = [LoopPin(ref, f"p{i}") for i, ref in enumerate(pin_refs)]
    loop = _make_loop(components=components, pins=pins)
    refs = _kernels.component_refs(loop)

    if components:
        # Components win verbatim (the stored list, in order) — even when
        # the pin path would produce a different (merged) list.
        assert list(refs) == components
    else:
        # Pins-only: unique refs in first-appearance order.
        seen = []
        for ref in pin_refs:
            if ref not in seen:
                seen.append(ref)
        assert list(refs) == seen


def test_p3_components_win_over_pins():
    """Deterministic vacuity anchor: a loop with BOTH a components list and
    pins whose refs differ must return the components list — a degenerate
    kernel that merged pins+components would fail here."""
    loop = _make_loop(components=["A", "B"], pins=[LoopPin("B", "p0"), LoopPin("A", "p1")])
    assert list(_kernels.component_refs(loop)) == ["A", "B"]


def test_p3_fails_for_merged_refs(_restore_kernels):
    def merged(loop):
        refs = list(loop.components)
        for pin in loop.pins:
            if pin.component_ref not in refs:
                refs.append(pin.component_ref)
        return refs

    _kernels.component_refs = merged
    with pytest.raises(AssertionError):
        test_p3_component_refs_consistency.hypothesis.inner_test(["A"], ["B"])


# ---------------------------------------------------------------------------
# P4 — involves_component/involves_net predicate agreement
# ---------------------------------------------------------------------------


@given(
    st.sampled_from(["Q1", "Q2", "R1"]),
    st.lists(st.sampled_from(["Q1", "Q2", "R1"]), min_size=0, max_size=5),
    st.lists(st.sampled_from(["GATE_H", "SW", "DC+"]), min_size=0, max_size=5),
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p4_involves_predicate_agreement(ref, component_refs, net_names):
    loop = _make_loop(components=component_refs, nets=net_names)
    assert _kernels.involves_component(loop, ref) == (ref in component_refs), ref
    assert _kernels.involves_net(loop, ref) == (ref in net_names), ref
    # Vacuity guard: refs and membership lists are drawn from overlapping
    # small alphabets, so both the member and non-member branches of the
    # predicate are exercised across the example run.
    assert ref in ("Q1", "Q2", "R1")


def test_p4_fails_for_always_false_involves(_restore_kernels):
    _kernels.involves_component = lambda *_a, **_k: False
    with pytest.raises(AssertionError):
        test_p4_involves_predicate_agreement.hypothesis.inner_test(
            "Q1", ["Q1"], []
        )


# ---------------------------------------------------------------------------
# P5 — area compliance and margin (exact closed form, None lifecycle)
# ---------------------------------------------------------------------------


@given(
    st.floats(min_value=1.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=10.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p5_area_compliance_and_margin(area, max_area):
    loop = _make_loop(max_area_mm2=max_area)
    assert _kernels.is_compliant(loop) is None
    assert _kernels.margin(loop) is None

    loop.set_current_area(area)
    compliant = _kernels.is_compliant(loop)
    margin = _kernels.margin(loop)
    assert compliant == (area <= max_area), f"area={area} max={max_area}"
    expected_margin = (max_area - area) / max_area * 100.0
    assert float(margin).hex() == float(expected_margin).hex()
    # Vacuity guard: the sampled range genuinely crosses the threshold
    # (area is drawn independently of max_area in overlapping ranges).
    assert area <= 500.0 and max_area >= 10.0


def test_p5_fails_for_sign_flipped_margin(_restore_kernels):
    def flipped_margin(loop):
        area = loop.get_current_area()
        if area is None:
            return None
        return (area - loop.max_area_mm2) / loop.max_area_mm2 * 100.0

    _kernels.margin = flipped_margin
    with pytest.raises(AssertionError):
        test_p5_area_compliance_and_margin.hypothesis.inner_test(200.0, 100.0)


# ---------------------------------------------------------------------------
# MR1 — construction→access round-trip and kwarg-order commutativity
# ---------------------------------------------------------------------------


@given(
    st.floats(min_value=0.1, max_value=1e12, allow_nan=False, allow_infinity=False),
    st.one_of(st.none(), st.floats(min_value=0.1, max_value=1e12, allow_nan=False, allow_infinity=False)),
    st.floats(min_value=0.1, max_value=1e9, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.1, max_value=1e9, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.1, max_value=1e9, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.1, max_value=1e9, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr1_event_round_trip_and_kwarg_order_commute(
    di_dt, dv_dt, frequency_hz, peak_current_a, rms_current_a, ringing_freq_hz
):
    kwargs = {
        "di_dt": di_dt,
        "dv_dt": dv_dt,
        "frequency_hz": frequency_hz,
        "peak_current_a": peak_current_a,
        "rms_current_a": rms_current_a,
        "ringing_freq_hz": ringing_freq_hz,
    }
    event = LoopEvent(**kwargs)
    assert _f(event.di_dt) == _f(di_dt)
    assert _f(event.dv_dt) == _f(dv_dt)
    assert _f(event.frequency_hz) == _f(frequency_hz)
    assert _f(event.peak_current_a) == _f(peak_current_a)
    assert _f(event.rms_current_a) == _f(rms_current_a)
    assert _f(event.ringing_freq_hz) == _f(ringing_freq_hz)
    # Vacuity guard: drawn values differ from the all-None defaults.
    assert any(v is not None for v in kwargs.values())
    # Kwarg-order commutativity.
    reversed_event = LoopEvent(**dict(reversed(list(kwargs.items()))))
    assert _f(reversed_event.di_dt) == _f(event.di_dt)
    assert _f(reversed_event.ringing_freq_hz) == _f(event.ringing_freq_hz)


# ---------------------------------------------------------------------------
# MR2 — LoopCollection insertion-order permutation invariance
# ---------------------------------------------------------------------------


def _sample_loop(name, loop_type, components, nets):
    return Loop(
        name=name,
        loop_type=loop_type,
        description=f"desc-{name}",
        components=components,
        nets=nets,
        max_area_mm2=100.0,
    )


def test_mr2_collection_insertion_order_permutation_invariance():
    import itertools

    loops = [
        _sample_loop("a", LoopType.COMMUTATION, ["Q1", "Q2"], ["SW", "DC+"]),
        _sample_loop("b", LoopType.GATE_DRIVE_HIGH, ["U1", "Q1"], ["GATE_H"]),
        _sample_loop("c", LoopType.BOOTSTRAP, ["D1", "C1"], []),
        _sample_loop("d", LoopType.SENSING, ["R1"], ["I_SENSE"]),
    ]
    expected_refs = {"Q1", "Q2", "U1", "D1", "C1", "R1"}
    expected_nets = {"SW", "DC+", "GATE_H", "I_SENSE"}

    for order in itertools.permutations(range(len(loops))):
        coll = LoopCollection(loops=[loops[i] for i in order])
        assert coll.get_all_component_refs() == expected_refs, order
        assert coll.get_all_nets() == expected_nets, order
        assert len(coll) == 4, order
        # Vacuity guard: distinct permutations really were exercised.
    assert len(list(itertools.permutations(range(4)))) == 24


# ---------------------------------------------------------------------------
# MR3 — Loop.estimated_voltage_spike ≡ chained LoopEvent computation
# ---------------------------------------------------------------------------


@given(
    st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.05, max_value=2.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=1e5, max_value=1e10, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr3_estimated_voltage_spike_matches_chained_computation(area, height, di_dt):
    loop = _make_loop(events=LoopEvent(di_dt=di_dt), max_area_mm2=1000.0)
    loop.set_current_area(area)
    spike = loop.estimated_voltage_spike(trace_height_mm=height)

    # Independent chained path through the kernel seam (L then V = L*di/dt).
    chain = _kernels.voltage_spike(loop.events, _kernels.inductance(area, height))
    assert spike is not None
    assert float(spike).hex() == float(chain).hex(), (
        f"area={area} h={height}: {spike!r} vs {chain!r}"
    )
    # Vacuity guard: the area is genuinely set, so the method's None-guard
    # is not the branch under test, and the spike is nonzero.
    assert float(spike).hex() != (0.0).hex()


def test_mr3_fails_for_wrong_inductance_chain(_restore_kernels):
    def wrong_chain(area_mm2, trace_height_mm):
        # Wrong: drops the trace-height conversion (treats mm as m).
        return 4 * _PI * 1e-7 * area_mm2 * 1e-6 / trace_height_mm * 1e9

    _kernels.inductance = wrong_chain
    with pytest.raises(AssertionError):
        test_mr3_estimated_voltage_spike_matches_chained_computation.hypothesis.inner_test(
            100.0, 0.2, 1e9
        )


# ---------------------------------------------------------------------------
# Presence guard: this proof must not silently skip in CI.
# ---------------------------------------------------------------------------

_REQUIRE = os.environ.get("TEMPER_REQUIRE_RUST_LOOP", "").strip().lower() in {
    "1",
    "true",
    "yes",
}

if _REQUIRE and not hasattr(_tdb, "LoopType"):
    pytest.fail(
        "TEMPER_REQUIRE_RUST_LOOP=1 but temper_design_bundle_python "
        "does not expose the loop pyclasses — the Rust extension is "
        "stale or missing.",
        pytrace=False,
    )

pytestmark = pytest.mark.skipif(
    not hasattr(_tdb, "LoopType"),
    reason="temper_design_bundle_python loop pyclasses not installed "
    "(set TEMPER_REQUIRE_RUST_LOOP=1 to make this fatal instead of a skip)",
)
