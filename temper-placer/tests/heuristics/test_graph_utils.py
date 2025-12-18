import pytest
import networkx as nx
from typing import List

from temper_placer.core.netlist import Netlist, Net, Component, Pin
from temper_placer.heuristics.graph_utils import GraphBuilder


class TestGraphBuilder:
    def create_mock_netlist(self) -> Netlist:
        """Create a simple netlist for testing."""
        # Create components
        # Note: Component expects 'bounds' tuple (width, height), not separate width/height args
        u1 = Component(ref="U1", footprint="DIP-8", bounds=(10.0, 10.0), fixed=False)
        u2 = Component(ref="U2", footprint="DIP-8", bounds=(10.0, 10.0), fixed=False)
        r1 = Component(ref="R1", footprint="R0603", bounds=(5.0, 2.0), fixed=False)

        # Create nets
        # Net.pins is List[Tuple[str, str]] -> [(ref, pin_name), ...]

        # Net 1: U1-R1 (Signal, 2 pins)
        net1 = Net(name="SIG1", pins=[("U1", "1"), ("R1", "1")], net_class="Signal")

        # Net 2: U1-U2 (Critical, 2 pins)
        net2 = Net(name="CRIT1", pins=[("U1", "2"), ("U2", "1")], net_class="Critical")

        # Net 3: U1-U2-R1 (Power, 3 pins - clique expansion)
        net3 = Net(name="PWR", pins=[("U1", "3"), ("U2", "2"), ("R1", "2")], net_class="Power")

        netlist = Netlist()
        netlist.components = [u1, u2, r1]
        netlist.nets = [net1, net2, net3]
        return netlist

    def test_build_graph_nodes(self):
        """Verify all components become nodes with attributes."""
        netlist = self.create_mock_netlist()
        builder = GraphBuilder(netlist)
        G = builder.build_graph()

        assert len(G.nodes) == 3
        assert "U1" in G.nodes
        assert "U2" in G.nodes
        assert "R1" in G.nodes

        # Check attributes
        assert G.nodes["U1"]["width"] == 10
        assert G.nodes["R1"]["area"] == 10  # 5 * 2

    def test_build_graph_edges_and_weights(self):
        """Verify edges are created with correct weights."""
        netlist = self.create_mock_netlist()
        builder = GraphBuilder(netlist)
        G = builder.build_graph()

        # Check basic connectivity
        assert G.has_edge("U1", "R1")  # From SIG1 and PWR
        assert G.has_edge("U1", "U2")  # From CRIT1 and PWR
        assert G.has_edge("U2", "R1")  # From PWR (clique)

        # Check weight logic
        # 1. Critical Net (U1-U2):
        #    Base weight = 1.0
        #    Critical multiplier = 10.0
        #    Clique scale (2 pins) = 1/(2-1) = 1.0
        #    Contribution = 10.0

        # 2. Power Net (U1-U2, U2-R1, U1-R1):
        #    Base weight = 1.0
        #    Power multiplier = 2.0
        #    Clique scale (3 pins) = 1/(3-1) = 0.5
        #    Contribution = 1.0 per edge

        # 3. Signal Net (U1-R1):
        #    Base weight = 1.0
        #    Multiplier = 1.0
        #    Clique scale = 1.0
        #    Contribution = 1.0

        # Expected weights:
        # U1-U2: Critical(10.0) + Power(1.0) = 11.0
        # U1-R1: Signal(1.0) + Power(1.0) = 2.0
        # U2-R1: Power(1.0) = 1.0

        w_u1_u2 = G["U1"]["U2"]["weight"]
        w_u1_r1 = G["U1"]["R1"]["weight"]
        w_u2_r1 = G["U2"]["R1"]["weight"]

        assert w_u1_u2 == pytest.approx(11.0)
        assert w_u1_r1 == pytest.approx(2.0)
        assert w_u2_r1 == pytest.approx(1.0)

    def test_empty_netlist(self):
        """Verify empty netlist produces empty graph."""
        netlist = Netlist()
        builder = GraphBuilder(netlist)
        G = builder.build_graph()
        assert len(G) == 0
