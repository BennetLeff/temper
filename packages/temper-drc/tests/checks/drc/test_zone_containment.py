from temper_drc.checks.drc.zone_containment import ZoneContainmentCheck
from temper_drc.core.result import Severity
from temper_drc.input.constraints import ConstraintSet, ZoneDefinition
from temper_drc.input.placement import ComponentPlacement, Placement


def test_zone_check_pass():
    """Test passes when component is inside its assigned zone."""
    # Zone: [0, 0] to [10, 10]
    # Component C1 assigned to zone
    constraints = ConstraintSet(
        zones=[
            ZoneDefinition(name="PowerZone", bounds=(0.0, 0.0, 10.0, 10.0), components=["C1"])
        ]
    )

    # Place C1 at (5, 5) -> Inside
    placement = Placement(
        components={
            "C1": ComponentPlacement(
                ref="C1", footprint="R0603", x=5.0, y=5.0, rotation=0, layer="F.Cu", 
                width=1.0, height=1.0
            ),
        }
    )

    check = ZoneContainmentCheck()
    result = check.run(placement, constraints)

    assert result.passed
    assert len(result.issues) == 0


def test_zone_check_fail_outside():
    """Test fails when assigned component is outside zone."""
    # Zone: [0, 0] to [10, 10]
    # C1 assigned to zone
    constraints = ConstraintSet(
        zones=[
            ZoneDefinition(name="PowerZone", bounds=(0.0, 0.0, 10.0, 10.0), components=["C1"])
        ]
    )

    # Place C1 at (15, 5) -> Outside
    placement = Placement(
        components={
            "C1": ComponentPlacement(
                ref="C1", footprint="R0603", x=15.0, y=5.0, rotation=0, layer="F.Cu", 
                width=1.0, height=1.0
            ),
        }
    )

    check = ZoneContainmentCheck()
    result = check.run(placement, constraints)

    assert not result.passed
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.severity == Severity.ERROR
    assert "bound" in issue.message.lower() or "outside" in issue.message.lower()
    assert "C1" in issue.affected_items
    assert "PowerZone" in issue.details["zone"]


def test_zone_check_partial_overlap_fail():
    """Test fails if component is effectively outside (center outside) or we require full containment."""
    # Let's assume strict full containment for now, or at least center containment.
    # Implementation usually checks center.

    constraints = ConstraintSet(
        zones=[
            ZoneDefinition(name="SmallZone", bounds=(0.0, 0.0, 2.0, 2.0), components=["C1"])
        ]
    )

    # Place C1 at (2.1, 1.0) -> Center Outside
    placement = Placement(
        components={
            "C1": ComponentPlacement(
                ref="C1", footprint="R0603", x=2.1, y=1.0, rotation=0, layer="F.Cu", 
                width=1.0, height=1.0
            ),
        }
    )

    check = ZoneContainmentCheck()
    result = check.run(placement, constraints)

    assert not result.passed
    assert len(result.issues) == 1
