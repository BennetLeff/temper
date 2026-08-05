"""Differential test: Rust manufacturing tolerance pyclasses
(``temper_design_bundle_python``) vs the pinned Python oracle.

Wave 4, Phase 4 leftovers slice — the manufacturing/tolerances.py migration.
The Rust pyo3 pyclasses ``CopperWeight``, ``LayerType``, ``ToleranceTable``,
``FeatureTolerance``, ``ToleranceAnalyzer`` (in ``temper_design_bundle_python``,
from the ``temper-design-bundle`` crate) must reproduce the pre-migration
Python implementation of ``temper_placer/manufacturing/tolerances.py``
bit-identically. The pre-migration implementation is pinned verbatim as the
oracle (``_tolerances_py_oracle.py``, commit 6290942be) and every assertion
here drives IDENTICAL inputs through both sides.

Comparison convention (mirrors the priority/loop differentials): objects are
canonicalized into plain comparable tuples before assertion. Floats are
compared as exact bit patterns via ``float.hex()``. Enum parity is checked
via ``getattr(rust_enum, name)`` rather than class-level iteration (pyo3
enums expose no metaclass ``__iter__`` hook); ``getattr`` covers every
member, so the parity proof is identical.

Known, documented deviation (asserted only on the Python side here, per the
gates precedent): ``CopperWeight``/``LayerType`` are Python ``Enum``s whose
members ARE hashable and usable as dict keys; the pyclass members replicate
that (``#[pyclass(frozen, eq, hash)]``). The pyclass members are NOT
constructible by class-level iteration, exactly like the priority IntEnums.
No consumer iterates these enums at class level.
"""

from __future__ import annotations

import pytest
import temper_design_bundle_python as _tdb

import tests.manufacturing._tolerances_py_oracle as _oracle

# Rust symbols under test — must exist or this file fails to collect (RED).
COPPER_WEIGHT = _tdb.CopperWeight
LAYER_TYPE = _tdb.LayerType
TOLERANCE_TABLE = _tdb.ToleranceTable
FEATURE_TOLERANCE = _tdb.FeatureTolerance
TOLERANCE_ANALYZER = _tdb.ToleranceAnalyzer


# ---------------------------------------------------------------------------
# Canonicalization helpers (bit-exact floats).
# ---------------------------------------------------------------------------


def _f(value):
    """Bit-exact float key: None stays None, else float.hex()."""
    return None if value is None else float(value).hex()


def _feature_tolerance_fields(ft):
    return (
        ft.feature_type,
        _f(ft.nominal_value),
        _f(ft.tolerance_plus),
        _f(ft.tolerance_minus),
        _f(ft.worst_case_min),
        _f(ft.worst_case_max),
    )


def _tolerance_table_fields(tt):
    return (
        tuple(sorted((k.name, v) for k, v in tt.etch_tolerance.items())),
        tuple(sorted((k.name, v) for k, v in tt.registration.items())),
        _f(tt.solder_mask_registration),
    )


# ---------------------------------------------------------------------------
# Enum parity: names, values, str/repr, value-construction.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "py_enum,rust_enum,members",
    [
        (_oracle.CopperWeight, COPPER_WEIGHT, ["HALF_OZ", "ONE_OZ", "TWO_OZ"]),
        (_oracle.LayerType, LAYER_TYPE, ["OUTER", "INNER"]),
    ],
)
def test_enum_members_name_and_value_parity(py_enum, rust_enum, members):
    """Every enum member: identical name and identical value."""
    for name in members:
        py_member = getattr(py_enum, name)
        rust_member = getattr(rust_enum, name)
        assert rust_member.name == py_member.name
        assert rust_member.value == py_member.value
        # Value concrete type parity: CopperWeight values are floats,
        # LayerType values are strs — carry the type in the key.
        assert type(rust_member.value) is type(py_member.value)


@pytest.mark.parametrize(
    "py_enum,rust_enum,members",
    [
        (_oracle.CopperWeight, COPPER_WEIGHT, ["HALF_OZ", "ONE_OZ", "TWO_OZ"]),
        (_oracle.LayerType, LAYER_TYPE, ["OUTER", "INNER"]),
    ],
)
def test_enum_str_and_repr_identical(py_enum, rust_enum, members):
    """str() and repr() render identically for every member."""
    for name in members:
        py_member = getattr(py_enum, name)
        rust_member = getattr(rust_enum, name)
        assert str(rust_member) == str(py_member), f"{name}: str differs"
        assert repr(rust_member) == repr(py_member), f"{name}: repr differs"


def test_copper_weight_value_construction_parity():
    """CopperWeight(0.5) resolves to HALF_OZ like the Python Enum."""
    for value, name in [(0.5, "HALF_OZ"), (1.0, "ONE_OZ"), (2.0, "TWO_OZ")]:
        rust = COPPER_WEIGHT(value)
        py = _oracle.CopperWeight(value)
        assert rust.name == py.name == name


