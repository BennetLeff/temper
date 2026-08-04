"""Differential test: the Rust YAML loaders (temper_design_bundle_python) vs
the pinned Python oracles.

Wave 4, Phase 3 — candidate 2 of
``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md`` (the
loaders; R5 "YAML-to-contract bit-identical parity", gate set R1a-R1h).
This is the phase's opportunistic first pull: both loaders' target
contracts (``DesignRules``, ``Loop``/``LoopCollection``) became Rust
pyclasses in Phase 2, so the loaders bind straight onto them.

The Rust functions ``load_netclass_rules``, ``load_loop_from_dict``,
``load_loop_template`` and ``load_loop_collection`` (in
``temper_design_bundle_python``, from the ``temper-design-bundle`` crate)
must reproduce the pre-migration Python implementations of
``temper_placer/io/netclass_loader.py`` and ``temper_placer/io/loop_loader.py``
bit-identically. Those implementations are pinned VERBATIM as
``_netclass_loader_py_oracle.py`` / ``_loop_loader_py_oracle.py`` (commit
``e90991a2a``) and every assertion here drives IDENTICAL inputs through
both sides.

The save path (``save_loop_to_yaml``) is NOT a Rust symbol: per KTD7 of
the first-pulls plan (U3) it stays Python-side in the delegation shim —
the loaders' migration scope is the load path, and PyYAML's dumper
formatting is not in the parity surface. This file drives the shim's
Python save on Rust ``Loop`` pyclasses, which is exactly the U3 round-trip
scenario, and asserts its output byte-for-byte against the pinned oracle.

Comparison convention (mirrors the Phase-2 differentials): objects are
canonicalized into plain comparable tuples before assertion, and every
float is compared as an exact bit pattern via ``float.hex()`` — never a
tolerance. Where a value is not a float (an ``int`` that YAML produced,
a ``str``, ``None``) the raw value AND its ``type`` are compared, so an
int-vs-float drift cannot hide behind numeric equality.

Bit-parity scope and its two honestly-named boundaries:

1. **PyYAML remains the tokenizer.** The migrated loaders call
   ``yaml.safe_load`` across the pyo3 boundary rather than re-tokenizing
   with ``serde_yaml``. This is a correctness decision, not a shortcut:
   PyYAML implements YAML **1.1** and ``serde_yaml`` implements YAML
   **1.2**, and the two disagree on real inputs a loop template can
   contain (``net: on`` → ``True`` vs ``"on"``; ``012`` → ``10`` vs
   ``12``; ``1_000`` → ``1000`` vs ``"1_000"``). Re-tokenizing in Rust
   would therefore have *changed* behavior. Keeping the tokenizer makes
   the parse step bit-identical by identity; everything downstream of it
   (field mapping, defaults, coercion, enum resolution, error text,
   collection assembly, the save-dict shape) is the migrated surface and
   is what this differential pins. The same reasoning applies to
   ``pathlib.Path.glob``; ``yaml.dump`` is kept Python-side with the whole
   save path (KTD7).
2. **Contract construction is by identity.** The loaders build the
   ``DesignRules``/``Loop``/``LoopPin``/``LoopEvent``/``LoopCollection``
   pyclasses by calling the very same constructors the oracle calls, with
   kwargs assembled in Rust. Construction parity is therefore exact
   *including* the pyo3 argument-conversion ``TypeError`` texts, which a
   Rust-side re-extraction would have reworded.

Deliberate, documented deviation (asserted below, not hidden):
``LoopLoadError`` is now defined in Rust. Its ``__module__`` is restored to
``temper_placer.io.loop_loader`` at registration so tracebacks and
``repr(cls)`` read exactly as before, but it is a *different class object*
from the oracle's own ``LoopLoadError`` — so every error-parity assertion
here compares exception ``str()`` and the ``__class__.__name__`` /
``__module__`` pair, never class identity across the two sides.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import pytest
import temper_design_bundle_python as _tdb
import yaml

import tests.io._loop_loader_py_oracle as _loop_oracle
import tests.io._netclass_loader_py_oracle as _netclass_oracle

# Rust symbols under test — must exist or this file fails to collect (RED).
RUST_LOAD_NETCLASS = _tdb.load_netclass_rules
RUST_NETCLASS_RULES_DICT = _tdb.NetClassRulesDict
RUST_LOOP_LOAD_ERROR = _tdb.LoopLoadError
RUST_LOAD_LOOP_FROM_DICT = _tdb.load_loop_from_dict
RUST_LOAD_LOOP_TEMPLATE = _tdb.load_loop_template
RUST_LOAD_LOOP_COLLECTION = _tdb.load_loop_collection

# The save path is deliberately NOT a Rust symbol: per KTD7 of the
# first-pulls plan (U3), `save_loop_to_yaml` stays Python-side in the
# delegation shim — the loaders' migration scope is the load path. The
# differential drives the shim's Python save on Rust `Loop` pyclasses, which
# is exactly the U3 round-trip scenario ("a Rust-loaded loop re-saved by the
# Python save path re-loads identically").
from temper_placer.io.loop_loader import save_loop_to_yaml as SHIM_SAVE_LOOP_TO_YAML

_PLACER_ROOT = Path(__file__).resolve().parent.parent.parent
_NETCLASS_YAML = _PLACER_ROOT / "configs" / "netclass_rules.yaml"
_LOOP_TEMPLATE_DIR = _PLACER_ROOT / "configs" / "templates" / "loops"

# The logger name the pre-migration `netclass_loader` module used
# (`logging.getLogger(__name__)` in `temper_placer/io/netclass_loader.py`).
# The pinned oracle's own `__name__` is the test-package path, so the two
# sides necessarily log through differently-NAMED loggers; the differential
# asserts the rendered record instead, plus this name explicitly.
_PRODUCTION_LOGGER_NAME = "temper_placer.io.netclass_loader"


# ---------------------------------------------------------------------------
# Canonicalization helpers (field-level extraction, bit-exact floats).
# ---------------------------------------------------------------------------


def _scalar(value):
    """Canonical, type-preserving key for a leaf value.

    Floats become their exact bit pattern (``float.hex()``); everything
    else keeps both its value and its concrete type, so an int/float or
    str/bytes drift can never compare equal.
    """
    if isinstance(value, float):
        return ("float", value.hex())
    if isinstance(value, bool):  # before int — bool is an int subclass
        return ("bool", value)
    return (type(value).__name__, value)


def _net_class_fields(nc):
    """Canonical form of a (Pydantic) NetClassRules instance."""
    dumped = nc.model_dump()
    return tuple(sorted((k, _scalar(v)) for k, v in dumped.items()))


def _class_pairs_fields(pairs):
    """Canonical form of the class_pairs mapping (tuple keys -> dicts)."""
    return tuple(
        (
            key,
            tuple(sorted((k, _scalar(v)) for k, v in value.items())),
        )
        for key, value in sorted(pairs.items())
    )


def _via_template_fields(vt):
    return (vt.name, vt.rows, vt.cols, _scalar(vt.via_diameter_mm), _scalar(vt.via_drill_mm), _scalar(vt.pitch_mm))


def _design_rules_fields(dr):
    """Canonical form of a DesignRules instance — every field it carries."""
    return (
        _scalar(dr.default_trace_width),
        _scalar(dr.default_clearance),
        _scalar(dr.default_via_diameter),
        _scalar(dr.default_via_drill),
        tuple((name, _net_class_fields(nc)) for name, nc in sorted(dr.net_classes.items())),
        tuple(sorted(dr.net_overrides.items())),
        tuple(sorted(dr.net_class_assignments.items())),
        tuple(dr.differential_pairs),
        tuple(dr.bus_cohorts),
        tuple(sorted(dr.net_topologies.items())),
        tuple((name, _via_template_fields(vt)) for name, vt in sorted(dr.via_templates.items())),
        _class_pairs_fields(dr.class_pairs),
    )


def _netclass_result_fields(result):
    return (_design_rules_fields(result.design_rules), _class_pairs_fields(result.class_pairs))


def _pin_fields(pin):
    return (pin.component_ref, pin.pin_name, pin.net_name, type(pin.net_name).__name__)


def _event_fields(ev):
    return tuple(
        None if v is None else _scalar(v)
        for v in (
            ev.di_dt,
            ev.dv_dt,
            ev.frequency_hz,
            ev.peak_current_a,
            ev.rms_current_a,
            ev.ringing_freq_hz,
        )
    )


def _loop_fields(loop):
    """Canonical form of a Loop — every constructor field plus the cached area."""
    return (
        loop.name,
        (loop.loop_type.name, loop.loop_type.value),
        loop.description,
        tuple(_pin_fields(p) for p in loop.pins),
        tuple(loop.components),
        tuple(loop.nets),
        _scalar(loop.max_area_mm2),
        (loop.priority.name, loop.priority.value),
        _event_fields(loop.events),
        loop.return_layer,
        loop.return_net,
        loop.source,
        None if loop.get_current_area() is None else _scalar(loop.get_current_area()),
    )


def _collection_fields(collection):
    return (
        collection.name,
        collection.description,
        tuple(_loop_fields(loop) for loop in collection.loops),
    )


def _normalized_module(module_name):
    """Map the pinned oracle's own module path onto the production one.

    ``LoopLoadError`` is defined *inside* the oracle file, so the oracle's
    copy reports ``tests.io._loop_loader_py_oracle`` — an artifact of
    pinning, not a behaviour difference. The production value the migrated
    exception must report (``temper_placer.io.loop_loader``) is asserted
    literally by ``test_loop_load_error_identity_and_module``; here the two
    are normalized so the rest of the comparison stays meaningful.
    """
    if module_name == "tests.io._loop_loader_py_oracle":
        return "temper_placer.io.loop_loader"
    return module_name


def _raised(fn, *args, **kwargs):
    """Run ``fn`` and canonicalize whatever it raises.

    Returns ``("ok", None, None, None)`` on success, else
    ``("raised", <exception class name>, <__module__>, <str(exc)>)``.
    Class *identity* is deliberately not compared: the two sides define
    their own ``LoopLoadError`` (see the module docstring).
    """
    try:
        fn(*args, **kwargs)
    except BaseException as exc:  # noqa: BLE001 — parity of *any* raise is the point
        return (
            "raised",
            type(exc).__name__,
            _normalized_module(type(exc).__module__),
            str(exc),
        )
    return ("ok", None, None, None)


# ---------------------------------------------------------------------------
# netclass_loader — real fixture parity (the plan's named parity oracle)
# ---------------------------------------------------------------------------


def test_netclass_real_fixture_bit_identical():
    """The repo's own netclass_rules.yaml: every field bit-identical."""
    assert _NETCLASS_YAML.exists(), f"parity fixture missing: {_NETCLASS_YAML}"
    py = _netclass_oracle.load_netclass_rules(_NETCLASS_YAML)
    rust = RUST_LOAD_NETCLASS(_NETCLASS_YAML)
    assert _netclass_result_fields(rust) == _netclass_result_fields(py)


