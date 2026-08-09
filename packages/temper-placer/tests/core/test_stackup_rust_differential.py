"""Differential test: Rust stackup pyclasses + kernel
(temper_design_bundle_python) vs the pinned Python oracle.

Wave 4, core-contracts migration — ``temper_placer/core/stackup.py``.
This is the differential oracle for the ``stackup_contracts.rs`` migration.

The Rust pyo3 pyclasses ``LayerConfig``, ``Stackup`` and the pyfunction
``characteristic_impedance_microstrip`` (in ``temper_design_bundle_python``,
from the ``temper-design-bundle`` crate) must reproduce the pre-migration
Python implementation bit-identically. The pre-migration implementation is
pinned verbatim as the oracle (``_stackup_py_oracle.py``) and every
assertion here drives IDENTICAL inputs through both sides.

Comparison convention: objects are canonicalized into plain comparable
tuples before assertion. Floats are compared as exact bit patterns via
``float.hex()``.
"""

from __future__ import annotations

import math

import pytest
import temper_design_bundle_python as _tdb

import tests.core._stackup_py_oracle as _oracle

# Rust symbols under test — must exist or this file fails to collect (RED).
LAYER_CONFIG = _tdb.LayerConfig
STACKUP = _tdb.Stackup
CHARACTERISTIC_IMPEDANCE_MICROSTRIP = _tdb.characteristic_impedance_microstrip
JLC04161H_7628 = _tdb.jlc04161h_7628


# ---------------------------------------------------------------------------
# Canonicalization helpers (field-level extraction, bit-exact floats).
# ---------------------------------------------------------------------------


def _f(value):
    """Bit-exact float key: None stays None, else float.hex()."""
    return None if value is None else float(value).hex()


def _layer_fields(lc):
    """Extract LayerConfig fields into a comparable tuple."""
    return (lc.name, lc.kicad_index, lc.type, _f(lc.copper_weight_oz), _f(lc.thickness_mm))


def _stackup_fields(su):
    """Extract Stackup fields into a comparable tuple."""
    return (
        su.name,
        tuple(_layer_fields(ly) for ly in su.layers),
        _f(su.total_thickness_mm),
        _f(su.prepreg_outer_mm),
        _f(su.core_inner_mm),
        _f(su.dielectric_constant),
    )


# ---------------------------------------------------------------------------
# LayerConfig: construction, defaults, repr, eq, hash
# ---------------------------------------------------------------------------


def test_layer_config_construction_identical():
    py = _oracle.LayerConfig("F.Cu", 0, "signal", 1.0, 0.035)
    rust = LAYER_CONFIG("F.Cu", 0, "signal", 1.0, 0.035)
    assert _layer_fields(rust) == _layer_fields(py)


def test_layer_config_all_layers_identical():
    for py in _oracle.jlc04161h_7628().layers:
        rust = LAYER_CONFIG(py.name, py.kicad_index, py.type, py.copper_weight_oz, py.thickness_mm)
        assert _layer_fields(rust) == _layer_fields(py)


def test_layer_config_repr_identical():
    py = _oracle.LayerConfig("F.Cu", 0, "signal", 1.0, 0.035)
    rust = LAYER_CONFIG("F.Cu", 0, "signal", 1.0, 0.035)
    assert repr(rust) == repr(py)


def test_layer_config_eq_identical():
    a_rust = LAYER_CONFIG("F.Cu", 0, "signal", 1.0, 0.035)
    b_rust = LAYER_CONFIG("F.Cu", 0, "signal", 1.0, 0.035)
    c_rust = LAYER_CONFIG("B.Cu", 31, "signal", 1.0, 0.035)
    assert a_rust == b_rust
    assert a_rust != c_rust
    # Equality with foreign type returns NotImplemented (handled by Python).
    assert a_rust != "not a layer"


def test_layer_config_frozen():
    """LayerConfig is frozen — attributes cannot be set."""
    rust = LAYER_CONFIG("F.Cu", 0, "signal", 1.0, 0.035)
    with pytest.raises(AttributeError):
        rust.name = "B.Cu"


def test_layer_config_hash_identical():
    """frozen=True dataclasses are hashable — same fields -> same hash."""
    py = _oracle.LayerConfig("F.Cu", 0, "signal", 1.0, 0.035)
    rust = LAYER_CONFIG("F.Cu", 0, "signal", 1.0, 0.035)
    assert hash(rust) == hash(py)
    # Hash consistency
    assert hash(rust) == hash(LAYER_CONFIG("F.Cu", 0, "signal", 1.0, 0.035))
    # Hash changes with field change
    assert hash(rust) != hash(LAYER_CONFIG("B.Cu", 31, "signal", 1.0, 0.035))


# ---------------------------------------------------------------------------
# Stackup: construction, defaults, repr, eq, hash
# ---------------------------------------------------------------------------


def _make_layer_rust(name, idx, typ, oz, mm):
    return LAYER_CONFIG(name, idx, typ, oz, mm)


def _make_layer_py(name, idx, typ, oz, mm):
    return _oracle.LayerConfig(name, idx, typ, oz, mm)


