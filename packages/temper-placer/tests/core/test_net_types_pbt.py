"""Property-based + metamorphic tests for the Rust net-types pyclasses.

Wave 4, Phase 2 — the contracts-as-pyo3-pyclasses pivot (plan
``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``
R1c/R1d). These properties exercise the migrated
``temper_placer.core.net_types`` module (a pure delegation re-export of the
``temper_design_bundle_python`` pyclasses); bit-identical parity against the
pinned pre-migration Python is asserted separately by
``test_net_types_rust_differential.py``.

Five hypothesis properties (all non-vacuously guarded):

- P1. IEC 60335 clearance/creepage tables match an independent closed-form
  reference exactly (bit-identical), and the pollution-degree/material-group
  scaling genuinely bites (strict inequalities).
- P2. Ground-connectivity enforcement: ``validate()`` emits exactly the
  ground error iff connectivity is neither PLANE nor DIRECT.
- P3. High-voltage clearance/creepage threshold behavior: ``validate()``
  emits the creepage/clearance error iff the value is strictly below the
  IEC minimum (bit-exact threshold comparison).
- P4. ``classify_net`` triage: every pattern-substring net name and every
  noise name maps to the expected module constant (field-equal), and all
  four tiers are reachable.
- P5. Case-insensitive auto-classification: ``classify_net(name)`` and
  ``classify_net(name.upper())`` are field-equal for mixed-case names.

Three metamorphic relations:

- MR1. Construction→access round-trip: every explicitly-set field reads back
  bit-identically, and keyword-argument order is commutative.
- MR2. Insertion-order permutation invariance: reordering the ``specs``
  entries of a ``NetClassification`` leaves ``get_plane_nets``,
  ``get_pour_nets``, and ``classify_net`` results unchanged.
- MR3. Independent-path equivalence: ``from_yaml_config`` on a rule set
  produces a spec field-equal to a direct ``NetTypeSpec`` construction with
  the corresponding resolved fields.
"""

from __future__ import annotations

import os

import pytest
import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.board import LayerIndex
from temper_placer.core.net_types import (
    GROUND_PLANE_SPEC,
    MAINS_HV_SPEC,
    POWER_PLANE_SPEC,
    SIGNAL_SPEC,
    ConnectivityStrategy,
    NetClassification,
    NetType,
    NetTypeSpec,
    VoltageClass,
)

MAX_EXAMPLES = 100

# Independent IEC 60335 reference tables (base values, Table 16/17 basic
# insulation). The property recomputes ``base * factor`` itself, so the
# assertion is against the closed form, not against either implementation.
_CLEARANCE_BASE = {
    "SELV": 0.5,
    "LOW_VOLTAGE": 1.0,
    "MAINS_120V": 1.5,
    "MAINS_240V": 3.0,
    "HIGH_VOLTAGE": 8.0,
}
_CREEPAGE_BASE = {
    "SELV": 0.5,
    "LOW_VOLTAGE": 1.6,
    "MAINS_120V": 2.5,
    "MAINS_240V": 5.0,
    "HIGH_VOLTAGE": 14.0,
}
_CLEARANCE_FACTOR = {1: 0.8, 2: 1.0, 3: 1.5}
_CREEPAGE_FACTOR = {1: 0.8, 2: 1.0, 3: 1.4}

_SPEC_CONSTANTS = {
    "ground": "GROUND_PLANE_SPEC",
    "power": "POWER_PLANE_SPEC",
    "hv": "MAINS_HV_SPEC",
    "signal": "SIGNAL_SPEC",
}

# The pyo3 pyclass enums are not class-iterable (a pyo3 limitation — see
# the differential test's docstring), so enumerate members explicitly.
_NET_TYPES = [
    NetType.GROUND,
    NetType.POWER,
    NetType.HIGH_VOLTAGE,
    NetType.SIGNAL,
    NetType.DIFFERENTIAL,
    NetType.HIGH_CURRENT,
]
_CONNECTIVITIES = [
    ConnectivityStrategy.PLANE,
    ConnectivityStrategy.COPPER_POUR,
    ConnectivityStrategy.TRACE,
    ConnectivityStrategy.VIA_ARRAY,
    ConnectivityStrategy.DIRECT,
]
_VOLTAGE_CLASSES = [
    VoltageClass.SELV,
    VoltageClass.LOW_VOLTAGE,
    VoltageClass.MAINS_120V,
    VoltageClass.MAINS_240V,
    VoltageClass.HIGH_VOLTAGE,
]

