
import jax.numpy as jnp
from pathlib import Path
from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.io.config_loader import load_constraints, constraints_to_design_rules
from temper_placer.routing.maze_router import MazeRouter

def test_rrr_uses_net_topology(tmp_path):
    # 1. Create a config with net topology
    config_content = """
net_topology:
  GND:
    star_nodes: ['R1.1']
    edges:
      - source: R1.1
        sink: C1.1
        width: 1.0
      - source: R1.1
        sink: U1.GND
        width: 0.2
"""
    config_file = tmp_path / "test_topo.yaml"
    config_file.write_text(config_content)
    
    constraints = load_constraints(config_file)
    design_rules = constraints_to_design_rules(constraints)
    
    # 2. Create netlist matching config
    components = [
        Component("R1", "RES", (2, 2), [Pin("1", "1", (1, 0), net="GND")]),
        Component("C1", "CAP", (2, 2), [Pin("1", "1", (-1, 0), net="GND")]),
        Component("U1", "MCU", (4, 4), [Pin("GND", "GND", (0, 2), net="GND")]),
    ]
    nets = [Net("GND", [("R1", "1"), ("C1", "1"), ("U1", "GND")])]
    netlist = Netlist(components, nets)
    
    # Positions
    positions = jnp.array([
        [10.0, 10.0], # R1
        [5.0, 10.0],  # C1
        [10.0, 15.0], # U1
    ])
    
    board = Board(20, 20)
    router = MazeRouter.from_board(board, cell_size_mm=0.5, design_rules=design_rules)
    
    # 3. Route
    results = router.rrr_route_all_nets(
        netlist,
        positions,
        net_order=["GND"],
        assignments={},
        max_iterations=1
    )
    
    assert "GND" in results
    gnd_path = results["GND"]
    assert gnd_path.success
    
    # Check if we have segments with mixed widths
    assert len(gnd_path.segments) == 2
    
    # Segment 0: R1.1 -> C1.1 (Width 1.0)
    # Segment 1: R1.1 -> U1.GND (Width 0.2)
    # Note: NetGraph edges are routed in sorted order (priority then reversed insertion)
    # Here both have priority 0.
    
    widths = [s.trace_width for s in gnd_path.segments]
    assert 1.0 in widths
    assert 0.2 in widths
    
    print(f"Routed GND with segments: {widths}")
