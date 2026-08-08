"""Additional tests for core.community module coverage."""

from temper_placer.core.community import (
    ComponentCommunity,
    Community,
    get_community_component_indices,
    partition_netlist_min_cut,
)
from temper_placer.core.netlist import Component, Net, Netlist


def _make_simple_netlist():
    """Create a simple 4-component, 2-cluster netlist."""
    comps = [
        Component(ref="U1", footprint="MCU", bounds=(10, 10)),
        Component(ref="C1", footprint="0603", bounds=(2, 1)),
        Component(ref="U2", footprint="BUCK", bounds=(5, 5)),
        Component(ref="C2", footprint="1210", bounds=(3, 3)),
    ]
    nets = [
        Net("N1", [("U1", "1"), ("C1", "1")]),
        Net("N2", [("U2", "1"), ("C2", "1")]),
        Net("BRIDGE", [("U1", "2"), ("U2", "2")]),
    ]
    return Netlist(components=comps, nets=nets)


class TestGetCommunityComponentIndices:
    """Tests for get_community_component_indices."""

    def test_resolves_refs(self):
        netlist = _make_simple_netlist()
        community = Community(
            name="test", component_refs=["U1", "C1"], modularity_score=0.5
        )
        indices = get_community_component_indices(netlist, community)
        assert indices == [0, 1]

    def test_resolves_single(self):
        netlist = _make_simple_netlist()
        community = Community(
            name="test", component_refs=["U2"], modularity_score=0.5
        )
        indices = get_community_component_indices(netlist, community)
        assert indices == [2]


class TestPartitionNetlistMinCut:
    """Tests for partition_netlist_min_cut."""

    def test_empty_netlist(self):
        netlist = Netlist([], [])
        result = partition_netlist_min_cut(netlist, n_parts=2)
        assert result == []

    def test_basic_partition(self):
        netlist = _make_simple_netlist()
        result = partition_netlist_min_cut(netlist, n_parts=2)
        # Should return 2 partitions covering all 4 components
        assert len(result) == 2
        all_indices = sorted(i for part in result for i in part)
        assert all_indices == [0, 1, 2, 3]

    def test_partition_covers_all(self):
        """Each component appears exactly once."""
        netlist = _make_simple_netlist()
        result = partition_netlist_min_cut(netlist, n_parts=4)
        all_indices = [i for part in result for i in part]
        assert sorted(all_indices) == [0, 1, 2, 3]


class TestDataclasses:
    """Smoke tests for Community and ComponentCommunity dataclasses."""

    def test_community_create(self):
        c = Community(name="power", component_refs=["U1", "C1"], modularity_score=0.8)
        assert c.name == "power"
        assert c.component_refs == ["U1", "C1"]
        assert c.modularity_score == 0.8

    def test_component_community_defaults(self):
        cc = ComponentCommunity(component_ref="U1", community_name="power")
        assert cc.component_ref == "U1"
        assert cc.community_name == "power"
        assert cc.confidence == 1.0