def test_netclass_real_fixture_net_classes_compare_equal_as_models():
    """NetClassRules is a frozen Pydantic model with field ``__eq__``; the
    two sides' instances must compare equal object-for-object (a stronger,
    independent check than the canonicalized tuples above)."""
    py = _netclass_oracle.load_netclass_rules(_NETCLASS_YAML)
    rust = RUST_LOAD_NETCLASS(_NETCLASS_YAML)
    assert set(rust.design_rules.net_classes) == set(py.design_rules.net_classes)
    for name, py_nc in py.design_rules.net_classes.items():
        assert rust.design_rules.net_classes[name] == py_nc, name


def test_netclass_real_fixture_class_pairs_exact():
    """class_pairs: identical sorted tuple keys, identical clearance floats
    (bit-exact) and identical ``because`` strings."""
    py = _netclass_oracle.load_netclass_rules(_NETCLASS_YAML)
    rust = RUST_LOAD_NETCLASS(_NETCLASS_YAML)
    assert list(rust.class_pairs.keys()) == list(py.class_pairs.keys())
    for key, py_val in py.class_pairs.items():
        rust_val = rust.class_pairs[key]
        assert _scalar(rust_val["clearance"]) == _scalar(py_val["clearance"]), key
        assert rust_val["because"] == py_val["because"], key


