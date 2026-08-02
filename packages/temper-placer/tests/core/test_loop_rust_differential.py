"""Differential test: Rust loop pyclasses (temper_design_bundle_python) vs
the pinned Python oracle.

Wave 4, Phase 2 — the contracts-as-pyo3-pyclasses pivot (plan
``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``,
D5 / Phase B). This is the SECOND Wave-4 Phase 2 migration; it mirrors the
net-types migration (``test_net_types_rust_differential.py``) exactly.

The Rust pyo3 pyclasses ``LoopType``, ``LoopPriority``, ``LoopEvent``,
``LoopPin``, ``Loop``, ``LoopCollection`` (in ``temper_design_bundle_python``,
from the ``temper-design-bundle`` crate) must reproduce the pre-migration
Python implementation of ``temper_placer/core/loop.py`` bit-identically.
The pre-migration implementation is pinned verbatim as the oracle
(``_loop_py_oracle.py``, commit 76f38db0a) and every assertion here drives
IDENTICAL inputs through both sides.

Comparison convention (mirrors the net-types differential): objects are
canonicalized into plain comparable tuples before assertion. Floats are
compared as exact bit patterns via ``float.hex()``.

Enum parity is checked via ``getattr(rust_enum, name)`` rather than
class-level iteration (``for m in rust_enum``): a pyo3 ``#[pyclass]``
enum cannot implement class-level ``__iter__`` — Python class iteration
requires the *metaclass* to define ``__iter__``, and pyo3 exposes no
metaclass hook. ``getattr`` covers every member, so the parity proof is
identical; only the accessor differs.

Known, deliberately-asserted consumer adaptation: ``io/loop_loader.py``
iterated these enums at class level (``for lt in LoopType:``) to resolve
members by string value — the pre-migration code path for YAML loop
templates. pyo3 enums cannot support class-level iteration, so the
pyclass exposes a ``#[staticmethod] members()`` (all members, declaration
order) and ``loop_loader.py`` was adapted to use it; behavior is
identical (same members, same order, same ValueError message). Value-based
construction ``LoopType("commutation")`` — used by
``core/loop_extractor_rs.py`` — IS supported on the pyclass via ``#[new]``
and raises the same ``ValueError`` text on unknown values.
"""

from __future__ import annotations

import os

import pytest
import temper_design_bundle_python as _tdb

import tests.core._loop_py_oracle as _oracle

# Rust symbols under test — must exist or this file fails to collect (RED).
LOOP_TYPE = _tdb.LoopType
LOOP_PRIORITY = _tdb.LoopPriority
LOOP_EVENT = _tdb.LoopEvent
LOOP_PIN = _tdb.LoopPin
LOOP = _tdb.Loop
LOOP_COLLECTION = _tdb.LoopCollection


# ---------------------------------------------------------------------------
# Canonicalization helpers (field-level extraction, bit-exact floats).
# ---------------------------------------------------------------------------


def _f(value):
    """Bit-exact float key: None stays None, else float.hex()."""
    return None if value is None else float(value).hex()


def _event_fields(event):
    return (
        _f(event.di_dt),
        _f(event.dv_dt),
        _f(event.frequency_hz),
        _f(event.peak_current_a),
        _f(event.rms_current_a),
        _f(event.ringing_freq_hz),
    )


def _pin_fields(pin):
    return (pin.component_ref, pin.pin_name, pin.net_name)


def _loop_fields(loop):
    """Extract every Loop field into a comparable tuple.

    Enums by ``(name, value)``; floats by bit pattern; ``events`` via
    ``_event_fields``; pins element-wise via ``_pin_fields``; the cached
    current area via ``get_current_area()`` (the dataclass's
    ``_current_area_mm2`` field participates in dataclass equality, so the
    canonical form carries it too).
    """
    return (
        loop.name,
        (loop.loop_type.name, loop.loop_type.value),
        loop.description,
        tuple(_pin_fields(p) for p in loop.pins),
        tuple(loop.components),
        tuple(loop.nets),
        _f(loop.max_area_mm2),
        (loop.priority.name, loop.priority.value),
        _event_fields(loop.events),
        loop.return_layer,
        loop.return_net,
        loop.source,
        _f(loop.get_current_area()),
    )


def _collection_fields(nc):
    """Extract a LoopCollection into a comparable mapping."""
    return {
        "loops": tuple(_loop_fields(loop) for loop in nc.loops),
        "name": nc.name,
        "description": nc.description,
    }


