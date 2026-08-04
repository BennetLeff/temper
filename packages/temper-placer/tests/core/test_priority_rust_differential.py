"""Differential test: Rust priority pyclasses (temper_design_bundle_python) vs
the pinned Python oracle.

Wave 4, Phase 2 — the contracts-as-pyo3-pyclasses pivot (plan
``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``,
D5 / Phase B). This is the FIFTH Wave-4 Phase 2 migration; it mirrors the
loop migration (``test_loop_rust_differential.py``) exactly.

The Rust pyo3 pyclasses ``PlacementPriority``, ``RoutingPriority``,
``PlacementPhaseConfig``, ``RoutingPhaseConfig``, ``PriorityConfig`` (in
``temper_design_bundle_python``, from the ``temper-design-bundle`` crate)
must reproduce the pre-migration Python implementation of
``temper_placer/core/priority.py`` bit-identically. The pre-migration
implementation is pinned verbatim as the oracle
(``_priority_py_oracle.py``, commit a47527751) and every assertion here
drives IDENTICAL inputs through both sides.

Comparison convention (mirrors the loop differential): objects are
canonicalized into plain comparable tuples before assertion. Floats are
compared as exact bit patterns via ``float.hex()``.

Enum parity is checked via ``getattr(rust_enum, name)`` rather than
class-level iteration (``for m in rust_enum``): a pyo3 ``#[pyclass]``
enum cannot implement class-level ``__iter__`` — Python class iteration
requires the *metaclass* to define ``__iter__``, and pyo3 exposes no
metaclass hook. ``getattr`` covers every member, so the parity proof is
identical; only the accessor differs.

Known, documented deviation (asserted only on the Python side here, per the
gates precedent): ``PlacementPriority``/``RoutingPriority`` are Python
``IntEnum``s, whose members compare ``==`` to their int value
(``PlacementPriority.POWER == 1`` is True). The pyclass members are NOT
equal to ints. No consumer in-repo relies on the int comparison (verified
2026-08-03: no ``PlacementPriority.* == <int>`` or ``<int> == ...``
expressions anywhere in ``src/`` or ``tests/``); recorded in
``packages/temper-design-bundle/VERIFICATION.md``.
"""

from __future__ import annotations

import pytest
import temper_design_bundle_python as _tdb

import tests.core._priority_py_oracle as _oracle

# Rust symbols under test — must exist or this file fails to collect (RED).
PLACEMENT_PRIORITY = _tdb.PlacementPriority
ROUTING_PRIORITY = _tdb.RoutingPriority
PLACEMENT_PHASE_CONFIG = _tdb.PlacementPhaseConfig
ROUTING_PHASE_CONFIG = _tdb.RoutingPhaseConfig
PRIORITY_CONFIG = _tdb.PriorityConfig


# ---------------------------------------------------------------------------
# Canonicalization helpers (field-level extraction, bit-exact floats).
# ---------------------------------------------------------------------------


def _f(value):
    """Bit-exact float key: None stays None, else float.hex()."""
    return None if value is None else float(value).hex()


def _placement_phase_fields(pc):
    return (
        pc.name,
        (pc.priority.name, pc.priority.value),
        tuple(pc.components),
        pc.method,
        pc.template,
        None if pc.anchor is None else (_f(pc.anchor[0]), _f(pc.anchor[1])),
        pc.reference,
        _f(pc.max_distance_mm),
        pc.zone,
    )


def _routing_phase_fields(rc):
    return (
        rc.name,
        (rc.priority.name, rc.priority.value),
        tuple(rc.nets),
        _f(rc.trace_width_mm),
        _f(rc.via_cost),
        rc.allow_layer_change,
        _f(rc.max_length_mm) if rc.max_length_mm is not None else None,
    )


def _priority_config_fields(cfg):
    return (
        tuple(_placement_phase_fields(p) for p in cfg.placement_phases),
        tuple(_routing_phase_fields(r) for r in cfg.routing_phases),
    )


# ---------------------------------------------------------------------------
# Enum parity: names, values, str/repr, value-construction (IntEnum style).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "py_enum,rust_enum",
    [(_oracle.PlacementPriority, PLACEMENT_PRIORITY), (_oracle.RoutingPriority, ROUTING_PRIORITY)],
)
def test_enum_members_name_and_value_parity(py_enum, rust_enum):
    """Every enum member: identical name and identical int value."""
    py_names = [m.name for m in py_enum]
    rust_names = [getattr(rust_enum, n).name for n in py_names]
    assert rust_names == py_names, f"{py_enum.__name__}: names differ"
    py_values = [m.value for m in py_enum]
    rust_values = [getattr(rust_enum, n).value for n in py_names]
    assert rust_values == py_values, f"{py_enum.__name__}: values differ"


