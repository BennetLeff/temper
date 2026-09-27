"""Safety regressions for KiCad insulation rule generation."""

import importlib.util
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("write_rules_under_test", UNIT / "tools" / "write_rules.py")
write_rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(write_rules)


def test_saved_board_tracks_are_not_attributed_to_the_last_footprint():
    # KiCad-saved boards put routed tracks after their last footprint and use
    # tabs for indentation. The previous split-at-start parser assigned those
    # track nets to J5, suppressing a real 1.84 mm tank clearance violation.
    board = '''(kicad_pcb
\t(footprint "terminal"
\t\t(property "Reference" "J5")
\t\t(pad "1" thru_hole circle (net 1 "res_a"))
\t)
\t(segment (start 0 0) (end 1 0) (net 2 "vdiv_1"))
)'''
    assert write_rules.footprint_nets(board) == {"J5": {"res_a"}}


def test_footprint_nets_only_come_from_pad_expressions():
    board = '''(kicad_pcb
  (footprint "test (package)"
    (property "Reference" "R1")
    (pad "1" smd rect (net 1 "bus_p"))
    (pad "2" smd rect (net 2 "vdiv_1"))
    (fp_text user "escaped \\"(pad (net 3 \\\"foreign\\\"))\\\"")
  )
  (segment (start 0 0) (end 1 0) (net 4 "vdiv_2"))
)'''
    assert write_rules.footprint_nets(board) == {"R1": {"bus_p", "vdiv_1"}}


def test_rule_does_not_exempt_tracks_merely_touching_courtyard():
    board = (UNIT / "native-12" / "section.kicad_pcb").read_text()
    selv = write_rules.audit_selv_nets(UNIT / "audit.rs")
    rules = write_rules.rules(board, selv)
    assert "intersectsCourtyard" not in rules
    assert "memberOfFootprint('R27')" in rules


def test_barrier_rules_have_final_priority_over_escape_rules():
    board = (UNIT / "native-12" / "section.kicad_pcb").read_text()
    selv = write_rules.audit_selv_nets(UNIT / "audit.rs")
    # KiCad applies its last matching rule. Even a bad future request must
    # never make a component-local relaxation outrank either 8 mm barrier.
    escape = '(rule "test escape" (condition "A.NetName == \'pe\'") (constraint clearance (min 0.2mm)))'
    generated = write_rules.rules(board, selv, escape)
    names = [line for line in generated.splitlines() if line.startswith('(rule ')]
    assert names[-3:] == [
        '(rule "test escape" (condition "A.NetName == \'pe\'") (constraint clearance (min 0.2mm)))',
        '(rule "SELV to HOT: reinforced, D5 provisional"',
        '(rule "PE to HOT: D5 provisional floor"',
    ]
