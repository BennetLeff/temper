from temper_drc.checks.emc.loop_area import LoopAreaCheck
from temper_drc.core.result import Severity
from temper_drc.input.constraints import ConstraintSet, LoopConstraint
from temper_drc.input.placement import ComponentPlacement, Placement


def test_loop_area_check_pass():
    """Test passes when components in loop form a small area."""
    # Critical loop involves NetA and NetB.
    constraints = ConstraintSet(
        critical_loops=[
            LoopConstraint(name="Loop1", nets=["NetA", "NetB"], max_area_mm2=10.0)
        ]
    )

    # Components connected to NetA or NetB
    # Placed in a 2x2 box -> Area = 4.0 < 10.0
    placement = Placement(
        components={
            "C1": ComponentPlacement(ref="C1", footprint="R", x=0.0, y=0.0, rotation=0, layer="F.Cu", width=1, height=1),
            "C2": ComponentPlacement(ref="C2", footprint="R", x=2.0, y=2.0, rotation=0, layer="F.Cu", width=1, height=1),
        },
        nets={
            "NetA": ["C1", "C2"],
            "NetB": ["C1", "C2"] # Redundant but shows connection
        }
    )

    check = LoopAreaCheck()
    result = check.run(placement, constraints)

    assert result.passed
    assert len(result.issues) == 0


def test_loop_area_check_fail():
    """Test fails when component arrangement exceeds max area."""
    constraints = ConstraintSet(
        critical_loops=[
            LoopConstraint(name="LoopHuge", nets=["CriticalNet"], max_area_mm2=5.0)
        ]
    )

    # Placed in a 3x3 box -> Area = 9.0 > 5.0
    placement = Placement(
        components={
            "U1": ComponentPlacement(ref="U1", footprint="IC", x=0.0, y=0.0, rotation=0, layer="F.Cu", width=1, height=1),
            "U2": ComponentPlacement(ref="U2", footprint="IC", x=3.0, y=3.0, rotation=0, layer="F.Cu", width=1, height=1),
        },
        nets={
            "CriticalNet": ["U1", "U2"]
        }
    )

    check = LoopAreaCheck()
    result = check.run(placement, constraints)

    assert not result.passed
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.severity == Severity.WARNING # Loops are usually warnings unless severe
    assert "LoopHuge" in issue.message
    assert "9.00mm²" in issue.message
    assert "U1" in issue.affected_items


def test_loop_area_ignores_single_component():
    """Loops need at least 2 components to have area."""
    constraints = ConstraintSet(
        critical_loops=[
            LoopConstraint(name="Tiny", nets=["NetX"], max_area_mm2=1.0)
        ]
    )

    placement = Placement(
        components={
            "R1": ComponentPlacement(ref="R1", footprint="R", x=0.0, y=0.0, rotation=0, layer="F.Cu", width=1, height=1),
        },
        nets={
            "NetX": ["R1"]
        }
    )

    check = LoopAreaCheck()
    result = check.run(placement, constraints)
    assert result.passed
