from temper_drc.checks.drc.courtyard import CourtyardCheck
from temper_drc.core.result import Severity
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import ComponentPlacement, Placement


def test_courtyard_check_pass():
    """Test passes when components have sufficient courtyard spacing."""
    constraints = ConstraintSet()

    # Margin is usually small, e.g., 0.05mm
    # C1: x=0, size=1 -> [-0.5, 0.5] + margin
    # C2: x=2, size=1 -> [1.5, 2.5] - margin
    # Distance = 1.0mm >> margin
    placement = Placement(
        components={
            "C1": ComponentPlacement(
                ref="C1", footprint="R0603", x=0.0, y=0.0, rotation=0, layer="F.Cu", 
                width=1.0, height=1.0
            ),
            "C2": ComponentPlacement(
                ref="C2", footprint="R0603", x=2.0, y=0.0, rotation=0, layer="F.Cu", 
                width=1.0, height=1.0
            ),
        }
    )

    check = CourtyardCheck()
    result = check.run(placement, constraints)

    assert result.passed
    assert len(result.issues) == 0


def test_courtyard_check_fail():
    """Test fails when components violate the courtyard margin (too close but not touching)."""
    constraints = ConstraintSet()

    # C1: x=0, size=1 -> [-0.5, 0.5]
    # C2: x=1.05, size=1 -> [0.55, 1.55]
    # Gap = 0.05
    # If courtyard margin is 0.05mm per component, total required gap is 0.1mm.
    # So 0.05mm gap should fail.
    placement = Placement(
        components={
            "C1": ComponentPlacement(
                ref="C1", footprint="R0603", x=0.0, y=0.0, rotation=0, layer="F.Cu", 
                width=1.0, height=1.0
            ),
            "C2": ComponentPlacement(
                ref="C2", footprint="R0603", x=1.05, y=0.0, rotation=0, layer="F.Cu", 
                width=1.0, height=1.0
            ),
        }
    )

    check = CourtyardCheck(margin_mm=0.05)
    result = check.run(placement, constraints)

    assert not result.passed
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.severity == Severity.WARNING # Courtyard is usually warning or error, not critical like overlap
    assert "courtyard" in issue.message.lower()


def test_courtyard_diff_layers_pass():
    """Test passes on different layers."""
    constraints = ConstraintSet()

    placement = Placement(
        components={
            "C1": ComponentPlacement(
                ref="C1", footprint="R0603", x=0.0, y=0.0, rotation=0, layer="F.Cu", 
                width=1.0, height=1.0
            ),
            "C2": ComponentPlacement(
                ref="C2", footprint="R0603", x=0.0, y=0.0, rotation=0, layer="B.Cu", 
                width=1.0, height=1.0
            ),
        }
    )

    check = CourtyardCheck(margin_mm=0.25)
    result = check.run(placement, constraints)

    assert result.passed
