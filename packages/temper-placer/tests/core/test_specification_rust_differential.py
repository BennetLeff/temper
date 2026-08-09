"""
Differential test: Rust specification pyclasses (temper_design_bundle_python) vs
the pinned Python oracle.

Wave 4 fan-out migration — specification dataclasses (ThermalSpec, EMISpec,
SignalIntegritySpec, SafetySpec, PcbSpecification) migrated to pyo3 pyclasses in
``temper-design-bundle``.

The pre-migration implementation is pinned verbatim in
``_specification_py_oracle.py`` and every assertion here drives IDENTICAL inputs
through both sides.

G1 (TDD): This file is committed BEFORE the Rust pyclass code. In identity mode
(before Rust), the shim imports ARE the Python dataclasses and the test
compares them against the oracles — trivially green. After migration, the shim
imports are the Rust pyclasses and the test compares Rust vs Python oracle.

Comparison convention: objects are canonicalized into plain comparable tuples.
Floats use exact bit-pattern comparison via ``float.hex()``.
Dicts are compared key-by-key with hex-float values.
"""

from __future__ import annotations

import re

import pytest

import tests.core._specification_py_oracle as _oracle

# ---------------------------------------------------------------------------
# Before migration: these ARE the Python dataclasses (identity mode).
# After migration: these are the Rust pyclasses via the delegation shim.
# We import from the PRODUCTION module (the shim), not from the oracle.
# In identity mode (pre-migration), this import IS the oracle.
# ---------------------------------------------------------------------------
from temper_placer.core.specification import (  # noqa: E402
    EMISpec,
    PcbSpecification,
    SafetySpec,
    SignalIntegritySpec,
    ThermalSpec,
)


# ============================================================================
# Repr normalization — the oracle classes are name-prefixed ``_Oracle*`` to
# avoid clashing with the production imports. We normalize both sides before
# comparing repr strings.
# ============================================================================

# Map from production class name to oracle class name (and back).
_PRODUCTION_TO_ORACLE = {
    "ThermalSpec": "_OracleThermalSpec",
    "EMISpec": "_OracleEMISpec",
    "SignalIntegritySpec": "_OracleSignalIntegritySpec",
    "SafetySpec": "_OracleSafetySpec",
    "PcbSpecification": "_OraclePcbSpecification",
}


def _norm_repr(r: str) -> str:
    """Normalize repr by stripping the ``_Oracle`` prefix from class names."""
    for prod, oracle in _PRODUCTION_TO_ORACLE.items():
        r = r.replace(oracle, prod)
    return r


# ============================================================================
# Canonicalization helpers — field-level extraction, bit-exact floats.
# ============================================================================


def _f(value):
    """Bit-exact float key: None stays None, else float.hex()."""
    return None if value is None else float(value).hex()


def _float_dict(d: dict) -> tuple:
    """Canonicalize a ``dict[str, float]``: sorted keys, hex-float values."""
    return tuple(sorted((k, _f(v)) for k, v in d.items()))


def _list_dict(d: dict) -> tuple:
    """Canonicalize a ``dict[str, list[str]]``: sorted keys, tuple of sorted lists."""
    return tuple(sorted((k, tuple(sorted(v))) for k, v in d.items()))


def _thermal_fields(spec) -> tuple:
    return (
        _f(spec.max_junction_temp_c),
        _f(spec.ambient_temp_c),
        _float_dict(spec.power_dissipation),
        spec.target_edge,
        _f(spec.max_heatspread_mm),
    )


def _emi_fields(spec) -> tuple:
    return (
        _float_dict(spec.max_loop_area_mm2),
        _list_dict(spec.loop_components),
        _f(spec.frequency_hz),
    )


def _si_fields(spec) -> tuple:
    return (
        _float_dict(spec.max_length_mm),
        _float_dict(spec.length_match_mm),
    )


def _safety_fields(spec) -> tuple:
    return (
        _f(spec.mains_voltage_v),
        spec.pollution_degree,  # int, not float
    )


