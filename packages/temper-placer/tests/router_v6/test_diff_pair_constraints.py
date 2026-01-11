
import pytest
import networkx as nx
from temper_placer.core.netlist import Net
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.constraint_model import ModelBuilder, DiffPairConstraint
from temper_placer.router_v6.diff_pair_inference import DiffPair

@pytest.fixture
def mock_skeletons():
    # Single layer, single edge
    g = nx.Graph()
    u, v = (0, 0), (10, 0)
    g.add_node(u)
    g.add_node(v)
    g.add_edge(u, v)
    
    sk = ChannelSkeleton(graph=g, layer_name="L1", total_length=10.0)
    return {"L1": sk}

@pytest.fixture
def mock_nets():
    return [
        Net(name="USB_D+", pins=[]),
        Net(name="USB_D-", pins=[])
    ]

def test_diff_pair_constraints_generated(mock_skeletons, mock_nets):
    diff_pairs = [
        DiffPair(base_name="USB_D", p_net="USB_D+", n_net="USB_D-")
    ]
    
    builder = ModelBuilder(
        skeletons=mock_skeletons, 
        nets=mock_nets, 
        diff_pairs=diff_pairs
    )
    model = builder.build()
    
    # Check constraints
    # 1 edge -> 1 diff pair constraint
    diff_constraints = [c for c in model.constraints if isinstance(c, DiffPairConstraint)]
    assert len(diff_constraints) == 1
    
    c = diff_constraints[0]
    assert c.p_net_idx == 0
    assert c.n_net_idx == 1
    assert c.p_var.net_idx == 0
    assert c.n_var.net_idx == 1
    assert c.p_var.channel_id == c.n_var.channel_id

def test_no_diff_pair_constraints_if_mismatch(mock_skeletons, mock_nets):
    # Diff pair with nets that don't exist in mock_nets
    diff_pairs = [
        DiffPair(base_name="CLK", p_net="CLK_P", n_net="CLK_N")
    ]
    
    builder = ModelBuilder(
        skeletons=mock_skeletons, 
        nets=mock_nets, 
        diff_pairs=diff_pairs
    )
    model = builder.build()
    
    diff_constraints = [c for c in model.constraints if isinstance(c, DiffPairConstraint)]
    assert len(diff_constraints) == 0