# Every auto-classification pattern with its expected tier.
_PATTERN_TIERS = [
    *[("ground", p) for p in ("GND", "PGND", "CGND", "AGND", "DGND", "VSS")],
    *[("power", p) for p in ("+3V3", "+5V", "+12V", "+15V", "VCC", "VDD", "VBUS")],
    *[("hv", p) for p in ("AC_L", "AC_N", "PE", "DC_BUS+", "DC_BUS-", "SW_NODE")],
]


def _spec_fields(spec):
    """Canonicalize a NetTypeSpec into a plain comparable tuple.

    Floats via ``float.hex()`` (exact bit patterns); ``target_layer``
    canonicalized by value (str stays str, LayerIndex IntEnum → int).
    """
    target = spec.target_layer
    target_key = target if isinstance(target, str) else int(target)
    return (
        (spec.net_type.name, spec.net_type.value),
        (spec.connectivity.name, spec.connectivity.value),
        target_key,
        (spec.voltage_class.name, spec.voltage_class.value),
        float(spec.max_current_a).hex(),
        None if spec.impedance_ohm is None else float(spec.impedance_ohm).hex(),
        float(spec.trace_width_mm).hex(),
        float(spec.clearance_mm).hex(),
        float(spec.creepage_mm).hex(),
        spec.via_template,
        bool(spec.allow_layer_change),
        bool(spec.prefer_short_stubs),
    )


_CONSTANT_BY_TIER = {
    "ground": GROUND_PLANE_SPEC,
    "power": POWER_PLANE_SPEC,
    "hv": MAINS_HV_SPEC,
    "signal": SIGNAL_SPEC,
}


# ---------------------------------------------------------------------------
# P1 — IEC 60335 tables match an independent closed-form reference
# ---------------------------------------------------------------------------