def _pcb_spec_fields(spec) -> tuple:
    safety = None if spec.safety is None else _safety_fields(spec.safety)
    return (
        spec.name,
        _thermal_fields(spec.thermal),
        _emi_fields(spec.emi),
        _si_fields(spec.signal_integrity),
        safety,
    )


# ============================================================================
# Construction + defaults
# ============================================================================


def test_thermal_spec_defaults_identical():
    py = _oracle._OracleThermalSpec()
    rust = ThermalSpec()
    assert _thermal_fields(rust) == _thermal_fields(py)
    assert _norm_repr(repr(rust)) == _norm_repr(repr(py))
    # Cross-class ``==`` is not tested in identity mode (different types).
    # After migration, the Rust pyclass ``__eq__`` is tested via field tuples.


def test_thermal_spec_custom_values_identical():
    py = _oracle._OracleThermalSpec(
        max_junction_temp_c=125.0,
        ambient_temp_c=25.0,
        power_dissipation={"Q1": 15.0, "Q2": 12.0},
        target_edge="BOTTOM",
        max_heatspread_mm=30.0,
    )
    rust = ThermalSpec(
        max_junction_temp_c=125.0,
        ambient_temp_c=25.0,
        power_dissipation={"Q1": 15.0, "Q2": 12.0},
        target_edge="BOTTOM",
        max_heatspread_mm=30.0,
    )
    assert _thermal_fields(rust) == _thermal_fields(py)
    assert _norm_repr(repr(rust)) == _norm_repr(repr(py))
    # Cross-class ``==`` is not tested in identity mode (different types).
    # After migration, the Rust pyclass ``__eq__`` is tested via field tuples.
    # Mutable container identity: default factory creates fresh dict per instance.
    a = ThermalSpec()
    b = ThermalSpec()
    assert a.power_dissipation is not b.power_dissipation
    assert a.power_dissipation == {}
    assert b.power_dissipation == {}


def test_thermal_spec_eq_neq():
    a = ThermalSpec(max_junction_temp_c=100.0)
    b = ThermalSpec(max_junction_temp_c=100.0)
    c = ThermalSpec(max_junction_temp_c=110.0)
    assert a == b
    assert a != c
    # Different class: dataclass returns NotImplemented, so Python falls back
    # to identity check — the other's __eq__ likewise returns NotImplemented,
    # and Python compares by identity (a is not an int).
    assert a != 42


def test_emi_spec_defaults_identical():
    py = _oracle._OracleEMISpec()
    rust = EMISpec()
    assert _emi_fields(rust) == _emi_fields(py)
    assert _norm_repr(repr(rust)) == _norm_repr(repr(py))
    # Cross-class ``==`` is not tested in identity mode (different types).
    # After migration, the Rust pyclass ``__eq__`` is tested via field tuples.
    # Mutable container identity.
    a = EMISpec()
    b = EMISpec()
    assert a.max_loop_area_mm2 is not b.max_loop_area_mm2
    assert a.loop_components is not b.loop_components


def test_emi_spec_custom_values_identical():
    py = _oracle._OracleEMISpec(
        max_loop_area_mm2={"commutation_loop": 80.0},
        loop_components={"commutation_loop": ["C_BUS1", "Q1"]},
        frequency_hz=50000.0,
    )
    rust = EMISpec(
        max_loop_area_mm2={"commutation_loop": 80.0},
        loop_components={"commutation_loop": ["C_BUS1", "Q1"]},
        frequency_hz=50000.0,
    )
    assert _emi_fields(rust) == _emi_fields(py)
    assert _norm_repr(repr(rust)) == _norm_repr(repr(py))
    # Cross-class ``==`` is not tested in identity mode (different types).
    # After migration, the Rust pyclass ``__eq__`` is tested via field tuples.


