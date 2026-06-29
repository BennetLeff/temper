
from temper_placer.io.config_loader import load_constraints


def test_load_net_topology(tmp_path):
    config_content = """
net_topology:
  NET_I_SENSE:
    star_nodes: ['R_SENSE.1']
    edges:
      - source: R_SENSE.1
        sink: LOAD.1
        width: 2.0
        priority: 1
      - source: R_SENSE.1
        sink: MCU.ADC1
        width: 0.2
        clearance: 0.5
        priority: 0
"""
    config_file = tmp_path / "test_topology.yaml"
    config_file.write_text(config_content)

    constraints = load_constraints(config_file)

    assert len(constraints.net_topologies) == 1
    graph = constraints.net_topologies[0]
    assert graph.net_name == "NET_I_SENSE"
    assert "R_SENSE.1" in graph.star_nodes
    assert len(graph.edges) == 2

    # Check Edge 1
    edge1 = graph.get_edge("R_SENSE.1", "LOAD.1")
    assert edge1 is not None
    assert edge1.trace_width_mm == 2.0
    assert edge1.priority == 1
    assert edge1.clearance_mm is None

    # Check Edge 2
    edge2 = graph.get_edge("R_SENSE.1", "MCU.ADC1")
    assert edge2 is not None
    assert edge2.trace_width_mm == 0.2
    assert edge2.clearance_mm == 0.5
    assert edge2.priority == 0