def test_netclass_class_pairs_is_the_same_object_on_design_rules():
    """``dr.class_pairs`` and the returned ``class_pairs`` are the SAME dict
    object on both sides (the oracle assigns the one it built)."""
    py = _netclass_oracle.load_netclass_rules(_NETCLASS_YAML)
    rust = RUST_LOAD_NETCLASS(_NETCLASS_YAML)
    assert py.design_rules.class_pairs is py.class_pairs
    assert rust.design_rules.class_pairs is rust.class_pairs


def test_netclass_result_is_the_rust_wrapper_type():
    """The migrated wrapper replaces the dataclass; its attribute surface is
    unchanged (the public-API contract this migration must preserve)."""
    rust = RUST_LOAD_NETCLASS(_NETCLASS_YAML)
    assert isinstance(rust, RUST_NETCLASS_RULES_DICT)
    assert hasattr(rust, "design_rules")
    assert hasattr(rust, "class_pairs")


_NETCLASS_CASES = {
    "minimal": {"default_clearance_mm": 0.2},
    "no_classes_only_pairs": {
        "default_clearance_mm": 0.15,
        "class_pairs": {"A-B": {"clearance": 1.5, "because": "why"}},
    },
    "class_defaults_fall_through": {
        # Every optional key omitted -> the DesignRules defaults must be read
        # AFTER default_clearance was overwritten from the YAML.
        "default_clearance_mm": 0.42,
        "classes": {"Bare": {}},
    },
    "explicit_zero_and_negative": {
        "default_clearance_mm": 0.0,
        "classes": {"Z": {"trace_width": 0.0, "clearance": -1.0, "creepage_mm": 0.0}},
    },
    "int_valued_yaml_scalars": {
        # YAML ints must land exactly as the oracle lands them (Pydantic
        # coerces to float on a float-typed field; the parity is on the
        # coerced result, and the type is asserted by `_scalar`).
        "default_clearance_mm": 1,
        "classes": {"I": {"trace_width": 3, "voltage_v": 400, "dru_priority": 7}},
    },
    "pair_key_arity": {
        "default_clearance_mm": 0.2,
        "class_pairs": {
            "OneOnly": {"clearance": 1.0},
            "A-B": {"clearance": 2.0, "because": "ok"},
            "A-B-C": {"clearance": 3.0},
            "": {"clearance": 4.0},
            "-": {"clearance": 5.0, "because": "empty halves"},
        },
    },
    "pair_key_sorting": {
        "default_clearance_mm": 0.2,
        # Both orders of the same pair -> the second must overwrite the first
        # under the sorted key, on both sides.
        "class_pairs": {
            "Zeta-Alpha": {"clearance": 1.0, "because": "first"},
            "Alpha-Zeta": {"clearance": 2.0, "because": "second"},
        },
    },
    "pair_missing_fields": {
        "default_clearance_mm": 0.2,
        "class_pairs": {"A-B": {}},
    },
    "unicode_names": {
        "default_clearance_mm": 0.2,
        "classes": {"Ω_class": {"clearance": 0.3}},
        "class_pairs": {"Ω_class-Signal": {"clearance": 6.0, "because": "µ"}},
    },
    "extra_unmapped_keys_ignored": {
        "default_clearance_mm": 0.2,
        "version": "1.0",
        "metadata": {"name": "x"},
        "classes": {"C": {"clearance": 0.3, "because": "ignored", "target_impedance": 50.0}},
    },
}


@pytest.mark.parametrize("case_name", sorted(_NETCLASS_CASES))
def test_netclass_crafted_yaml_bit_identical(case_name, tmp_path):
    """Crafted YAML documents: bit-identical DesignRules on both sides."""
    path = tmp_path / f"{case_name}.yaml"
    path.write_text(yaml.safe_dump(_NETCLASS_CASES[case_name], allow_unicode=True))
    py = _netclass_oracle.load_netclass_rules(path)
    rust = RUST_LOAD_NETCLASS(path)
    assert _netclass_result_fields(rust) == _netclass_result_fields(py)


@pytest.mark.parametrize(
    "doc",
    [
        pytest.param({}, id="missing_default_clearance"),
        pytest.param({"default_clearance_mm": "wide"}, id="non_numeric_default_clearance"),
        pytest.param(
            {"default_clearance_mm": 0.2, "classes": {"A": {"trace_width": "wide"}}},
            id="non_numeric_class_field",
        ),
        pytest.param(
            {"default_clearance_mm": 0.2, "classes": ["not", "a", "mapping"]},
            id="classes_not_a_mapping",
        ),
        pytest.param(
            {"default_clearance_mm": 0.2, "class_pairs": ["nope"]},
            id="class_pairs_not_a_mapping",
        ),
        pytest.param(
            {"default_clearance_mm": 0.2, "class_pairs": {"A-B": "not a mapping"}},
            id="pair_value_not_a_mapping",
        ),
    ],
)
def test_netclass_error_parity(doc, tmp_path):
    """Malformed documents raise the SAME exception type with the SAME text."""
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(doc))
    assert _raised(RUST_LOAD_NETCLASS, path) == _raised(_netclass_oracle.load_netclass_rules, path)


def test_netclass_missing_file_error_parity(tmp_path):
    missing = tmp_path / "nope.yaml"
    assert _raised(RUST_LOAD_NETCLASS, missing) == _raised(
        _netclass_oracle.load_netclass_rules, missing
    )


def test_netclass_accepts_str_path_like_the_oracle(tmp_path):
    path = tmp_path / "ok.yaml"
    path.write_text(yaml.safe_dump({"default_clearance_mm": 0.2}))
    py = _netclass_oracle.load_netclass_rules(str(path))
    rust = RUST_LOAD_NETCLASS(str(path))
    assert _netclass_result_fields(rust) == _netclass_result_fields(py)


