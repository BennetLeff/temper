import pytest
import networkx as nx
from temper_placer.core.netlist import Netlist, Net, Component
from temper_placer.heuristics.graph_utils import GraphBuilder

class TestGraphHeuristics:
    """Tests for graph-based heuristics and utilities."""

    def test_star_topology(self):
        """Verify star topology (e.g. decoupling caps around IC)."""
        u1 = Component(ref="U1", footprint="SOIC-8", bounds=(10, 10))
        c1 = Component(ref="C1", footprint="C0603", bounds=(2, 2))
        c2 = Component(ref="C2", footprint="C0603", bounds=(2, 2))
        
        # Two separate nets connecting caps to U1
        net1 = Net(name="N1", pins=[("U1", "1"), ("C1", "1")])
        net2 = Net(name="N2", pins=[("U1", "2"), ("C2", "1")])
        
        netlist = Netlist()
        netlist.components = [u1, c1, c2]
        netlist.nets = [net1, net2]
        
        builder = GraphBuilder(netlist)
        G = builder.build_graph()
        
        assert G.degree("U1") == 2
        assert G.degree("C1") == 1
        assert G.degree("C2") == 1
        assert nx.is_connected(G)

    def test_bus_topology(self):
        """Verify bus topology (clique expansion)."""
        # 4 components on a single net (e.g. I2C bus or GND)
        comps = [Component(ref=f"U{i}", footprint="DIP-8", bounds=(5, 5)) for i in range(4)]
        pins = [(f"U{i}", "1") for i in range(4)]
        net = Net(name="BUS", pins=pins)
        
        netlist = Netlist()
        netlist.components = comps
        netlist.nets = [net]
        
        builder = GraphBuilder(netlist)
        G = builder.build_graph()
        
        # k=4 pins -> scale = 1/(4-1) = 0.333
        # Clique expansion should have 4*3/2 = 6 edges
        assert len(G.edges) == 6
        for u, v in G.edges:
            assert G[u][v]["weight"] == pytest.approx(1.0 / 3.0)

    def test_critical_net_weighting(self):
        """Verify that critical nets have higher weights."""
        u1 = Component(ref="U1", footprint="SOIC-8", bounds=(5, 5))
        u2 = Component(ref="U2", footprint="SOIC-8", bounds=(5, 5))
        u3 = Component(ref="U3", footprint="SOIC-8", bounds=(5, 5))
        
        # Standard signal net
        net_std = Net(name="SIG", pins=[("U1", "1"), ("U2", "1")])
        # Critical net
        net_crit = Net(name="CRIT", pins=[("U1", "2"), ("U3", "1")], net_class="Critical")
        
        netlist = Netlist()
        netlist.components = [u1, u2, u3]
        netlist.nets = [net_std, net_crit]
        
        builder = GraphBuilder(netlist)
        G = builder.build_graph()
        
        w_std = G["U1"]["U2"]["weight"]
        w_crit = G["U1"]["U3"]["weight"]
        
        assert w_crit == pytest.approx(w_std * 10.0)

    def test_disconnected_components(self):
        """Verify that disconnected components still become nodes."""
        u1 = Component(ref="U1", footprint="SOIC-8", bounds=(5, 5))
        u2 = Component(ref="U2", footprint="SOIC-8", bounds=(5, 5)) # Not connected to anything
        
        netlist = Netlist()
        netlist.components = [u1, u2]
        netlist.nets = []
        
        builder = GraphBuilder(netlist)
        G = builder.build_graph()
        
        assert len(G.nodes) == 2
        assert len(G.edges) == 0
        assert not nx.is_connected(G)
