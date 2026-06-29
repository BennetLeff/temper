from temper_drc.checks.emc.noise_coupling import NoiseCouplingCheck
from temper_drc.input.constraints import ClearanceRule, ConstraintSet
from temper_drc.input.placement import ComponentPlacement, Placement


def test_noise_coupling_pass():
    """Test passes when aggressor and victim are separated."""
    # Define Power as Aggressor, Analog as Victim
    # Required separation: 5.0mm
    constraints = ConstraintSet(
        clearances=[
            ClearanceRule(from_class="Power", to_class="Analog", min_mm=5.0)
        ]
    )

    # C1 (Power) at 0, C2 (Analog) at 10 -> Distance 9.0 (assuming 1mm width)
    placement = Placement(
        components={
            "C1": ComponentPlacement(ref="C1", footprint="D", x=0.0, y=0.0, rotation=0, layer="F.Cu", width=1, height=1, net_class="Power"),
            "C2": ComponentPlacement(ref="C2", footprint="R", x=10.0, y=0.0, rotation=0, layer="F.Cu", width=1, height=1, net_class="Analog"),
        }
    )

    check = NoiseCouplingCheck()
    result = check.run(placement, constraints)

    assert result.passed
    assert len(result.issues) == 0

def test_noise_coupling_fail():
    """Test fails when aggressor and victim are too close."""
    constraints = ConstraintSet(
        clearances=[
            ClearanceRule(from_class="Power", to_class="Analog", min_mm=5.0)
        ]
    )

    # C1 (Power) at 0, C2 (Analog) at 2 -> Edge-to-edge Distance 1.0 < 5.0
    placement = Placement(
        components={
            "C1": ComponentPlacement(ref="C1", footprint="D", x=0.0, y=0.0, rotation=0, layer="F.Cu", width=1, height=1, net_class="Power"),
            "C2": ComponentPlacement(ref="C2", footprint="R", x=2.0, y=0.0, rotation=0, layer="F.Cu", width=1, height=1, net_class="Analog"),
        }
    )

    check = NoiseCouplingCheck()
    result = check.run(placement, constraints)

    assert not result.passed
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert "coupling" in issue.message.lower() or "clearance" in issue.message.lower()
    assert "C1" in issue.affected_items
    assert "C2" in issue.affected_items