def test_netclass_invalid_pair_key_warning_parity(tmp_path, caplog):
    """The skipped-key warning is emitted with the identical rendered message
    at the identical level — and the migrated loader logs through the
    production logger name the pre-migration module used."""
    doc = {
        "default_clearance_mm": 0.2,
        "class_pairs": {"OnlyOne": {"clearance": 1.0}, "A-B-C": {"clearance": 2.0}},
    }
    path = tmp_path / "warn.yaml"
    path.write_text(yaml.safe_dump(doc))

    with caplog.at_level(logging.WARNING):
        caplog.clear()
        _netclass_oracle.load_netclass_rules(path)
        py_records = [(r.levelname, r.getMessage()) for r in caplog.records]
        caplog.clear()
        RUST_LOAD_NETCLASS(path)
        rust_records = [(r.levelname, r.getMessage()) for r in caplog.records]
        rust_logger_names = {r.name for r in caplog.records}

    # `safe_dump` sorts mapping keys, so `A-B-C` is emitted (and therefore
    # parsed and warned about) before `OnlyOne`.
    assert py_records == [
        ("WARNING", "Invalid class_pairs key 'A-B-C' — skipping"),
        ("WARNING", "Invalid class_pairs key 'OnlyOne' — skipping"),
    ]
    assert rust_records == py_records
    assert rust_logger_names == {_PRODUCTION_LOGGER_NAME}


# ---------------------------------------------------------------------------
# loop_loader — load_loop_from_dict parity
# ---------------------------------------------------------------------------

_LOOP_DICT_CASES = {
    "minimal": {"name": "test_loop", "loop_type": "custom"},
    "full": {
        "name": "commutation",
        "loop_type": "commutation",
        "description": "Main switching loop",
        "components": ["Q1", "Q2", "C_BUS"],
        "pins": [
            {"component": "Q1", "pin": "COLLECTOR", "net": "DC_BUS+"},
            {"component": "Q1", "pin": "EMITTER", "net": "SW_NODE"},
        ],
        "nets": ["DC_BUS+", "SW_NODE"],
        "max_area_mm2": 200,
        "priority": "critical",
        "events": {"di_dt": 1e9, "frequency_hz": 25000, "peak_current_a": 50},
        "return_layer": "L2_GND",
        "return_net": "PGND",
    },
    "uppercase_enums": {"name": "t", "loop_type": "COMMUTATION", "priority": "CRITICAL"},
    "mixedcase_enums": {"name": "t", "loop_type": "GaTe_DrIvE_hIgH", "priority": "MeDiUm"},
    "empty_containers": {
        "name": "t",
        "loop_type": "custom",
        "components": [],
        "nets": [],
        "pins": [],
        "events": {},
    },
    "explicit_none_optionals": {
        "name": "t",
        "loop_type": "custom",
        "priority": None,
        "pins": None,
        "events": None,
        "return_layer": None,
        "return_net": None,
    },
    "pin_without_net": {
        "name": "t",
        "loop_type": "custom",
        "pins": [{"component": "Q1", "pin": "G"}],
    },
    "pin_non_string_component": {
        # str() coercion is part of the migrated surface.
        "name": "t",
        "loop_type": "custom",
        "pins": [{"component": 7, "pin": 3}],
    },
    "int_max_area": {"name": "t", "loop_type": "custom", "max_area_mm2": 250},
    "string_max_area": {
        # float() coercion accepts numeric strings — replicated exactly.
        "name": "t",
        "loop_type": "custom",
        "max_area_mm2": "1e3",
    },
    "subnormal_max_area": {"name": "t", "loop_type": "custom", "max_area_mm2": 5e-324},
    "huge_max_area": {"name": "t", "loop_type": "custom", "max_area_mm2": 1.7976931348623157e308},
    "negative_zero_max_area": {"name": "t", "loop_type": "custom", "max_area_mm2": -0.0},
    "events_all_fields": {
        "name": "t",
        "loop_type": "custom",
        "events": {
            "di_dt": 1e9,
            "dv_dt": 2.5e10,
            "frequency_hz": 25000,
            "peak_current_a": 50.5,
            "rms_current_a": 0.1,
            "ringing_freq_hz": 1.2345678901234567e7,
        },
    },
    "events_partial": {"name": "t", "loop_type": "custom", "events": {"dv_dt": 3.0}},
    "unicode_name": {"name": "løøp_Ω", "loop_type": "custom", "description": "µ-scale"},
    "every_loop_type": None,  # expanded below
}
del _LOOP_DICT_CASES["every_loop_type"]

for _lt in ("buck_switch", "boost_switch", "flyback_primary", "flyback_secondary",
            "gate_drive_high", "gate_drive_low", "bootstrap", "auxiliary_supply",
            "sensing", "feedback", "decoupling", "custom", "commutation"):
    _LOOP_DICT_CASES[f"loop_type_{_lt}"] = {"name": "t", "loop_type": _lt}
for _lp in ("critical", "high", "medium", "low"):
    _LOOP_DICT_CASES[f"priority_{_lp}"] = {"name": "t", "loop_type": "custom", "priority": _lp}


@pytest.mark.parametrize("case_name", sorted(_LOOP_DICT_CASES))
def test_load_loop_from_dict_bit_identical(case_name):
    """Every crafted loop dict yields a field-identical Loop on both sides."""
    data = _LOOP_DICT_CASES[case_name]
    py = _loop_oracle.load_loop_from_dict(dict(data))
    rust = RUST_LOAD_LOOP_FROM_DICT(dict(data))
    assert _loop_fields(rust) == _loop_fields(py)


@pytest.mark.parametrize("case_name", sorted(_LOOP_DICT_CASES))
def test_load_loop_from_dict_source_parity(case_name):
    """The ``source`` kwarg is threaded identically (default and explicit)."""
    data = _LOOP_DICT_CASES[case_name]
    assert RUST_LOAD_LOOP_FROM_DICT(dict(data)).source == "yaml"
    py = _loop_oracle.load_loop_from_dict(dict(data), source="template:x.yaml")
    rust = RUST_LOAD_LOOP_FROM_DICT(dict(data), source="template:x.yaml")
    assert _loop_fields(rust) == _loop_fields(py)
    rust_pos = RUST_LOAD_LOOP_FROM_DICT(dict(data), "template:x.yaml")
    assert _loop_fields(rust_pos) == _loop_fields(py)


