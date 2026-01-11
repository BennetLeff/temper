
import pytest
import networkx as nx
from temper_placer.core.netlist import Net, Component, Pin
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.constraint_model import ModelBuilder, LayerConstraint
from temper_placer.router_v6.stage0_data import ParsedPCB, StackupInfo, LayerInfo

@pytest.fixture
def mock_pcb():
    # 2 layer stackup
    stackup = StackupInfo(
        layers=[
            LayerInfo(index=0, name="F.Cu", layer_type="signal", thickness_um=35.0),
            LayerInfo(index=1, name="B.Cu", layer_type="signal", thickness_um=35.0)
        ],
        total_thickness_mm=1.6,
        layer_count=2
    )
    
    # One net, one SMD pin on Top (F.Cu) at (0,0)
    pin = Pin(name="1", number="1", position=(0, 0), net="N1", layer="F.Cu", is_pth=False)
    comp = Component(ref="U1", footprint="FP", bounds=(1,1), pins=[pin], initial_position=(0,0))
    
    return ParsedPCB(
        components=[comp],
        nets=[], # Not used by builder for this check
        zones=[],
        board=None,
        design_rules=None,
        stackup=stackup,
        source_path=None
    )

@pytest.fixture
def mock_skeletons():
    # Top Layer Skeleton: edge from (0,0) to (10,0)
    g_top = nx.Graph()
    g_top.add_edge((0, 0), (10, 0))
    sk_top = ChannelSkeleton(graph=g_top, layer_name="F.Cu", total_length=10.0)
    
    # Bottom Layer Skeleton: edge from (0,0) to (0,10)
    g_bot = nx.Graph()
    g_bot.add_edge((0, 0), (0, 10))
    sk_bot = ChannelSkeleton(graph=g_bot, layer_name="B.Cu", total_length=10.0)
    
    return {"F.Cu": sk_top, "B.Cu": sk_bot}

def test_layer_constraints_smd_top(mock_pcb, mock_skeletons):
    nets = [Net(name="N1", pins=[])]
    
    builder = ModelBuilder(
        skeletons=mock_skeletons, 
        nets=nets, 
        pcb=mock_pcb
    )
    model = builder.build()
    
    # Pin is at (0,0) on F.Cu.
    # Breakout edge on B.Cu at (0,0) should be restricted (allowed=False).
    layer_constraints = [c for c in model.constraints if isinstance(c, LayerConstraint)]
    
    # Should have one constraint for the B.Cu breakout edge
    assert len(layer_constraints) >= 1
    
    # Find constraint for B.Cu edge
    restr = [c for c in layer_constraints if "B.Cu" in c.channel_id]
    assert len(restr) == 1
    assert restr[0].allowed == False
    assert restr[0].net_idx == 0

def test_layer_constraints_pth(mock_pcb, mock_skeletons):
    # Make pin PTH
    mock_pcb.components[0].pins[0].is_pth = True
    nets = [Net(name="N1", pins=[])]
    
    builder = ModelBuilder(
        skeletons=mock_skeletons, 
        nets=nets, 
        pcb=mock_pcb
    )
    model = builder.build()
    
    # PTH pins can connect to any layer, so no layer restrictions
    layer_constraints = [c for c in model.constraints if isinstance(c, LayerConstraint)]
    assert len(layer_constraints) == 0
