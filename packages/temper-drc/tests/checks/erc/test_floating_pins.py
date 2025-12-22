from temper_drc.checks.erc.floating_pins import FloatingPinsCheck
from temper_drc.core.result import Severity
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import ComponentPlacement, Placement


def test_floating_pins_pass():
    """Test passes when all components are connected to at least one net."""
    placement = Placement(
        components={
            "R1": ComponentPlacement(ref="R1", footprint="R", x=0, y=0, rotation=0, layer="F.Cu", width=1, height=1),
        },
        nets={
            "Net1": ["R1", "U1"],
            "Net2": ["U1", "MCU"]
        }
    )
    # R1 is in Net1. U1 is in Net1 and Net2. MCU is in Net2.
    # Note: Placement components dict might not have all refs in nets, 
    # but the check should focus on components listed in 'components'.
    placement.components["U1"] = ComponentPlacement(ref="U1", footprint="IC", x=5, y=5, rotation=0, layer="F.Cu", width=2, height=2)
    placement.components["MCU"] = ComponentPlacement(ref="MCU", footprint="QFP", x=10, y=10, rotation=0, layer="F.Cu", width=5, height=5)
    
    check = FloatingPinsCheck()
    result = check.run(placement, ConstraintSet())
    
    assert result.passed
    assert len(result.issues) == 0


def test_floating_pins_fail():
    """Test fails when a component is not connected to any net."""
    placement = Placement(
        components={
            "R1": ComponentPlacement(ref="R1", footprint="R", x=0, y=0, rotation=0, layer="F.Cu", width=1, height=1),
            "FL": ComponentPlacement(ref="FL", footprint="R", x=10, y=10, rotation=0, layer="F.Cu", width=1, height=1),
        },
        nets={
            "Net1": ["R1", "U1"]
        }
    )
    # FL is in components but NOT in any net.
    
    check = FloatingPinsCheck()
    result = check.run(placement, ConstraintSet())
    
    assert not result.passed
    assert len(result.issues) == 1
    assert result.issues[0].affected_items == ["FL"]
    assert "floating" in result.issues[0].message.lower()