@pytest.mark.parametrize(
    "py_enum,rust_enum",
    [(_oracle.PlacementPriority, PLACEMENT_PRIORITY), (_oracle.RoutingPriority, ROUTING_PRIORITY)],
)
def test_enum_str_and_repr_identical(py_enum, rust_enum):
    """``str(member)`` == ``"1"`` (IntEnum's ``str`` is ``int.__str__``)
    and ``repr(member)`` == ``<PlacementPriority.POWER: 1>`` — the CPython
    IntEnum rendering (int value, unquoted)."""
    for py_member in py_enum:
        rust_member = getattr(rust_enum, py_member.name)
        assert str(rust_member) == str(py_member), py_member.name
        assert repr(rust_member) == repr(py_member), py_member.name


@pytest.mark.parametrize(
    "py_enum,rust_enum",
    [(_oracle.PlacementPriority, PLACEMENT_PRIORITY), (_oracle.RoutingPriority, ROUTING_PRIORITY)],
)
def test_enum_value_construction_identical(py_enum, rust_enum):
    """``Cls(value)`` resolves by int value like Python IntEnum."""
    for py_member in py_enum:
        rust_member = rust_enum(py_member.value)
        assert rust_member.name == py_member.name
        assert rust_member == getattr(rust_enum, py_member.name)
    with pytest.raises(ValueError) as py_exc:
        py_enum(999)
    with pytest.raises(ValueError) as rust_exc:
        rust_enum(999)
    assert str(rust_exc.value) == str(py_exc.value)


def test_enum_member_equality_and_dict_key_usage():
    """Members compare equal to themselves, unequal to other members, and
    hash stably (the dict-key pattern)."""
    assert PLACEMENT_PRIORITY.POWER == PLACEMENT_PRIORITY.POWER
    assert PLACEMENT_PRIORITY.POWER != PLACEMENT_PRIORITY.DIGITAL
    assert hash(PLACEMENT_PRIORITY.POWER) == hash(PLACEMENT_PRIORITY.POWER)
    d = {PLACEMENT_PRIORITY.POWER: "p"}
    assert d[PLACEMENT_PRIORITY.POWER] == "p"
    assert ROUTING_PRIORITY.AUTO.value == 10
    assert ROUTING_PRIORITY(10) == ROUTING_PRIORITY.AUTO


# ---------------------------------------------------------------------------
# PlacementPhaseConfig / RoutingPhaseConfig: defaults, round-trip, repr, eq.
# ---------------------------------------------------------------------------


def test_placement_phase_defaults_identical():
    py = _oracle.PlacementPhaseConfig(name="p", priority=_oracle.PlacementPriority.POWER)
    rust = PLACEMENT_PHASE_CONFIG(name="p", priority=PLACEMENT_PRIORITY.POWER)
    assert _placement_phase_fields(rust) == _placement_phase_fields(py)


def test_placement_phase_full_round_trip_identical():
    py = _oracle.PlacementPhaseConfig(
        name="power",
        priority=_oracle.PlacementPriority.POWER,
        components=["Q1", "Q2", "C_BUS1"],
        method="template",
        template="half_bridge_vertical",
        anchor=(1.5, -2.25),
        reference="Q1",
        max_distance_mm=12.5,
        zone="HV_ZONE",
    )
    rust = PLACEMENT_PHASE_CONFIG(
        name="power",
        priority=PLACEMENT_PRIORITY.POWER,
        components=["Q1", "Q2", "C_BUS1"],
        method="template",
        template="half_bridge_vertical",
        anchor=(1.5, -2.25),
        reference="Q1",
        max_distance_mm=12.5,
        zone="HV_ZONE",
    )
    assert _placement_phase_fields(rust) == _placement_phase_fields(py)
    # Fresh default_factory list per instance (never shared).
    a = PLACEMENT_PHASE_CONFIG(name="a", priority=PLACEMENT_PRIORITY.POWER)
    b = PLACEMENT_PHASE_CONFIG(name="b", priority=PLACEMENT_PRIORITY.POWER)
    assert a.components == []
    assert b.components == []
    assert a.components is not b.components