# ---------------------------------------------------------------------------
# Enum parity: names, string values, str/repr, value-construction.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "py_enum,rust_enum",
    [(_oracle.LoopType, LOOP_TYPE), (_oracle.LoopPriority, LOOP_PRIORITY)],
)
def test_enum_members_name_and_value_parity(py_enum, rust_enum):
    """Every enum member: identical name and identical string value."""
    py_names = [m.name for m in py_enum]
    rust_names = [getattr(rust_enum, n).name for n in py_names]
    assert rust_names == py_names, f"{py_enum.__name__}: names differ"
    py_values = [m.value for m in py_enum]
    rust_values = [getattr(rust_enum, n).value for n in py_names]
    assert rust_values == py_values, f"{py_enum.__name__}: values differ"


@pytest.mark.parametrize(
    "py_enum,rust_enum",
    [(_oracle.LoopType, LOOP_TYPE), (_oracle.LoopPriority, LOOP_PRIORITY)],
)
def test_enum_str_and_repr_identical(py_enum, rust_enum):
    """``str(member)`` == ``LoopType.COMMUTATION`` and
    ``repr(member)`` == ``<LoopType.COMMUTATION: 'commutation'>`` — the
    CPython Enum rendering (note the QUOTED string value in repr, unlike
    the auto()/int net-types repr which had no quotes)."""
    for py_member in py_enum:
        rust_member = getattr(rust_enum, py_member.name)
        assert str(rust_member) == str(py_member), py_member.name
        assert repr(rust_member) == repr(py_member), py_member.name


def test_loop_type_value_construction_identical():
    """``LoopType("commutation")`` value-based construction (used by
    ``core/loop_extractor_rs.py``) resolves like Python Enum."""
    for py_member in _oracle.LoopType:
        rust_member = LOOP_TYPE(py_member.value)
        assert rust_member.name == py_member.name
        assert rust_member == getattr(LOOP_TYPE, py_member.name)
    # Same ValueError type AND text on unknown values.
    with pytest.raises(ValueError) as py_exc:
        _oracle.LoopType("bogus_loop")
    with pytest.raises(ValueError) as rust_exc:
        LOOP_TYPE("bogus_loop")
    assert str(rust_exc.value) == str(py_exc.value)


def test_loop_priority_value_construction_identical():
    for py_member in _oracle.LoopPriority:
        rust_member = LOOP_PRIORITY(py_member.value)
        assert rust_member.name == py_member.name
    with pytest.raises(ValueError):
        LOOP_PRIORITY("bogus_priority")


def test_enum_member_not_equal_to_string():
    """Python plain Enum: LoopType.COMMUTATION == "commutation" is False
    (unlike a str-valued IntEnum). The pyclass must not coerce to its
    string value — a silent semantic change would flip consumer branches
    that compare member identity (e.g. the ``_LOOP_TYPE_PRIORITY`` dict
    lookups in ``core/loop_extractor_rs.py``)."""
    from temper_placer.core.loop import LoopType

    assert LoopType.COMMUTATION != "commutation"
    assert LoopType.COMMUTATION != "commutation"
    # Members compare equal to themselves and hash like Enum members.
    assert LoopType.COMMUTATION == LoopType.COMMUTATION
    assert hash(LoopType.COMMUTATION) == hash(LoopType.COMMUTATION)
    # dict keys (the extractor's pattern).
    d = {LoopType.COMMUTATION: 1}
    assert d[LoopType.COMMUTATION] == 1


# ---------------------------------------------------------------------------
# LoopEvent: defaults, round-trip, physics methods (bit-exact).
# ---------------------------------------------------------------------------


def test_event_defaults_identical():
    assert _event_fields(LOOP_EVENT()) == _event_fields(_oracle.LoopEvent())


def test_event_construction_all_fields_round_trip():
    kwargs = {
        "di_dt": 1e9,
        "dv_dt": 1e10,
        "frequency_hz": 50000.0,
        "peak_current_a": 50.0,
        "rms_current_a": 25.0,
        "ringing_freq_hz": 10e6,
    }
    py_event = _oracle.LoopEvent(**kwargs)
    rust_event = LOOP_EVENT(**kwargs)
    assert _event_fields(rust_event) == _event_fields(py_event)


