from temper_drc.checks.safety.isolation import IsolationCheck
from temper_drc.input.constraints import ConstraintSet, ZoneDefinition
from temper_drc.input.placement import ComponentPlacement, Placement


def test_isolation_pass():
    """Test passes when components respect isolation zone and optoisolator straddles it."""
    # Isolation zone at x=[10, 15]
    constraints = ConstraintSet(
        zones=[
            ZoneDefinition(name="Isolation_Slot", bounds=(10.0, 0.0, 15.0, 100.0), net_classes=["ISO"])
        ]
    )

    placement = Placement(
        components={
            "U_MCU": ComponentPlacement(ref="U_MCU", footprint="QFP", x=5, y=5, rotation=0, layer="F.Cu", width=4, height=4, net_class="LV"),
            "Q_SWITCH": ComponentPlacement(ref="Q_SWITCH", footprint="TO-220", x=20, y=20, rotation=0, layer="F.Cu", width=4, height=4, net_class="HV"),
            "ISO1": ComponentPlacement(ref="ISO1", footprint="Opto", x=12.5, y=10, rotation=0, layer="F.Cu", width=8, height=4, net_class="ISO"),
        },
        zones={
            "Isolation_Slot": (10.0, 0.0, 15.0, 100.0)
        }
    )

    check = IsolationCheck()
    result = check.run(placement, constraints)

    assert result.passed
    assert len(result.issues) == 0


def test_isolation_fail_component_in_slot():
    """Test fails when a non-isolation component is inside the isolation zone."""
    constraints = ConstraintSet(
        zones=[
            ZoneDefinition(name="Isolation_Slot", bounds=(10.0, 0.0, 15.0, 100.0), net_classes=["ISO"])
        ]
    )

    placement = Placement(
        components={
            "R_BAD": ComponentPlacement(ref="R_BAD", footprint="R", x=12, y=12, rotation=0, layer="F.Cu", width=1, height=1, net_class="LV"),
        },
        zones={
            "Isolation_Slot": (10.0, 0.0, 15.0, 100.0)
        }
    )

    check = IsolationCheck()
    result = check.run(placement, constraints)

    assert not result.passed
    assert len(result.issues) == 1
    assert "in isolation zone" in result.issues[0].message.lower()
    assert "R_BAD" in result.issues[0].affected_items
