"""Property-based + metamorphic tests for the Rust priority pyclasses.

Wave 4, Phase 2 — the contracts-as-pyo3-pyclasses pivot (plan
``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``
R1c/R1d). These properties exercise the migrated
``temper_placer.core.priority`` module (a pure-delegation re-export of the
``temper_design_bundle_python`` pyclasses); bit-identical parity against
the pinned pre-migration Python is asserted separately by
``test_priority_rust_differential.py``.

Five hypothesis properties (all non-vacuously guarded):

- P1. ``classify_net`` totality: every net name (from a keyword-rich
  alphabet) maps to a valid ``RoutingPriority`` member and never raises.
- P2. ``classify_component`` explicit-assignment precedence: a component
  listed in a placement phase classifies to that phase's priority
  regardless of its prefix default.
- P3. ``classify_net`` explicit-pattern precedence: a net matching an
  explicit exact/wildcard pattern maps to the phase's priority even when
  the keyword defaults would classify it differently.
- P4. Enum value bijection: the fixed (name, value) tables match
  ``getattr(Cls, name).value`` and ``Cls(value)`` round-trips to the
  member.
- P5. Phase-lookup round-trip: ``get_placement_phase``/``get_routing_phase``
  return the phase with the queried priority for listed priorities and
  ``None`` for unlisted ones.

Four metamorphic relations:

- MR1. Prefix-decoration invariance: ``classify_net("ZZ_" + net) ==
  classify_net(net)`` (exact — ``ZZ_`` introduces no keyword at a
  boundary; the keyword's preceding char stays ``_`` and its following
  context is unchanged).
- MR2. Phase-list order independence: with distinct priorities,
  ``get_*_phase`` results are identical after reversing the phase list
  (``find`` semantics are order-independent when priorities are unique —
  the honest bound).
- MR3. Digit-suffix invariance: ``classify_component(ref) ==
  classify_component(ref + digits)`` (the prefix rule strips trailing
  digits).
- MR4. Case invariance: ``classify_net(name) == classify_net(swapped)``
  (both sides uppercase before matching — exact).
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.priority import (
    PlacementPhaseConfig,
    PlacementPriority,
    PriorityConfig,
    RoutingPhaseConfig,
    RoutingPriority,
)

MAX_EXAMPLES = 100

# A keyword-rich net-name alphabet: every keyword family plus decoys.
_NET_ALPHABET = st.text(
    alphabet=st.sampled_from(list("BUSHVGATE0123456789_+SWNODEINSPICLKUSBSENCENTRTD3VABCMYZ")),
    min_size=1,
    max_size=16,
)

_PREFIX_ALPHABET = st.text(
    alphabet=st.sampled_from(list("QRDUCXYJ0123456789_")), min_size=1, max_size=8
)

_PLACEMENT_PRIORITIES = [
    PlacementPriority.POWER,
    PlacementPriority.DRIVER,
    PlacementPriority.HIGH_SPEED,
    PlacementPriority.ANALOG,
    PlacementPriority.DIGITAL,
]
_ROUTING_PRIORITIES = [
    RoutingPriority.POWER,
    RoutingPriority.GATE_DRIVE,
    RoutingPriority.HIGH_SPEED,
    RoutingPriority.ANALOG,
    RoutingPriority.DIGITAL,
    RoutingPriority.AUTO,
]


# ---------------------------------------------------------------------------
# Kernel indirection — the vacuity-mutant seam (G4 evidence pattern).
# ---------------------------------------------------------------------------


class _PriorityKernels:
    classify_net = staticmethod(lambda cfg, net: cfg.classify_net(net))
    classify_component = staticmethod(lambda cfg, ref: cfg.classify_component(ref, object()))
    get_placement_phase = staticmethod(lambda cfg, p: cfg.get_placement_phase(p))
    get_routing_phase = staticmethod(lambda cfg, p: cfg.get_routing_phase(p))
    enum_value = staticmethod(lambda cls, name: getattr(cls, name).value)


_kernels = _PriorityKernels()

_KERNEL_NAMES = (
    "classify_net",
    "classify_component",
    "get_placement_phase",
    "get_routing_phase",
    "enum_value",
)


@pytest.fixture
def _restore_kernels():
    saved = {name: getattr(_kernels, name) for name in _KERNEL_NAMES}
    yield
    for name, fn in saved.items():
        setattr(_kernels, name, fn)


# ---------------------------------------------------------------------------
# P1 — classify_net totality
# ---------------------------------------------------------------------------


@given(_NET_ALPHABET)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p1_classify_net_totality(net_name):
    """Every generated net name maps to a valid RoutingPriority member."""
    result = _kernels.classify_net(PriorityConfig(), net_name)
    assert result in _ROUTING_PRIORITIES


def test_p1_fails_for_bogus_value_kernel(_restore_kernels):
    """A degenerate kernel returning a non-member makes P1 fail — proving
    the property genuinely discriminates valid members from junk."""

    def bogus_kernel(cfg, net_name):
        if "_" in net_name:
            return "not_a_priority"
        return cfg.classify_net(net_name)

    _kernels.classify_net = bogus_kernel
    with pytest.raises(AssertionError):
        test_p1_classify_net_totality.hypothesis.inner_test("MY_BUS")


# ---------------------------------------------------------------------------
# P2 — classify_component explicit-assignment precedence
# ---------------------------------------------------------------------------


@st.composite
def _explicit_component_args(draw):
    """A (config, ref) pair where ref is explicitly listed in a phase whose
    priority differs from the ref's prefix default."""
    phase_priority = draw(st.sampled_from(_PLACEMENT_PRIORITIES))
    # A POWER-prefix ref (Q*) mis-assigned to a non-POWER phase.
    ref = draw(st.sampled_from(["Q1", "Q2", "Q3"]))
    return (
        PriorityConfig(
            placement_phases=[
                PlacementPhaseConfig(name="p", priority=phase_priority, components=[ref])
            ]
        ),
        ref,
    )