@pytest.mark.parametrize("area_mm2", [0.5, 1.0, 50.0, 100.0, 200.0, 1234.567])
@pytest.mark.parametrize("trace_height_mm", [0.05, 0.2, 1.6])
def test_estimated_inductance_nh_bit_identical(area_mm2, trace_height_mm):
    py_result = _oracle.LoopEvent().estimated_inductance_nh(area_mm2, trace_height_mm)
    rust_result = LOOP_EVENT().estimated_inductance_nh(area_mm2, trace_height_mm)
    assert float(rust_result).hex() == float(py_result).hex(), (
        f"area={area_mm2} h={trace_height_mm}: rust={rust_result!r} py={py_result!r}"
    )


@pytest.mark.parametrize("target_nh", [0.5, 10.0, 100.0, 628.3185307179587])
@pytest.mark.parametrize("trace_height_mm", [0.05, 0.2, 1.6])
def test_max_area_for_inductance_nh_bit_identical(target_nh, trace_height_mm):
    py_result = _oracle.LoopEvent().max_area_for_inductance_nh(target_nh, trace_height_mm)
    rust_result = LOOP_EVENT().max_area_for_inductance_nh(target_nh, trace_height_mm)
    assert float(rust_result).hex() == float(py_result).hex(), (
        f"target={target_nh} h={trace_height_mm}: rust={rust_result!r} py={py_result!r}"
    )


def test_voltage_spike_bit_identical():
    event_kwargs = {"di_dt": 1e9, "dv_dt": 5e9}
    py_event = _oracle.LoopEvent(**event_kwargs)
    rust_event = LOOP_EVENT(**event_kwargs)
    for inductance_nh in (62.83185307179586, 0.5, 1e6):
        py_result = py_event.voltage_spike_v(inductance_nh)
        rust_result = rust_event.voltage_spike_v(inductance_nh)
        assert float(rust_result).hex() == float(py_result).hex(), inductance_nh
    # di_dt = None -> None on both sides.
    assert LOOP_EVENT().voltage_spike_v(10.0) is None
    assert _oracle.LoopEvent().voltage_spike_v(10.0) is None


# ---------------------------------------------------------------------------
# LoopPin: positional + keyword construction, __str__.
# ---------------------------------------------------------------------------


def test_pin_construction_positional_and_keyword():
    py_pin = _oracle.LoopPin("C_DC", "POS", "DC_BUS+")
    rust_pin = LOOP_PIN("C_DC", "POS", "DC_BUS+")
    assert _pin_fields(rust_pin) == _pin_fields(py_pin)

    py_pin2 = _oracle.LoopPin(component_ref="Q1", pin_name="GATE")
    rust_pin2 = LOOP_PIN(component_ref="Q1", pin_name="GATE")
    assert _pin_fields(rust_pin2) == _pin_fields(py_pin2)


def test_pin_str_identical():
    py_with = _oracle.LoopPin("Q1", "GATE", "GATE_H")
    rust_with = LOOP_PIN("Q1", "GATE", "GATE_H")
    assert str(rust_with) == str(py_with) == "Q1.GATE (GATE_H)"
    py_without = _oracle.LoopPin("Q1", "GATE")
    rust_without = LOOP_PIN("Q1", "GATE")
    assert str(rust_without) == str(py_without) == "Q1.GATE"


# ---------------------------------------------------------------------------
# Loop: all-field round-trip, defaults, query/area methods.
# ---------------------------------------------------------------------------


def test_loop_construction_all_fields_round_trip():
    kwargs = {
        "name": "commutation",
        "loop_type": "COMMUTATION",
        "description": "Main half-bridge commutation loop",
        "pins": [
            {"component_ref": "C_DC", "pin_name": "POS", "net_name": "DC_BUS+"},
            {"component_ref": "Q1", "pin_name": "COLLECTOR", "net_name": "DC_BUS+"},
        ],
        "components": ["C_DC", "Q1", "Q2"],
        "nets": ["DC_BUS+", "SW_NODE", "DC_BUS-"],
        "max_area_mm2": 200.0,
        "priority": "CRITICAL",
        "events": {"di_dt": 1e9, "peak_current_a": 50.0},
        "return_layer": "L2_GND",
        "return_net": "PGND",
        "source": "template",
    }
    py_kwargs, rust_kwargs = _split_enum_kwargs(kwargs)
    py_loop = _oracle.Loop(**py_kwargs)
    rust_loop = LOOP(**rust_kwargs)
    assert _loop_fields(rust_loop) == _loop_fields(py_loop)


def test_loop_construction_defaults_identical():
    py_loop = _oracle.Loop(name="x", loop_type=_oracle.LoopType.CUSTOM, description="d")
    rust_loop = LOOP(name="x", loop_type=LOOP_TYPE.CUSTOM, description="d")
    assert _loop_fields(rust_loop) == _loop_fields(py_loop)


