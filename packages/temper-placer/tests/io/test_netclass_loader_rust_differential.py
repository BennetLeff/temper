"""Differential: Rust netclass_loader vs the verbatim Python oracle.

The Rust port (packages/temper-design-bundle/src/netclass_loader.rs) must be
bit-identical to the pinned pre-migration loader
(tests/io/_netclass_loader_py_oracle.py, origin/main f2b09d846) on the real
config, on crafted fixtures, and on malformed inputs. The oracle loads from a
file path; the Rust side takes YAML text — the differential writes the same
YAML to disk for the oracle and passes the text to Rust.

B9/B10 note: the produced ``DesignRules`` pyclass is the SAME object on both
sides (it was migrated in Phase 2), so repr parity here pins the loader's
construction, not the pyclass's repr.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from temper_design_bundle_python import load_netclass_rules as rust_load

from tests.io._netclass_loader_py_oracle import load_netclass_rules as oracle_load

RULES_PATH = Path(__file__).resolve().parents[2] / "configs" / "netclass_rules.yaml"

# Fields NetClassRules carries that the loader's kwargs touch (or default).
_NCR_FIELDS = (
    "name",
    "trace_width",
    "clearance",
    "via_diameter",
    "via_drill",
    "creepage_mm",
    "voltage_v",
    "safety_category",
    "dru_priority",
    "required_layer",
    "layer",
)


def _f(value):
    if value is None or isinstance(value, str):
        return value
    return float(value).hex()


def _ncr_canonical(ncr):
    return {f: _f(getattr(ncr, f)) for f in _NCR_FIELDS}


def _pair_canonical(value):
    return {"clearance": _f(value["clearance"]), "because": value.get("because")}


def _dr_canonical(design_rules):
    return {
        "default_clearance": _f(design_rules.default_clearance),
        "net_classes": {
            name: _ncr_canonical(ncr)
            for name, ncr in sorted(design_rules.net_classes.items())
        },
        "net_class_assignments": dict(sorted(design_rules.net_class_assignments.items())),
        "class_pairs": {
            key: _pair_canonical(value)
            for key, value in sorted(
                design_rules.class_pairs.items(), key=lambda kv: kv[0]
            )
        },
    }


def _both(text: str, tmp_path: Path):
    path = tmp_path / "rules.yaml"
    path.write_text(text)
    oracle = oracle_load(path)
    rust = rust_load(text)
    return oracle, rust


class TestRealConfigParity:
    def test_full_state_parity(self, tmp_path):
        oracle, rust = _both(RULES_PATH.read_text(), tmp_path)
        assert _dr_canonical(rust[0]) == _dr_canonical(oracle.design_rules)
        assert dict(rust[1]) == dict(oracle.class_pairs)

    def test_class_count_and_names(self, tmp_path):
        oracle, rust = _both(RULES_PATH.read_text(), tmp_path)
        assert set(rust[0].net_classes) == set(oracle.design_rules.net_classes)

    def test_every_class_field_maps_identically(self, tmp_path):
        """Clearance, widths, drill, creepage, voltage, layer, safety
        category, and priorities all come through the Rust mapping."""
        oracle, rust = _both(RULES_PATH.read_text(), tmp_path)
        for name in oracle.design_rules.net_classes:
            assert _ncr_canonical(rust[0].net_classes[name]) == _ncr_canonical(
                oracle.design_rules.net_classes[name]
            ), name

    def test_default_clearance_from_yaml(self, tmp_path):
        oracle, rust = _both(RULES_PATH.read_text(), tmp_path)
        assert rust[0].default_clearance == oracle.design_rules.default_clearance == 0.2

    def test_assignments_inherited_identically(self, tmp_path):
        oracle, rust = _both(RULES_PATH.read_text(), tmp_path)
        assert dict(rust[0].net_class_assignments) == dict(
            oracle.design_rules.net_class_assignments
        )
        assert "AC_L" in rust[0].net_class_assignments

    def test_class_pairs_direction_agnostic(self, tmp_path):
        oracle, rust = _both(RULES_PATH.read_text(), tmp_path)
        assert ("ACMains", "Signal") in rust[1]
        assert rust[1][("ACMains", "Signal")]["clearance"] == 6.0

    def test_repr_byte_identical(self, tmp_path):
        """B9/B10: full repr parity on the constructed DesignRules."""
        oracle, rust = _both(RULES_PATH.read_text(), tmp_path)
        assert repr(rust[0]) == repr(oracle.design_rules)


class TestCraftedFixtures:
    def test_override_assignment_wins(self, tmp_path):
        """A class_pairs-less fixture where a net name maps to a class that
        also appears in the assignments — inheritance parity."""
        text = """
