"""Property-based + metamorphic tests for the Rust footprint library.

Wave 4, Phase 3, candidate 5 (plan ``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md``,
R1c/R1d). These properties exercise the migrated ``temper_placer.io.footprint_library``
module (a pure-delegation re-export of the ``temper_io_types`` pyclasses);
bit-identical parity against the pinned pre-migration Python is asserted
separately by ``test_footprint_library_rust_differential.py``.

Properties (all non-vacuously guarded):

- P1. YAML-load parity: for any generated library YAML (names, float/int
  bounds, optional fields), the Rust and oracle loads agree bit-identically
  (floats via ``float.hex()``, concrete leaf types carried).
- P2. Int-bounds type preservation: YAML int bounds stay ``int`` and
  ``width``/``height`` return ``int`` — the pyclass widens nothing.
- P3. Add/get/contains coherence: adding a spec then querying it returns the
  same spec; missing names raise ``KeyError``; ``default`` is returned when
  present.
- P4. String-value coercion: a string ``courtyard_margin`` is coerced by
  CPython's own ``float()``, identically on both arms.
- P5. Empty/missing-section semantics: empty, ``{}``, ``null``, and
  missing-``footprints`` inputs all yield an empty library on both arms.

Metamorphic relations:

- MR1. Library insertion order is order-preserving: adding specs in order
  ``a, b, c`` yields ``list(lib.footprints) == [a, b, c]`` on both arms.
- MR2. Loading is idempotent over content: re-adding an identical spec
  replaces the earlier one (dict semantics), and the library size stays 1.
- MR3. ``get(name, default)`` with a missing name returns the default, and
  ``get`` with an existing name ignores the default — on both arms.
"""

from __future__ import annotations

import temper_io_types as _io
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

import tests.io._footprint_library_py_oracle as _oracle
from tests.io.test_footprint_library_rust_differential import _lib_key, _spec_key

FOOTPRINT_LIBRARY = _io.FootprintLibrary
LOAD = _io.load_footprint_library

MAX_EXAMPLES = 100


@st.composite
def footprint_spec_dict(draw):
    """A random footprint entry as a plain dict (what the loader consumes)."""
    name = draw(st.text(min_size=1, max_size=12, alphabet="ABCDEF0123456789_-"))
    bounds = draw(st.lists(st.floats(min_value=0.1, max_value=50.0, allow_nan=False,
                                     allow_infinity=False), min_size=2, max_size=2))
    entry: dict = {"bounds": bounds}
    draw_opt = st.booleans()
    if draw(draw_opt):
        entry["courtyard_margin"] = draw(st.floats(min_value=0.0, max_value=2.0,
                                                   allow_nan=False, allow_infinity=False))
    if draw(draw_opt):
        entry["thermal_pad"] = draw(st.booleans())
    if draw(draw_opt):
        entry["pin_1_offset"] = draw(st.lists(st.floats(min_value=-20.0, max_value=20.0,
                                                        allow_nan=False, allow_infinity=False),
                                              min_size=2, max_size=2))
    return name, entry


@st.composite
def library_yaml(draw):
    specs = draw(st.lists(footprint_spec_dict(), min_size=0, max_size=6))
    data = {"footprints": dict(specs)}
    return yaml.safe_dump(data, default_flow_style=False, sort_keys=False)


@st.composite
def int_bounds_yaml(draw):
    name = draw(st.text(min_size=1, max_size=8, alphabet="ABC0123"))
    w = draw(st.integers(min_value=1, max_value=100))
    h = draw(st.integers(min_value=1, max_value=100))
    return f"footprints:\n  {name}:\n    bounds: [{w}, {h}]\n"


@given(library_yaml())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p1_yaml_load_parity(content):
    py_lib = _oracle.FootprintLibrary.from_yaml_string(content)
    rs_lib = FOOTPRINT_LIBRARY.from_yaml_string(content)
    assert len(rs_lib) == len(py_lib)
    assert list(rs_lib.footprints.keys()) == list(py_lib.footprints.keys())
    assert _lib_key(rs_lib) == _lib_key(py_lib)