@pytest.mark.parametrize(
    "data",
    [
        pytest.param({"loop_type": "custom"}, id="missing_name"),
        pytest.param({"name": "t"}, id="missing_loop_type"),
        pytest.param({}, id="missing_both"),
        pytest.param({"name": "t", "loop_type": "invalid_type"}, id="unknown_loop_type"),
        pytest.param({"name": "t", "loop_type": ""}, id="empty_loop_type"),
        pytest.param({"name": "t", "loop_type": "Custom "}, id="loop_type_trailing_space"),
        pytest.param(
            {"name": "t", "loop_type": "custom", "priority": "super_critical"},
            id="unknown_priority",
        ),
        pytest.param({"name": "t", "loop_type": "custom", "priority": ""}, id="empty_priority"),
        pytest.param({"name": "t", "loop_type": 5}, id="non_string_loop_type"),
        pytest.param({"name": "t", "loop_type": "custom", "priority": 5}, id="non_string_priority"),
        pytest.param(
            {"name": "t", "loop_type": "custom", "pins": [{"pin": "G"}]},
            id="pin_missing_component",
        ),
        pytest.param(
            {"name": "t", "loop_type": "custom", "pins": [{"component": "Q1"}]},
            id="pin_missing_pin",
        ),
        pytest.param(
            {"name": "t", "loop_type": "custom", "pins": [{"component": "Q1", "pin": "G", "net": 5}]},
            id="pin_non_string_net",
        ),
        pytest.param(
            {"name": "t", "loop_type": "custom", "max_area_mm2": "wide"},
            id="non_numeric_max_area",
        ),
        pytest.param(
            {"name": "t", "loop_type": "custom", "max_area_mm2": None}, id="none_max_area"
        ),
        pytest.param({"name": 5, "loop_type": "custom"}, id="non_string_name"),
        pytest.param(
            {"name": "t", "loop_type": "custom", "components": [1, 2]}, id="non_string_components"
        ),
        pytest.param({"name": "t", "loop_type": "custom", "nets": [1]}, id="non_string_nets"),
        pytest.param(
            {"name": "t", "loop_type": "custom", "components": "QQ"}, id="components_not_a_list"
        ),
        pytest.param({"name": "t", "loop_type": "custom", "pins": 5}, id="pins_not_a_list"),
        pytest.param({"name": "t", "loop_type": "custom", "events": 5}, id="events_not_a_mapping"),
        pytest.param(
            {"name": "t", "loop_type": "custom", "events": {"di_dt": "fast"}},
            id="non_numeric_event",
        ),
        pytest.param(
            {"name": "t", "loop_type": "custom", "return_layer": 5}, id="non_string_return_layer"
        ),
    ],
)
def test_load_loop_from_dict_error_parity(data):
    """Every malformed input raises the SAME exception type with the SAME text."""
    assert _raised(RUST_LOAD_LOOP_FROM_DICT, dict(data)) == _raised(
        _loop_oracle.load_loop_from_dict, dict(data)
    )


def test_loop_load_error_message_texts_are_pinned():
    """The exact user-facing error strings, pinned literally (a message drift
    would otherwise pass the parity assertions only if BOTH sides drifted)."""
    with pytest.raises(RUST_LOOP_LOAD_ERROR) as exc:
        RUST_LOAD_LOOP_FROM_DICT({"loop_type": "custom"})
    assert str(exc.value) == "Missing required field: 'name'"

    with pytest.raises(RUST_LOOP_LOAD_ERROR) as exc:
        RUST_LOAD_LOOP_FROM_DICT({"name": "t", "loop_type": "nope"})
    assert str(exc.value) == (
        "Unknown loop type: nope. Valid types: ['commutation', 'buck_switch', "
        "'boost_switch', 'flyback_primary', 'flyback_secondary', 'gate_drive_high', "
        "'gate_drive_low', 'bootstrap', 'auxiliary_supply', 'sensing', 'feedback', "
        "'decoupling', 'custom']"
    )

    with pytest.raises(RUST_LOOP_LOAD_ERROR) as exc:
        RUST_LOAD_LOOP_FROM_DICT({"name": "t", "loop_type": "custom", "priority": "nope"})
    assert str(exc.value) == (
        "Unknown priority: nope. Valid priorities: ['critical', 'high', 'medium', 'low']"
    )


def test_loop_load_error_identity_and_module():
    """``LoopLoadError`` subclasses ``Exception`` and reports the
    pre-migration ``__module__`` so tracebacks read unchanged."""
    assert issubclass(RUST_LOOP_LOAD_ERROR, Exception)
    assert RUST_LOOP_LOAD_ERROR.__name__ == "LoopLoadError"
    assert RUST_LOOP_LOAD_ERROR.__module__ == "temper_placer.io.loop_loader"


def test_loop_load_error_preserves_cause_chain():
    """``raise ... from e`` is replicated: the KeyError stays as ``__cause__``."""
    py_cause = None
    try:
        _loop_oracle.load_loop_from_dict({"loop_type": "custom"})
    except _loop_oracle.LoopLoadError as exc:
        py_cause = exc.__cause__
    rust_cause = None
    try:
        RUST_LOAD_LOOP_FROM_DICT({"loop_type": "custom"})
    except RUST_LOOP_LOAD_ERROR as exc:
        rust_cause = exc.__cause__
    assert type(py_cause) is KeyError
    assert type(rust_cause) is type(py_cause)
    assert str(rust_cause) == str(py_cause)


# ---------------------------------------------------------------------------
# loop_loader — load_loop_template parity (real fixtures)
# ---------------------------------------------------------------------------


def _template_paths():
    if not _LOOP_TEMPLATE_DIR.exists():
        return []
    return sorted(p for p in _LOOP_TEMPLATE_DIR.glob("*.yaml"))


@pytest.mark.parametrize("template", _template_paths(), ids=lambda p: p.name)
def test_load_loop_template_real_fixture_bit_identical(template):
    """Every shipped loop template loads bit-identically on both sides."""
    py = _loop_oracle.load_loop_template(template)
    rust = RUST_LOAD_LOOP_TEMPLATE(template)
    assert _loop_fields(rust) == _loop_fields(py)
    assert rust.source == f"template:{template.name}"


