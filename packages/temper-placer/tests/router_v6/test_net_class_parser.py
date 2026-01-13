
import pytest
from temper_placer.io.kicad_parser import extract_net_classes

def test_extract_net_classes_basic():
    content = """
(kicad_pcb
  (setup
    (net_class "Default" "This is the default net class."
      (clearance 0.2)
      (trace_width 0.25)
      (via_dia 0.8)
      (via_drill 0.4)
      (add_net "Net-(C1-Pad1)")
      (add_net "GND")
    )
    (net_class "Power" "Power nets"
      (clearance 0.5)
      (trace_width 1.0)
      (via_dia 1.2)
      (via_drill 0.6)
      (add_net "+15V")
      (add_net "+5V")
    )
  )
)
"""
    classes = extract_net_classes(content)
    
    assert "Default" in classes
    assert classes["Default"]["clearance"] == 0.2
    assert classes["Default"]["trace_width"] == 0.25
    assert classes["Default"]["via_dia"] == 0.8
    assert classes["Default"]["via_drill"] == 0.4
    assert "GND" in classes["Default"]["nets"]
    assert "Net-(C1-Pad1)" in classes["Default"]["nets"]

    assert "Power" in classes
    assert classes["Power"]["clearance"] == 0.5
    assert classes["Power"]["trace_width"] == 1.0
    assert "+15V" in classes["Power"]["nets"]

def test_extract_net_classes_nested_parentheses():
    # Test robustness against other S-expressions
    content = """
(net_class "Complex" "Desc"
  (clearance 0.2)
  (add_net "A")
)
(something_else
  (net_class "Fake" "Should not be parsed if outside setup? or maybe just find all net_class")
)
"""
    # Assuming we search for (net_class ...) anywhere or specifically in setup.
    # The regex approach usually finds all.
    classes = extract_net_classes(content)
    assert "Complex" in classes
    assert classes["Complex"]["nets"] == ["A"]
