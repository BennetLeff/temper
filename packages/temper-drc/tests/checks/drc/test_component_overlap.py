from temper_drc.checks.drc.component_overlap import ComponentOverlapCheck
from temper_drc.core.result import Severity
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import ComponentPlacement, Placement


def test_overlap_check_pass():
    """Test passes when components do not overlap."""
    constraints = ConstraintSet()

    # C1: x=0, size=1 -> [-0.5, 0.5]
    # C2: x=2, size=1 -> [1.5, 2.5]
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

    check = ComponentOverlapCheck()
    result = check.run(placement, constraints)

    assert result.passed
    assert len(result.issues) == 0


def test_overlap_check_fail():
    """Test fails when components overlap."""
    constraints = ConstraintSet()

    # C1: x=0, size=1 -> [-0.5, 0.5]
    # C2: x=0.5, size=1 -> [0.0, 1.0]
    # Overlap range [0.0, 0.5]
    placement = Placement(
        components={
            "C1": ComponentPlacement(
                ref="C1", footprint="R0603", x=0.0, y=0.0, rotation=0, layer="F.Cu", 
                width=1.0, height=1.0
            ),
            "C2": ComponentPlacement(
                ref="C2", footprint="R0603", x=0.5, y=0.0, rotation=0, layer="F.Cu", 
                width=1.0, height=1.0
            ),
        }
    )

    check = ComponentOverlapCheck()
    result = check.run(placement, constraints)

    assert not result.passed
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.severity == Severity.CRITICAL # Overlap is critical usually
    assert "overlap" in issue.message.lower()
    assert "C1" in issue.affected_items
    assert "C2" in issue.affected_items
    assert issue.details["overlap_area_mm2"] > 0


def test_overlap_diff_layers_pass():
    """Test passes when components overlap but on different layers."""
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

    check = ComponentOverlapCheck()
    result = check.run(placement, constraints)

    assert result.passed