@pytest.mark.parametrize("template", _template_paths(), ids=lambda p: p.name)
def test_load_loop_template_accepts_str_path(template):
    py = _loop_oracle.load_loop_template(str(template))
    rust = RUST_LOAD_LOOP_TEMPLATE(str(template))
    assert _loop_fields(rust) == _loop_fields(py)


def test_load_loop_template_missing_file_parity(tmp_path):
    missing = tmp_path / "nope.yaml"
    assert _raised(RUST_LOAD_LOOP_TEMPLATE, missing) == _raised(
        _loop_oracle.load_loop_template, missing
    )


def test_load_loop_template_invalid_yaml_parity(tmp_path):
    """The PyYAML error text (which embeds the stream name and position) is
    reproduced verbatim — this is what pins ``yaml.safe_load`` being handed
    the open FILE OBJECT, not the file's text."""
    path = tmp_path / "bad.yaml"
    path.write_text("invalid: yaml: content: [}")
    assert _raised(RUST_LOAD_LOOP_TEMPLATE, path) == _raised(
        _loop_oracle.load_loop_template, path
    )


def test_load_loop_template_empty_file_parity(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text("")
    assert _raised(RUST_LOAD_LOOP_TEMPLATE, path) == _raised(
        _loop_oracle.load_loop_template, path
    )


def test_load_loop_template_null_document_parity(tmp_path):
    """A document that parses to ``None`` (``~``) takes the Empty-YAML path."""
    path = tmp_path / "null.yaml"
    path.write_text("~\n")
    assert _raised(RUST_LOAD_LOOP_TEMPLATE, path) == _raised(
        _loop_oracle.load_loop_template, path
    )


def test_load_loop_template_scalar_document_parity(tmp_path):
    """A non-mapping document reaches ``data["name"]`` and fails identically."""
    path = tmp_path / "scalar.yaml"
    path.write_text("just a string\n")
    assert _raised(RUST_LOAD_LOOP_TEMPLATE, path) == _raised(
        _loop_oracle.load_loop_template, path
    )


def test_load_loop_template_yaml_11_booleans_parity(tmp_path):
    """PyYAML's YAML-1.1 scalar resolution (``on``/``off``/``012``/``1_000``)
    is preserved by construction — the divergence class that made
    re-tokenizing in Rust the WRONG move (see module docstring)."""
    path = tmp_path / "yaml11.yaml"
    path.write_text(
        "name: t\nloop_type: custom\npins:\n  - component: on\n    pin: off\n"
        "max_area_mm2: 1_000\n"
    )
    py = _loop_oracle.load_loop_template(path)
    rust = RUST_LOAD_LOOP_TEMPLATE(path)
    assert _loop_fields(rust) == _loop_fields(py)
    # And the 1.1 resolution really is in force (guards against this test
    # passing vacuously if both sides ever moved to YAML 1.2).
    assert rust.pins[0].component_ref == "True"
    assert _scalar(rust.max_area_mm2) == _scalar(1000.0)


# ---------------------------------------------------------------------------
# loop_loader — load_loop_collection parity
# ---------------------------------------------------------------------------


def test_load_loop_collection_real_directory_bit_identical():
    """The shipped template directory: identical collection, identical order."""
    assert _LOOP_TEMPLATE_DIR.exists(), f"parity fixture missing: {_LOOP_TEMPLATE_DIR}"
    py = _loop_oracle.load_loop_collection(_LOOP_TEMPLATE_DIR)
    rust = RUST_LOAD_LOOP_COLLECTION(_LOOP_TEMPLATE_DIR)
    assert _collection_fields(rust) == _collection_fields(py)
    assert len(rust.loops) >= 5


def test_load_loop_collection_name_and_description_parity():
    py = _loop_oracle.load_loop_collection(
        _LOOP_TEMPLATE_DIR, name="my_loops", description="mine"
    )
    rust = RUST_LOAD_LOOP_COLLECTION(_LOOP_TEMPLATE_DIR, name="my_loops", description="mine")
    assert _collection_fields(rust) == _collection_fields(py)
    default_py = _loop_oracle.load_loop_collection(_LOOP_TEMPLATE_DIR)
    default_rust = RUST_LOAD_LOOP_COLLECTION(_LOOP_TEMPLATE_DIR)
    assert default_rust.name == default_py.name == "loops"


def test_load_loop_collection_pattern_parity():
    py = _loop_oracle.load_loop_collection(_LOOP_TEMPLATE_DIR, pattern="gate_*.yaml")
    rust = RUST_LOAD_LOOP_COLLECTION(_LOOP_TEMPLATE_DIR, pattern="gate_*.yaml")
    assert _collection_fields(rust) == _collection_fields(py)
    assert len(rust.loops) == 2


def test_load_loop_collection_pattern_matching_nothing_parity(tmp_path):
    py = _loop_oracle.load_loop_collection(tmp_path, pattern="*.nomatch")
    rust = RUST_LOAD_LOOP_COLLECTION(tmp_path, pattern="*.nomatch")
    assert _collection_fields(rust) == _collection_fields(py)


def test_load_loop_collection_pattern_type_message_divergence_pinned():
    """P2-3 pinning: the pyo3 String boundary and pathlib.glob raise
    DIFFERENT messages for a non-``str`` pattern.

    ``source``/``name``/``description`` funnel into pyclass constructors on
    both sides, so a non-``str`` argument raises pyo3's own message
    (``'int' object is not an instance of 'str'``) identically. ``pattern``
    is the one exception: the oracle hands it straight to
    ``directory.glob(...)`` — pathlib, deliberately kept Python-side — whose
    message is ``expected str, bytes or os.PathLike object, not int``, while
    the Rust side rejects it at the pyo3 ``String`` boundary before the body
    runs. The divergence is intentional (pathlib.glob semantics are not
    re-implemented); this test pins both exact messages so the deviation is
    asserted, not merely described.
    """
    dir_path = _LOOP_TEMPLATE_DIR
    py = _raised(_loop_oracle.load_loop_collection, dir_path, pattern=5)
    rust = _raised(RUST_LOAD_LOOP_COLLECTION, dir_path, pattern=5)
    assert py == (
        "raised",
        "TypeError",
        "builtins",
        "expected str, bytes or os.PathLike object, not int",
    )
    assert rust == (
        "raised",
        "TypeError",
        "builtins",
        "'int' object is not an instance of 'str'",
    )
    assert py[3] != rust[3]


def test_load_loop_collection_readme_skip_parity(tmp_path):
    """README.md / README.yaml / README.txt are skipped case-insensitively,
    and nothing else is."""
    (tmp_path / "README.yaml").write_text("not: a loop\n")
    (tmp_path / "readme.YAML").write_text("also: not a loop\n")
    (tmp_path / "a.yaml").write_text("name: a\nloop_type: custom\n")
    (tmp_path / "readmex.yaml").write_text("name: rx\nloop_type: custom\n")
    py = _loop_oracle.load_loop_collection(tmp_path)
    rust = RUST_LOAD_LOOP_COLLECTION(tmp_path)
    assert _collection_fields(rust) == _collection_fields(py)
    assert [ln.name for ln in rust.loops] == ["a", "rx"]


def test_load_loop_collection_ordering_parity(tmp_path):
    """Files are loaded in ``sorted()`` order — asserted with names whose
    sort order differs from filesystem enumeration order."""
    for stem in ("zz", "aa", "Mm", "10", "2"):
        # The loop's own name is quoted so `10`/`2` stay strings; the FILE
        # names are what the ordering assertion probes.
        (tmp_path / f"{stem}.yaml").write_text(f'name: "{stem}"\nloop_type: custom\n')
    py = _loop_oracle.load_loop_collection(tmp_path)
    rust = RUST_LOAD_LOOP_COLLECTION(tmp_path)
    assert _collection_fields(rust) == _collection_fields(py)
    assert [ln.name for ln in rust.loops] == ["10", "2", "Mm", "aa", "zz"]


def test_load_loop_collection_missing_directory_parity(tmp_path):
    missing = tmp_path / "nope"
    assert _raised(RUST_LOAD_LOOP_COLLECTION, missing) == _raised(
        _loop_oracle.load_loop_collection, missing
    )


def test_load_loop_collection_not_a_directory_parity(tmp_path):
    path = tmp_path / "file.yaml"
    path.write_text("")
    assert _raised(RUST_LOAD_LOOP_COLLECTION, path) == _raised(
        _loop_oracle.load_loop_collection, path
    )


def test_load_loop_collection_bad_member_wraps_identically(tmp_path):
    """A template that fails to load is wrapped as
    ``Failed to load <path>: <inner>`` — identical text on both sides."""
    (tmp_path / "ok.yaml").write_text("name: ok\nloop_type: custom\n")
    (tmp_path / "zbad.yaml").write_text("name: bad\nloop_type: nonsense\n")
    assert _raised(RUST_LOAD_LOOP_COLLECTION, tmp_path) == _raised(
        _loop_oracle.load_loop_collection, tmp_path
    )


def test_load_loop_collection_duplicate_names_wrap_identically(tmp_path):
    """``LoopCollection.add_loop``'s duplicate-name ValueError is caught by
    the ``except Exception`` wrap on both sides."""
    (tmp_path / "a.yaml").write_text("name: dup\nloop_type: custom\n")
    (tmp_path / "b.yaml").write_text("name: dup\nloop_type: custom\n")
    assert _raised(RUST_LOAD_LOOP_COLLECTION, tmp_path) == _raised(
        _loop_oracle.load_loop_collection, tmp_path
    )


def test_load_loop_collection_accepts_str_path():
    py = _loop_oracle.load_loop_collection(str(_LOOP_TEMPLATE_DIR))
    rust = RUST_LOAD_LOOP_COLLECTION(str(_LOOP_TEMPLATE_DIR))
    assert _collection_fields(rust) == _collection_fields(py)


# ---------------------------------------------------------------------------
# loop_loader — save_loop_to_yaml parity (byte-for-byte)
# ---------------------------------------------------------------------------


def _save_cases():
    """(id, Loop) pairs covering every conditional branch of the emitter."""
    from temper_placer.core.loop import Loop, LoopEvent, LoopPin, LoopPriority, LoopType

    return [
        (
            "full",
            Loop(
                name="test_loop",
                loop_type=LoopType.GATE_DRIVE_HIGH,
                description="Test loop for saving",
                components=["U1", "Q1"],
                pins=[LoopPin("U1", "OUT", "NET1"), LoopPin("Q1", "GATE", "NET1")],
                nets=["NET1"],
                max_area_mm2=50.0,
                priority=LoopPriority.HIGH,
                events=LoopEvent(di_dt=1e9, frequency_hz=50000),
                return_layer="L2_GND",
                return_net="GND",
            ),
        ),
        ("minimal", Loop(name="minimal", loop_type=LoopType.CUSTOM, description="")),
        (
            "pins_without_nets",
            Loop(
                name="p",
                loop_type=LoopType.CUSTOM,
                description="",
                pins=[LoopPin("U1", "OUT"), LoopPin("Q1", "GATE", "")],
            ),
        ),
        (
            "all_events",
            Loop(
                name="e",
                loop_type=LoopType.BUCK_SWITCH,
                description="",
                events=LoopEvent(1.0, 2.0, 3.0, 4.0, 5.0, 6.0),
                max_area_mm2=1e-7,
            ),
        ),
        (
            "zero_valued_events",
            # 0.0 is falsy but NOT None — the emitter's `is not None` guard
            # must keep it; a `if v:` mutant would drop it.
            Loop(
                name="z",
                loop_type=LoopType.CUSTOM,
                description="",
                events=LoopEvent(di_dt=0.0, dv_dt=0.0),
            ),
        ),
        (
            "unicode",
            Loop(
                name="løøp_Ω",
                loop_type=LoopType.SENSING,
                description="µ-scale — em dash",
                components=["Ω1"],
                nets=["Ω_NET"],
            ),
        ),
        (
            "float_repr_edges",
            Loop(
                name="f",
                loop_type=LoopType.CUSTOM,
                description="",
                max_area_mm2=1e300,
                events=LoopEvent(di_dt=1e-5, dv_dt=0.1 + 0.2),
            ),
        ),
    ]


@pytest.mark.parametrize("case", _save_cases(), ids=lambda c: c[0])
def test_save_loop_to_yaml_byte_identical(case, tmp_path):
    """The emitted YAML file is byte-for-byte identical on both sides."""
    _, loop = case
    py_path = tmp_path / "py" / "out.yaml"
    rust_path = tmp_path / "rust" / "out.yaml"
    _loop_oracle.save_loop_to_yaml(loop, py_path)
    SHIM_SAVE_LOOP_TO_YAML(loop, rust_path)
    assert rust_path.read_bytes() == py_path.read_bytes()


@pytest.mark.parametrize("case", _save_cases(), ids=lambda c: c[0])
def test_save_loop_to_yaml_round_trip_parity(case, tmp_path):
    """save → load round trip yields field-identical Loops on both sides."""
    _, loop = case
    # Same FILE NAME in different directories: `source` is derived from the
    # basename, so differing names would make the comparison fail spuriously.
    py_path = tmp_path / "py" / "out.yaml"
    rust_path = tmp_path / "rust" / "out.yaml"
    _loop_oracle.save_loop_to_yaml(loop, py_path)
    SHIM_SAVE_LOOP_TO_YAML(loop, rust_path)
    py_reloaded = _loop_oracle.load_loop_template(py_path)
    rust_reloaded = RUST_LOAD_LOOP_TEMPLATE(rust_path)
    assert _loop_fields(rust_reloaded) == _loop_fields(py_reloaded)


@pytest.mark.parametrize(
    "char", ["\n", "\r", "\x85", "\u2028", "\u2029"], ids=["lf", "cr", "nel", "ls", "ps"]
)
def test_yaml_line_break_characters_are_equally_lossy_on_both_sides(char, tmp_path):
    """YAML's reader normalizes U+000A/U+000D/U+0085/U+2028/U+2029, so a
    scalar containing one does NOT survive ``dump`` → ``safe_load`` verbatim.

    That is a property of PyYAML — the tokenizer/emitter this migration
    deliberately keeps — and it held identically before the migration. Pinned
    here so the bound stated on the PBT round-trip relations is evidenced
    rather than asserted: both sides emit the same bytes and both sides
    recover the same (possibly altered) value.
    """
    from temper_placer.core.loop import Loop, LoopType

    loop = Loop(name="lb", loop_type=LoopType.CUSTOM, description=f"a{char}b")
    py_path = tmp_path / "py" / "out.yaml"
    rust_path = tmp_path / "rust" / "out.yaml"
    _loop_oracle.save_loop_to_yaml(loop, py_path)
    SHIM_SAVE_LOOP_TO_YAML(loop, rust_path)
    assert rust_path.read_bytes() == py_path.read_bytes()
    assert _loop_fields(RUST_LOAD_LOOP_TEMPLATE(rust_path)) == _loop_fields(
        _loop_oracle.load_loop_template(py_path)
    )


def test_save_loop_to_yaml_creates_parent_directories(tmp_path):
    target = tmp_path / "deep" / "nested" / "out.yaml"
    SHIM_SAVE_LOOP_TO_YAML(_save_cases()[0][1], target)
    assert target.exists()


def test_save_loop_to_yaml_accepts_str_path(tmp_path):
    _, loop = _save_cases()[0]
    py_path = tmp_path / "py" / "out.yaml"
    rust_path = tmp_path / "rust" / "out.yaml"
    _loop_oracle.save_loop_to_yaml(loop, str(py_path))
    SHIM_SAVE_LOOP_TO_YAML(loop, str(rust_path))
    assert rust_path.read_bytes() == py_path.read_bytes()


def test_save_then_load_real_templates_round_trip(tmp_path):
    """Every shipped template survives Rust save → Rust load with the same
    fields the oracle's own round trip produces."""
    for template in _template_paths():
        loop = RUST_LOAD_LOOP_TEMPLATE(template)
        out = tmp_path / template.name
        SHIM_SAVE_LOOP_TO_YAML(loop, out)
        py_out = tmp_path / "py" / template.name
        _loop_oracle.save_loop_to_yaml(_loop_oracle.load_loop_template(template), py_out)
        assert out.read_bytes() == py_out.read_bytes(), template.name


# ---------------------------------------------------------------------------
# Public-API preservation: the delegation shims re-export the Rust symbols.
# ---------------------------------------------------------------------------


def test_netclass_loader_module_delegates_to_rust():
    from temper_placer.io import netclass_loader

    assert netclass_loader.load_netclass_rules is RUST_LOAD_NETCLASS
    assert netclass_loader.NetClassRulesDict is RUST_NETCLASS_RULES_DICT
    # The pre-migration module surface that consumers may touch.
    assert netclass_loader.logger.name == _PRODUCTION_LOGGER_NAME


def test_loop_loader_module_delegates_to_rust():
    from temper_placer.io import loop_loader

    assert loop_loader.LoopLoadError is RUST_LOOP_LOAD_ERROR
    assert loop_loader.load_loop_from_dict is RUST_LOAD_LOOP_FROM_DICT
    assert loop_loader.load_loop_template is RUST_LOAD_LOOP_TEMPLATE
    assert loop_loader.load_loop_collection is RUST_LOAD_LOOP_COLLECTION
    # The save path is Python-side by design (KTD7): it is a real Python
    # function in the shim, NOT a re-export of a Rust symbol.
    import inspect

    assert inspect.isfunction(loop_loader.save_loop_to_yaml)
    assert not hasattr(_tdb, "save_loop_to_yaml")


def test_no_yaml_or_tempfile_import_drift():
    """Guards the imports this file relies on actually being exercised (the
    module would otherwise pass ruff's unused-import check by accident)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "x.yaml"
        path.write_text(yaml.safe_dump({"name": "t", "loop_type": "custom"}))
        assert _loop_fields(RUST_LOAD_LOOP_TEMPLATE(path)) == _loop_fields(
            _loop_oracle.load_loop_template(path)
        )
