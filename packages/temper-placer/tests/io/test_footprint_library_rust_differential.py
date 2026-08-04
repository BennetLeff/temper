"""Differential test: Rust footprint library (temper_io_types) vs the pinned
Python oracle.

Wave 4, Phase 3, candidate 5 — the config/reference loaders migration (plan
``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md``, candidate
5). This mirrors the loop/netclass loader judgment: PyYAML (``yaml.safe_load``)
stays on the Python side and is called back across the boundary; everything
downstream — bounds validation, coercion order, error strings, dict iteration
order — is Rust.

The Rust ``FootprintSpec``/``FootprintLibrary`` pyclasses (in
``temper_io_types``, from the ``temper-io-types`` crate) must reproduce the
pre-migration implementation of ``temper_placer/io/footprint_library.py``
bit-identically. The pre-migration implementation is pinned verbatim as the
oracle (``_footprint_library_py_oracle.py``, commit 79ab9bd0e) and every
assertion here drives IDENTICAL inputs through both sides.

Comparison convention (mirrors the landed contract differentials): floats are
compared as exact bit patterns via ``float.hex()``, never a tolerance, and each
leaf's concrete ``type`` is carried in the comparison key so ``int``-vs-``float``
cannot hide behind numeric equality.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import temper_io_types as _io

import tests.io._footprint_library_py_oracle as _oracle

# Rust symbols under test — FootprintLibrary must exist or this file fails to
# collect (RED). FootprintSpec already exists in temper_io_types (it is the
# type the library holds), but the library surface is new.
FOOTPRINT_SPEC = _io.FootprintSpec
FOOTPRINT_LIBRARY = _io.FootprintLibrary
LOAD_FOOTPRINT_LIBRARY = _io.load_footprint_library


# ---------------------------------------------------------------------------
# Canonicalization helpers (bit-exact floats, concrete leaf types).
# ---------------------------------------------------------------------------


def _f(value):
    """Bit-exact float key: None stays None, else float.hex()."""
    return None if value is None else float(value).hex()


def _spec_key(spec):
    """Canonical tuple for a FootprintSpec: every leaf's concrete type matters.

    bounds is a 2-tuple whose elements may be int or float; each element is
    rendered as (type.__name__, float.hex()) so an int 2 vs a float 2.0
    cannot hide behind numeric equality.
    """
    bounds = spec.bounds
    return (
        spec.name,
        tuple((type(v).__name__, _f(v)) for v in bounds),
        type(spec.bounds).__name__,
        _f(spec.courtyard_margin),
        spec.thermal_pad,
        None if spec.pin_1_offset is None else tuple(
            (type(v).__name__, _f(v)) for v in spec.pin_1_offset
        ),
    )


def _lib_key(lib):
    """Canonical dict key for a library: insertion order + per-spec keys."""
    return tuple((name, _spec_key(spec)) for name, spec in lib.footprints.items())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_YAML = """
footprints:
  TO-247-3:
    bounds: [16.0, 21.0]
    courtyard_margin: 0.25
    thermal_pad: true
    pin_1_offset: [-5.08, 0]

  SOIC-16_W:
    bounds: [10.3, 7.5]
    courtyard_margin: 0.2
    thermal_pad: false

  "0805":
    bounds: [2.0, 1.25]
    courtyard_margin: 0.15
    thermal_pad: false

  "0603":
    bounds: [1.6, 0.8]
    courtyard_margin: 0.1
    thermal_pad: false