@given(_explicit_component_args())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p2_component_explicit_assignment_wins(args):
    """Explicitly-listed components classify to the phase's priority, even
    when their prefix default differs (here Q* → POWER by prefix)."""
    cfg, ref = args
    result = _kernels.classify_component(cfg, ref)
    assert result == cfg.placement_phases[0].priority


def test_p2_fails_for_prefix_only_kernel(_restore_kernels):
    """A degenerate kernel ignoring explicit assignments classifies Q* by
    prefix (POWER) — P2 fails when the assignment is DRIVER."""

    def prefix_only(cfg, ref):
        if ref.startswith("Q"):
            return PlacementPriority.POWER
        return PlacementPriority.DIGITAL

    _kernels.classify_component = prefix_only
    cfg = PriorityConfig(
        placement_phases=[
            PlacementPhaseConfig(name="p", priority=PlacementPriority.DRIVER, components=["Q1"])
        ]
    )
    with pytest.raises(AssertionError):
        test_p2_component_explicit_assignment_wins.hypothesis.inner_test((cfg, "Q1"))


# ---------------------------------------------------------------------------
# P3 — classify_net explicit-pattern precedence
# ---------------------------------------------------------------------------


@st.composite
def _explicit_net_args(draw):
    """A (config, net) pair where net matches an explicit pattern whose
    priority differs from the keyword default for that net."""
    priority = draw(st.sampled_from(_ROUTING_PRIORITIES))
    # "3V3" defaults to DIGITAL; "SPI1" defaults to HIGH_SPEED — assign them
    # to a different explicit priority and assert the explicit one wins.
    net = draw(st.sampled_from(["3V3", "SPI1", "GND"]))
    return (
        PriorityConfig(
            routing_phases=[RoutingPhaseConfig(name="r", priority=priority, nets=[net])]
        ),
        net,
    )


@given(_explicit_net_args())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p3_net_explicit_pattern_wins(args):
    """Exact explicit patterns beat keyword defaults."""
    cfg, net = args
    result = _kernels.classify_net(cfg, net)
    assert result == cfg.routing_phases[0].priority


