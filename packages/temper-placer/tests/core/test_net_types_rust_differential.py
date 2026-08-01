"""Differential test: Rust net-types pyclasses (temper_design_bundle_python)
vs the pinned Python oracle.

Wave 4, Phase 2 — the contracts-as-pyo3-pyclasses pivot (plan
``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``,
D5 / Phase B). This is the FIRST Wave-4 Phase 2 migration; it sets the
pattern for every later contract migration.

The Rust pyo3 pyclasses ``NetType``, ``ConnectivityStrategy``,
``VoltageClass``, ``NetTypeSpec``, ``NetClassification`` (in
``temper_design_bundle_python``, from the ``temper-design-bundle`` crate)
must reproduce the pre-migration Python implementation of
``temper_placer/core/net_types.py`` bit-identically. The pre-migration
implementation is pinned verbatim as the oracle
(``_net_types_py_oracle.py``, commit 37a4251e0) and every assertion here
drives IDENTICAL inputs through both sides.

Comparison convention (mirrors the repo's other ``*_rust_differential.py``
files): objects are canonicalized into plain comparable tuples before
assertion — cross-type ``==`` between a Python dataclass and a pyo3
pyclass is not defined, so field-by-field extraction is the oracle-proof
comparison. Floats are compared as exact bit patterns via ``float.hex()``
(``==`` would also be exact for IEEE-754 doubles, but ``hex()`` makes the
bit-exactness explicit and fails with a readable diff).

Enum parity is checked via ``getattr(rust_enum, name)`` rather than
class-level iteration (``for m in rust_enum``): a pyo3 ``#[pyclass]``
enum cannot implement class-level ``__iter__`` — Python class iteration
requires the *metaclass* to define ``__iter__``, and pyo3 exposes no
metaclass hook. ``getattr`` covers every member, so the parity proof is
identical; only the accessor differs.

Known, deliberately-asserted normalization: the pre-migration
``NetClassification`` pattern fields are ``frozenset[str]``; the pyo3
pyclass exposes them as Python ``set`` (Rust ``HashSet``). The differential
compares pattern CONTENTS (set equality — frozenset == set compares
contents in Python). No consumer of ``NetClassification``
(``io/zone_manager.py`` etc.) relies on the frozenset type; all iterate
the patterns.

Deliberately PRESERVED (not normalized): ``from_yaml_config``'s
``target_layer`` default is a ``LayerIndex`` IntEnum (e.g.
``LayerIndex.IN1_CU``) in the pre-migration code, and the Rust pyclass
resolves the same IntEnum via a lazy ``temper_placer.core.board`` import
at call time. This is load-bearing: ``io/zone_manager.py`` serializes the
value with ``str()`` into the KiCad ``(layer "…")`` token — a bare ``int``
would serialize as ``"1"`` instead of ``"In1.Cu"``.
"""

from __future__ import annotations

import os

import pytest
import temper_design_bundle_python as _tdb

import tests.core._net_types_py_oracle as _oracle
from temper_placer.core.board import LayerIndex

# Rust symbols under test — must exist or this file fails to collect (RED).
NET_TYPE = _tdb.NetType
CONNECTIVITY = _tdb.ConnectivityStrategy
VOLTAGE_CLASS = _tdb.VoltageClass
NET_TYPE_SPEC = _tdb.NetTypeSpec
NET_CLASSIFICATION = _tdb.NetClassification


# ---------------------------------------------------------------------------
# Canonicalization helpers (field-level extraction, bit-exact floats).
# ---------------------------------------------------------------------------


def _layer_key(value):
    """Canonicalize a ``target_layer`` field value.

    Both the pre-migration Python AND the Rust pyclass can store a plain
    ``str`` ("F.Cu") OR — via ``from_yaml_config``'s ``_default_layer``
    default — a ``LayerIndex`` IntEnum (an ``int`` subclass; preserved
    exactly by the Rust side, see the module docstring). Canonicalizing by
    value (str stays str, IntEnum → its int value) makes the two sides
    comparable regardless of which storage form is in play.
    """
    if isinstance(value, str):
        return value
    return int(value)