def test_routing_phase_defaults_and_round_trip_identical():
    py_default = _oracle.RoutingPhaseConfig(name="r", priority=_oracle.RoutingPriority.POWER)
    rust_default = ROUTING_PHASE_CONFIG(name="r", priority=ROUTING_PRIORITY.POWER)
    assert _routing_phase_fields(rust_default) == _routing_phase_fields(py_default)

    py = _oracle.RoutingPhaseConfig(
        name="gate_drive",
        priority=_oracle.RoutingPriority.GATE_DRIVE,
        nets=["GATE_*", "BOOT*"],
        trace_width_mm=0.5,
        via_cost=2.0,
        allow_layer_change=False,
        max_length_mm=25.0,
    )
    rust = ROUTING_PHASE_CONFIG(
        name="gate_drive",
        priority=ROUTING_PRIORITY.GATE_DRIVE,
        nets=["GATE_*", "BOOT*"],
        trace_width_mm=0.5,
        via_cost=2.0,
        allow_layer_change=False,
        max_length_mm=25.0,
    )
    assert _routing_phase_fields(rust) == _routing_phase_fields(py)


def test_phase_config_repr_identical():
    py = _oracle.PlacementPhaseConfig(
        name="power",
        priority=_oracle.PlacementPriority.POWER,
        components=["Q1"],
        method="template",
        template="half_bridge_vertical",
        anchor=(1.5, -2.25),
        reference="Q1",
        max_distance_mm=12.5,
        zone="HV_ZONE",
    )
    rust = PLACEMENT_PHASE_CONFIG(
        name="power",
        priority=PLACEMENT_PRIORITY.POWER,
        components=["Q1"],
        method="template",
        template="half_bridge_vertical",
        anchor=(1.5, -2.25),
        reference="Q1",
        max_distance_mm=12.5,
        zone="HV_ZONE",
    )
    assert repr(rust) == repr(py)
    assert rust == PLACEMENT_PHASE_CONFIG(
        name="power",
        priority=PLACEMENT_PRIORITY.POWER,
        components=["Q1"],
        method="template",
        template="half_bridge_vertical",
        anchor=(1.5, -2.25),
        reference="Q1",
        max_distance_mm=12.5,
        zone="HV_ZONE",
    )
    assert rust != PLACEMENT_PHASE_CONFIG(name="other", priority=PLACEMENT_PRIORITY.POWER)

    py_r = _oracle.RoutingPhaseConfig(name="r", priority=_oracle.RoutingPriority.AUTO)
    rust_r = ROUTING_PHASE_CONFIG(name="r", priority=ROUTING_PRIORITY.AUTO)
    assert repr(rust_r) == repr(py_r)
    assert rust_r == ROUTING_PHASE_CONFIG(name="r", priority=ROUTING_PRIORITY.AUTO)
    assert rust_r != ROUTING_PHASE_CONFIG(name="r", priority=ROUTING_PRIORITY.POWER)


# ---------------------------------------------------------------------------
# PriorityConfig: phase lookup + classification (the migrated logic).
# ---------------------------------------------------------------------------


def _make_configs():
    py = _oracle.PriorityConfig(
        placement_phases=[
            _oracle.PlacementPhaseConfig(
                name="power", priority=_oracle.PlacementPriority.POWER, components=["Q1", "D1"]
            ),
            _oracle.PlacementPhaseConfig(
                name="analog", priority=_oracle.PlacementPriority.ANALOG, components=["U_OPAMP1"]
            ),
        ],
        routing_phases=[
            _oracle.RoutingPhaseConfig(
                name="power", priority=_oracle.RoutingPriority.POWER, nets=["BUS*", "340V"]
            ),
            _oracle.RoutingPhaseConfig(
                name="high_speed",
                priority=_oracle.RoutingPriority.HIGH_SPEED,
                nets=["SPI1", "I2C0"],
            ),
        ],
    )
    rust = PRIORITY_CONFIG(
        placement_phases=[
            PLACEMENT_PHASE_CONFIG(
                name="power", priority=PLACEMENT_PRIORITY.POWER, components=["Q1", "D1"]
            ),
            PLACEMENT_PHASE_CONFIG(
                name="analog", priority=PLACEMENT_PRIORITY.ANALOG, components=["U_OPAMP1"]
            ),
        ],
        routing_phases=[
            ROUTING_PHASE_CONFIG(
                name="power", priority=ROUTING_PRIORITY.POWER, nets=["BUS*", "340V"]
            ),
            ROUTING_PHASE_CONFIG(
                name="high_speed", priority=ROUTING_PRIORITY.HIGH_SPEED, nets=["SPI1", "I2C0"]
            ),
        ],
    )
    return py, rust


def test_priority_config_round_trip_identical():
    py, rust = _make_configs()
    assert _priority_config_fields(rust) == _priority_config_fields(py)
    assert repr(rust) == repr(py)
    assert rust == PRIORITY_CONFIG(
        placement_phases=list(rust.placement_phases), routing_phases=list(rust.routing_phases)
    )


