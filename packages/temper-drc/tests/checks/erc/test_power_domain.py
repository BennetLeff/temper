from temper_drc.checks.erc.power_domain import PowerDomainCheck
from temper_drc.core.result import Severity
from temper_drc.input.constraints import ConstraintSet
from temper_drc.input.placement import ComponentPlacement, Placement


def test_power_domain_pass():
    """Test passes when all components on a net share the same voltage domain."""
    placement = Placement(
        components={
            "U1": ComponentPlacement(ref="U1", footprint="IC", x=0, y=0, rotation=0, layer="F.Cu", width=1, height=1, voltage_domain="3V3"),
            "C1": ComponentPlacement(ref="C1", footprint="R", x=5, y=0, rotation=0, layer="F.Cu", width=1, height=1, voltage_domain="3V3"),
        },
        nets={
            "VCC": ["U1", "C1"]
        }
    )
    
    check = PowerDomainCheck()
    result = check.run(placement, ConstraintSet())
    
    assert result.passed
    assert len(result.issues) == 0


def test_power_domain_pass_none_and_value():
    """Test passes when one component has a domain and the other is generic (None)."""
    placement = Placement(
        components={
            "U1": ComponentPlacement(ref="U1", footprint="IC", x=0, y=0, rotation=0, layer="F.Cu", width=1, height=1, voltage_domain="3V3"),
            "R1": ComponentPlacement(ref="R1", footprint="R", x=5, y=0, rotation=0, layer="F.Cu", width=1, height=1, voltage_domain=None),
        },
        nets={
            "SIG": ["U1", "R1"]
        }
    )
    
    check = PowerDomainCheck()
    result = check.run(placement, ConstraintSet())
    
    # Generic components like resistors are allowed to connect to any domain
    assert result.passed


def test_power_domain_fail_conflict():
    """Test fails when two components with DIFFERENT explicit voltage domains share a net."""
    placement = Placement(
        components={
            "U1": ComponentPlacement(ref="U1", footprint="IC", x=0, y=0, rotation=0, layer="F.Cu", width=1, height=1, voltage_domain="3V3"),
            "U2": ComponentPlacement(ref="U2", footprint="IC", x=10, y=10, rotation=0, layer="F.Cu", width=1, height=1, voltage_domain="5V"),
        },
        nets={
            "BUG": ["U1", "U2"]
        }
    )
    
    check = PowerDomainCheck()
    result = check.run(placement, ConstraintSet())
    
    assert not result.passed
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert "conflict" in issue.message.lower()
    assert "3V3" in issue.message
    assert "5V" in issue.message
    assert "BUG" in issue.message