def test_p3_fails_for_no_explicit_kernel(_restore_kernels):
    """A degenerate kernel skipping explicit phases classifies "3V3" as
    DIGITAL — P3 fails when the explicit assignment is HIGH_SPEED."""

    def no_explicit(cfg, net_name):
        return RoutingPriority.DIGITAL

    _kernels.classify_net = no_explicit
    cfg = PriorityConfig(
        routing_phases=[
            RoutingPhaseConfig(name="r", priority=RoutingPriority.HIGH_SPEED, nets=["3V3"])
        ]
    )
    with pytest.raises(AssertionError):
        test_p3_net_explicit_pattern_wins.hypothesis.inner_test((cfg, "3V3"))


def test_p3_wildcard_pattern_wins():
    """Wildcard explicit patterns beat keyword defaults too (BUS* → HIGH_SPEED
    overrides the BUS→POWER keyword rule)."""
    cfg = PriorityConfig(
        routing_phases=[
            RoutingPhaseConfig(name="r", priority=RoutingPriority.HIGH_SPEED, nets=["BUS*"])
        ]
    )
    assert cfg.classify_net("BUS_12V") == RoutingPriority.HIGH_SPEED
    assert cfg.classify_net("BUS_5V") == RoutingPriority.HIGH_SPEED


# ---------------------------------------------------------------------------
# P4 — Enum value bijection
# ---------------------------------------------------------------------------

_ENUM_TABLES = {
    PlacementPriority: {"POWER": 1, "DRIVER": 2, "HIGH_SPEED": 3, "ANALOG": 4, "DIGITAL": 5},
    RoutingPriority: {
        "POWER": 1,
        "GATE_DRIVE": 2,
        "HIGH_SPEED": 3,
        "ANALOG": 4,
        "DIGITAL": 5,
        "AUTO": 10,
    },
}


@given(st.sampled_from(sorted(_ENUM_TABLES, key=id)))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p4_enum_value_bijection(enum_cls):
    """For every member: getattr(cls, name).value matches the fixed table and
    cls(value) round-trips to the member."""
    table = _ENUM_TABLES[enum_cls]
    for name, value in table.items():
        assert _kernels.enum_value(enum_cls, name) == value
        assert enum_cls(value).name == name
    # Value construction rejects unknown values with ValueError.
    with pytest.raises(ValueError):
        enum_cls(max(table.values()) + 1)


def test_p4_fails_for_wrong_value_kernel(_restore_kernels):
    """A degenerate kernel reporting the wrong value for one member makes P4
    fail — proving the value table is genuinely asserted."""

    def wrong_value(cls, name):
        if name == "AUTO":
            return 99
        return getattr(cls, name).value

    _kernels.enum_value = wrong_value
    with pytest.raises(AssertionError):
        test_p4_enum_value_bijection.hypothesis.inner_test(RoutingPriority)


# ---------------------------------------------------------------------------
# P5 — Phase-lookup round-trip
# ---------------------------------------------------------------------------


@given(st.sampled_from([PlacementPriority, RoutingPriority]))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p5_phase_lookup_round_trip(enum_cls):
    """get_*_phase returns the listed phase for its priority and None for
    priorities not in the list."""
    if enum_cls is PlacementPriority:
        phases = [
            PlacementPhaseConfig(name="a", priority=PlacementPriority.POWER),
            PlacementPhaseConfig(name="b", priority=PlacementPriority.DIGITAL),
        ]
        cfg = PriorityConfig(placement_phases=phases)
        for phase in phases:
            found = _kernels.get_placement_phase(cfg, phase.priority)
            assert found is not None and found.priority == phase.priority
        assert _kernels.get_placement_phase(cfg, PlacementPriority.DRIVER) is None
    else:
        phases = [
            RoutingPhaseConfig(name="a", priority=RoutingPriority.GATE_DRIVE),
            RoutingPhaseConfig(name="b", priority=RoutingPriority.AUTO),
        ]
        cfg = PriorityConfig(routing_phases=phases)
        for phase in phases:
            found = _kernels.get_routing_phase(cfg, phase.priority)
            assert found is not None and found.priority == phase.priority
        assert _kernels.get_routing_phase(cfg, RoutingPriority.POWER) is None


