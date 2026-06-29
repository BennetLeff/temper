from temper_drc.checks.emc.ground_plane import GroundPlaneCheck
from temper_drc.input.constraints import ConstraintSet, ZoneDefinition
from temper_drc.input.placement import ComponentPlacement, Placement

def test_ground_plane_pass():
    """Test passes when component is over a ground zone."""
    constraints = ConstraintSet(
        zones=[
            ZoneDefinition(name="GND_Plane", bounds=(0.0, 0.0, 100.0, 100.0), net_classes=["GND"])
        ]
    )

    # C1 (Power) at (50, 50) -> Inside GND_Plane
    placement = Placement(
        components={
            "C1": ComponentPlacement(ref="C1", footprint="D", x=50.0, y=50.0, rotation=0, layer="F.Cu", width=1, height=1, net_class="Power"),
        },
        zones={
            "GND_Plane": (0.0, 0.0, 100.0, 100.0)
        }
    )

    check = GroundPlaneCheck()
    result = check.run(placement, constraints)

    assert result.passed
    assert len(result.issues) == 0

def test_ground_plane_fail():
    """Test fails when a noisy component is placed without a ground plane underneath."""
    constraints = ConstraintSet(
        zones=[
            ZoneDefinition(name="SmallGND", bounds=(0.0, 0.0, 10.0, 10.0), net_classes=["GND"])
        ]
    )

    # C1 (Switching) at (50, 50) -> Far outside local GND plane
    placement = Placement(
        components={
            "C1": ComponentPlacement(ref="C1", footprint="MOD", x=50.0, y=50.0, rotation=0, layer="F.Cu", width=1, height=1, net_class="Switching"),
        },
        zones={
            "SmallGND": (0.0, 0.0, 10.0, 10.0)
        }
    )

    check = GroundPlaneCheck()
    result = check.run(placement, constraints)

    assert not result.passed
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert "ground plane" in issue.message.lower()
    assert "C1" in issue.affected_items
