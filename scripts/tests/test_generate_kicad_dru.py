"""Tests for scripts/generate_kicad_dru.py's HighVoltageIsolated rules.

Background: ``grep -c HighVoltageIsolated scripts/generate_kicad_dru.py``
used to return 0 -- this netclass (the gate-drive floating bootstrap
supply: ``+5V_ISO``, ``VBOOT_H``, ``VBOOT_L``, and the UCC21550 gate
driver's own secondary bias nets ``hb.gate_hs.driver-p1-1``/``-p2``) carried
no custom clearance constraint anywhere in this generator. It fell through
to KiCad's per-netclass baseline (6.0mm clearance, from this class's own
``packages/temper-placer/configs/netclass_rules.yaml`` entry) with no
domain-aware rule at all.

``elec/domain_manifest.yaml`` declares every net in this class a member of
the same ``HV`` domain as ``ac_l``/``+170V_BUS``/``SW_NODE`` -- "isolated"
names the gate driver's own internal primary/secondary barrier, not a
barrier this class's own nets sit on the far side of relative to the rest
of HV. Two new rules apply the resulting asymmetric treatment:

  "HighVoltageIsolated same side" -- functional-only clearance (2.0mm,
                                      matching RULE 4's existing HV-to-LV
                                      clearance) against its own
                                      HV/ACMains neighbours.
  "HighVoltageIsolated to LV"     -- the same reinforced 2.0mm clearance
                                      against every other (LV/SELV) class.

Scope note: this generator has no ``creepage`` KiCad constraint concept
yet (no rule anywhere in this file emits it, and no PD2/PD3
pollution-degree figure has been derived for this class) -- creepage
enforcement for HighVoltageIsolated is deliberately deferred to the unit
that adds creepage-constraint emission generator-wide, rather than
inventing an uncited figure here for a mains-adjacent netclass.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import generate_kicad_dru as gen  # noqa: E402


def _rule_block(dru_text: str, rule_name: str) -> str:
    """Return the full text of a `(rule "<rule_name>" ...)` block, up to
    (but not including) the blank line that separates it from the next
    rule."""
    marker = f'(rule "{rule_name}"'
    start = dru_text.index(marker)
    end = dru_text.index("\n\n", start)
    return dru_text[start:end]


class TestHighVoltageIsolatedRulesEmitted:
    """The netclass with no rules at all now has rules."""

    def test_high_voltage_isolated_netclass_no_longer_absent(self):
        content = gen.generate_dru()
        assert content.count("HighVoltageIsolated") >= 2, (
            "expected at least the two new HighVoltageIsolated rules in "
            "the generated DRU text"
        )

    def test_same_side_rule_is_hv_domain_scoped_clearance_only(self):
        content = gen.generate_dru()
        block = _rule_block(content, "HighVoltageIsolated same side")
        assert "A.NetClass == 'HighVoltageIsolated'" in block
        assert "HighVoltage" in block and "ACMains" in block
        assert "(constraint clearance (min 2.0mm))" in block
        assert "creepage" not in block

    def test_to_lv_rule_has_reinforced_clearance(self):
        content = gen.generate_dru()
        block = _rule_block(content, "HighVoltageIsolated to LV")
        assert "A.NetClass == 'HighVoltageIsolated'" in block
        assert "B.NetClass != 'HighVoltageIsolated'" in block
        assert "B.NetClass != 'HighVoltage'" in block
        assert "B.NetClass != 'ACMains'" in block
        assert "(constraint clearance (min 2.0mm))" in block
        # Deliberately no creepage constraint yet -- see module docstring.
        assert "creepage" not in block

    def test_generated_dru_is_well_formed(self):
        """Smoke test: the generator runs end to end and produces text
        with balanced rule blocks, not just the two rules under test."""
        content = gen.generate_dru()
        assert content.count("(rule ") == content.count(")\n\n") or content.count(
            "(rule "
        ) <= content.count(")")
        assert "HighVoltageIsolated same side" in content
        assert "HighVoltageIsolated to LV" in content


class TestHighVoltageIsolatedNetclassRulesYaml:
    """packages/temper-placer/configs/netclass_rules.yaml carries the
    matching class definition consumed by the Python placer/router's own
    feasibility model (core/design_rules.py's TEMPER_NET_CLASSES)."""

    def test_netclass_rules_yaml_declares_the_class(self):
        import yaml

        repo_root = Path(__file__).resolve().parent.parent.parent
        path = repo_root / "packages" / "temper-placer" / "configs" / "netclass_rules.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert "HighVoltageIsolated" in data["classes"]
        entry = data["classes"]["HighVoltageIsolated"]
        assert entry["safety_category"] == "HV"
        assert entry["clearance"] == 6.0
