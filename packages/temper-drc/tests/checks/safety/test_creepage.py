from temper_drc.checks.safety.creepage import CreepageCheck
from temper_drc.core.result import Severity
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import ComponentPlacement, Placement


def test_creepage_pass():
    """Test passes when optoisolator has sufficient internal clearance (simulated by body width)."""
    # Optoisolator U1: Width 10mm -> Internal separation is plenty
    placement = Placement(
        components={
            "U1": ComponentPlacement(
                ref="U1", footprint="Optoisolator", x=0, y=0, rotation=0, layer="F.Cu", 
                width=10.0, height=5.0, net_class="ISO"
            ),
        }
    )

    check = CreepageCheck(min_iso_width_mm=7.0)
    result = check.run(placement, ConstraintSet())

    assert result.passed
    assert len(result.issues) == 0


def test_creepage_fail():
    """Test fails when isolation component is too narrow for safe creepage."""
    # U1 is only 4mm wide -> Too small for safety across HV/LV
    placement = Placement(
        components={
            "U1": ComponentPlacement(
                ref="U1", footprint="Optoisolator", x=0, y=0, rotation=0, layer="F.Cu", 
                width=4.0, height=4.0, net_class="ISO"
            ),
        }
    )

    check = CreepageCheck(min_iso_width_mm=7.0)
    result = check.run(placement, ConstraintSet())

    assert not result.passed
    assert len(result.issues) == 1
    assert "creepage" in result.issues[0].message.lower()
    assert "U1" in result.issues[0].affected_items