def _split_enum_kwargs(kwargs):
    """Map string enum names in ``kwargs`` to each side's enum members, and
    expand ``events`` dicts / ``pins`` dict-lists into each side's LoopEvent
    / LoopPin instances."""
    py_kwargs, rust_kwargs = dict(kwargs), dict(kwargs)
    for key, (py_enum, rust_enum) in {
        "loop_type": (_oracle.LoopType, LOOP_TYPE),
        "priority": (_oracle.LoopPriority, LOOP_PRIORITY),
    }.items():
        if key in py_kwargs and isinstance(py_kwargs[key], str):
            name = py_kwargs[key]
            py_kwargs[key] = py_enum[name]
            rust_kwargs[key] = getattr(rust_enum, name)
    if "events" in py_kwargs and isinstance(py_kwargs["events"], dict):
        py_kwargs["events"] = _oracle.LoopEvent(**py_kwargs["events"])
        rust_kwargs["events"] = LOOP_EVENT(**rust_kwargs["events"])
    if (
        "pins" in py_kwargs
        and isinstance(py_kwargs["pins"], list)
        and py_kwargs["pins"]
        and isinstance(py_kwargs["pins"][0], dict)
    ):
        py_kwargs["pins"] = [_oracle.LoopPin(**p) for p in py_kwargs["pins"]]
        rust_kwargs["pins"] = [LOOP_PIN(**p) for p in rust_kwargs["pins"]]
    return py_kwargs, rust_kwargs


def test_loop_get_component_refs_from_components_identical():
    kwargs = {
        "name": "gate_drive_high",
        "loop_type": "GATE_DRIVE_HIGH",
        "description": "d",
        "components": ["U_GATE_DRV", "Q1", "R_GATE"],
    }
    py_kwargs, rust_kwargs = _split_enum_kwargs(kwargs)
    py_loop = _oracle.Loop(**py_kwargs)
    rust_loop = LOOP(**rust_kwargs)
    assert rust_loop.get_component_refs() == py_loop.get_component_refs()


def test_loop_get_component_refs_from_pins_identical():
    """Pins-only loop: unique refs in first-appearance order."""
    kwargs = {
        "name": "commutation",
        "loop_type": "COMMUTATION",
        "description": "d",
        "pins": [
            {"component_ref": "C_DC", "pin_name": "POS"},
            {"component_ref": "Q1", "pin_name": "COLLECTOR"},
            {"component_ref": "Q1", "pin_name": "EMITTER"},
            {"component_ref": "C_DC", "pin_name": "NEG"},
        ],
    }
    py_kwargs, rust_kwargs = _split_enum_kwargs(kwargs)
    py_loop = _oracle.Loop(**py_kwargs)
    rust_loop = LOOP(**rust_kwargs)
    assert rust_loop.get_component_refs() == py_loop.get_component_refs() == ["C_DC", "Q1"]


def test_loop_involves_queries_identical():
    kwargs = {
        "name": "commutation",
        "loop_type": "COMMUTATION",
        "description": "d",
        "components": ["C_DC", "Q1", "Q2"],
        "nets": ["DC_BUS+", "SW_NODE"],
        "pins": [{"component_ref": "Q1", "pin_name": "EMITTER", "net_name": "SW_NODE"}],
    }
    py_kwargs, rust_kwargs = _split_enum_kwargs(kwargs)
    py_loop = _oracle.Loop(**py_kwargs)
    rust_loop = LOOP(**rust_kwargs)
    for ref in ("Q1", "C_DC", "NOPE"):
        assert rust_loop.involves_component(ref) == py_loop.involves_component(ref), ref
    for net in ("SW_NODE", "DC_BUS+", "NOPE"):
        assert rust_loop.involves_net(net) == py_loop.involves_net(net), net