def test_layer_type_value_construction_parity():
    """LayerType("outer") resolves to OUTER like the Python Enum."""
    for value, name in [("outer", "OUTER"), ("inner", "INNER")]:
        rust = LAYER_TYPE(value)
        py = _oracle.LayerType(value)
        assert rust.name == py.name == name


@pytest.mark.parametrize(
    "py_enum,rust_enum,invalid",
    [
        (_oracle.CopperWeight, COPPER_WEIGHT, 999),
        (_oracle.LayerType, LAYER_TYPE, "x"),
    ],
)
def test_enum_invalid_value_error_text(py_enum, rust_enum, invalid):
    """Invalid value construction raises the same ValueError text."""
    with pytest.raises(ValueError) as py_exc:
        py_enum(invalid)
    with pytest.raises(ValueError) as rust_exc:
        rust_enum(invalid)
    assert str(rust_exc.value) == str(py_exc.value)


def test_enum_members_hashable_and_dict_keyable():
    """Enum members work as dict keys (hash + eq), like Python Enum."""
    d = {COPPER_WEIGHT.ONE_OZ: 0.05, LAYER_TYPE.OUTER: 0.1}
    assert d[COPPER_WEIGHT.ONE_OZ] == 0.05
    assert d[LAYER_TYPE.OUTER] == 0.1
    # Equal-but-not-identical members resolve to the same key.
    assert d[COPPER_WEIGHT(1.0)] == 0.05
    assert d[LAYER_TYPE("outer")] == 0.1
    assert len(d) == 2


# ---------------------------------------------------------------------------
# ToleranceTable parity.
# ---------------------------------------------------------------------------


def test_tolerance_table_defaults_parity():
    """Default ToleranceTable: identical etch/registration dicts and mask reg."""
    py = _oracle.ToleranceTable()
    rust = TOLERANCE_TABLE()
    assert _tolerance_table_fields(rust) == _tolerance_table_fields(py)
    assert rust.solder_mask_registration == py.solder_mask_registration


def test_tolerance_table_default_etch_values():
    """Per-weight etch tolerances match the oracle table exactly (bits)."""
    py = _oracle.ToleranceTable()
    rust = TOLERANCE_TABLE()
    for name in ("HALF_OZ", "ONE_OZ", "TWO_OZ"):
        py_v = py.etch_tolerance[getattr(_oracle.CopperWeight, name)]
        rust_v = rust.etch_tolerance[getattr(COPPER_WEIGHT, name)]
        assert _f(rust_v) == _f(py_v), f"{name}: {rust_v} vs {py_v}"


def test_tolerance_table_default_registration_values():
    """Per-layer-type registration values match the oracle table exactly."""
    py = _oracle.ToleranceTable()
    rust = TOLERANCE_TABLE()
    for name in ("OUTER", "INNER"):
        py_v = py.registration[getattr(_oracle.LayerType, name)]
        rust_v = rust.registration[getattr(LAYER_TYPE, name)]
        assert _f(rust_v) == _f(py_v), f"{name}: {rust_v} vs {py_v}"


def test_tolerance_table_custom_construction_parity():
    """Custom dict overrides flow through identically."""
    custom_etch = {_oracle.CopperWeight.ONE_OZ: 0.01}
    custom_reg = {_oracle.LayerType.INNER: 0.2}
    py = _oracle.ToleranceTable(
        etch_tolerance=custom_etch,
        registration=custom_reg,
        solder_mask_registration=0.5,
    )
    rust_custom_etch = {COPPER_WEIGHT.ONE_OZ: 0.01}
    rust_custom_reg = {LAYER_TYPE.INNER: 0.2}
    rust = TOLERANCE_TABLE(
        etch_tolerance=rust_custom_etch,
        registration=rust_custom_reg,
        solder_mask_registration=0.5,
    )
    assert _tolerance_table_fields(rust) == _tolerance_table_fields(py)
    assert _f(rust.solder_mask_registration) == _f(py.solder_mask_registration)


def test_tolerance_table_repr_parity():
    """repr() matches byte-for-byte for default and custom tables."""
    assert repr(TOLERANCE_TABLE()) == repr(_oracle.ToleranceTable())


# ---------------------------------------------------------------------------
# FeatureTolerance parity.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "clearance_mm,copper_name,layer_name",
    [
        (0.5, "ONE_OZ", "OUTER"),
        (0.3, "HALF_OZ", "INNER"),
        (2.0, "TWO_OZ", "OUTER"),
        (0.125, "HALF_OZ", "INNER"),
        (1e-9, "TWO_OZ", "OUTER"),
    ],
)
def test_analyze_clearance_field_parity(clearance_mm, copper_name, layer_name):
    """analyze_clearance produces bit-identical FeatureTolerance fields."""
    py = _oracle.ToleranceAnalyzer().analyze_clearance(
        clearance_mm, getattr(_oracle.CopperWeight, copper_name), getattr(_oracle.LayerType, layer_name)
    )
    rust = TOLERANCE_ANALYZER().analyze_clearance(
        clearance_mm, getattr(COPPER_WEIGHT, copper_name), getattr(LAYER_TYPE, layer_name)
    )
    assert _feature_tolerance_fields(rust) == _feature_tolerance_fields(py)


