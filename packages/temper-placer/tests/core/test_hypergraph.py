
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.extraction.hypergraph_factory import netlist_to_hypergraph


def test_star_ground_filtering():
    """
    Test that the 'Star Ground' (massive net) is correctly filtered
    when ignore_global_nets is True. This prevents the 'Super-Node' trap.
    """
    # 1. Create a netlist with a massive Ground net
    components = [
        Component(ref=f"U{i}", footprint="R0402", bounds=(1.0, 0.5))
        for i in range(100)
    ]

    # Net 0: Global Ground (Connects all 100 components)
    gnd_pins = [(f"U{i}", "GND") for i in range(100)]
    gnd_net = Net(name="GND", pins=gnd_pins)

    # Net 1: Signal Net (Connects U0 and U1)
    sig_net = Net(name="SIG", pins=[("U0", "1"), ("U1", "1")])

    netlist = Netlist(components=components, nets=[gnd_net, sig_net])

    # 2. Build Hypergraph with filtering
    hg = netlist_to_hypergraph(
        netlist,
        ignore_global_nets=True,
        global_net_threshold=50
    )

    # 3. Assertions
    # Should only have 1 edge (SIG), because GND (size 100) > 50
    assert hg.n_edges == 1
    assert hg.hyperedge_names == ["SIG"]

    # Verify incidence matrix shape
    # BCOO.shape is dynamic, but we can check the dense shape concept
    assert hg.incidence.matrix.shape == (100, 1)

    # Verify U0 and U1 are connected to the single edge
    # We can check node degrees
    degrees = hg.compute_node_degrees()
    assert degrees[0] == 1.0 # U0
    assert degrees[1] == 1.0 # U1
    assert degrees[2] == 0.0 # U2 (orphaned by filtering)

def test_physics_embedding():
    """Verify physics attributes are correctly populated."""
    c1 = Component(ref="C1", footprint="C", bounds=(1,1))
    c2 = Component(ref="C2", footprint="C", bounds=(1,1))

    hv_net = Net(name="HV_BUS", pins=[("C1", "1"), ("C2", "1")], net_class="HighVoltage")
    lv_net = Net(name="SIG", pins=[("C1", "2"), ("C2", "2")], net_class="Signal")

    netlist = Netlist(components=[c1, c2], nets=[hv_net, lv_net])

    hg = netlist_to_hypergraph(netlist)

    # Check HV flag
    assert hg.edge_voltages[0] == 1.0 # HV_BUS
    assert hg.edge_voltages[1] == 0.0 # SIG