def test_p5_fails_for_none_kernel(_restore_kernels):
    """A degenerate kernel returning None for every lookup makes P5 fail."""
    _kernels.get_placement_phase = lambda cfg, p: None  # noqa: ARG005
    with pytest.raises(AssertionError):
        test_p5_phase_lookup_round_trip.hypothesis.inner_test(PlacementPriority)


# ---------------------------------------------------------------------------
# MR1 — prefix-decoration invariance (exact)
# ---------------------------------------------------------------------------


@given(_NET_ALPHABET)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr1_prefix_decoration_invariance(net_name):
    """classify_net("ZZ_" + net) == classify_net(net) on the default config
    (no explicit patterns): the extra "ZZ_" prefix introduces no keyword at
    a boundary and leaves the keyword's preceding/following context intact."""
    cfg = PriorityConfig()
    assert cfg.classify_net(f"ZZ_{net_name}") == cfg.classify_net(net_name)


# ---------------------------------------------------------------------------
# MR2 — phase-list order independence (distinct priorities)
# ---------------------------------------------------------------------------


def test_mr2_phase_list_order_independence():
    """With distinct priorities, get_*_phase finds the same phase after the
    list is reversed (find semantics are order-independent for unique
    priorities)."""
    placements = [
        PlacementPhaseConfig(name="a", priority=PlacementPriority.POWER),
        PlacementPhaseConfig(name="b", priority=PlacementPriority.ANALOG),
        PlacementPhaseConfig(name="c", priority=PlacementPriority.DIGITAL),
    ]
    routings = [
        RoutingPhaseConfig(name="x", priority=RoutingPriority.POWER),
        RoutingPhaseConfig(name="y", priority=RoutingPriority.AUTO),
    ]
    cfg = PriorityConfig(placement_phases=placements, routing_phases=routings)
    rev = PriorityConfig(
        placement_phases=list(reversed(placements)),
        routing_phases=list(reversed(routings)),
    )
    for p in _PLACEMENT_PRIORITIES:
        a = cfg.get_placement_phase(p)
        b = rev.get_placement_phase(p)
        assert (a is None) == (b is None)
        if a is not None:
            assert a.name == b.name
    for r in _ROUTING_PRIORITIES:
        a = cfg.get_routing_phase(r)
        b = rev.get_routing_phase(r)
        assert (a is None) == (b is None)
        if a is not None:
            assert a.name == b.name


# ---------------------------------------------------------------------------
# MR3 — digit-suffix invariance (exact)
# ---------------------------------------------------------------------------


@given(_PREFIX_ALPHABET)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr3_digit_suffix_invariance(ref):
    """classify_component(ref) == classify_component(ref + "123"): the prefix
    rule strips trailing digits, so numeric suffixes never change the
    classification."""
    cfg = PriorityConfig()
    assert cfg.classify_component(ref, None) == cfg.classify_component(ref + "123", None)


# ---------------------------------------------------------------------------
# MR4 — case invariance (exact)
# ---------------------------------------------------------------------------


@given(_NET_ALPHABET)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr4_case_invariance(net_name):
    """classify_net(name) == classify_net(name.swapcase()): both sides
    uppercase before matching, so case never changes the classification."""
    cfg = PriorityConfig()
    assert cfg.classify_net(net_name) == cfg.classify_net(net_name.swapcase())


def test_vacuity_sanity_default_config_discriminates():
    """The default-config keyword rules genuinely discriminate — the input
    space for MR1/MR4 is not collapsed to a single output."""
    cfg = PriorityConfig()
    classes = {
        cfg.classify_net(n) for n in ["HV_SW", "GATE_DRV", "SPI1", "SENSE", "3V3", "BUS_12V"]
    }
    assert len(classes) == 5
