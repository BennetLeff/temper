
import pytest
from kiutils.board import Board as KiBoard
from kiutils.items.brditems import Stackup, StackupLayer
from kiutils.items.zones import Zone

from temper_placer.io.kicad_parser import _extract_stackup

def test_parse_stackup_from_setup():
    """Test parsing stackup from KiCad board setup (Method 1)."""
    # Mock KiBoard with Stackup
    board = KiBoard()
    board.setup = type("Setup", (), {})()
    
    # Create layers
    # Note: StackupLayer constructor arguments depend on kiutils version, 
    # but based on inspection, it's a dataclass.
    l1 = StackupLayer(name="F.SilkS", type="Top Silk Screen")
    l2 = StackupLayer(name="F.Mask", type="Top Solder Mask", thickness=0.01)
    l3 = StackupLayer(name="F.Cu", type="copper", thickness=0.035)
    # kiutils uses epsilonR and lossTangent
    l4 = StackupLayer(name="dielectric 1", type="core", thickness=1.51, material="FR4", epsilonR=4.5, lossTangent=0.02)
    l5 = StackupLayer(name="B.Cu", type="copper", thickness=0.035)
    l6 = StackupLayer(name="B.Mask", type="Bottom Solder Mask", thickness=0.01)
    
    board.setup.stackup = Stackup(layers=[l1, l2, l3, l4, l5, l6])
    
    # Zones for plane detection
    z1 = Zone(netName="GND", layers=["F.Cu"])
    board.zones = [z1]
    
    stackup = _extract_stackup(board, [])
    
    assert stackup.layer_count == 2
    assert abs(stackup.total_thickness_mm - 1.6) < 0.0001 # 0.01*2 + 0.035*2 + 1.51 = 1.6
    assert len(stackup.layers) == 2
    
    # Check Copper Layers
    assert stackup.layers[0].name == "F.Cu"
    assert stackup.layers[0].layer_type == "plane" # Due to GND zone
    assert stackup.layers[0].plane_net == "GND"
    assert stackup.layers[0].thickness_um == 35.0
    
    assert stackup.layers[1].name == "B.Cu"
    assert stackup.layers[1].layer_type == "signal" # No zone
    assert stackup.layers[1].plane_net is None
    
    # Check Dielectrics
    assert len(stackup.dielectrics) == 1
    d = stackup.dielectrics[0]
    assert d.name == "dielectric 1"
    assert d.thickness_mm == 1.51
    assert d.epsilon_r == 4.5
    assert d.loss_tangent == 0.02

def test_parse_stackup_fallback():
    """Test fallback parsing when stackup table is missing (Method 2)."""
    # Mock KiBoard without setup.stackup
    board = KiBoard()
    # board.layers needed for fallback
    # Mocking generic objects for layers since kiutils Layer might require more args
    board.layers = [
        type("Layer", (), {"name": "F.Cu"})(),
        type("Layer", (), {"name": "In1.Cu"})(),
        type("Layer", (), {"name": "In2.Cu"})(),
        type("Layer", (), {"name": "B.Cu"})()
    ]
    
    # Zones
    z1 = Zone(netName="GND", layers=["In1.Cu"])
    board.zones = [z1]
    
    stackup = _extract_stackup(board, [])
    
    assert stackup.layer_count == 4
    assert len(stackup.layers) == 4
    
    # F.Cu (Signal default)
    assert stackup.layers[0].name == "F.Cu"
    assert stackup.layers[0].layer_type == "signal"
    
    # In1.Cu (Plane due to zone)
    assert stackup.layers[1].name == "In1.Cu"
    assert stackup.layers[1].layer_type == "plane"
    assert stackup.layers[1].plane_net == "GND"
    
    # In2.Cu (Mixed default)
    assert stackup.layers[2].name == "In2.Cu"
    assert stackup.layers[2].layer_type == "mixed"
    
    # B.Cu (Signal default)
    assert stackup.layers[3].name == "B.Cu"
    assert stackup.layers[3].layer_type == "signal"
    
    # Fallback assumes default thickness logic
    assert stackup.total_thickness_mm == 1.6
    assert len(stackup.dielectrics) == 0 # Fallback doesn't parse dielectrics