def _spec_fields(spec):
    """Extract every NetTypeSpec field into a comparable tuple.

    Enums are compared by ``(name, value)`` (the Rust pyclasses expose
    ``.name``/``.value`` mirrors of Python Enum semantics); floats by
    ``float.hex()`` bit patterns; ``target_layer`` via ``_layer_key``.
    """
    return (
        (spec.net_type.name, spec.net_type.value),
        (spec.connectivity.name, spec.connectivity.value),
        _layer_key(spec.target_layer),
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


def _classification_fields(nc):
    """Extract a NetClassification into a comparable mapping.

    ``specs`` is compared per-net via ``_spec_fields``; pattern fields via
    set-content equality (the documented frozenset -> set normalization).
    """
    return {
        "specs": {name: _spec_fields(spec) for name, spec in nc.specs.items()},
        "ground_patterns": set(nc.ground_patterns),
        "power_patterns": set(nc.power_patterns),
        "hv_patterns": set(nc.hv_patterns),
    }


# ---------------------------------------------------------------------------
# Enum parity: names, auto() values, and the IEC 60335 float tables.
# ---------------------------------------------------------------------------


def test_enum_members_name_and_value_parity():
    """Every enum member: identical name and identical auto()/int value.

    Rust members are reached via ``getattr`` (class-level iteration is not
    supported for pyo3 pyclass enums — see the module docstring), which
    covers every member the Python enum defines.
    """
    for py_enum, rust_enum in (
        (_oracle.NetType, NET_TYPE),
        (_oracle.ConnectivityStrategy, CONNECTIVITY),
        (_oracle.VoltageClass, VOLTAGE_CLASS),
    ):
        py_names = [m.name for m in py_enum]
        rust_names = [getattr(rust_enum, n).name for n in py_names]
        assert rust_names == py_names, f"{py_enum.__name__}: names differ"
        py_values = [m.value for m in py_enum]
        rust_values = [getattr(rust_enum, n).value for n in py_names]
        assert rust_values == py_values, f"{py_enum.__name__}: values differ"


@pytest.mark.parametrize("pollution_degree", [1, 2, 3])
def test_get_clearance_mm_bit_identical(pollution_degree):
    for py_member in _oracle.VoltageClass:
        rust_member = getattr(VOLTAGE_CLASS, py_member.name)
        py_result = py_member.get_clearance_mm(pollution_degree)
        rust_result = rust_member.get_clearance_mm(pollution_degree)
        assert float(rust_result).hex() == float(py_result).hex(), (
            f"{py_member.name} pollution_degree={pollution_degree}: "
            f"rust={rust_result!r} py={py_result!r}"
        )


@pytest.mark.parametrize("material_group", [1, 2, 3])
def test_get_creepage_mm_bit_identical(material_group):
    for py_member in _oracle.VoltageClass:
        rust_member = getattr(VOLTAGE_CLASS, py_member.name)
        py_result = py_member.get_creepage_mm(material_group)
        rust_result = rust_member.get_creepage_mm(material_group)
        assert float(rust_result).hex() == float(py_result).hex(), (
            f"{py_member.name} material_group={material_group}: "
            f"rust={rust_result!r} py={py_result!r}"
        )


# ---------------------------------------------------------------------------
# NetTypeSpec: construction round-trip, defaults, validation.
# ---------------------------------------------------------------------------

_PY_ENUM_MAP = {
    "net_type": (_oracle.NetType, NET_TYPE),
    "connectivity": (_oracle.ConnectivityStrategy, CONNECTIVITY),
    "voltage_class": (_oracle.VoltageClass, VOLTAGE_CLASS),
}


def _split_enum_kwargs(kwargs):
    """Map string enum names in ``kwargs`` to each side's enum members."""
    py_kwargs, rust_kwargs = dict(kwargs), dict(kwargs)
    for key, (py_enum, rust_enum) in _PY_ENUM_MAP.items():
        if key in py_kwargs and isinstance(py_kwargs[key], str):
            name = py_kwargs[key]
            py_kwargs[key] = py_enum[name]
            rust_kwargs[key] = getattr(rust_enum, name)
    return py_kwargs, rust_kwargs


def test_spec_construction_all_fields_round_trip():
    """All 13 fields, explicitly set, round-trip bit-identically."""
    kwargs = {
        "net_type": "HIGH_VOLTAGE",
        "connectivity": "COPPER_POUR",
        "target_layer": "B.Cu",
        "voltage_class": "MAINS_240V",
        "max_current_a": 20.0,
        "impedance_ohm": 50.0,
        "trace_width_mm": 2.0,
        "clearance_mm": 6.0,
        "creepage_mm": 6.0,
        "via_template": "Via3x3",
        "allow_layer_change": False,
        "prefer_short_stubs": True,
    }
    py_kwargs, rust_kwargs = _split_enum_kwargs(kwargs)
    py_spec = _oracle.NetTypeSpec(**py_kwargs)
    rust_spec = NET_TYPE_SPEC(**rust_kwargs)
    assert _spec_fields(rust_spec) == _spec_fields(py_spec)


def test_spec_construction_defaults_identical():
    """Keyword-only construction with every default matches the dataclass."""
    py_spec = _oracle.NetTypeSpec(
        net_type=_oracle.NetType.SIGNAL,
        connectivity=_oracle.ConnectivityStrategy.TRACE,
    )
    rust_spec = NET_TYPE_SPEC(net_type=NET_TYPE.SIGNAL, connectivity=CONNECTIVITY.TRACE)
    assert _spec_fields(rust_spec) == _spec_fields(py_spec)


@pytest.mark.parametrize(
    "kwargs",
    [
        # Ground with non-plane connectivity -> error
        {"net_type": "GROUND", "connectivity": "TRACE"},
        # Ground with DIRECT is allowed -> no error
        {"net_type": "GROUND", "connectivity": "DIRECT"},
        # HV with insufficient creepage/clearance -> errors
        {
            "net_type": "HIGH_VOLTAGE",
            "connectivity": "COPPER_POUR",
            "voltage_class": "MAINS_240V",
            "creepage_mm": 1.0,
            "clearance_mm": 1.0,
        },
        # HV with sufficient clearances -> no error
        {
            "net_type": "HIGH_VOLTAGE",
            "connectivity": "COPPER_POUR",
            "voltage_class": "MAINS_240V",
            "creepage_mm": 6.0,
            "clearance_mm": 6.0,
        },
        # High current with Via1x1 -> error
        {"net_type": "HIGH_CURRENT", "connectivity": "VIA_ARRAY", "via_template": "Via1x1"},
        # High current with Via2x2 -> no error
        {"net_type": "HIGH_CURRENT", "connectivity": "VIA_ARRAY", "via_template": "Via2x2"},
        # Over-current signal with Via1x1 -> error
        {"net_type": "SIGNAL", "connectivity": "TRACE", "max_current_a": 6.0},
        # Differential without impedance -> error
        {"net_type": "DIFFERENTIAL", "connectivity": "TRACE"},
        # Differential with impedance -> no error
        {"net_type": "DIFFERENTIAL", "connectivity": "TRACE", "impedance_ohm": 90.0},
    ],
)
def test_spec_validate_bit_identical(kwargs):
    """validate()/is_valid() return identical error lists on both sides."""
    py_kwargs, rust_kwargs = _split_enum_kwargs(kwargs)
    py_spec = _oracle.NetTypeSpec(**py_kwargs)
    rust_spec = NET_TYPE_SPEC(**rust_kwargs)
    assert rust_spec.validate() == py_spec.validate()
    assert bool(rust_spec.is_valid()) == bool(py_spec.is_valid())


@pytest.mark.parametrize(
    "name",
    ["GROUND_PLANE_SPEC", "POWER_PLANE_SPEC", "MAINS_HV_SPEC", "SIGNAL_SPEC"],
)
def test_module_constants_bit_identical(name):
    """The pre-defined specs must reproduce the Python constants exactly."""
    py_spec = getattr(_oracle, name)
    rust_spec = getattr(_tdb, name)
    assert _spec_fields(rust_spec) == _spec_fields(py_spec), name


# ---------------------------------------------------------------------------
# NetClassification: construction, classification, plane/pour queries,
# validation, and YAML-config construction.
# ---------------------------------------------------------------------------


def test_nc_default_patterns_identical():
    py_nc = _oracle.NetClassification()
    rust_nc = NET_CLASSIFICATION()
    assert _classification_fields(rust_nc) == _classification_fields(py_nc)


@pytest.mark.parametrize(
    "net_name,expected",
    [
        ("GND", "GROUND_PLANE_SPEC"),
        ("PGND", "GROUND_PLANE_SPEC"),
        ("AGND_x", "GROUND_PLANE_SPEC"),
        ("+3V3", "POWER_PLANE_SPEC"),
        ("VCC", "POWER_PLANE_SPEC"),
        ("+12V", "POWER_PLANE_SPEC"),
        ("AC_L", "MAINS_HV_SPEC"),
        ("AC_N", "MAINS_HV_SPEC"),
        ("SW_NODE", "MAINS_HV_SPEC"),
        ("DC_BUS+", "MAINS_HV_SPEC"),
        ("PE", "MAINS_HV_SPEC"),
        ("some_plain_signal", "SIGNAL_SPEC"),
        ("SPI_CLK", "SIGNAL_SPEC"),
        ("gnd", "GROUND_PLANE_SPEC"),  # case-insensitive auto-classification
    ],
)
def test_classify_net_auto_identical(net_name, expected):
    py_nc = _oracle.NetClassification()
    rust_nc = NET_CLASSIFICATION()
    py_spec = py_nc.classify_net(net_name)
    rust_spec = rust_nc.classify_net(net_name)
    assert _spec_fields(rust_spec) == _spec_fields(py_spec), (
        f"{net_name}: rust={rust_spec!r} py={py_spec!r}"
    )
    # The auto-classified spec must be field-equal to the matching module
    # constant (identity is not the contract — classify_net returns a fresh
    # equal object; the pre-migration returned the shared constant).
    assert _spec_fields(rust_spec) == _spec_fields(getattr(_oracle, expected))


def test_classify_net_explicit_spec_wins():
    """An explicitly-registered spec shadows pattern auto-classification."""
    py_nc = _oracle.NetClassification(
        specs={
            "GND": _oracle.NetTypeSpec(
                net_type=_oracle.NetType.SIGNAL,
                connectivity=_oracle.ConnectivityStrategy.TRACE,
                max_current_a=1.0,
            )
        }
    )
    rust_nc = NET_CLASSIFICATION(
        specs={
            "GND": NET_TYPE_SPEC(
                net_type=NET_TYPE.SIGNAL,
                connectivity=CONNECTIVITY.TRACE,
                max_current_a=1.0,
            )
        }
    )
    assert _spec_fields(rust_nc.classify_net("GND")) == _spec_fields(
        py_nc.classify_net("GND")
    )


def test_plane_and_pour_nets_identical():
    py_nc = _oracle.NetClassification(
        specs={
            "GND": _oracle.NetTypeSpec(
                net_type=_oracle.NetType.GROUND,
                connectivity=_oracle.ConnectivityStrategy.PLANE,
            ),
            "+5V": _oracle.NetTypeSpec(
                net_type=_oracle.NetType.POWER,
                connectivity=_oracle.ConnectivityStrategy.PLANE,
            ),
            "AC_L": _oracle.NetTypeSpec(
                net_type=_oracle.NetType.HIGH_VOLTAGE,
                connectivity=_oracle.ConnectivityStrategy.COPPER_POUR,
            ),
            "SIG": _oracle.NetTypeSpec(
                net_type=_oracle.NetType.SIGNAL,
                connectivity=_oracle.ConnectivityStrategy.TRACE,
            ),
        }
    )
    rust_nc = NET_CLASSIFICATION(
        specs={
            "GND": NET_TYPE_SPEC(net_type=NET_TYPE.GROUND, connectivity=CONNECTIVITY.PLANE),
            "+5V": NET_TYPE_SPEC(net_type=NET_TYPE.POWER, connectivity=CONNECTIVITY.PLANE),
            "AC_L": NET_TYPE_SPEC(
                net_type=NET_TYPE.HIGH_VOLTAGE, connectivity=CONNECTIVITY.COPPER_POUR
            ),
            "SIG": NET_TYPE_SPEC(net_type=NET_TYPE.SIGNAL, connectivity=CONNECTIVITY.TRACE),
        }
    )
    assert set(rust_nc.get_plane_nets()) == set(py_nc.get_plane_nets())
    assert set(rust_nc.get_pour_nets()) == set(py_nc.get_pour_nets())


def test_validate_all_identical():
    py_nc = _oracle.NetClassification(
        specs={
            "GND_BAD": _oracle.NetTypeSpec(
                net_type=_oracle.NetType.GROUND,
                connectivity=_oracle.ConnectivityStrategy.TRACE,
            ),
            "OK": _oracle.NetTypeSpec(
                net_type=_oracle.NetType.SIGNAL,
                connectivity=_oracle.ConnectivityStrategy.TRACE,
            ),
        }
    )
    rust_nc = NET_CLASSIFICATION(
        specs={
            "GND_BAD": NET_TYPE_SPEC(net_type=NET_TYPE.GROUND, connectivity=CONNECTIVITY.TRACE),
            "OK": NET_TYPE_SPEC(net_type=NET_TYPE.SIGNAL, connectivity=CONNECTIVITY.TRACE),
        }
    )
    py_result = py_nc.validate_all()
    rust_result = rust_nc.validate_all()
    assert set(rust_result.keys()) == set(py_result.keys())
    for name in py_result:
        assert rust_result[name] == py_result[name], name


# ---------------------------------------------------------------------------
# from_yaml_config: the config-mapping path, including the LayerIndex
# default quirk (target_layer defaulting to a LayerIndex int when the rule
# omits it).
# ---------------------------------------------------------------------------

_YAML_NET_CLASSES = {
    "GND": "ground_class",
    "+5V": "power_class",
    "AC_L": "hv_class",
    "SIG_1": "signal_class",
    "DIFF_P": "diff_class",
    "HC": "high_current_class",
}

_YAML_NET_CLASS_RULES = {
    "ground_class": {"type": "ground", "connectivity": "plane"},
    "power_class": {"type": "power", "connectivity": "plane"},
    "hv_class": {"type": "high_voltage", "voltage_class": "mains_240v"},
    "signal_class": {},
    "diff_class": {"type": "differential", "target_impedance": 90.0},
    "high_current_class": {"type": "high_current"},
}


def test_from_yaml_config_identical():
    py_nc = _oracle.NetClassification.from_yaml_config(
        _YAML_NET_CLASSES, _YAML_NET_CLASS_RULES
    )
    rust_nc = NET_CLASSIFICATION.from_yaml_config(_YAML_NET_CLASSES, _YAML_NET_CLASS_RULES)
    assert _classification_fields(rust_nc) == _classification_fields(py_nc)


def test_from_yaml_config_default_layer_is_layerindex_int():
    """The pre-migration quirk: a rule without ``target_layer`` defaults to
    ``_default_layer(net_type)`` — a ``LayerIndex`` IntEnum. The Rust pyclass
    resolves the SAME IntEnum (lazy ``temper_placer.core.board`` import),
    preserving the type exactly — ``str(LayerIndex.IN1_CU) == "In1.Cu"`` is
    what ``io/zone_manager.py`` serializes into the KiCad ``(layer "…")``
    token, so flattening it to a bare ``int`` would be a real regression."""
    py_nc = _oracle.NetClassification.from_yaml_config(
        {"GND": "g"}, {"g": {"type": "ground"}}
    )
    rust_nc = NET_CLASSIFICATION.from_yaml_config({"GND": "g"}, {"g": {"type": "ground"}})
    py_spec = py_nc.specs["GND"]
    rust_spec = rust_nc.specs["GND"]
    assert py_spec.target_layer == LayerIndex.IN1_CU
    assert isinstance(py_spec.target_layer, LayerIndex)
    assert rust_spec.target_layer == LayerIndex.IN1_CU
    assert isinstance(rust_spec.target_layer, LayerIndex), (
        "target_layer default must be a LayerIndex IntEnum (zone_manager "
        "serializes it with str()), not a bare int"
    )
    assert str(rust_spec.target_layer) == "In1.Cu"
    assert _layer_key(rust_spec.target_layer) == _layer_key(py_spec.target_layer)


def test_from_yaml_config_explicit_target_layer_identical():
    py_nc = _oracle.NetClassification.from_yaml_config(
        {"NET": "c"}, {"c": {"type": "signal", "target_layer": "B.Cu"}}
    )
    rust_nc = NET_CLASSIFICATION.from_yaml_config(
        {"NET": "c"}, {"c": {"type": "signal", "target_layer": "B.Cu"}}
    )
    assert _classification_fields(rust_nc) == _classification_fields(py_nc)
    assert rust_nc.specs["NET"].target_layer == "B.Cu"


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
        "stale or missing. Rebuild with `uv run --no-sync maturin develop "
        "--release --manifest-path packages/temper-design-bundle/Cargo.toml`.",
        pytrace=False,
    )

pytestmark = pytest.mark.skipif(
    not hasattr(_tdb, "NetTypeSpec"),
    reason="temper_design_bundle_python net-types pyclasses not installed "
    "(set TEMPER_REQUIRE_RUST_NET_TYPES=1 to make this fatal instead of a skip)",
)
