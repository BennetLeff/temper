"""Differential: Rust loop_loader vs the verbatim Python oracle.

The Rust port (packages/temper-design-bundle/src/loop_loader.rs) must be
bit-identical to the pinned pre-migration loader
(tests/io/_loop_loader_py_oracle.py, origin/main f2b09d846) on the real
templates and on crafted/malformed inputs. The oracle's
``load_loop_from_dict`` takes a parsed dict; the Rust side takes YAML text —
the differential serializes the same dict for the Rust side, and compares
the full template-load path (oracle ``load_loop_template`` vs the migrated
shim) on disk fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from temper_placer.io.loop_loader import (
    LoopLoadError,
    load_loop_collection,
    load_loop_from_dict,
    load_loop_template,
    save_loop_to_yaml,
)
from tests.io._loop_loader_py_oracle import LoopLoadError as OracleLoopLoadError
from tests.io._loop_loader_py_oracle import load_loop_from_dict as oracle_from_dict
from tests.io._loop_loader_py_oracle import load_loop_template as oracle_template

LOOPS_DIR = Path(__file__).resolve().parents[2] / "configs" / "templates" / "loops"

_EVENT_FIELDS = (
    "di_dt",
    "dv_dt",
    "frequency_hz",
    "peak_current_a",
    "rms_current_a",
    "ringing_freq_hz",
)


def _f(value):
    return None if value is None else float(value).hex()


def _loop_canonical(loop):
    return {
        "name": loop.name,
        "loop_type": (loop.loop_type.name, loop.loop_type.value),
        "description": loop.description,
        "pins": [
            (p.component_ref, p.pin_name, p.net_name) for p in loop.pins
        ],
        "components": list(loop.components),
        "nets": list(loop.nets),
        "max_area_mm2": _f(loop.max_area_mm2),
        "priority": (loop.priority.name, loop.priority.value),
        "events": {f: _f(getattr(loop.events, f)) for f in _EVENT_FIELDS},
        "return_layer": loop.return_layer,
        "return_net": loop.return_net,
        "source": loop.source,
    }


def _both_from_dict(data: dict, source: str = "yaml"):
    oracle = oracle_from_dict(data, source=source)
    rust = load_loop_from_dict(data, source=source)
    return oracle, rust


class TestTemplateParity:
    @pytest.mark.parametrize(
        "template_name",
        ["commutation", "buck_15v", "bootstrap", "gate_drive_high", "gate_drive_low"],
    )
    def test_template_loads_identically(self, template_name):
        path = LOOPS_DIR / f"{template_name}.yaml"
        oracle = oracle_template(path)
        rust = load_loop_template(path)
        assert _loop_canonical(rust) == _loop_canonical(oracle)

    def test_collection_loads_identically(self):
        from tests.io._loop_loader_py_oracle import load_loop_collection as oracle_collection_fn

        oracle_collection = oracle_collection_fn(LOOPS_DIR)
        rust_collection = load_loop_collection(LOOPS_DIR)
        assert len(rust_collection) == len(oracle_collection) == 5
        oracle_loops = {loop.name: _loop_canonical(loop) for loop in oracle_collection}
        for loop in rust_collection:
            assert _loop_canonical(loop) == oracle_loops[loop.name]

    def test_priority_default_and_explicit(self):
        minimal = {"name": "x", "loop_type": "commutation"}
        oracle, rust = _both_from_dict(minimal)
        assert rust.priority.name == oracle.priority.name == "MEDIUM"
        explicit = {"name": "x", "loop_type": "commutation", "priority": "CRITICAL"}
        oracle, rust = _both_from_dict(explicit)
        assert rust.priority.name == oracle.priority.name == "CRITICAL"

    def test_case_insensitive_loop_type(self):
        data = {"name": "x", "loop_type": "ComMuTaTiOn"}
        oracle, rust = _both_from_dict(data)
        assert rust.loop_type.name == oracle.loop_type.name == "COMMUTATION"

    def test_events_round_trip(self):
        data = {
            "name": "x",
            "loop_type": "commutation",
            "events": {
                "di_dt": 1e7,
                "dv_dt": 1e6,
                "frequency_hz": 150000.0,
                "peak_current_a": 12.5,
                "rms_current_a": 8.25,
                "ringing_freq_hz": 5e6,
            },
        }
        oracle, rust = _both_from_dict(data)
        assert _loop_canonical(rust) == _loop_canonical(oracle)

    def test_missing_optional_fields(self):
        data = {"name": "x", "loop_type": "commutation"}
        oracle, rust = _both_from_dict(data)
        assert _loop_canonical(rust) == _loop_canonical(oracle)

    def test_save_reload_round_trip(self, tmp_path):
        """A Rust-loaded loop re-saved by the Python writer re-loads
        identically through the migrated path."""
        path = LOOPS_DIR / "commutation.yaml"
        loop = load_loop_template(path)
        out = tmp_path / "out.yaml"
        save_loop_to_yaml(loop, out)
        reloaded = load_loop_template(out)
        expected = _loop_canonical(loop)
        expected.pop("source")
        actual = _loop_canonical(reloaded)
        actual.pop("source")
        assert actual == expected


class TestErrorParity:
    def test_unknown_loop_type_text(self):
        data = {"name": "x", "loop_type": "nope"}
        with pytest.raises(OracleLoopLoadError) as oracle_exc:
            oracle_from_dict(data)
        with pytest.raises(LoopLoadError) as rust_exc:
            load_loop_from_dict(data)
        assert str(rust_exc.value) == str(oracle_exc.value)
        assert "nope" in str(rust_exc.value)

    def test_unknown_priority_text(self):
        data = {"name": "x", "loop_type": "commutation", "priority": "nope"}
        with pytest.raises(OracleLoopLoadError) as oracle_exc:
            oracle_from_dict(data)
        with pytest.raises(LoopLoadError) as rust_exc:
            load_loop_from_dict(data)
        assert str(rust_exc.value) == str(oracle_exc.value)

    def test_missing_name_field_text(self):
        data = {"loop_type": "commutation"}
        with pytest.raises(OracleLoopLoadError) as oracle_exc:
            oracle_from_dict(data)
        with pytest.raises(LoopLoadError) as rust_exc:
            load_loop_from_dict(data)
        assert str(rust_exc.value) == str(oracle_exc.value)
        assert "'name'" in str(rust_exc.value)

    def test_missing_loop_type_field_text(self):
        data = {"name": "x"}
        with pytest.raises(OracleLoopLoadError) as oracle_exc:
            oracle_from_dict(data)
        with pytest.raises(LoopLoadError) as rust_exc:
            load_loop_from_dict(data)
        assert str(rust_exc.value) == str(oracle_exc.value)

    def test_missing_pin_component_text(self):
        """The oracle raises a raw KeyError from `str(pin_data["component"])`
        — parity means the same KeyError, not a LoopLoadError wrap."""
        data = {"name": "x", "loop_type": "commutation", "pins": [{"pin": "1"}]}
        with pytest.raises(KeyError) as oracle_exc:
            oracle_from_dict(data)
        with pytest.raises(KeyError) as rust_exc:
            load_loop_from_dict(data)
        assert str(rust_exc.value) == str(oracle_exc.value)


class TestMalformedInputs:
    def test_empty_yaml_document_raises_missing_name_error(self):
        """An empty YAML document reaches the Rust mapping as no mapping at
        all; the oracle's empty dict raises the same missing-name text."""
        with pytest.raises(LoopLoadError) as rust_empty:
            load_loop_from_dict("")
        with pytest.raises(OracleLoopLoadError) as oracle_empty:
            oracle_from_dict({})
        assert str(rust_empty.value) == str(oracle_empty.value)