@pytest.mark.parametrize(
    "width_mm,copper_name",
    [
        (1.0, "TWO_OZ"),
        (0.5, "ONE_OZ"),
        (0.25, "HALF_OZ"),
        (3.5, "TWO_OZ"),
    ],
)
def test_analyze_trace_field_parity(width_mm, copper_name):
    """analyze_trace produces bit-identical FeatureTolerance fields."""
    py = _oracle.ToleranceAnalyzer().analyze_trace(
        width_mm, getattr(_oracle.CopperWeight, copper_name)
    )
    rust = TOLERANCE_ANALYZER().analyze_trace(
        width_mm, getattr(COPPER_WEIGHT, copper_name)
    )
    assert _feature_tolerance_fields(rust) == _feature_tolerance_fields(py)


def test_feature_tolerance_repr_parity():
    """FeatureTolerance repr matches byte-for-byte."""
    py = _oracle.ToleranceAnalyzer().analyze_clearance(0.5, _oracle.CopperWeight.ONE_OZ, _oracle.LayerType.OUTER)
    rust = TOLERANCE_ANALYZER().analyze_clearance(0.5, COPPER_WEIGHT.ONE_OZ, LAYER_TYPE.OUTER)
    assert repr(rust) == repr(py)


def test_feature_tolerance_eq_parity():
    """Dataclass-style equality: same fields equal, different fields not."""
    py = _oracle.ToleranceAnalyzer().analyze_clearance(0.5, _oracle.CopperWeight.ONE_OZ, _oracle.LayerType.OUTER)
    rust = TOLERANCE_ANALYZER().analyze_clearance(0.5, COPPER_WEIGHT.ONE_OZ, LAYER_TYPE.OUTER)
    assert rust == rust
    assert not (rust == py)  # different types never compare equal (dataclass __eq__)
    other = TOLERANCE_ANALYZER().analyze_clearance(0.6, COPPER_WEIGHT.ONE_OZ, LAYER_TYPE.OUTER)
    assert rust != other


# ---------------------------------------------------------------------------
# ToleranceAnalyzer: custom-table and fallback parity.
# ---------------------------------------------------------------------------


def test_analyzer_custom_table_parity():
    """Custom ToleranceTable flows into the analyzer identically."""
    py_table = _oracle.ToleranceTable(etch_tolerance={_oracle.CopperWeight.ONE_OZ: 0.01})
    rust_table = TOLERANCE_TABLE(etch_tolerance={COPPER_WEIGHT.ONE_OZ: 0.01})
    py = _oracle.ToleranceAnalyzer(table=py_table).analyze_trace(1.0, _oracle.CopperWeight.ONE_OZ)
    rust = TOLERANCE_ANALYZER(table=rust_table).analyze_trace(1.0, COPPER_WEIGHT.ONE_OZ)
    assert _feature_tolerance_fields(rust) == _feature_tolerance_fields(py)


def test_analyzer_missing_copper_weight_falls_back_to_005():
    """Copper weight absent from the table falls back to 0.05 (bit-exact)."""
    py_table = _oracle.ToleranceTable(etch_tolerance={_oracle.CopperWeight.ONE_OZ: 0.01})
    rust_table = TOLERANCE_TABLE(etch_tolerance={COPPER_WEIGHT.ONE_OZ: 0.01})
    # TWO_OZ is missing from the custom table -> fallback 0.05.
    py = _oracle.ToleranceAnalyzer(table=py_table).analyze_trace(1.0, _oracle.CopperWeight.TWO_OZ)
    rust = TOLERANCE_ANALYZER(table=rust_table).analyze_trace(1.0, COPPER_WEIGHT.TWO_OZ)
    assert _feature_tolerance_fields(rust) == _feature_tolerance_fields(py)
    assert _f(rust.tolerance_minus) == _f(0.05)


def test_analyzer_missing_layer_type_falls_back_to_01():
    """Layer type absent from the registration table falls back to 0.1."""
    py_table = _oracle.ToleranceTable(registration={_oracle.LayerType.OUTER: 0.05})
    rust_table = TOLERANCE_TABLE(registration={LAYER_TYPE.OUTER: 0.05})
    py = _oracle.ToleranceAnalyzer(table=py_table).analyze_clearance(
        0.5, _oracle.CopperWeight.ONE_OZ, _oracle.LayerType.INNER
    )
    rust = TOLERANCE_ANALYZER(table=rust_table).analyze_clearance(
        0.5, COPPER_WEIGHT.ONE_OZ, LAYER_TYPE.INNER
    )
    assert _feature_tolerance_fields(rust) == _feature_tolerance_fields(py)


def test_analyzer_table_identity_semantics():
    """analyzer.table is the exact instance passed in (not a copy)."""
    table = TOLERANCE_TABLE()
    analyzer = TOLERANCE_ANALYZER(table=table)
    assert analyzer.table is table
