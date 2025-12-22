from temper_drc.checks.safety.hv_lv_separation import HVLVSeparationCheck
from temper_drc.core.result import Severity
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import ComponentPlacement, Placement


def test_hv_lv_separation_pass():
    """Test passes when HV and LV components are sufficiently separated."""
    constraints = ConstraintSet(hv_clearance_mm=10.0)
    
    # Q1 (HV) at 0, C1 (LV) at 20 -> Dist 19.0 > 10.0
    placement = Placement(
        components={
            "Q1": ComponentPlacement(ref="Q1", footprint="TO-247", x=0, y=0, rotation=0, layer="F.Cu", width=1.0, height=1.0, net_class="HV"),
            "C1": ComponentPlacement(ref="C1", footprint="R", x=20, y=0, rotation=0, layer="F.Cu", width=1.0, height=1.0, net_class="LV"),
        }
    )

    check = HVLVSeparationCheck()
    result = check.run(placement, constraints)

    assert result.passed
    assert len(result.issues) == 0


def test_hv_lv_separation_fail():
    """Test fails when HV and LV components are too close."""
    constraints = ConstraintSet(hv_clearance_mm=10.0)

    # Q1 (HV) at 0, C1 (LV) at 5 -> Edge-to-edge Dist 4.0 < 10.0
    placement = Placement(
        components={
            "Q1": ComponentPlacement(ref="Q1", footprint="TO-247", x=0, y=0, rotation=0, layer="F.Cu", width=1.0, height=1.0, net_class="HV"),
            "C1": ComponentPlacement(ref="C1", footprint="R", x=5, y=0, rotation=0, layer="F.Cu", width=1.0, height=1.0, net_class="LV"),
        }
    )

    check = HVLVSeparationCheck()
    result = check.run(placement, constraints)

    assert not result.passed
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.severity == Severity.CRITICAL
    assert "HV" in issue.message
    assert "LV" in issue.message


def test_hv_lv_separation_multi_layer_fail():
    """Safety checks often apply across layers too."""
    constraints = ConstraintSet(hv_clearance_mm=10.0)

    # Q1 (HV) Top layer, C1 (LV) Bottom layer, same (x,y) -> Dist 0.0 < 10.0
    placement = Placement(
        components={
            "Q1": ComponentPlacement(ref="Q1", footprint="TO-247", x=0, y=0, rotation=0, layer="F.Cu", width=1.0, height=1.0, net_class="HV"),
            "C1": ComponentPlacement(ref="C1", footprint="R", x=0, y=0, rotation=0, layer="B.Cu", width=1.0, height=1.0, net_class="LV"),
        }
    )

    check = HVLVSeparationCheck()
    result = check.run(placement, constraints)

    assert not result.passed