default_clearance_mm: 0.3
classes:
  Signal:
    clearance: 0.15
    layer: F.Cu
class_pairs:
  "Signal-FinePitch":
    clearance: 0.25
    because: test
"""
        oracle, rust = _both(text, tmp_path)
        assert _dr_canonical(rust[0]) == _dr_canonical(oracle.design_rules)
        assert dict(rust[1]) == dict(oracle.class_pairs)

    def test_undeclared_safety_category_resolves_via_keyword_fallback(self, tmp_path):
        """L11: an undeclared net class exercises the keyword fallback in
        get_rules_for_net — the loader's output must feed it identically."""
        text = """
default_clearance_mm: 0.2
classes:
  MysteryHV:
    clearance: 1.5
"""
        oracle, rust = _both(text, tmp_path)
        for rules in (rust[0].get_rules_for_net("ac_l", net_class="MysteryHV"),
                      oracle.design_rules.get_rules_for_net("ac_l", net_class="MysteryHV")):
            assert rules.clearance == 1.5

    def test_no_classes_no_pairs(self, tmp_path):
        text = "default_clearance_mm: 0.2\n"
        oracle, rust = _both(text, tmp_path)
        assert _dr_canonical(rust[0]) == _dr_canonical(oracle.design_rules)
        assert dict(rust[1]) == {}

    def test_unknown_keys_inside_class_entry_behave_identically(self, tmp_path):
        """Extra keys land in Pydantic on BOTH sides (KTD7 call-back), so
        they are ignored identically — not silently dropped by Rust."""
        text = """
default_clearance_mm: 0.2
classes:
  Signal:
    clearance: 0.15
    future_field: whatever
"""
        oracle, rust = _both(text, tmp_path)
        assert _dr_canonical(rust[0]) == _dr_canonical(oracle.design_rules)


class TestMalformedInputs:
    def test_empty_yaml_raises_same_typeerror(self, tmp_path):
        path = tmp_path / "empty.yaml"
        path.write_text("")
        with pytest.raises(TypeError) as oracle_exc:
            oracle_load(path)
        with pytest.raises(TypeError) as rust_exc:
            rust_load("")
        assert str(rust_exc.value) == str(oracle_exc.value)

    def test_missing_default_clearance_raises_same_keyerror(self, tmp_path):
        text = "classes: {}\n"
        path = tmp_path / "missing.yaml"
        path.write_text(text)
        with pytest.raises(KeyError) as oracle_exc:
            oracle_load(path)
        with pytest.raises(KeyError) as rust_exc:
            rust_load(text)
        assert str(rust_exc.value) == str(oracle_exc.value)

    def test_bad_class_pairs_key_warns_and_skips_identically(self, tmp_path, caplog):
        text = """
default_clearance_mm: 0.2
class_pairs:
  "A-B-C":
    clearance: 0.3
"""
        with caplog.at_level("WARNING", logger="temper_placer.io.netclass_loader"):
            oracle, rust = _both(text, tmp_path)
        oracle_warnings = [
            r.message
            for r in caplog.records
            if r.name == "temper_placer.io.netclass_loader"
        ]
        assert oracle_warnings, "the oracle should have warned"
        assert dict(rust[1]) == {}
        # The Rust side logs through the same logger name.
        assert any("A-B-C" in w for w in oracle_warnings)
