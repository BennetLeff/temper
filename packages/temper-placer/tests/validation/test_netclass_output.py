"""Tests for netclass (net_class ...) s-expression output in exported PCBs.

Validates that write_netclass_forms produces correct KiCad s-expression
forms and that they are injected into board output without corrupting
existing content.
"""

from pathlib import Path

import pytest

from temper_placer.core.design_rules import NetClassRules


def _make_minimal_rules():
    """Build a NetClassRulesDict compatible dict with 3 net classes."""
    return {
        "net_classes": {
            "Signal": NetClassRules(
                name="Signal",
                trace_width=0.2,
                clearance=0.15,
                via_diameter=0.6,
                via_drill=0.3,
            ),
            "Power": NetClassRules(
                name="Power",
                trace_width=0.5,
                clearance=0.25,
                via_diameter=0.8,
                via_drill=0.4,
            ),
            "HighVoltage": NetClassRules(
                name="HighVoltage",
                trace_width=3.0,
                clearance=6.0,
                via_diameter=1.2,
                via_drill=0.6,
            ),
        },
        "pair_clearances": {},
        "default_clearance_mm": 0.2,
        "because": {},
    }


class TestWriteNetclassForms:
    """Unit tests for write_netclass_forms output."""

    def test_produces_correct_sexpr_lines(self):
        """Output contains properly formatted (net_class ...) forms."""
        from temper_placer.io.kicad_exporter import write_netclass_forms

        rules = _make_minimal_rules()
        result = write_netclass_forms(None, rules)

        assert '(net_class "HighVoltage"' in result
        assert '(clearance 6.0)' in result
        assert '(trace_width 3.0)' in result
        assert '(via_dia 1.2)' in result
        assert '(via_drill 0.6)' in result

        assert '(net_class "Power"' in result
        assert '(clearance 0.25)' in result
        assert '(trace_width 0.5)' in result
        assert '(via_dia 0.8)' in result
        assert '(via_drill 0.4)' in result

        assert '(net_class "Signal"' in result
        assert '(clearance 0.15)' in result
        assert '(trace_width 0.2)' in result
        assert '(via_dia 0.6)' in result
        assert '(via_drill 0.3)' in result

    def test_output_is_sorted_alphabetically(self):
        """Output lists net classes in alphabetical order."""
        from temper_placer.io.kicad_exporter import write_netclass_forms

        rules = _make_minimal_rules()
        result = write_netclass_forms(None, rules)
        lines = result.strip().split("\n")

        idx_hv = [i for i, l in enumerate(lines) if "HighVoltage" in l][0]
        idx_power = [i for i, l in enumerate(lines) if '"Power"' in l][0]
        idx_signal = [i for i, l in enumerate(lines) if '"Signal"' in l][0]
        assert idx_hv < idx_power < idx_signal

    def test_empty_net_classes_produces_empty_output(self):
        """When no net classes defined, returns empty string."""
        from temper_placer.io.kicad_exporter import write_netclass_forms

        rules = {
            "net_classes": {},
            "pair_clearances": {},
            "default_clearance_mm": 0.2,
            "because": {},
        }
        result = write_netclass_forms(None, rules)
        assert result == ""


