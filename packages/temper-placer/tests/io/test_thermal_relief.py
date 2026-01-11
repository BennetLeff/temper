
import pytest
from kiutils.board import Board as KiBoard
from temper_placer.io.zone_manager import create_zone, PlaneConfig

def test_create_zone_has_thermal_relief():
    """Verify that create_zone sets thermal relief parameters correctly."""
    board = KiBoard()
    # Add a net to the board
    from kiutils.items.common import Net
    net = Net(number=1, name="GND")
    board.nets.append(net)
    
    config = PlaneConfig(
        layer="In1.Cu",
        net_name="GND",
        priority=1,
        clearance=0.4,
        thermal_gap=0.6,
        thermal_bridge_width=0.7
    )
    
    outline = [(0, 0), (10, 0), (10, 10), (0, 10)]
    
    zone = create_zone(board, config, outline)
    
    assert zone.netName == "GND"
    assert zone.layers == ["In1.Cu"]
    assert zone.priority == 1
    assert zone.connectPads == "thermal_reliefs"
    assert zone.clearance == 0.4
    
    assert zone.fillSettings is not None
    assert zone.fillSettings.thermalGap == 0.6
    assert zone.fillSettings.thermalBridgeWidth == 0.7