"""

CONFIGS_DIR = Path(__file__).parent.parent.parent / "configs"
PRODUCTION_YAML = (CONFIGS_DIR / "footprint_library.yaml").read_text(encoding="utf-8")


@pytest.fixture
def sample_library_yaml():
    return SAMPLE_YAML


# ---------------------------------------------------------------------------
# from_yaml_string parity (R1a — the load surface).
# ---------------------------------------------------------------------------


def test_from_yaml_string_matches_oracle_on_sample():
    py_lib = _oracle.FootprintLibrary.from_yaml_string(SAMPLE_YAML)
    rs_lib = FOOTPRINT_LIBRARY.from_yaml_string(SAMPLE_YAML)

    assert len(rs_lib) == len(py_lib)
    assert list(rs_lib.footprints.keys()) == list(py_lib.footprints.keys())
    assert _lib_key(rs_lib) == _lib_key(py_lib)


def test_from_yaml_string_matches_oracle_on_production_fixture():
    py_lib = _oracle.FootprintLibrary.from_yaml_string(PRODUCTION_YAML)
    rs_lib = FOOTPRINT_LIBRARY.from_yaml_string(PRODUCTION_YAML)

    assert len(rs_lib) == len(py_lib)
    assert list(rs_lib.footprints.keys()) == list(py_lib.footprints.keys())
    assert _lib_key(rs_lib) == _lib_key(py_lib)


def test_from_yaml_string_empty_and_missing_section_match_oracle():
    for content in ("", "{}", "other: 1", "footprints: {}", "null"):
        py_lib = _oracle.FootprintLibrary.from_yaml_string(content)
        rs_lib = FOOTPRINT_LIBRARY.from_yaml_string(content)
        assert len(rs_lib) == len(py_lib) == 0
        assert _lib_key(rs_lib) == _lib_key(py_lib)


def test_load_footprint_library_from_file_matches_oracle(tmp_path):
    path = tmp_path / "fp.yaml"
    path.write_text(SAMPLE_YAML, encoding="utf-8")
    py_lib = _oracle.load_footprint_library(path)
    rs_lib = LOAD_FOOTPRINT_LIBRARY(str(path))
    assert _lib_key(rs_lib) == _lib_key(py_lib)


def test_load_missing_file_raises_same_error(tmp_path):
    missing = tmp_path / "nope.yaml"
    with pytest.raises(FileNotFoundError):
        _oracle.load_footprint_library(missing)
    with pytest.raises(FileNotFoundError):
        LOAD_FOOTPRINT_LIBRARY(str(missing))


def test_malformed_yaml_raises_same_error(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("{ invalid yaml: [", encoding="utf-8")
    with pytest.raises(yaml.YAMLError):
        _oracle.FootprintLibrary.from_yaml_string(bad.read_text())
    with pytest.raises(yaml.YAMLError):
        FOOTPRINT_LIBRARY.from_yaml_string(bad.read_text())


def test_missing_bounds_raises_same_value_error():
    content = """
footprints:
  BadFootprint:
    courtyard_margin: 0.1
"""
    with pytest.raises(ValueError) as py_exc:
        _oracle.FootprintLibrary.from_yaml_string(content)
    with pytest.raises(ValueError) as rs_exc:
        FOOTPRINT_LIBRARY.from_yaml_string(content)
    assert str(rs_exc.value) == str(py_exc.value)


def test_invalid_bounds_format_raises_same_value_error():
    content = """
footprints:
  BadFootprint:
    bounds: [1.0]
"""
    with pytest.raises(ValueError) as py_exc:
        _oracle.FootprintLibrary.from_yaml_string(content)
    with pytest.raises(ValueError) as rs_exc:
        FOOTPRINT_LIBRARY.from_yaml_string(content)
    assert str(rs_exc.value) == str(py_exc.value)


def test_invalid_pin_1_offset_raises_same_value_error():
    content = """
footprints:
  BadFootprint:
    bounds: [2.0, 1.0]
    pin_1_offset: [1.0]
