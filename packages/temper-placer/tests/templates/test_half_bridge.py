
from temper_placer.core.netlist import Component, Netlist
from temper_placer.templates.half_bridge import HalfBridgeTemplate


def test_load_half_bridge_template():
    template = HalfBridgeTemplate.load()
    assert template.name == "half_bridge"
    assert "high_side_switch" in template.components

def test_match_half_bridge_components():
    template = HalfBridgeTemplate.load()

    # Mock netlist with components matching patterns
    c1 = Component(ref="Q1", footprint="TO-247", bounds=(15, 20))
    c2 = Component(ref="Q2", footprint="TO-247", bounds=(15, 20))
    c3 = Component(ref="U_GD", footprint="SOIC-16", bounds=(10, 10))

    netlist = Netlist(components=[c1, c2, c3])

    matches = template.match_components(netlist)
    assert matches["high_side_switch"] == "Q1"
    assert matches["low_side_switch"] == "Q2"
    assert matches["gate_driver"] == "U_GD"

def test_generate_constraints():
    template = HalfBridgeTemplate.load()
    component_map = {
        "high_side_switch": "Q1",
        "low_side_switch": "Q2",
        "gate_driver": "U_GD"
    }

    constraints = template.generate_constraints(component_map)

    # Check if 'high_side_switch' was replaced by 'Q1'
    adj_switch = [c for c in constraints if c["type"] == "adjacent" and c["a"] == "Q1"][0]
    assert adj_switch["b"] == "Q2"
    assert adj_switch["max_distance_mm"] == 10
