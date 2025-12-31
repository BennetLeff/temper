
import logging
import sys
import jax.numpy as jnp
from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.io.config_loader import PlacementConstraints, NetClassRule
from temper_placer.pipeline.auto_layout import auto_layout_pcb

logging.basicConfig(level=logging.INFO)

def run_verification():
    print("Verifying Net Class Integration...")

    # 1. create dummy board
    board = Board(width=100, height=100)

    # 2. create dummy netlist
    # C1 (10, 50) -> C2 (90, 50) : NET_PWR
    # C3 (10, 40) -> C4 (90, 40) : NET_SIG
    
    c1 = Component(ref="C1", footprint="C0402", bounds=(1.0, 0.5), pins=[Pin(name="1", number="1", position=(0,0))], initial_position=(10, 50))
    c2 = Component(ref="C2", footprint="C0402", bounds=(1.0, 0.5), pins=[Pin(name="1", number="1", position=(0,0))], initial_position=(90, 50))
    c3 = Component(ref="C3", footprint="C0402", bounds=(1.0, 0.5), pins=[Pin(name="1", number="1", position=(0,0))], initial_position=(10, 40))
    c4 = Component(ref="C4", footprint="C0402", bounds=(1.0, 0.5), pins=[Pin(name="1", number="1", position=(0,0))], initial_position=(90, 40))

    components = [c1, c2, c3, c4]
    
    nets = [
        Net(name="NET_PWR", pins=[("C1", "1"), ("C2", "1")]),
        Net(name="NET_SIG", pins=[("C3", "1"), ("C4", "1")]),
    ]
    
    netlist = Netlist(components=components, nets=nets)

    # 3. Define Constraints
    constraints = PlacementConstraints()
    
    # Define Rules
    constraints.net_class_rules["Power"] = NetClassRule(
        name="Power",
        trace_width_mm=2.0,
        clearance_mm=0.5,
        via_size_mm=1.0,
        via_drill_mm=0.5
    )
    constraints.net_class_rules["Signal"] = NetClassRule(
        name="Signal",
        trace_width_mm=0.2,
        clearance_mm=0.2,
        via_size_mm=0.6,
        via_drill_mm=0.3
    )
    
    # Assign Nets
    constraints.net_classes["NET_PWR"] = "Power"
    constraints.net_classes["NET_SIG"] = "Signal"
    
    # 4. Run Auto Layout
    # Use initial positions from components (auto_layout uses initial_positions arg)
    initial_pos = jnp.array([c.initial_position for c in components])
    
    positions, routes = auto_layout_pcb(
        netlist, 
        board, 
        initial_positions=initial_pos,
        max_outer_iterations=1,
        constraints=constraints,
        cell_size_mm=0.1, # Fine grid
        num_layers=2
    )
    
    # 5. Verify Results
    pwr_route = routes["NET_PWR"]
    sig_route = routes["NET_SIG"]
    
    print(f"NET_PWR Trace Width: {pwr_route.trace_width} mm")
    print(f"NET_SIG Trace Width: {sig_route.trace_width} mm")
    
    assert pwr_route.trace_width == 2.0, f"Expected 2.0, got {pwr_route.trace_width}"
    assert sig_route.trace_width == 0.2, f"Expected 0.2, got {sig_route.trace_width}"
    assert pwr_route.success, "PWR net failed to route"
    assert sig_route.success, "SIG net failed to route"
    
    print("SUCCESS: Net classes correctly applied!")

if __name__ == "__main__":
    run_verification()
