
import logging
import sys
import jax.numpy as jnp
from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.io.config_loader import PlacementConstraints, NetClassRule, constraints_to_design_rules
from temper_placer.routing.maze_router import MazeRouter, CLASS_HV, CLASS_LV

logging.basicConfig(level=logging.INFO, format="%(message)s")

def run_experiment():
    print("Running EXP-05-C: Mixed Signal Integration...")
    
    # 1. Setup Constraints
    # Define all classes
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
    # 100x100mm Board
    board = Board(width=100.0, height=100.0)
    router = MazeRouter(
        grid_size=(1000, 1000), # 0.1mm cell
        cell_size_mm=0.1,
        num_layers=2,
        design_rules=dr,
        min_clearance=0.1
    )
    
    # 3. Define Components (simplified footprints)
    # Positions:
    # MCU (Left): (20, 50)
    # IGBT (Right): (80, 50)
    # Relay (Top): (50, 80)
    # HV Conn (Top Edge): (50, 95)
    # Power Conn (Bot Right): (80, 20)
    # Sense Conn (Bot Left): (20, 20)
    
    # All on Top Layer (Side 0)
    
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
    
    # Net definitions for block_pads compliance
    netlist = Netlist(components=components, nets=[]) # Empty nets, we route by name manually
    
    pos_arr = jnp.array([c.initial_position for c in components])
    
    print("Blocking obstacles...")
    router.block_pads(components, pos_arr, netlist)
    
    # 4. Routing
    # Order matters? 
    # Usually Critical first (HV, PWR) then Signals.
    
    nets_to_route = [
        ("NET_HV", [c_relay.pins[2], c_hv_conn.pins[0]]),
        ("NET_PWR", [c_pwr_conn.pins[0], c_igbt.pins[2]]), # Segment 1
        ("NET_PWR", [c_igbt.pins[2], c_relay.pins[1]]),    # Segment 2 (IGBT->Relay)
        ("NET_GATE", [c_mcu.pins[0], c_igbt.pins[0]]),
        ("NET_SENSE", [c_igbt.pins[1], c_mcu.pins[1]])
    ]
    
    success_count = 0
    for net_name, pins in nets_to_route:
        # Get absolute positions
        # Note: Pin.absolute_position needs component center etc.
        # But we don't have easy access here unless we map pins back to components.
        # I'll manually compute them.
        
        # HACK: find component for pin
        pts = []
        for p in pins:
            # Find comp
            for c in components:
                if p in c.pins:
                    # found
                    px, py = p.absolute_position(c.initial_position, 0.0, 0)
                    pts.append((px, py))
                    break
        
        start_pt = pts[0]
        end_pt = pts[1]
        
        print(f"Routing {net_name} from {start_pt} to {end_pt}...")
        path = router.route_net_rrr(net_name, [start_pt, end_pt], assignment=None)
        
        if path.success:
            print(f"SUCCESS: {net_name} routed. Len: {len(path.cells)}")
            success_count += 1
        else:
            print(f"FAILURE: {net_name} failed! Reason: {path.failure_reason}")
            
    if success_count == len(nets_to_route):
        print("\nALL NETS ROUTED SUCCESSFULLY!")
    else:
        print(f"\nCompleted {success_count}/{len(nets_to_route)} nets.")

if __name__ == "__main__":
    run_experiment()
