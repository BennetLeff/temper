from temper_drc.checks.erc.net_connectivity import NetConnectivityCheck
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import ComponentPlacement, Placement


def test_net_connectivity_pass():
    """Test passes when all nets have at least 2 connections."""
    placement = Placement(
        components={
            "C1": ComponentPlacement(ref="C1", footprint="R", x=0, y=0, rotation=0, layer="F.Cu", width=1, height=1),
            "C2": ComponentPlacement(ref="C2", footprint="R", x=2, y=0, rotation=0, layer="F.Cu", width=1, height=1),
        },
        nets={
            "Net1": ["C1", "C2"]
        }
    )
    
    check = NetConnectivityCheck()
    result = check.run(placement, ConstraintSet())
    
    assert result.passed
    assert len(result.issues) == 0


def test_net_connectivity_fail_single_pin():
    """Test fails when a net has only one connection."""
    placement = Placement(
        components={
            "C1": ComponentPlacement(ref="C1", footprint="R", x=0, y=0, rotation=0, layer="F.Cu", width=1, height=1),
        },
        nets={
            "Alone": ["C1"]
        }
    )
    
    check = NetConnectivityCheck()
    result = check.run(placement, ConstraintSet())
    
    assert not result.passed
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert "Alone" in issue.message
    assert "1 connection" in issue.message.lower()


def test_net_connectivity_fail_empty_net():
    """Test fails when a net has no connections."""
    placement = Placement(
        components={},
        nets={
            "Empty": []
        }
    )
    
    check = NetConnectivityCheck()
    result = check.run(placement, ConstraintSet())
    
    assert not result.passed
    assert len(result.issues) == 1
    assert "Empty" in result.issues[0].message
