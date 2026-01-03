
import jax.numpy as jnp
import pytest
from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.io.config_loader import PlacementConstraints, NetClassRule, constraints_to_design_rules
from temper_placer.routing.maze_router import MazeRouter

def test_mixed_signal_integration():
    """
    EXP-05-C Verification:
    Verify coexistence of all types on a mini-board.
    - Routing HV, Power, Gate, and Signal nets simultaneously.
    - Different widths and clearances.
    """
    
    # 1. Setup Constraints
    constraints = PlacementConstraints(
        net_class_rules={
            "HighVoltage": NetClassRule(
                name="HighVoltage",
                trace_width_mm=1.0, 
                clearance_mm=2.0,
                creepage_mm=8.0,
                via_size_mm=1.5
            ),
            "Power": NetClassRule(
                name="Power",
                trace_width_mm=1.5,
                clearance_mm=0.5,
                via_size_mm=1.2
            ),
            "GateDrive": NetClassRule(
                name="GateDrive",
                trace_width_mm=0.4,
                clearance_mm=0.3,
                via_size_mm=0.8
            ),
            "Signal": NetClassRule(
                name="Signal",
                trace_width_mm=0.2,
                clearance_mm=0.2,
                via_size_mm=0.5
            )
        },
        net_classes={
            "NET_HV": "HighVoltage",
            "NET_PWR": "Power",
            "NET_GATE": "GateDrive",
            "NET_SENSE": "Signal"
        }
    )
    dr = constraints_to_design_rules(constraints)

    # 2. Setup Board & Router
    router = MazeRouter(
        grid_size=(1000, 1000), 
        cell_size_mm=0.1,
        num_layers=2,
        design_rules=dr,
        min_clearance=0.1
    )
    
    # 3. Define Components 
    c_mcu = Component(ref="MCU", footprint="QFP", bounds=(10.0, 10.0), initial_position=(20.0, 50.0), initial_side=0,
                      pins=[Pin(name="1", number="1", net="NET_GATE", position=(2.0, 0.0)), 
                            Pin(name="2", number="2", net="NET_SENSE", position=(2.0, 2.0))])
                      
    c_igbt = Component(ref="IGBT", footprint="TO-247", bounds=(15.0, 20.0), initial_position=(80.0, 50.0), initial_side=0,
                       pins=[Pin(name="G", number="1", net="NET_GATE", position=(-5.0, 0.0)), 
                             Pin(name="E", number="2", net="NET_SENSE", position=(-5.0, 2.0)), 
                             Pin(name="C", number="3", net="NET_PWR", position=(0.0, 5.0))])
                             
    c_relay = Component(ref="K1", footprint="RELAY", bounds=(20.0, 10.0), initial_position=(50.0, 80.0), initial_side=0,
                        pins=[Pin(name="COIL1", number="1", net="NET_PWR", position=(5.0, -2.0)), 
                              Pin(name="COM", number="3", net="NET_PWR", position=(-5.0, -2.0)),
                              Pin(name="NO", number="4", net="NET_HV", position=(0.0, 2.0))])
                              
    c_hv_conn = Component(ref="J_HV", footprint="CONN", bounds=(10.0, 5.0), initial_position=(50.0, 95.0), initial_side=0,
                          pins=[Pin(name="1", number="1", net="NET_HV", position=(0.0, 0.0))])
                          
    c_pwr_conn = Component(ref="J_PWR", footprint="CONN", bounds=(10.0, 5.0), initial_position=(80.0, 20.0), initial_side=0,
                           pins=[Pin(name="1", number="1", net="NET_PWR", position=(0.0, 0.0))])
                           
    c_sense_conn = Component(ref="J_SENSE", footprint="CONN", bounds=(5.0, 5.0), initial_position=(20.0, 20.0), initial_side=0,
                             pins=[Pin(name="1", number="1", net="NET_SENSE", position=(0.0, 0.0))])
                             
    components = [c_mcu, c_igbt, c_relay, c_hv_conn, c_pwr_conn, c_sense_conn]
    netlist = Netlist(components=components, nets=[])
    pos_arr = jnp.array([c.initial_position for c in components])
    
    router.block_pads(components, pos_arr, netlist)
    
    # 4. Routing
    nets_to_route = [
        ("NET_HV", [c_relay.pins[2], c_hv_conn.pins[0]]),
        ("NET_PWR", [c_pwr_conn.pins[0], c_igbt.pins[2]]), 
        ("NET_PWR", [c_igbt.pins[2], c_relay.pins[1]]),
        ("NET_GATE", [c_mcu.pins[0], c_igbt.pins[0]]),
        ("NET_SENSE", [c_igbt.pins[1], c_mcu.pins[1]])
    ]
    
    for net_name, pins in nets_to_route:
        # Resolve positions
        pts = []
        for p in pins:
            for c in components:
                if p in c.pins:
                    px, py = p.absolute_position(c.initial_position, 0.0, 0)
                    pts.append((px, py))
                    break
        
        start_pt = pts[0]
        end_pt = pts[1]
        
        path = router.route_net_rrr(net_name, [start_pt, end_pt], assignment=None)
        
        assert path.success, f"{net_name} failed to route! Reason: {path.failure_reason}"
