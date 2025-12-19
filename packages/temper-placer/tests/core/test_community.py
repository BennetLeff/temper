"""
TDD Tests for Netlist Community Detection.
"""

from temper_placer.core.community import detect_communities
from temper_placer.core.netlist import Component, Net, Netlist


def create_clustered_netlist():
    """
    Create a netlist with two clearly defined clusters:
    Cluster 1: U1, C1, C2, R1 (Highly connected)
    Cluster 2: U2, C3, C4, R2 (Highly connected)
    Bridge: U1 -> U2 (Weakly connected)
    """
    # Cluster 1 (MCU-like)
    comps1 = [
        Component(ref="U1", footprint="MCU", bounds=(10, 10)),
        Component(ref="C1", footprint="0603", bounds=(2, 1)),
        Component(ref="C2", footprint="0603", bounds=(2, 1)),
        Component(ref="R1", footprint="0603", bounds=(2, 1)),
    ]

    # Cluster 2 (Buck-like)
    comps2 = [
        Component(ref="U2", footprint="BUCK", bounds=(5, 5)),
        Component(ref="C3", footprint="1210", bounds=(3, 3)),
        Component(ref="C4", footprint="1210", bounds=(3, 3)),
        Component(ref="R2", footprint="0805", bounds=(2, 1)),
    ]

    nets = [
        # Nets within Cluster 1
        Net("N1_VCC", [("U1", "1"), ("C1", "1"), ("C2", "1")]),
        Net("N1_GND", [("U1", "2"), ("C1", "2"), ("C2", "2"), ("R1", "1")]),
        Net("N1_SIG", [("U1", "3"), ("R1", "2")]),

        # Nets within Cluster 2
        Net("N2_VIN", [("U2", "1"), ("C3", "1")]),
        Net("N2_SW",  [("U2", "2"), ("C4", "1")]),
        Net("N2_GND", [("U2", "3"), ("C3", "2"), ("C4", "2"), ("R2", "1")]),

        # Bridge net (Weak coupling)
        Net("BRIDGE", [("U1", "10"), ("U2", "10")])
    ]

    return Netlist(components=comps1 + comps2, nets=nets)

def test_detect_communities_finds_subsystems():
    """Verify that Louvain detection partitions the clusters correctly."""
    netlist = create_clustered_netlist()
    communities = detect_communities(netlist)

    # We expect exactly 2 communities
    assert len(communities) == 2

    # Extract sets of refs for each community
    comm_sets = [set(c.component_refs) for c in communities]

    cluster1_refs = {"U1", "C1", "C2", "R1"}
    cluster2_refs = {"U2", "C3", "C4", "R2"}

    # Verify that one community matches cluster 1 and the other cluster 2
    if cluster1_refs in comm_sets:
        assert cluster2_refs in comm_sets
    else:
        assert cluster2_refs in comm_sets
        assert cluster1_refs in comm_sets

def test_detect_communities_empty():
    netlist = Netlist([], [])
    communities = detect_communities(netlist)
    assert communities == []

def test_detect_communities_single_cluster():
    # Chain of 3 components
    comps = [
        Component(ref="R1", footprint="0603", bounds=(2, 1)),
        Component(ref="R2", footprint="0603", bounds=(2, 1)),
        Component(ref="R3", footprint="0603", bounds=(2, 1)),
    ]
    nets = [
        Net("N1", [("R1", "1"), ("R2", "1")]),
        Net("N2", [("R2", "2"), ("R3", "1")]),
    ]
    netlist = Netlist(comps, nets)
    communities = detect_communities(netlist)

    # Should find 1 community containing all 3
    assert len(communities) == 1
    assert set(communities[0].component_refs) == {"R1", "R2", "R3"}