"""
    with pytest.raises(ValueError) as py_exc:
        _oracle.FootprintLibrary.from_yaml_string(content)
    with pytest.raises(ValueError) as rs_exc:
        FOOTPRINT_LIBRARY.from_yaml_string(content)
    assert str(rs_exc.value) == str(py_exc.value)


def test_bounds_ints_preserve_concrete_type():
    """The dataclass coerces nothing: bounds [2, 1] stay ints, and .width is
    int 2, not 2.0. The pyclass must not widen (R1a: concrete leaf type in the
    comparison key — verified by _spec_key above, driven here explicitly)."""
    content = "footprints:\n  R0805:\n    bounds: [2, 1]\n"
    py_lib = _oracle.FootprintLibrary.from_yaml_string(content)
    rs_lib = FOOTPRINT_LIBRARY.from_yaml_string(content)
    assert _lib_key(rs_lib) == _lib_key(py_lib)
    py_spec = py_lib["R0805"]
    rs_spec = rs_lib["R0805"]
    assert type(rs_spec.bounds[0]).__name__ == type(py_spec.bounds[0]).__name__
    assert type(rs_spec.width).__name__ == type(py_spec.width).__name__


# ---------------------------------------------------------------------------
# Container surface parity (R1a — mutability, dict-like access, defaults).
# ---------------------------------------------------------------------------


def test_add_get_contains_getitem_len_match_oracle():
    py_lib = _oracle.FootprintLibrary()
    rs_lib = FOOTPRINT_LIBRARY()

    for spec in (
        _oracle.FootprintSpec("0805", (2.0, 1.25)),
        _oracle.FootprintSpec("0603", (1.6, 0.8)),
    ):
        py_lib.add(spec)
    for spec in (
        FOOTPRINT_SPEC("0805", (2.0, 1.25)),
        FOOTPRINT_SPEC("0603", (1.6, 0.8)),
    ):
        rs_lib.add(spec)

    assert len(rs_lib) == len(py_lib) == 2
    assert ("0805" in rs_lib) == ("0805" in py_lib)
    assert ("NOPE" in rs_lib) == ("NOPE" in py_lib)
    assert _spec_key(rs_lib["0805"]) == _spec_key(py_lib["0805"])
    assert _spec_key(rs_lib.get("0603")) == _spec_key(py_lib.get("0603"))


def test_get_with_default_matches_oracle():
    py_lib = _oracle.FootprintLibrary()
    rs_lib = FOOTPRINT_LIBRARY()
    py_default = _oracle.FootprintSpec("DEFAULT", (1.0, 1.0))
    rs_default = FOOTPRINT_SPEC("DEFAULT", (1.0, 1.0))

    assert _spec_key(py_lib.get("NOPE", default=py_default)) == _spec_key(py_default)
    assert _spec_key(rs_lib.get("NOPE", default=rs_default)) == _spec_key(rs_default)


def test_get_missing_raises_same_key_error():
    py_lib = _oracle.FootprintLibrary()
    rs_lib = FOOTPRINT_LIBRARY()
    with pytest.raises(KeyError) as py_exc:
        py_lib.get("NONEXISTENT")
    with pytest.raises(KeyError) as rs_exc:
        rs_lib.get("NONEXISTENT")
    assert str(rs_exc.value) == str(py_exc.value)


def test_library_footprints_dict_is_mutable_and_shared():
    """lib.footprints is the live dict: in-place mutation persists (the
    dataclass contract)."""
    rs_lib = FOOTPRINT_LIBRARY()
    rs_lib.footprints["X"] = FOOTPRINT_SPEC("X", (1.0, 2.0))
    assert "X" in rs_lib
    assert len(rs_lib) == 1
    del rs_lib.footprints["X"]
    assert "X" not in rs_lib


def test_footprint_spec_width_height_repr_match_oracle():
    py_spec = _oracle.FootprintSpec("TO-247-3", (16.0, 21.0), courtyard_margin=0.25,
                                    thermal_pad=True, pin_1_offset=(-5.08, 0.0))
    rs_spec = FOOTPRINT_SPEC("TO-247-3", (16.0, 21.0), courtyard_margin=0.25,
                             thermal_pad=True, pin_1_offset=(-5.08, 0.0))
    assert rs_spec.width == py_spec.width
    assert rs_spec.height == py_spec.height
    assert repr(rs_spec) == repr(py_spec)


def test_footprint_spec_defaults_match_oracle():
    py_spec = _oracle.FootprintSpec("0805", (2.0, 1.25))
    rs_spec = FOOTPRINT_SPEC("0805", (2.0, 1.25))
    assert _spec_key(rs_spec) == _spec_key(py_spec)
    assert repr(rs_spec) == repr(py_spec)


def test_footprint_spec_equality_matches_oracle():
    py_a = _oracle.FootprintSpec("0805", (2.0, 1.25))
    py_b = _oracle.FootprintSpec("0805", (2.0, 1.25))
    py_c = _oracle.FootprintSpec("0603", (1.6, 0.8))
    rs_a = FOOTPRINT_SPEC("0805", (2.0, 1.25))
    rs_b = FOOTPRINT_SPEC("0805", (2.0, 1.25))
    rs_c = FOOTPRINT_SPEC("0603", (1.6, 0.8))
    assert (rs_a == rs_b) == (py_a == py_b)
    assert (rs_a == rs_c) == (py_a == py_c)
    assert (rs_a == 42) == (py_a == 42)
    assert (rs_a != rs_c) == (py_a != py_c)


def test_footprint_spec_is_unhashable_like_dataclass():
    rs_spec = FOOTPRINT_SPEC("0805", (2.0, 1.25))
    with pytest.raises(TypeError):
        hash(rs_spec)