def _jlc_layers_rust():
    return [
        _make_layer_rust("F.Cu", 0, "signal", 1.0, 0.035),
        _make_layer_rust("In1.Cu", 1, "plane", 0.5, 0.017),
        _make_layer_rust("In2.Cu", 2, "plane", 0.5, 0.017),
        _make_layer_rust("B.Cu", 31, "signal", 1.0, 0.035),
    ]


def _jlc_layers_py():
    return [
        _make_layer_py("F.Cu", 0, "signal", 1.0, 0.035),
        _make_layer_py("In1.Cu", 1, "plane", 0.5, 0.017),
        _make_layer_py("In2.Cu", 2, "plane", 0.5, 0.017),
        _make_layer_py("B.Cu", 31, "signal", 1.0, 0.035),
    ]


def test_stackup_construction_identical():
    py = _oracle.Stackup(
        name="JLCPCB JLC04161H-7628",
        layers=_jlc_layers_py(),
        total_thickness_mm=1.6,
        prepreg_outer_mm=0.2,
        core_inner_mm=1.1,
        dielectric_constant=4.5,
    )
    rust = STACKUP(
        name="JLCPCB JLC04161H-7628",
        layers=_jlc_layers_rust(),
        total_thickness_mm=1.6,
        prepreg_outer_mm=0.2,
        core_inner_mm=1.1,
        dielectric_constant=4.5,
    )
    assert _stackup_fields(rust) == _stackup_fields(py)


def test_stackup_repr_identical():
    py = _oracle.Stackup(
        name="TestBoard",
        layers=_jlc_layers_py(),
        total_thickness_mm=1.6,
        prepreg_outer_mm=0.2,
        core_inner_mm=1.1,
        dielectric_constant=4.5,
    )
    rust = STACKUP(
        name="TestBoard",
        layers=_jlc_layers_rust(),
        total_thickness_mm=1.6,
        prepreg_outer_mm=0.2,
        core_inner_mm=1.1,
        dielectric_constant=4.5,
    )
    assert repr(rust) == repr(py)


def test_stackup_eq_identical():
    a = STACKUP(
        name="TestBoard",
        layers=_jlc_layers_rust(),
        total_thickness_mm=1.6,
        prepreg_outer_mm=0.2,
        core_inner_mm=1.1,
        dielectric_constant=4.5,
    )
    b = STACKUP(
        name="TestBoard",
        layers=_jlc_layers_rust(),
        total_thickness_mm=1.6,
        prepreg_outer_mm=0.2,
        core_inner_mm=1.1,
        dielectric_constant=4.5,
    )
    c = STACKUP(
        name="Other",
        layers=_jlc_layers_rust(),
        total_thickness_mm=1.6,
        prepreg_outer_mm=0.2,
        core_inner_mm=1.1,
        dielectric_constant=4.5,
    )
    assert a == b
    assert a != c
    assert a != "not a stackup"


def test_stackup_frozen():
    rust = STACKUP(
        name="TestBoard",
        layers=_jlc_layers_rust(),
        total_thickness_mm=1.6,
        prepreg_outer_mm=0.2,
        core_inner_mm=1.1,
        dielectric_constant=4.5,
    )
    with pytest.raises(AttributeError):
        rust.name = "Other"


def test_stackup_unhashable():
    """Stackup has a ``list`` field (layers) — even with frozen=True,
    hash() raises TypeError because the list is unhashable."""
    su = STACKUP(
        name="TestBoard",
        layers=_jlc_layers_rust(),
        total_thickness_mm=1.6,
        prepreg_outer_mm=0.2,
        core_inner_mm=1.1,
        dielectric_constant=4.5,
    )
    with pytest.raises(TypeError):
        hash(su)

    py_su = _oracle.Stackup(
        name="TestBoard",
        layers=_jlc_layers_py(),
        total_thickness_mm=1.6,
        prepreg_outer_mm=0.2,
        core_inner_mm=1.1,
        dielectric_constant=4.5,
    )
    with pytest.raises(TypeError):
        hash(py_su)


# ---------------------------------------------------------------------------
# Factory: jlc04161h_7628()
# ---------------------------------------------------------------------------


def test_jlc04161h_7628_identical():
    py = _oracle.jlc04161h_7628()
    rust = JLC04161H_7628()
    assert _stackup_fields(rust) == _stackup_fields(py)
    assert repr(rust) == repr(py)
    assert rust.name == py.name
    assert len(rust.layers) == len(py.layers) == 4


# ---------------------------------------------------------------------------
# Kernel: characteristic_impedance_microstrip — bit-exact float comparison
# ---------------------------------------------------------------------------


def test_impedance_bit_exact_at_jlc_default():
    """Z0 at the USB differential-pair target width (~0.3 mm on JLC04161H-7628)."""
    py_su = _oracle.jlc04161h_7628()
    rust_su = JLC04161H_7628()
    for w_mm in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.5, 2.0]:
        py_z = _oracle.characteristic_impedance_microstrip(w_mm, py_su)
        rust_z = CHARACTERISTIC_IMPEDANCE_MICROSTRIP(w_mm, rust_su)
        assert float(rust_z).hex() == float(py_z).hex(), f"width={w_mm}mm: {rust_z!r} != {py_z!r}"