def test_loop_area_lifecycle_identical():
    """set_current_area / get_current_area / is_area_compliant /
    area_margin_pct / estimated_voltage_spike — full lifecycle, bit-exact."""
    kwargs = {
        "name": "commutation",
        "loop_type": "COMMUTATION",
        "description": "d",
        "max_area_mm2": 200.0,
        "priority": "CRITICAL",
        "events": {"di_dt": 1e9},
    }
    py_kwargs, rust_kwargs = _split_enum_kwargs(kwargs)
    py_loop = _oracle.Loop(**py_kwargs)
    rust_loop = LOOP(**rust_kwargs)

    assert rust_loop.get_current_area() is None
    assert rust_loop.is_area_compliant() is None
    assert rust_loop.area_margin_pct() is None
    assert rust_loop.estimated_voltage_spike() is None

    for area in (40.0, 250.0, 200.0):
        py_loop.set_current_area(area)
        rust_loop.set_current_area(area)
        assert float(rust_loop.get_current_area()).hex() == float(py_loop.get_current_area()).hex()
        assert rust_loop.is_area_compliant() == py_loop.is_area_compliant()
        assert float(rust_loop.area_margin_pct()).hex() == float(
            py_loop.area_margin_pct()
        ).hex()
        rust_spike = rust_loop.estimated_voltage_spike()
        py_spike = py_loop.estimated_voltage_spike()
        assert (rust_spike is None) == (py_spike is None)
        if py_spike is not None:
            assert float(rust_spike).hex() == float(py_spike).hex()


# ---------------------------------------------------------------------------
# LoopCollection: construction, add, queries, summary, __getitem__/iter/len.
# ---------------------------------------------------------------------------


def _make_loop_kwargs(name, loop_type, components, max_area=100.0, priority="MEDIUM"):
    return {
        "name": name,
        "loop_type": loop_type,
        "description": f"desc-{name}",
        "components": components,
        "max_area_mm2": max_area,
        "priority": priority,
    }


def _py_collection():
    loops = [
        _oracle.Loop(**_split_enum_kwargs(_make_loop_kwargs(
            "gate_drive_high", "GATE_DRIVE_HIGH", ["U_GATE_DRV", "Q1"], 50.0, "CRITICAL"
        ))[0]),
        _oracle.Loop(**_split_enum_kwargs(_make_loop_kwargs(
            "commutation", "COMMUTATION", ["C_DC", "Q1", "Q2"], 200.0, "CRITICAL"
        ))[0]),
        _oracle.Loop(**_split_enum_kwargs(_make_loop_kwargs(
            "bootstrap", "BOOTSTRAP", ["D_BOOT", "C_BOOT"], 80.0, "HIGH"
        ))[0]),
        _oracle.Loop(**_split_enum_kwargs(_make_loop_kwargs(
            "current_sense", "SENSING", ["R_SENSE"], 30.0, "LOW"
        ))[0]),
    ]
    return _oracle.LoopCollection(loops=loops, name="temper", description="test")


def _rust_collection():
    loops = [
        LOOP(**_split_enum_kwargs(_make_loop_kwargs(
            "gate_drive_high", "GATE_DRIVE_HIGH", ["U_GATE_DRV", "Q1"], 50.0, "CRITICAL"
        ))[1]),
        LOOP(**_split_enum_kwargs(_make_loop_kwargs(
            "commutation", "COMMUTATION", ["C_DC", "Q1", "Q2"], 200.0, "CRITICAL"
        ))[1]),
        LOOP(**_split_enum_kwargs(_make_loop_kwargs(
            "bootstrap", "BOOTSTRAP", ["D_BOOT", "C_BOOT"], 80.0, "HIGH"
        ))[1]),
        LOOP(**_split_enum_kwargs(_make_loop_kwargs(
            "current_sense", "SENSING", ["R_SENSE"], 30.0, "LOW"
        ))[1]),
    ]
    return LOOP_COLLECTION(loops=loops, name="temper", description="test")


def test_collection_default_and_construction_identical():
    py_nc = _oracle.LoopCollection()
    rust_nc = LOOP_COLLECTION()
    assert _collection_fields(rust_nc) == _collection_fields(py_nc)
    assert _collection_fields(_rust_collection()) == _collection_fields(_py_collection())


def test_collection_add_loop_identical():
    py_coll = _oracle.LoopCollection()
    rust_coll = LOOP_COLLECTION()
    py_kwargs, rust_kwargs = _split_enum_kwargs(
        _make_loop_kwargs("g", "GATE_DRIVE_HIGH", ["Q1"])
    )
    py_coll.add_loop(_oracle.Loop(**py_kwargs))
    rust_coll.add_loop(LOOP(**rust_kwargs))
    assert _collection_fields(rust_coll) == _collection_fields(py_coll)
    # Duplicate name raises ValueError on both sides.
    with pytest.raises(ValueError):
        py_coll.add_loop(_oracle.Loop(**py_kwargs))
    with pytest.raises(ValueError):
        rust_coll.add_loop(LOOP(**rust_kwargs))


