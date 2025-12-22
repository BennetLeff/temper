from temper_drc.checks.drc.clearance import ClearanceCheck
from temper_drc.core.result import Severity
from temper_drc.input.constraints import ClearanceRule, ConstraintSet
from temper_drc.input.placement import ComponentPlacement, Placement


def test_clearance_check_pass():
    """Test that check passes when components are far enough apart."""
    # Define constraints: 1.0mm clearance required between Signal and Power
    constraints = ConstraintSet(
        clearances=[
            ClearanceRule(from_class="Signal", to_class="Power", min_mm=1.0)
        ]
    )

    # Place components 2.0mm apart (edge-to-edge)
    # C1: x=0, width=1 (bounds -0.5 to 0.5)
    # C2: x=3, width=1 (bounds 2.5 to 3.5)
    # Gap = 2.5 - 0.5 = 2.0mm > 1.0mm -> Pass
    placement = Placement(
        components={
            "C1": ComponentPlacement(
                ref="C1", footprint="R0603", x=0.0, y=0.0, rotation=0, layer="F.Cu", 
                width=1.0, height=1.0, net_class="Signal"
            ),
            "C2": ComponentPlacement(
                ref="C2", footprint="R0603", x=3.0, y=0.0, rotation=0, layer="F.Cu", 
                width=1.0, height=1.0, net_class="Power"
            ),
        }
    )

    check = ClearanceCheck()
    result = check.run(placement, constraints)

    assert result.passed
    assert len(result.issues) == 0


def test_clearance_check_fail():
    """Test that check fails when components are too close."""
    constraints = ConstraintSet(
        clearances=[
            ClearanceRule(from_class="Signal", to_class="Power", min_mm=1.0)
        ]
    )

    # Place components 0.5mm apart (edge-to-edge)
    # C1: x=0, width=1 (bounds -0.5 to 0.5)
    # C2: x=1.5, width=1 (bounds 1.0 to 2.0)
    # Gap = 1.0 - 0.5 = 0.5mm < 1.0mm -> Fail
    placement = Placement(
        components={
            "C1": ComponentPlacement(
                ref="C1", footprint="R0603", x=0.0, y=0.0, rotation=0, layer="F.Cu", 
                width=1.0, height=1.0, net_class="Signal"
            ),
            "C2": ComponentPlacement(
                ref="C2", footprint="R0603", x=1.5, y=0.0, rotation=0, layer="F.Cu", 
                width=1.0, height=1.0, net_class="Power"
            ),
        }
    )

    check = ClearanceCheck()
    result = check.run(placement, constraints)

    assert not result.passed
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.severity == Severity.ERROR
    assert "clearance" in issue.message.lower()
    assert "C1" in issue.affected_items
    assert "C2" in issue.affected_items


def test_clearance_check_ignore_same_net_class_if_no_rule():
    """Test that check ignores pairs if no rule applies."""
    constraints = ConstraintSet(clearances=[]) # No rules

    # Very close components
    placement = Placement(
        components={
            "C1": ComponentPlacement(
                ref="C1", footprint="R0603", x=0.0, y=0.0, rotation=0, layer="F.Cu", 
                width=1.0, height=1.0, net_class="Signal"
            ),
            "C2": ComponentPlacement(
                ref="C2", footprint="R0603", x=1.1, y=0.0, rotation=0, layer="F.Cu", 
                width=1.0, height=1.0, net_class="Signal"
            ),
        }
    )

    check = ClearanceCheck()
    result = check.run(placement, constraints)

    assert result.passed
    assert len(result.issues) == 0

def test_clearance_ignore_diff_layers():
    """Test that check accounts for layers (only check usually on same layer, or all? Clearance usually 3D but standard DRC component clearance acts on same layer)."""
    # Assuming standard component clearance checks only apply to same layer for now, 
    # unless specific 3D clearance is requested. Standard KiCad Courtyard/Clearance is same layer.
    
    constraints = ConstraintSet(
        clearances=[
            ClearanceRule(from_class="Signal", to_class="Signal", min_mm=1.0)
        ]
    )

    # Overlapping coordinates but different layers
    placement = Placement(
        components={
            "C1": ComponentPlacement(
                ref="C1", footprint="R0603", x=0.0, y=0.0, rotation=0, layer="F.Cu", 
                width=1.0, height=1.0, net_class="Signal"
            ),
            "C2": ComponentPlacement(
                ref="C2", footprint="R0603", x=0.0, y=0.0, rotation=0, layer="B.Cu", 
                width=1.0, height=1.0, net_class="Signal"
            ),
        }
    )

    check = ClearanceCheck()
    result = check.run(placement, constraints)

    # Should pass if we check layer
    assert result.passed