def test_get_phase_identical():
    py, rust = _make_configs()
    for p in _oracle.PlacementPriority:
        py_phase = py.get_placement_phase(p)
        rust_phase = rust.get_placement_phase(getattr(PLACEMENT_PRIORITY, p.name))
        assert (rust_phase is None) == (py_phase is None), p.name
        if py_phase is not None:
            assert _placement_phase_fields(rust_phase) == _placement_phase_fields(py_phase)
    for r in _oracle.RoutingPriority:
        py_phase = py.get_routing_phase(r)
        rust_phase = rust.get_routing_phase(getattr(ROUTING_PRIORITY, r.name))
        assert (rust_phase is None) == (py_phase is None), r.name
        if py_phase is not None:
            assert _routing_phase_fields(rust_phase) == _routing_phase_fields(py_phase)


@pytest.mark.parametrize(
    "ref",
    [
        "Q1",  # explicit assignment in placement_phases
        "U_OPAMP1",  # explicit assignment
        "Q2",
        "D7",
        "C_BUS3",  # POWER prefix defaults
        "U_GATE1",
        "R_GATE2",
        "C_BOOT1",
        "C_VCC1",  # DRIVER prefix defaults
        "U_MCU1",
        "Y1",
        "X2",  # HIGH_SPEED prefix defaults
        "U_OPAMP2",
        "U_CT1",
        "R_BURDEN1",  # ANALOG prefix defaults
        "R1",
        "C1",
        "J1",
        "U_UNKNOWN",  # DIGITAL fallback
        "Q10",  # digit-stripping: prefix Q
        "C_BUS10",  # digit-stripping: prefix C_BUS
    ],
)
def test_classify_component_identical(ref):
    """classify_component: explicit assignments first, then prefix rules —
    identical on both sides. The ``_netlist`` arg is unused by the oracle;
    a dummy object is passed on both sides."""
    py, rust = _make_configs()
    assert rust.classify_component(ref, object()).name == py.classify_component(ref, object()).name


@pytest.mark.parametrize(
    "net_name",
    [
        # Explicit exact pattern wins over keyword defaults.
        "340V",
        "SPI1",
        # Explicit wildcard pattern (BUS*).
        "BUS_5V",
        "BUS_MAIN",
        "BUS",
        # POWER keyword boundaries — the 2026-07-27 bug-history regression set.
        "BUS1",
        "BUS_12V",
        "PWR_BUS",
        "MY_BUS",
        "BUS_A",
        "BUS0",
        "340V_NET",
        "SW_NODE",
        "HV_SW",
        "HV",
        # Non-boundary POWER negatives: substring must NOT match.
        "BUSTER",
        "BUSBAR",
        "BHV",
        "ABUS",
        "HVX",
        "AHV",
        # GATE_DRIVE keyword boundaries.
        "GATE_DRV",
        "GATE",
        "GATE1",
        "+15V",
        "+15V_2",
        "CGND",
        "MY_CGND",
        "MY_GATE",
        # Non-boundary GATE_DRIVE negatives.
        "AGATE",
        "GATEWAY",
        "GATED",
        # HIGH_SPEED substring classes.
        "SPI1",
        "I2C0",
        "USB",
        "CLK",
        "MCU_CLK",
        "SPI_MISO",
        # ANALOG substring classes.
        "SENSE",
        "NTC1",
        "RTD2",
        "V_SENSE",
        "NTC",
        # DIGITAL fallback.
        "3V3",
        "VCC",
        "GND",
        "PWM1",
        "LED",
        "R_1K",
        "D1",
        "Q1",
    ],
)
def test_classify_net_identical(net_name):
    """classify_net: explicit phases first, then keyword boundary rules —
    identical on both sides, including the word-boundary regression set."""
    py, rust = _make_configs()
    assert rust.classify_net(net_name).name == py.classify_net(net_name).name


def test_classify_net_default_config_identical():
    """The no-phases config exercises the pure keyword defaults."""
    py = _oracle.PriorityConfig()
    rust = PRIORITY_CONFIG()
    for net_name in ["HV_SW", "GATE_DRV", "SPI1", "SENSE", "3V3", "BUS", "SW_NODE"]:
        assert rust.classify_net(net_name).name == py.classify_net(net_name).name


def test_classify_net_priority_delegation_identical():
    """The module-level ``classify_net_priority`` convenience wrapper (kept
    Python, delegating to the pyclass) matches the oracle's."""
    from temper_placer.core.priority import classify_net_priority

    for net_name in ["HV_SW", "BUS_12V", "GATE_DRV", "SPI1", "SENSE", "3V3", "NTC"]:
        assert classify_net_priority(net_name).name == _oracle.classify_net_priority(net_name).name
