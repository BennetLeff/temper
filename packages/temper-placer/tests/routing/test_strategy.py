
import pytest

from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.routing.strategy import assign_layers, order_nets


@pytest.fixture
def mock_netlist():
    c1 = Component(ref="U1", footprint="F", bounds=(5, 5))
    c2 = Component(ref="R1", footprint="F", bounds=(2, 1))

    # High voltage net
    n1 = Net(name="HV", pins=[("U1", "1"), ("R1", "1")], net_class="HighVoltage")
    # Low voltage signal net
    n2 = Net(name="SIG", pins=[("U1", "2"), ("R1", "2")], net_class="Signal")

    return Netlist(components=[c1, c2], nets=[n1, n2])

def test_net_ordering(mock_netlist):
    ordered = order_nets(mock_netlist)
    # HV should come before SIG due to net class priority
    assert ordered[0] == "HV"
    assert ordered[1] == "SIG"

def test_layer_assignment(mock_netlist):
    ordered = order_nets(mock_netlist)
    assignments = assign_layers(mock_netlist, ordered)

    assert assignments["HV"] == 0 # L1
    assert assignments["SIG"] == 3 # L4
