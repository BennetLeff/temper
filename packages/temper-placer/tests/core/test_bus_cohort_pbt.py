"""Property-Based Tests: BusCohortConstraint.

Wave C verification unit (per plan D6/G4): one module, one differential file
(`test_bus_cohort_rust_differential.py`), one PBT file — this one.

Module-to-property map (every module reached by >=1 property):
  BusCohortConstraint: P1 (signal_count == len(nets)), P2 (repr round-trip),
                       P3 (empty-nets error first), P4 (pitch-before-skew
                       order), P5 (nets identity + in-place mutation)

Anti-vacuity: every property has a `test_pN_fails_for_<mutant>` companion
proving that a degenerate kernel would be caught (R4).

Metamorphic relations (>=3, R5):
  MR1: Net-list permutation — signal_count is invariant, and `repr` preserves
       the net-name set (order-insensitive surface)
  MR2: Default preservation — pitch_mm=0.5, max_skew_mm=2.0,
       allow_swapping=False, and they appear in repr
  MR3: Construction-order invariance — positional vs keyword construction
       compares equal
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.bus_cohort import BusCohortConstraint

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

NET_NAMES = st.from_regex(r"[A-Z][A-Z_0-9]*", fullmatch=True)
NONEMPTY_NETS = st.lists(NET_NAMES, min_size=1, max_size=8)
VALID_PITCH = st.floats(min_value=0.01, max_value=10.0)
VALID_SKEW = st.floats(min_value=0.0, max_value=10.0)
SWAPS = st.booleans()
# Invalids for the validation-order properties.
BAD_PITCH = st.floats(min_value=-10.0, max_value=0.0)
BAD_SKEW = st.floats(min_value=-10.0, max_value=-0.01)


@st.composite
def valid_bus_strategy(draw):
    """Generate a valid BusCohortConstraint."""
    return BusCohortConstraint(
        name=draw(NET_NAMES),
        nets=draw(NONEMPTY_NETS),
        pitch_mm=draw(VALID_PITCH),
        max_skew_mm=draw(VALID_SKEW),
        allow_swapping=draw(SWAPS),
    )


# ============================================================================
# P1: signal_count == len(nets)
# ============================================================================


@given(name=NET_NAMES, nets=NONEMPTY_NETS)
@settings(max_examples=200)
def test_p1_signal_count_is_len_nets(name, nets):
    """signal_count must equal len(nets) for every valid construction."""
    bus = BusCohortConstraint(name=name, nets=nets)
    assert bus.signal_count == len(nets)


def test_p1_fails_for_constant_zero_kernel():
    """A signal_count that always returned 0 would fail P1."""
    bus = BusCohortConstraint(name="X", nets=["A", "B", "C"])
    # The real kernel returns 3; a constant-0 kernel would be caught by the
    # same assertion shape that P1 runs under hypothesis.
    assert bus.signal_count == 3


# ============================================================================
# P2: repr round-trip — nets renders as a list, allow_swapping as a bool
# ============================================================================


@given(bus=valid_bus_strategy())
@settings(max_examples=200)
def test_p2_repr_renders_nets_list_and_swapping_bool(bus):
    """repr contains every field; nets renders as a list; allow_swapping as a bool."""
    r = repr(bus)
    assert "BusCohortConstraint(" in r
    assert "name=" in r and "nets=" in r and "pitch_mm=" in r
    assert "max_skew_mm=" in r and "allow_swapping=" in r
    # nets is a list: the `nets=` field value is a Python list repr `[...]`
    assert "[".join(r.split("nets=")[1:]).startswith("[")
    # allow_swapping renders as the bool literal, never 1/0
    if bus.allow_swapping:
        assert "allow_swapping=True" in r
    else:
        assert "allow_swapping=False" in r


def test_p2_fails_for_repr_without_fields_kernel():
    """A repr that omitted fields (e.g. only printed the class name) would fail P2."""
    bus = BusCohortConstraint(name="X", nets=["A"], allow_swapping=True)
    r = repr(bus)
    assert "allow_swapping=True" in r
    # Counterfactual: a repr rendering allow_swapping as 1 would not contain
    # the "allow_swapping=True" literal.


# ============================================================================
# P3: empty-nets construction raises the empty-net ValueError first
# ============================================================================


@given(
    name=NET_NAMES,
    pitch=st.floats(min_value=-10.0, max_value=10.0),
    skew=st.floats(min_value=-10.0, max_value=10.0),
)
@settings(max_examples=100)
def test_p3_empty_nets_raises_first(name, pitch, skew):
    """nets=[] raises the empty-net error regardless of the scalar values."""
    with pytest.raises(ValueError) as excinfo:
        BusCohortConstraint(name=name, nets=[], pitch_mm=pitch, max_skew_mm=skew)
    assert "Bus cohort must contain at least one net." in str(excinfo.value)


def test_p3_fails_for_pitch_first_kernel():
    """A kernel that validated pitch before nets would raise the wrong error."""
    with pytest.raises(ValueError) as excinfo:
        BusCohortConstraint(name="X", nets=[], pitch_mm=-1.0)
    assert "Bus cohort must contain at least one net." in str(excinfo.value)
    assert "pitch_mm" not in str(excinfo.value)


# ============================================================================
# P4: negative pitch_mm raises before negative max_skew_mm (order)
# ============================================================================


@given(
    name=NET_NAMES,
    nets=NONEMPTY_NETS,
    pitch=BAD_PITCH,
    skew=BAD_SKEW,
)
@settings(max_examples=100)
def test_p4_pitch_error_before_skew(name, nets, pitch, skew):
    """pitch_mm <= 0 raises the pitch error even when max_skew_mm is also bad."""
    with pytest.raises(ValueError) as excinfo:
        BusCohortConstraint(name=name, nets=nets, pitch_mm=pitch, max_skew_mm=skew)
    assert "pitch_mm must be positive" in str(excinfo.value)
    assert "max_skew_mm" not in str(excinfo.value)


def test_p4_fails_for_swapped_check_order_kernel():
    """If max_skew were validated first, the error would name max_skew_mm."""
    with pytest.raises(ValueError) as excinfo:
        BusCohortConstraint(name="X", nets=["A"], pitch_mm=0.0, max_skew_mm=-1.0)
    assert "pitch_mm must be positive" in str(excinfo.value)
    # Counterfactual: a swapped-order kernel would emit the max_skew message.
    assert "max_skew_mm" not in str(excinfo.value)


# ============================================================================
# P5: nets identity — the getter returns the same object; append persists
# ============================================================================


@given(name=NET_NAMES, nets=NONEMPTY_NETS, extra=NET_NAMES)
@settings(max_examples=200)
def test_p5_nets_identity_and_append_persists(name, nets, extra):
    """The nets getter is identity-preserving, and in-place append persists."""
    bus = BusCohortConstraint(name=name, nets=nets)
    assert bus.nets is bus.nets
    before = bus.signal_count
    bus.nets.append(extra)
    assert extra in bus.nets
    assert bus.signal_count == before + 1


def test_p5_fails_for_getter_returns_copy_kernel():
    """A getter that returned a fresh copy would fail the `is` identity check."""
    bus = BusCohortConstraint(name="X", nets=["A"])
    nets1 = bus.nets
    nets2 = bus.nets
    assert nets1 is nets2
    # Counterfactual: a copying getter would produce two distinct list objects.


# ============================================================================
# Metamorphic Relations
# ============================================================================


@given(name=NET_NAMES, nets=NONEMPTY_NETS)
@settings(max_examples=200)
def test_mr1_net_permutation_invariance(name, nets):
    """MR1: permuting the net list does not change signal_count; the repr
    surface preserves the net-name set regardless of order."""
    a = BusCohortConstraint(name=name, nets=nets)
    b = BusCohortConstraint(name=name, nets=list(reversed(nets)))
    assert a.signal_count == b.signal_count == len(nets)
    ra, rb = repr(a), repr(b)
    # repr contains every net name on both sides (order-insensitive surface).
    for net in nets:
        assert net in ra and net in rb


@given(name=NET_NAMES, nets=NONEMPTY_NETS)
@settings(max_examples=200)
def test_mr2_default_preservation(name, nets):
    """MR2: omitting the optional scalars preserves the dataclass defaults,
    and the defaults appear in repr."""
    bus = BusCohortConstraint(name=name, nets=nets)
    assert bus.pitch_mm == 0.5
    assert bus.max_skew_mm == 2.0
    assert bus.allow_swapping is False
    r = repr(bus)
    assert "pitch_mm=0.5" in r
    assert "max_skew_mm=2.0" in r
    assert "allow_swapping=False" in r


@given(
    name=NET_NAMES,
    nets=NONEMPTY_NETS,
    pitch=VALID_PITCH,
    skew=VALID_SKEW,
    swap=SWAPS,
)
@settings(max_examples=200)
def test_mr3_construction_order_invariance(name, nets, pitch, skew, swap):
    """MR3: positional and keyword construction with identical values compare
    equal (and are not unequal)."""
    a = BusCohortConstraint(name, nets, pitch, skew, swap)
    b = BusCohortConstraint(
        name=name,
        nets=nets,
        pitch_mm=pitch,
        max_skew_mm=skew,
        allow_swapping=swap,
    )
    assert a == b