def test_collection_get_loop_identical():
    py_coll, rust_coll = _py_collection(), _rust_collection()
    assert rust_coll.get_loop("commutation").name == py_coll.get_loop("commutation").name
    assert rust_coll.get_loop("NOPE") is None
    assert py_coll.get_loop("NOPE") is None


def test_collection_query_methods_identical():
    py_coll, rust_coll = _py_collection(), _rust_collection()
    assert [ln.name for ln in rust_coll.get_loops_for_component("Q1")] == [
        ln.name for ln in py_coll.get_loops_for_component("Q1")
    ]
    assert [ln.name for ln in rust_coll.get_loops_for_component("NOPE")] == []
    assert [ln.name for ln in py_coll.get_loops_for_component("NOPE")] == []
    assert [ln.name for ln in rust_coll.get_loops_for_net("X")] == []
    assert [ln.name for ln in py_coll.get_loops_for_net("X")] == []
    assert [
        ln.name for ln in rust_coll.get_loops_by_type(LOOP_TYPE.COMMUTATION)
    ] == [ln.name for ln in py_coll.get_loops_by_type(_oracle.LoopType.COMMUTATION)]
    assert [
        ln.name for ln in rust_coll.get_loops_by_priority(LOOP_PRIORITY.CRITICAL)
    ] == [ln.name for ln in py_coll.get_loops_by_priority(_oracle.LoopPriority.CRITICAL)]
    assert [ln.name for ln in rust_coll.get_critical_loops()] == [
        ln.name for ln in py_coll.get_critical_loops()
    ]
    assert [ln.name for ln in rust_coll.get_high_priority_loops()] == [
        ln.name for ln in py_coll.get_high_priority_loops()
    ]
    assert rust_coll.get_all_component_refs() == py_coll.get_all_component_refs()
    assert rust_coll.get_all_nets() == py_coll.get_all_nets()


def test_collection_non_compliant_and_violation_identical():
    py_coll, rust_coll = _py_collection(), _rust_collection()
    py_coll["gate_drive_high"].set_current_area(60.0)  # 10 over
    py_coll["commutation"].set_current_area(250.0)  # 50 over
    py_coll["bootstrap"].set_current_area(25.0)  # OK
    rust_coll["gate_drive_high"].set_current_area(60.0)
    rust_coll["commutation"].set_current_area(250.0)
    rust_coll["bootstrap"].set_current_area(25.0)
    assert [ln.name for ln in rust_coll.get_non_compliant_loops()] == [
        ln.name for ln in py_coll.get_non_compliant_loops()
    ]
    assert float(rust_coll.total_area_violation_mm2()).hex() == float(
        py_coll.total_area_violation_mm2()
    ).hex()
    assert rust_coll.total_area_violation_mm2() == 60.0  # 10 + 50


def test_collection_summary_identical():
    py_coll, rust_coll = _py_collection(), _rust_collection()
    py_coll["gate_drive_high"].set_current_area(40.0)
    py_coll["commutation"].set_current_area(250.0)
    rust_coll["gate_drive_high"].set_current_area(40.0)
    rust_coll["commutation"].set_current_area(250.0)
    py_summary = py_coll.summary()
    rust_summary = rust_coll.summary()
    assert set(rust_summary.keys()) == set(py_summary.keys())
    for key in py_summary:
        if isinstance(py_summary[key], float):
            assert float(rust_summary[key]).hex() == float(py_summary[key]).hex(), key
        else:
            assert rust_summary[key] == py_summary[key], key


def test_collection_len_iter_getitem_identical():
    py_coll, rust_coll = _py_collection(), _rust_collection()
    assert len(rust_coll) == len(py_coll) == 4
    assert [ln.name for ln in rust_coll] == [ln.name for ln in py_coll]
    assert rust_coll["commutation"].name == py_coll["commutation"].name
    assert rust_coll[0].name == py_coll[0].name
    assert rust_coll[-1].name == py_coll[-1].name
    with pytest.raises(KeyError):
        rust_coll["NOPE"]
    with pytest.raises(TypeError):
        rust_coll[1.5]
    with pytest.raises(IndexError):
        rust_coll[99]


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
        "stale or missing. Rebuild with `uv run --no-sync maturin develop "
        "--release --manifest-path packages/temper-design-bundle/Cargo.toml`.",
        pytrace=False,
    )

pytestmark = pytest.mark.skipif(
    not hasattr(_tdb, "LoopType"),
    reason="temper_design_bundle_python loop pyclasses not installed "
    "(set TEMPER_REQUIRE_RUST_LOOP=1 to make this fatal instead of a skip)",
)
