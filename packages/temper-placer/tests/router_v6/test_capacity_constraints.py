
import networkx as nx
import pytest

from temper_placer.core.netlist import Net
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.constraint_model import CapacityConstraint, ModelBuilder
from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules


@pytest.fixture
def mock_design_rules():
    default_rules = NetClassRules(
        name="Default",
        clearance_mm=0.1,
        trace_width_mm=0.1,
        via_diameter_mm=0.3,
        via_drill_mm=0.15
    )
    return DesignRules(
        net_classes={"Default": default_rules},
        net_class_assignments={},
        default_clearance_mm=0.1,
        default_trace_width_mm=0.1,
        default_via_diameter_mm=0.3,
        default_via_drill_mm=0.15
    )

@pytest.fixture
def mock_skeletons_and_widths():
    # Single layer, single edge
    g = nx.Graph()
    u, v = (0, 0), (10, 0)
    g.add_node(u)
    g.add_node(v)
    g.add_edge(u, v)

    sk = ChannelSkeleton(graph=g, layer_name="L1", total_length=10.0)

    # Capacity: 1.0mm
    # Net width: 0.1 (width) + 0.1 (clearance) = 0.2mm
    widths = ChannelWidths(
        layer_name="L1",
        node_widths={},
        edge_widths={(u, v): 1.0},
        min_width=1.0,
        max_width=1.0,
        avg_width=1.0
    )

    return {"L1": sk}, {"L1": widths}

@pytest.fixture
def mock_nets():
    return [
        Net(name="NET1", pins=[]),
        Net(name="NET2", pins=[])
    ]

def test_capacity_constraints_generated(mock_skeletons_and_widths, mock_nets, mock_design_rules):
    skeletons, widths = mock_skeletons_and_widths

    builder = ModelBuilder(
        skeletons=skeletons,
        nets=mock_nets,
        channel_widths=widths,
        design_rules=mock_design_rules
    )
    model = builder.build()

    # Check constraints
    # 1 edge -> 1 constraint
    constraints = [c for c in model.constraints if isinstance(c, CapacityConstraint)]
    assert len(constraints) == 1

    c = constraints[0]
    assert c.capacity == 1.0
    assert c.slack_factor == 0.8

    # 2 nets should be in the constraint
    assert len(c.terms) == 2
    for var, width in c.terms:
        # Net width: 0.1 (trace) + 0.1 (clearance) = 0.2
        assert abs(width - 0.2) < 1e-6
        assert var.var_type == "bool"

def test_no_constraints_if_no_widths(mock_skeletons_and_widths, mock_nets, mock_design_rules):
    skeletons, _ = mock_skeletons_and_widths

    builder = ModelBuilder(
        skeletons=skeletons,
        nets=mock_nets,
        channel_widths=None,
        design_rules=mock_design_rules
    )
    model = builder.build()

    assert model.constraint_count == 0