def test_signal_integrity_spec_defaults_identical():
    py = _oracle._OracleSignalIntegritySpec()
    rust = SignalIntegritySpec()
    assert _si_fields(rust) == _si_fields(py)
    assert _norm_repr(repr(rust)) == _norm_repr(repr(py))
    # Cross-class ``==`` is not tested in identity mode (different types).
    # After migration, the Rust pyclass ``__eq__`` is tested via field tuples.
    a = SignalIntegritySpec()
    b = SignalIntegritySpec()
    assert a.max_length_mm is not b.max_length_mm
    assert a.length_match_mm is not b.length_match_mm


def test_signal_integrity_spec_custom_values_identical():
    py = _oracle._OracleSignalIntegritySpec(
        max_length_mm={"CLK": 100.0},
        length_match_mm={"DIFF_P": 2.0, "DIFF_N": 2.0},
    )
    rust = SignalIntegritySpec(
        max_length_mm={"CLK": 100.0},
        length_match_mm={"DIFF_P": 2.0, "DIFF_N": 2.0},
    )
    assert _si_fields(rust) == _si_fields(py)
    assert _norm_repr(repr(rust)) == _norm_repr(repr(py))
    # Cross-class ``==`` is not tested in identity mode (different types).
    # After migration, the Rust pyclass ``__eq__`` is tested via field tuples.


def test_safety_spec_defaults_identical():
    py = _oracle._OracleSafetySpec()
    rust = SafetySpec()
    assert _safety_fields(rust) == _safety_fields(py)
    assert _norm_repr(repr(rust)) == _norm_repr(repr(py))
    # Cross-class ``==`` is not tested in identity mode (different types).
    # After migration, the Rust pyclass ``__eq__`` is tested via field tuples.


def test_safety_spec_custom_values_identical():
    py = _oracle._OracleSafetySpec(mains_voltage_v=120.0, pollution_degree=3)
    rust = SafetySpec(mains_voltage_v=120.0, pollution_degree=3)
    assert _safety_fields(rust) == _safety_fields(py)
    assert _norm_repr(repr(rust)) == _norm_repr(repr(py))
    # Cross-class ``==`` is not tested in identity mode (different types).
    # After migration, the Rust pyclass ``__eq__`` is tested via field tuples.


def test_safety_spec_pollution_degree_is_int():
    """pollution_degree stays int, not widened to float."""
    s = SafetySpec(pollution_degree=2)
    assert type(s.pollution_degree) is int
    assert s.pollution_degree == 2


def test_pcb_spec_defaults_identical():
    py = _oracle._OraclePcbSpecification()
    rust = PcbSpecification()
    assert _pcb_spec_fields(rust) == _pcb_spec_fields(py)
    assert _norm_repr(repr(rust)) == _norm_repr(repr(py))
    # Cross-class ``==`` is not tested in identity mode (different types).
    # After migration, the Rust pyclass ``__eq__`` is tested via field tuples.
    assert rust.safety is None


def test_pcb_spec_full_round_trip_identical():
    py = _oracle._OraclePcbSpecification(
        name="Temper V1",
        thermal=_oracle._OracleThermalSpec(
            max_junction_temp_c=110.0,
            ambient_temp_c=40.0,
            power_dissipation={"Q1": 15.0, "Q2": 15.0},
            target_edge="BOTTOM",
            max_heatspread_mm=30.0,
        ),
        emi=_oracle._OracleEMISpec(
            max_loop_area_mm2={"commutation_loop": 80.0},
            loop_components={"commutation_loop": ["C_BUS1", "Q1", "Q2", "C_BUS2"]},
            frequency_hz=100000.0,
        ),
        signal_integrity=_oracle._OracleSignalIntegritySpec(
            max_length_mm={"CLK": 100.0},
            length_match_mm={"DIFF_P": 2.0, "DIFF_N": 2.0},
        ),
        safety=_oracle._OracleSafetySpec(mains_voltage_v=230.0, pollution_degree=2),
    )
    rust = PcbSpecification(
        name="Temper V1",
        thermal=ThermalSpec(
            max_junction_temp_c=110.0,
            ambient_temp_c=40.0,
            power_dissipation={"Q1": 15.0, "Q2": 15.0},
            target_edge="BOTTOM",
            max_heatspread_mm=30.0,
        ),
        emi=EMISpec(
            max_loop_area_mm2={"commutation_loop": 80.0},
            loop_components={"commutation_loop": ["C_BUS1", "Q1", "Q2", "C_BUS2"]},
            frequency_hz=100000.0,
        ),
        signal_integrity=SignalIntegritySpec(
            max_length_mm={"CLK": 100.0},
            length_match_mm={"DIFF_P": 2.0, "DIFF_N": 2.0},
        ),
        safety=SafetySpec(mains_voltage_v=230.0, pollution_degree=2),
    )
    assert _pcb_spec_fields(rust) == _pcb_spec_fields(py)
    assert _norm_repr(repr(rust)) == _norm_repr(repr(py))
    # Cross-class ``==`` is not tested in identity mode (different types).
    # After migration, the Rust pyclass ``__eq__`` is tested via field tuples.