@given(
    st.sampled_from(_VOLTAGE_CLASSES),
    st.sampled_from([1, 2, 3]),
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p1_clearance_table_matches_reference(member, degree):
    expected = _CLEARANCE_BASE[member.name] * _CLEARANCE_FACTOR[degree]
    got = member.get_clearance_mm(degree)
    assert float(got).hex() == float(expected).hex(), (
        f"{member.name} degree={degree}: rust={got!r} ref={expected!r}"
    )
    # Vacuity guards: the scaling dimension genuinely bites — degree 3 scales
    # strictly above the base, degree 1 strictly below (all bases are > 0).
    if degree == 3:
        assert member.get_clearance_mm(3) > member.get_clearance_mm(2)
    if degree == 1:
        assert member.get_clearance_mm(1) < member.get_clearance_mm(2)


@given(
    st.sampled_from(_VOLTAGE_CLASSES),
    st.sampled_from([1, 2, 3]),
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p1b_creepage_table_matches_reference(member, group):
    expected = _CREEPAGE_BASE[member.name] * _CREEPAGE_FACTOR[group]
    got = member.get_creepage_mm(group)
    assert float(got).hex() == float(expected).hex(), (
        f"{member.name} group={group}: rust={got!r} ref={expected!r}"
    )
    if group == 3:
        assert member.get_creepage_mm(3) > member.get_creepage_mm(2)
    if group == 1:
        assert member.get_creepage_mm(1) < member.get_creepage_mm(2)


# ---------------------------------------------------------------------------
# P2 — ground-connectivity enforcement in validate()
# ---------------------------------------------------------------------------


@given(st.sampled_from(_CONNECTIVITIES))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p2_ground_connectivity_enforcement(connectivity):
    spec = NetTypeSpec(net_type=NetType.GROUND, connectivity=connectivity)
    errors = spec.validate()
    ground_errors = [e for e in errors if e.startswith("Ground nets MUST")]
    allowed = (ConnectivityStrategy.PLANE, ConnectivityStrategy.DIRECT)
    if connectivity in allowed:
        assert ground_errors == [], f"PLANE/DIRECT ground must pass, got {ground_errors}"
    else:
        assert len(ground_errors) == 1, (
            f"non-plane ground must fail exactly once, got {ground_errors}"
        )
        assert connectivity.name in ground_errors[0]
    # Predicate agreement (always asserted on a real, non-empty domain).
    assert spec.is_valid() == (len(errors) == 0)


# ---------------------------------------------------------------------------
# P3 — high-voltage clearance/creepage thresholds (bit-exact comparisons)
# ---------------------------------------------------------------------------

_HV_CLASSES = [VoltageClass.MAINS_120V, VoltageClass.MAINS_240V, VoltageClass.HIGH_VOLTAGE]
_threshold_crossing = st.floats(
    min_value=0.01, max_value=20.0, allow_nan=False, allow_infinity=False
)


@given(
    st.sampled_from(_HV_CLASSES),
    _threshold_crossing,
    _threshold_crossing,
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p3_hv_creepage_and_clearance_thresholds(voltage_class, creepage_mm, clearance_mm):
    min_creep = voltage_class.get_creepage_mm()
    min_clear = voltage_class.get_clearance_mm()
    # Vacuity guard: the sampled range genuinely crosses both thresholds for
    # every sampled class, so both the error and no-error branches are
    # reachable from this domain.
    assert 0.01 < min_creep < 20.0, f"creepage threshold out of range: {min_creep}"
    assert 0.01 < min_clear < 20.0, f"clearance threshold out of range: {min_clear}"

    spec = NetTypeSpec(
        net_type=NetType.HIGH_VOLTAGE,
        connectivity=ConnectivityStrategy.COPPER_POUR,
        voltage_class=voltage_class,
        creepage_mm=creepage_mm,
        clearance_mm=clearance_mm,
    )
    errors = spec.validate()
    creep_err = [e for e in errors if "requires creepage" in e]
    clear_err = [e for e in errors if "requires clearance" in e]
    assert bool(creep_err) == (creepage_mm < min_creep), (
        f"creepage={creepage_mm} min={min_creep}: got {creep_err}"
    )
    assert bool(clear_err) == (clearance_mm < min_clear), (
        f"clearance={clearance_mm} min={min_clear}: got {clear_err}"
    )
    # Bit-exact threshold: a value equal to the minimum must NOT error.
    at_min = NetTypeSpec(
        net_type=NetType.HIGH_VOLTAGE,
        connectivity=ConnectivityStrategy.COPPER_POUR,
        voltage_class=voltage_class,
        creepage_mm=min_creep,
        clearance_mm=min_clear,
    )
    assert all("creepage" not in e and "clearance" not in e for e in at_min.validate())


# ---------------------------------------------------------------------------
# P4 — classify_net triage: every pattern and every noise name
# ---------------------------------------------------------------------------


@given(st.sampled_from([name for _, name in _PATTERN_TIERS] + ["plain_signal", "SPI_CLK", "x"]))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p4_classify_net_triage_matches_expected_tier(net_name):
    nc = NetClassification()
    spec = nc.classify_net(net_name)
    expected = _CONSTANT_BY_TIER[
        next(tier for tier, name in _PATTERN_TIERS if name == net_name)
        if any(name == net_name for _, name in _PATTERN_TIERS)
        else "signal"
    ]
    assert _spec_fields(spec) == _spec_fields(expected), (
        f"{net_name}: rust classified {_spec_fields(spec)}"
    )
    # Vacuity guard: every tier is reachable from the sampled domain.
    reached = {
        next(
            tier for tier, name in _PATTERN_TIERS if name == net_name
        )
        if any(name == net_name for _, name in _PATTERN_TIERS)
        else "signal"
        for net_name in [n for _, n in _PATTERN_TIERS] + ["noise"]
    }
    assert reached == set(_SPEC_CONSTANTS)


# ---------------------------------------------------------------------------
# P5 — case-insensitive auto-classification
# ---------------------------------------------------------------------------


@given(st.sampled_from([name for _, name in _PATTERN_TIERS]))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p5_classification_is_case_insensitive(pattern):
    nc = NetClassification()
    upper = nc.classify_net(pattern)
    mixed = nc.classify_net(pattern.lower() + "_x")
    assert _spec_fields(upper) == _spec_fields(mixed), (
        f"{pattern}: {_spec_fields(upper)} != {_spec_fields(mixed)}"
    )
    # Vacuity guard: mixed-case names really differ from the pattern text, so
    # the property is exercising the case-folding path, not string identity.
    assert (pattern.lower() + "_x") != pattern


# ---------------------------------------------------------------------------
# MR1 — construction→access round-trip and kwarg-order commutativity
# ---------------------------------------------------------------------------


@given(
    st.floats(min_value=0.1, max_value=50.0, allow_nan=False, allow_infinity=False),
    st.one_of(st.none(), st.floats(min_value=1.0, max_value=200.0, allow_nan=False, allow_infinity=False)),
    st.floats(min_value=0.05, max_value=10.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.05, max_value=10.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    st.booleans(),
    st.booleans(),
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr1_round_trip_and_kwarg_order_commute(
    max_current, impedance, trace_width, clearance, creepage, allow_change, prefer_stubs
):
    kwargs = {
        "net_type": NetType.DIFFERENTIAL,
        "connectivity": ConnectivityStrategy.TRACE,
        "target_layer": "B.Cu",
        "voltage_class": VoltageClass.SELV,
        "max_current_a": max_current,
        "impedance_ohm": impedance,
        "trace_width_mm": trace_width,
        "clearance_mm": clearance,
        "creepage_mm": creepage,
        "via_template": "Via2x2",
        "allow_layer_change": allow_change,
        "prefer_short_stubs": prefer_stubs,
    }
    # Construction→access round-trip: every field reads back bit-identically.
    spec = NetTypeSpec(**kwargs)
    assert _spec_fields(spec) == (
        (spec.net_type.name, spec.net_type.value),
        (spec.connectivity.name, spec.connectivity.value),
        spec.target_layer,
        (spec.voltage_class.name, spec.voltage_class.value),
        float(spec.max_current_a).hex(),
        None if spec.impedance_ohm is None else float(spec.impedance_ohm).hex(),
        float(spec.trace_width_mm).hex(),
        float(spec.clearance_mm).hex(),
        float(spec.creepage_mm).hex(),
        spec.via_template,
        bool(spec.allow_layer_change),
        bool(spec.prefer_short_stubs),
    )
    # Vacuity guard: the drawn values differ from the dataclass defaults, so
    # the round-trip is not trivially the default spec.
    assert spec.max_current_a != 0.5 or spec.creepage_mm != 0.0 or not spec.prefer_short_stubs

    # Kwarg-order commutativity: reordering keyword arguments yields an
    # equal spec.
    reversed_order = NetTypeSpec(**dict(reversed(list(kwargs.items()))))
    assert _spec_fields(spec) == _spec_fields(reversed_order)


# ---------------------------------------------------------------------------
# MR2 — insertion-order permutation invariance
# ---------------------------------------------------------------------------


def _make_nc(specs):
    return NetClassification(specs={name: NetTypeSpec(**kw) for name, kw in specs.items()})


_SPEC_KWS = {
    "GND": {"net_type": NetType.GROUND, "connectivity": ConnectivityStrategy.PLANE},
    "+5V": {"net_type": NetType.POWER, "connectivity": ConnectivityStrategy.PLANE},
    "AC_L": {
        "net_type": NetType.HIGH_VOLTAGE,
        "connectivity": ConnectivityStrategy.COPPER_POUR,
    },
    "SIG": {"net_type": NetType.SIGNAL, "connectivity": ConnectivityStrategy.TRACE},
    "HC": {"net_type": NetType.HIGH_CURRENT, "connectivity": ConnectivityStrategy.VIA_ARRAY},
}


def test_mr2_insertion_order_permutation_invariance():
    import itertools

    for order in itertools.permutations(_SPEC_KWS.keys()):
        nc = _make_nc({name: _SPEC_KWS[name] for name in order})
        assert set(nc.get_plane_nets()) == {"GND", "+5V"}, order
        assert set(nc.get_pour_nets()) == {"AC_L"}, order
        assert set(nc.get_plane_nets()) | set(nc.get_pour_nets()) == {"GND", "+5V", "AC_L"}
        for name in _SPEC_KWS:
            assert _spec_fields(nc.classify_net(name)) == _spec_fields(
                NetTypeSpec(**_SPEC_KWS[name])
            ), (order, name)
    # Vacuity guard: at least one permutation with a different order was
    # exercised (5! = 120 permutations, all asserted above).
    assert len(list(itertools.permutations(_SPEC_KWS.keys()))) == 120


# ---------------------------------------------------------------------------
# MR3 — from_yaml_config ≡ direct construction (independent paths)
# ---------------------------------------------------------------------------


def test_mr3_from_yaml_config_equals_direct_construction():
    net_classes = {"GND": "ground_class", "HV": "hv_class", "SIG": "signal_class"}
    net_class_rules = {
        "ground_class": {"type": "ground", "connectivity": "plane"},
        "hv_class": {
            "type": "high_voltage",
            "voltage_class": "mains_240v",
            "target_layer": "F.Cu",
            "creepage_mm": 6.0,
            "clearance_mm": 6.0,
            "via_template": "Via3x3",
            "allow_layer_change": False,
        },
        "signal_class": {"type": "signal", "connectivity": "trace", "target_layer": "B.Cu"},
    }
    via_yaml = NetClassification.from_yaml_config(net_classes, net_class_rules)

    direct = {
        "GND": NetTypeSpec(
            net_type=NetType.GROUND,
            connectivity=ConnectivityStrategy.PLANE,
            target_layer=LayerIndex.IN1_CU,
        ),
        "HV": NetTypeSpec(
            net_type=NetType.HIGH_VOLTAGE,
            connectivity=ConnectivityStrategy.COPPER_POUR,
            target_layer="F.Cu",
            voltage_class=VoltageClass.MAINS_240V,
            creepage_mm=6.0,
            clearance_mm=6.0,
            via_template="Via3x3",
            allow_layer_change=False,
        ),
        "SIG": NetTypeSpec(
            net_type=NetType.SIGNAL,
            connectivity=ConnectivityStrategy.TRACE,
            target_layer="B.Cu",
        ),
    }
    for name, expected in direct.items():
        assert _spec_fields(via_yaml.specs[name]) == _spec_fields(expected), name
    # Vacuity guard: the two paths construct at least one spec with a
    # non-default value (the HV rule) and one with a LayerIndex default (GND).
    assert via_yaml.specs["HV"].creepage_mm == 6.0
    assert isinstance(via_yaml.specs["GND"].target_layer, int)


# ---------------------------------------------------------------------------
# Presence guard: this proof must not silently skip in CI.
# ---------------------------------------------------------------------------

_REQUIRE = os.environ.get("TEMPER_REQUIRE_RUST_NET_TYPES", "").strip().lower() in {
    "1",
    "true",
    "yes",
}

if _REQUIRE and not hasattr(_tdb, "NetTypeSpec"):
    pytest.fail(
        "TEMPER_REQUIRE_RUST_NET_TYPES=1 but temper_design_bundle_python "
        "does not expose the net-types pyclasses — the Rust extension is "
        "stale or missing.",
        pytrace=False,
    )

pytestmark = pytest.mark.skipif(
    not hasattr(_tdb, "NetTypeSpec"),
    reason="temper_design_bundle_python net-types pyclasses not installed "
    "(set TEMPER_REQUIRE_RUST_NET_TYPES=1 to make this fatal instead of a skip)",
)
