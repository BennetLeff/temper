
import jax.numpy as jnp
import pytest
from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.io.config_loader import PlacementConstraints, NetClassRule, constraints_to_design_rules
from temper_placer.routing.maze_router import MazeRouter

def test_high_current_canal():
    """
    EXP-05-A Verification:
    Verify trace width enforcement in constrained channels.
    - Signal Net (0.2mm) should pass through 1.0mm canal.
    - Power Net (2.0mm) should fail in 1.0mm canal.
    - Power Net (2.0mm) should pass in 2.5mm canal.
    """
    
    # 1. Setup Constraints
    constraints = PlacementConstraints(
        net_class_rules={
            "Power": NetClassRule(
                name="Power",
                trace_width_mm=2.0,
                clearance_mm=0.2, 
            ),
            "Signal": NetClassRule(
                name="Signal",
                trace_width_mm=0.2,
                clearance_mm=0.2 
            )
        },
        net_classes={
            "NET_PWR": "Power",
            "NET_SIG": "Signal"
        }
    )
    dr = constraints_to_design_rules(constraints)

    # 2. Setup Board & Router
    router = MazeRouter(
        grid_size=(100, 100), # 0.1mm cell
        cell_size_mm=0.1,
        num_layers=2,
        design_rules=dr,
        min_clearance=0.1
    )
    
    # 3. Create Canal (Width 1.0mm)
    # Center y = 5.0.
    # Top Wall: y > 5.5 (Pos 7.5, Height 4.0)
    # Bottom Wall: y < 4.5 (Pos 2.5, Height 4.0)
    c_top = Component(ref="WALL_TOP", footprint="RECT", bounds=(10.0, 4.0), initial_position=(5.0, 7.5), initial_side=0, pins=[])
    c_bottom = Component(ref="WALL_BOT", footprint="RECT", bounds=(10.0, 4.0), initial_position=(5.0, 2.5), initial_side=0, pins=[])
    
    c_start = Component(ref="START", footprint="PIN", bounds=(0.2,0.2), initial_position=(1.0, 5.0), initial_side=0)
    c_end = Component(ref="END", footprint="PIN", bounds=(0.2,0.2), initial_position=(9.0, 5.0), initial_side=0)
    
    components = [c_top, c_bottom, c_start, c_end]
    positions = jnp.array([c.initial_position for c in components])
    netlist = Netlist(components=components, nets=[])
    
    router.block_pads(components, positions, netlist)
    
    # Case A: NET_SIG (0.2mm) -> Success
    path_sig = router.route_net_rrr(
        "NET_SIG",
        [c_start.initial_position, c_end.initial_position],
        assignment=None
    )
    assert path_sig.success, f"NET_SIG failed to route through 1.0mm canal: {path_sig.failure_reason}"
        
    # Case B: NET_PWR (2.0mm) -> Failure
    path_pwr = router.route_net_rrr(
        "NET_PWR",
        [c_start.initial_position, c_end.initial_position],
        assignment=None
    )
    assert not path_pwr.success, "NET_PWR unexpectedly routed through 1.0mm canal!"

def test_high_current_wide_canal():
    """
    EXP-05-A Part 2: Wide Canal
    Verify Power Net (2.0mm) passes in 2.5mm canal.
    """
    constraints = PlacementConstraints(
        net_class_rules={
            "Power": NetClassRule(name="Power", trace_width_mm=2.0, clearance_mm=0.2)
        },
        net_classes={"NET_PWR": "Power"}
    )
    dr = constraints_to_design_rules(constraints)
    
    router = MazeRouter(
        grid_size=(100, 100), 
        cell_size_mm=0.1,
        num_layers=2,
        design_rules=dr,
        min_clearance=0.1
    )
    
    # Canal 2.5mm wide. Center 5.0. 
    # Top Wall: y > 6.25 (Pos 8.25)
    # Bot Wall: y < 3.75 (Pos 1.75)
    c_top = Component(ref="WALL_TOP", footprint="RECT", bounds=(10.0, 4.0), initial_position=(5.0, 8.25), initial_side=0, pins=[])
    c_bot = Component(ref="WALL_BOT", footprint="RECT", bounds=(10.0, 4.0), initial_position=(5.0, 1.75), initial_side=0, pins=[])
    c_start = Component(ref="START", footprint="PIN", bounds=(0.2,0.2), initial_position=(1.0, 5.0), initial_side=0)
    c_end = Component(ref="END", footprint="PIN", bounds=(0.2,0.2), initial_position=(9.0, 5.0), initial_side=0)
    
    components = [c_top, c_bot, c_start, c_end]
    positions = jnp.array([c.initial_position for c in components])
    netlist = Netlist(components=components, nets=[])
    
    router.block_pads(components, positions, netlist)
    
    path_pwr = router.route_net_rrr(
        "NET_PWR",
        [c_start.initial_position, c_end.initial_position],
        assignment=None
    )
    
    assert path_pwr.success, f"NET_PWR failed in wide canal (2.5mm): {path_pwr.failure_reason}"