def test_pcb_spec_without_safety():
    py = _oracle._OraclePcbSpecification(name="NoSafety")
    rust = PcbSpecification(name="NoSafety")
    assert _pcb_spec_fields(rust) == _pcb_spec_fields(py)
    assert _norm_repr(repr(rust)) == _norm_repr(repr(py))
    # Cross-class ``==`` is not tested in identity mode (different types).
    # After migration, the Rust pyclass ``__eq__`` is tested via field tuples.
    assert rust.safety is None


# ============================================================================
# __hash__ — dataclass with eq=True, frozen=False → __hash__ is None
# ============================================================================


@pytest.mark.parametrize(
    "cls",
    [ThermalSpec, EMISpec, SignalIntegritySpec, SafetySpec, PcbSpecification],
)
def test_hash_raises_typeerror(cls):
    """All spec dataclasses have ``eq=True, frozen=False`` → ``__hash__`` is None."""
    instance = cls()
    with pytest.raises(TypeError) as exc:
        hash(instance)
    cls_name = cls.__name__
    assert f"unhashable type: '{cls_name}'" in str(exc.value)


# ============================================================================
# __repr__ format: Cls(f1=repr1, f2=repr2, ...)
# ============================================================================


def test_thermal_spec_repr_format():
    s = ThermalSpec(max_junction_temp_c=125.0, target_edge="BOTTOM")
    r = repr(s)
    assert r.startswith("ThermalSpec(")
    assert r.endswith(")")
    assert "max_junction_temp_c=125.0" in r
    assert "target_edge='BOTTOM'" in r


def test_pcb_spec_repr_nested():
    """repr of PcbSpecification must show nested repr of sub-specs."""
    spec = PcbSpecification(name="Test", safety=SafetySpec(mains_voltage_v=120.0))
    r = repr(spec)
    assert r.startswith("PcbSpecification(")
    assert "name='Test'" in r
    assert "ThermalSpec(" in r  # default thermal nested repr
    assert "SafetySpec(" in r  # custom safety nested repr
    assert "mains_voltage_v=120.0" in r


# ============================================================================
# PcbSpecification.load — YAML boundary (stays in Python shim)
# ============================================================================


def test_load_pcb_spec_yaml_is_still_callable():
    """``PcbSpecification.load(path)`` must still work after migration (it is
    the Python shim's yaml-boundary helper, not migrated)."""
    from pathlib import Path

    configs = Path(__file__).resolve().parent.parent.parent / "configs"
    spec = PcbSpecification.load(configs / "pcb_spec.yaml")
    assert spec.name == "Temper V1"
    assert spec.safety is not None
    assert spec.safety.mains_voltage_v == pytest.approx(230.0)
    assert spec.safety.pollution_degree == 2
    assert spec.thermal.max_junction_temp_c == pytest.approx(110.0)


# ============================================================================
# Cross-class equality: different spec types are never equal.
# ============================================================================


def test_different_spec_types_not_equal():
    """A ThermalSpec is never equal to an EMISpec, even if all fields match."""
    t = ThermalSpec()
    e = EMISpec()
    assert t != e
    assert e != t