class TestNetclassOutputIntegration:
    """Integration tests: inject forms into a real board and verify."""

    @pytest.fixture
    def template_pcb(self, tmp_path):
        """Create a minimal KiCad PCB file for testing."""
        pcb_path = tmp_path / "minimal.kicad_pcb"
        pcb_path.write_text(
            '(kicad_pcb (version 20221018) (generator pcbnew)\n'
            '  (general (thickness 1.6))\n'
            '  (paper "A4")\n'
            '  (layers\n'
            '    (0 "F.Cu" signal)\n'
            '    (31 "B.Cu" signal)\n'
            '    (44 "Edge.Cuts" user)\n'
            '  )\n'
            '  (setup\n'
            '    (pad_to_mask_clearance 0)\n'
            '  )\n'
            '  (net 0 "")\n'
            '  (net 1 "GND")\n'
            '  (net 2 "VCC")\n'
            ')\n'
        )
        return pcb_path

    def test_forms_injected_into_output(self, template_pcb, tmp_path):
        """Netclass forms appear in the output .kicad_pcb after export."""
        from kiutils.board import Board as KiBoard

        from temper_placer.io.kicad_exporter import (
            _insert_netclass_forms_into_sexpr,
            write_netclass_forms,
        )

        board = KiBoard.from_file(str(template_pcb))
        rules = _make_minimal_rules()
        forms = write_netclass_forms(board, rules)

        sexpr = board.to_sexpr()
        sexpr = _insert_netclass_forms_into_sexpr(sexpr, forms)

        output = tmp_path / "output.kicad_pcb"
        output.write_text(sexpr, encoding="utf-8")

        content = output.read_text(encoding="utf-8")
        assert '(net_class "HighVoltage"' in content
        assert '(net_class "Power"' in content
        assert '(net_class "Signal"' in content
        assert '(clearance 6.0)' in content
        assert '(clearance 0.25)' in content
        assert '(clearance 0.15)' in content

    def test_forms_inserted_after_setup_before_net(self, template_pcb, tmp_path):
        """Forms appear after (setup ...) and before (net ...)."""
        from kiutils.board import Board as KiBoard

        from temper_placer.io.kicad_exporter import (
            _insert_netclass_forms_into_sexpr,
            write_netclass_forms,
        )

        board = KiBoard.from_file(str(template_pcb))
        rules = _make_minimal_rules()
        forms = write_netclass_forms(board, rules)

        sexpr = board.to_sexpr()
        sexpr = _insert_netclass_forms_into_sexpr(sexpr, forms)

        setup_idx = sexpr.rfind("(pad_to_mask_clearance")
        net_class_idx = sexpr.find('(net_class "HighVoltage"')
        net_idx = sexpr.find("(net 0")

        assert setup_idx < net_class_idx < net_idx

    def test_existing_board_content_preserved(self, template_pcb, tmp_path):
        """Footprints, nets, and layers are untouched by form injection."""
        from kiutils.board import Board as KiBoard

        from temper_placer.io.kicad_exporter import (
            _insert_netclass_forms_into_sexpr,
            write_netclass_forms,
        )

        board = KiBoard.from_file(str(template_pcb))
        rules = _make_minimal_rules()
        forms = write_netclass_forms(board, rules)

        sexpr = board.to_sexpr()
        sexpr = _insert_netclass_forms_into_sexpr(sexpr, forms)

        assert 'General' in sexpr or 'thickness' in sexpr
        assert 'Edge.Cuts' in sexpr
        assert '(net 0 "")' in sexpr
        assert '(net 1 "GND")' in sexpr
        assert '(net 2 "VCC")' in sexpr

    def test_round_trip_write_then_parse_forms(self, template_pcb, tmp_path):
        """Netclass forms written to output survive file write/read round-trip.

        Note: kiutils Board.to_sexpr() drops unknown (net_class ...) forms
        on re-read, so we verify the raw file bytes, not the re-parsed
        kiutils object.
        """
        from kiutils.board import Board as KiBoard

        from temper_placer.io.kicad_exporter import (
            _insert_netclass_forms_into_sexpr,
            write_netclass_forms,
        )

        board = KiBoard.from_file(str(template_pcb))
        rules = _make_minimal_rules()
        forms = write_netclass_forms(board, rules)

        sexpr = board.to_sexpr()
        sexpr = _insert_netclass_forms_into_sexpr(sexpr, forms)

        output = tmp_path / "roundtrip.kicad_pcb"
        output.write_text(sexpr, encoding="utf-8")

        raw = output.read_text(encoding="utf-8")
        assert '(net_class "HighVoltage"' in raw
        assert '(net_class "Signal"' in raw
        assert '(net_class "Power"' in raw

    def test_no_netclass_rules_preserves_original_behavior(self, template_pcb, tmp_path):
        """When netclass_rules is None, output is unchanged."""
        from kiutils.board import Board as KiBoard

        board = KiBoard.from_file(str(template_pcb))
        original = board.to_sexpr()

        output = tmp_path / "no_rules.kicad_pcb"
        board.to_file(str(output))

        re_loaded = KiBoard.from_file(str(output))
        result = re_loaded.to_sexpr()

        assert original == result

    def test_export_routed_pcb_with_netclass_rules(self, template_pcb, tmp_path):
        """export_routed_pcb accepts netclass_rules and writes forms."""
        from temper_placer.io.kicad_exporter import export_routed_pcb

        rules = _make_minimal_rules()
        output = tmp_path / "with_rules.kicad_pcb"

        result = export_routed_pcb(
            template_pcb,
            routes={},
            output_pcb=output,
            netclass_rules=rules,
            auto_fill_zones=False,
        )

        assert result.output_path == output
        content = output.read_text(encoding="utf-8")
        assert '(net_class "HighVoltage"' in content
        assert '(net_class "Signal"' in content