def test_impedance_bit_exact_randomized():
    """Bit-exact parity across randomized widths and stackups."""
    import random

    rng = random.Random(42)
    for _ in range(200):
        w = rng.uniform(0.05, 5.0)
        er = rng.uniform(3.0, 6.0)
        h = rng.uniform(0.1, 1.0)
        t = rng.uniform(0.01, 0.1)

        py_layers = [_oracle.LayerConfig("F.Cu", 0, "signal", 1.0, t)]
        py_su = _oracle.Stackup("rand", py_layers, 1.6, h, 1.0, er)
        py_z = _oracle.characteristic_impedance_microstrip(w, py_su)

        rust_layers = [LAYER_CONFIG("F.Cu", 0, "signal", 1.0, t)]
        rust_su = STACKUP("rand", rust_layers, 1.6, h, 1.0, er)
        rust_z = CHARACTERISTIC_IMPEDANCE_MICROSTRIP(w, rust_su)

        assert float(rust_z).hex() == float(py_z).hex(), (
            f"w={w}, h={h}, t={t}, er={er}: {rust_z!r} != {py_z!r}"
        )


def test_impedance_edge_cases():
    """Edge case behaviours must match the Python oracle (NaN, inf, near-zero)."""
    py_su = _oracle.jlc04161h_7628()
    rust_su = JLC04161H_7628()

    # Very small width → large impedance (but finite)
    py_z = _oracle.characteristic_impedance_microstrip(1e-6, py_su)
    rust_z = CHARACTERISTIC_IMPEDANCE_MICROSTRIP(1e-6, rust_su)
    assert float(rust_z).hex() == float(py_z).hex()

    # Very large width → impedance approaches 0
    py_z = _oracle.characteristic_impedance_microstrip(1000.0, py_su)
    rust_z = CHARACTERISTIC_IMPEDANCE_MICROSTRIP(1000.0, rust_su)
    assert float(rust_z).hex() == float(py_z).hex()

    # NaN width → NaN result on both sides
    py_z = _oracle.characteristic_impedance_microstrip(float("nan"), py_su)
    rust_z = CHARACTERISTIC_IMPEDANCE_MICROSTRIP(float("nan"), rust_su)
    assert math.isnan(float(rust_z)) == math.isnan(float(py_z))

    # Inf width → log(0) raises ValueError on both sides (math domain error)
    with pytest.raises(ValueError, match="math domain error"):
        _oracle.characteristic_impedance_microstrip(float("inf"), py_su)
    with pytest.raises(ValueError, match="math domain error"):
        CHARACTERISTIC_IMPEDANCE_MICROSTRIP(float("inf"), rust_su)

    # Zero width → log(positive) should work (5.98*h / t > 0 for t > 0)
    py_z = _oracle.characteristic_impedance_microstrip(0.0, py_su)
    rust_z = CHARACTERISTIC_IMPEDANCE_MICROSTRIP(0.0, rust_su)
    assert float(rust_z).hex() == float(py_z).hex()

    # Negative width → denominator may be negative, but log arg may still be
    # positive or negative depending on values. Test with the JLC defaults.
    # For the JLC stackup, w=-0.04 gives 0.8*w + t = -0.032+0.035 = 0.003 > 0, so log_arg > 0.
    # The result still exists (though physically meaningless).
    py_z = _oracle.characteristic_impedance_microstrip(-0.04, py_su)
    rust_z = CHARACTERISTIC_IMPEDANCE_MICROSTRIP(-0.04, rust_su)
    assert float(rust_z).hex() == float(py_z).hex()


def test_impedance_depends_only_on_first_layer():
    """Z0 reads only layers[0].thickness_mm — second layer thickness is irrelevant."""
    t_0 = 0.035
    t_1_variants = [0.017, 0.035, 0.070, 0.1]
    w = 0.3
    er = 4.5
    h = 0.2

    base_z = None
    for t1 in t_1_variants:
        py_layers = [
            _oracle.LayerConfig("F.Cu", 0, "signal", 1.0, t_0),
            _oracle.LayerConfig("In1.Cu", 1, "plane", 0.5, t1),
        ]
        py_su = _oracle.Stackup("test", py_layers, 1.6, h, 1.0, er)
        py_z = _oracle.characteristic_impedance_microstrip(w, py_su)

        rust_layers = [
            LAYER_CONFIG("F.Cu", 0, "signal", 1.0, t_0),
            LAYER_CONFIG("In1.Cu", 1, "plane", 0.5, t1),
        ]
        rust_su = STACKUP("test", rust_layers, 1.6, h, 1.0, er)
        rust_z = CHARACTERISTIC_IMPEDANCE_MICROSTRIP(w, rust_su)

        if base_z is None:
            base_z = py_z
        assert float(py_z).hex() == float(base_z).hex(), f"Python Z0 changed with t1={t1}"
        assert float(rust_z).hex() == float(py_z).hex(), f"Rust/Python mismatch at t1={t1}"
