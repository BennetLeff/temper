
import pytest
from unittest.mock import MagicMock
from temper_placer.core.routing_validator import validate_routing_result, RoutingViolation
from temper_placer.core.netlist import Netlist, Net, Component, Pin

@pytest.fixture
def mock_netlist():
    netlist = MagicMock(spec=Netlist)
    netlist.nets = []
    netlist.components = []
    return netlist

def test_short_detection(mock_netlist):
    """Test detecting shorts (same cell used by different nets)."""
    # Create simple grid paths
    # Net A uses cell (10, 10, 0)
    # Net B uses cell (10, 10, 0) -> Short
    
    # Mock path objects
    class MockPath:
        def __init__(self, cells): self.cells = cells
    class MockCell:
        def __init__(self, x, y, l): self.x=x; self.y=y; self.layer=l
    
    routed_paths = {
        "NET_A": MockPath([MockCell(10, 10, 0), MockCell(11, 10, 0)]),
        "NET_B": MockPath([MockCell(10, 10, 0), MockCell(10, 11, 0)]) # Overlap at 10,10
    }
    
    violations = validate_routing_result(
        routed_paths, 
        mock_netlist, 
        component_positions=[], 
        cell_size_mm=0.1, 
        grid_size=(100, 100), 
        num_layers=2
    )
    
    assert len(violations) == 1
    assert violations[0].violation_type == "SHORT"
    assert "NET_A" in violations[0].message and "NET_B" in violations[0].message

def test_open_detection(mock_netlist):
    """Test detecting connected/unconnected pins."""
    # Net: NET_A connects U1.1 and U2.1
    # U1 at (10.0, 10.0), Pin 1 at (0,0) -> Abs (10,10)
    # U2 at (20.0, 10.0), Pin 1 at (0,0) -> Abs (20,10)
    # Path covers (10,10) but not (20,10)
    
    # Setup Netlist
    u1 = Component(ref="U1", footprint="F1", bounds=(5,5))
    u1.pins = [Pin(name="1", number="1", position=(0.0, 0.0), net="NET_A")]
    
    u2 = Component(ref="U2", footprint="F2", bounds=(5,5))
    u2.pins = [Pin(name="1", number="1", position=(0.0, 0.0), net="NET_A")]
    
    net_a = Net(name="NET_A", pins=[("U1", "1"), ("U2", "1")])
    
    mock_netlist.components = [u1, u2]
    mock_netlist.nets = [net_a]
    mock_netlist._component_index = {"U1": 0, "U2": 1}
    # Mock lookup methods
    def get_comp(ref): return u1 if ref == "U1" else u2
    mock_netlist.get_component = get_comp
    
    positions = [(10.0, 10.0), (20.0, 10.0)]
    
    # Path covers U1 (x=100 grid) but not U2 (x=200 grid) with cell_size=0.1
    class MockPath:
        def __init__(self, cells): self.cells = cells
    class MockCell:
        def __init__(self, x, y, l): self.x=x; self.y=y; self.layer=l
        
    routed_paths = {
        "NET_A": MockPath([MockCell(100, 100, 0)]) # Covers U1
    }
    
    violations = validate_routing_result(
        routed_paths, 
        mock_netlist, 
        component_positions=positions, 
        cell_size_mm=0.1, 
        grid_size=(300, 300), 
        num_layers=2
    )
    
    # Should detect open at U2
    assert len(violations) == 1
    assert violations[0].violation_type == "OPEN"
    assert "U2.1" in violations[0].message