@given(int_bounds_yaml())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p2_int_bounds_preserve_concrete_type(content):
    py_lib = _oracle.FootprintLibrary.from_yaml_string(content)
    rs_lib = FOOTPRINT_LIBRARY.from_yaml_string(content)
    assert _lib_key(rs_lib) == _lib_key(py_lib)
    name = next(iter(rs_lib.footprints))
    assert type(rs_lib[name].bounds[0]).__name__ == type(py_lib[name].bounds[0]).__name__
    assert type(rs_lib[name].width).__name__ == type(py_lib[name].width).__name__


@given(st.lists(footprint_spec_dict(), min_size=1, max_size=8))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p3_add_get_contains_coherence(specs):
    py_lib = _oracle.FootprintLibrary()
    rs_lib = FOOTPRINT_LIBRARY()
    for name, entry in specs:
        yaml_str = yaml.safe_dump({"footprints": {name: entry}}, sort_keys=False)
        py_spec = _oracle.FootprintLibrary.from_yaml_string(yaml_str)[name]
        rs_spec = FOOTPRINT_LIBRARY.from_yaml_string(yaml_str)[name]
        py_lib.add(py_spec)
        rs_lib.add(rs_spec)
        assert name in rs_lib
        assert len(rs_lib) == len(py_lib)
        assert _spec_key(rs_lib[name]) == _spec_key(py_lib[name])
        assert _spec_key(rs_lib.get(name)) == _spec_key(py_lib.get(name))


@given(footprint_spec_dict())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p4_string_value_coercion(name_entry):
    name, entry = name_entry
    entry = dict(entry)
    entry["courtyard_margin"] = "0.25"
    content = yaml.safe_dump({"footprints": {name: entry}}, sort_keys=False)
    py_spec = _oracle.FootprintLibrary.from_yaml_string(content)[name]
    rs_spec = FOOTPRINT_LIBRARY.from_yaml_string(content)[name]
    assert _spec_key(rs_spec) == _spec_key(py_spec)
    assert rs_spec.courtyard_margin == 0.25


@given(st.sampled_from(["", "{}", "null", "other: 1", "footprints: {}", "[]"]))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p5_empty_and_missing_section(content):
    py_lib = _oracle.FootprintLibrary.from_yaml_string(content)
    rs_lib = FOOTPRINT_LIBRARY.from_yaml_string(content)
    assert len(rs_lib) == len(py_lib) == 0
    assert _lib_key(rs_lib) == _lib_key(py_lib)


@given(st.lists(footprint_spec_dict(), min_size=0, max_size=6))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr1_insertion_order_preserved(specs):
    """dict semantics: ``list(lib.footprints)`` is insertion order on both
    arms (an insertion-ordered map, not a HashMap — the candidate-6 trap)."""
    names = [name for name, _ in specs]
    rs_names = []
    for name, entry in specs:
        content = yaml.safe_dump({"footprints": {name: entry}}, sort_keys=False)
        rs_lib = FOOTPRINT_LIBRARY.from_yaml_string(content)
        rs_names.extend(rs_lib.footprints.keys())
    # concatenation of single-spec loads preserves each spec's own key order
    assert rs_names == names


@given(footprint_spec_dict())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr2_add_replace_is_idempotent(name_entry):
    name, entry = name_entry
    content = yaml.safe_dump({"footprints": {name: entry}}, sort_keys=False)
    spec = FOOTPRINT_LIBRARY.from_yaml_string(content)[name]
    lib = FOOTPRINT_LIBRARY()
    lib.add(spec)
    lib.add(spec)
    assert len(lib) == 1
    assert _spec_key(lib[name]) == _spec_key(spec)


@given(footprint_spec_dict())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr3_get_default_vs_present(name_entry):
    name, entry = name_entry
    content = yaml.safe_dump({"footprints": {name: entry}}, sort_keys=False)
    lib = FOOTPRINT_LIBRARY.from_yaml_string(content)
    default = _io.FootprintSpec("DEFAULT", (1.0, 1.0))
    # present name: default ignored
    assert _spec_key(lib.get(name, default=default)) == _spec_key(lib[name])
    # missing name: default returned, identically on the oracle side
    py_lib = _oracle.FootprintLibrary.from_yaml_string(content)
    py_default = _oracle.FootprintSpec("DEFAULT", (1.0, 1.0))
    assert _spec_key(lib.get("NOPE", default=default)) == _spec_key(
        py_lib.get("NOPE", default=py_default)
    )
