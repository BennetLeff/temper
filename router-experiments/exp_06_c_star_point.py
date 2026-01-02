
import logging
import sys
import jax.numpy as jnp
import numpy as np
from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.io.config_loader import PlacementConstraints, NetClassRule, constraints_to_design_rules
from temper_placer.routing.maze_router import MazeRouter

logging.basicConfig(level=logging.INFO, format="%(message)s")

def dist(p1, p2):
    return ((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)**0.5

def run_experiment():
    print("Running EXP-06-C: Star Point Topology (Kelvin Sensing)...")
    
    # 1. Constraints
    # We have a Sense Net. But physically, Current Path and Sense Path share the net "NET_I_SENSE"?
    # Usually in schematics, it's one Net.
    # So we have one Net with 3 pins: [Resistor, Load, MCU].
    # Constraints:
    #   Segment (Resistor -> Load): High Power (Width=2.0)
    #   Segment (Resistor -> MCU): Signal (Width=0.2)
    
    # The current router applies ONE rule per Net.
    # This is the core problem!
    # If we mark the net as HighPower, the sense trace will be 2.0mm (too wide for MCU pin).
    # If we mark it as Signal, the load trace will burn.
    
    constraints = PlacementConstraints(
        net_class_rules={
            "Power": NetClassRule(name="Power", trace_width_mm=2.0, clearance_mm=0.5),
            "Signal": NetClassRule(name="Signal", trace_width_mm=0.2, clearance_mm=0.2)
        },
        net_classes={
            "NET_KELVIN": "Power" # Forced to Power for safety?
        }
    )
    dr = constraints_to_design_rules(constraints)

    # 2. Board & Router
    router = MazeRouter(
        grid_size=(100, 100), 
        cell_size_mm=0.1,
        num_layers=2,
        design_rules=dr,
        min_clearance=0.1
    )
    
    # 3. Components
    # R_SENSE (Source): (5.0, 5.0)
    # LOAD (Sink 1): (9.0, 5.0) -> High Current
    # MCU (Sink 2): (5.0, 9.0) -> Low Current (Sense)
    
    c_r = Component(ref="R", footprint="RES", bounds=(1.0,1.0), initial_position=(5.0, 5.0), initial_side=0, 
                    pins=[Pin(name="1", number="1", net="NET_KELVIN", position=(0,0))])
                    
    c_load = Component(ref="LOAD", footprint="CONN", bounds=(1.0,1.0), initial_position=(9.0, 5.0), initial_side=0,
                       pins=[Pin(name="1", number="1", net="NET_KELVIN", position=(0,0))])

    
    c_mcu = Component(ref="MCU", footprint="PIN", bounds=(0.5,0.5), initial_position=(7.0, 9.0), initial_side=0,
                      pins=[Pin(name="1", number="1", net="NET_KELVIN", position=(0,0))])
                      
    components = [c_r, c_load, c_mcu]
    # Define the Net object explicitly so the router finds it
    net_kelvin = Net(name="NET_KELVIN", pins=[("R", "1"), ("LOAD", "1"), ("MCU", "1")])
    netlist = Netlist(components=components, nets=[net_kelvin])
    pos_arr = jnp.array([c.initial_position for c in components])
    
    print("Blocking obstacles...")
    router.block_pads(components, pos_arr, netlist)
    

    # 4. Define Topology Constraints (The Fix)
    # We explicitly define the sub-net edges and start node
    from temper_placer.core.net_graph import NetGraph, SubNetEdge
    
    # Define topology: R.1 is the Star Point
    # Edge 1: R.1 -> LOAD.1 (High Current, Width 2.0)
    # Edge 2: R.1 -> MCU.1 (Signal, Width 0.2)
    
    graph = NetGraph(net_name="NET_KELVIN")
    graph.star_nodes.add("R-1")
    
    graph.edges.append(SubNetEdge(
        source_pin="R-1", 
        sink_pin="LOAD-1",
        trace_width_mm=2.0,
        clearance_mm=0.5,
        priority=10 # Route first
    ))
    
    graph.edges.append(SubNetEdge(
        source_pin="R-1",
        sink_pin="MCU-1",
        trace_width_mm=0.2, # Thin trace!
        clearance_mm=0.2,
        priority=5
    ))
    
    # Inject into Design Rules
    dr.net_topologies["NET_KELVIN"] = graph
    
    print("\nRunning Routing with Topology Constraints...")
    # We need to make sure the router uses this. 
    # Current rrr_route_all_nets doesn't support topology decomposition yet.
    # So we expect this to behave exactly as before (Fail) until we implement the feature.
    
    # To properly test, we need to pass the topology graph to the router or rely on it fetching from DR.
    # The router fetches from DR.
    
    router.occupancy = np.zeros_like(router.occupancy) # Reset occupancy
    router.block_pads(components, pos_arr, netlist)
    
    routes = router.rrr_route_all_nets(netlist, pos_arr, net_order=["NET_KELVIN"], assignments={})
    
    route = routes.get("NET_KELVIN")
    if not route or not route.success:
        print("FAILURE: Topology Routing failed to produce a result.")
        return

    print(f"Route Length: {route.length:.1f}mm")
    
    # Verification
    # Move MCU to (7,9) to test geometric pull
    # R(5,5), Load(9,5). Main Trace y=5.
    # Closest point on Main Trace to MCU(7,9) is (7,5).
    # If overlap allowed, router will tap at (7,5).
    # If disjoint required (Kelvin), router must run separate trace from R(5,5).
    
    # Check if we successfully enforced different constraints
    print(f"\nVerifying Segment Constraints...")
    
    # We can check specific points in the grid
    # (7.0, 5.0) should be occupied by Power Trace (Wide)
    # (7.0, 9.0) should be occupied by Signal Trace (Thin)
    # (7.0, 7.0) ? 
    # If tapped at (7,5), trace goes (7,5)->(7,9). So (7,6), (7,7) occupied.
    # If homerun from (5,5), trace goes (5,5)->(7,9) diagonal? Or (5,5)->(5,9)->(7,9)?
    # If (5,9)->(7,9), then (6,9) occupied.
    
    # Let's see the route difficulty/cost and cell count.
    # A shared route will have fewer "new" cells.
    
    # Ideally, we inspect the ROUTE OBJECT to see explicit segments?
    # But route object is flattened cells.
    
    # Use Grid Inspection
    g_x, g_y = router._world_to_grid(7.0, 5.2) # Just above the power trace center
    occ = router.occupancy[g_x, g_y, 0]
    print(f"Grid (7.0, 5.2): Occupancy={occ}")
    # If Main Trace is 2.0mm wide, it extends y=4.0 to 6.0.
    # So (7.0, 5.2) should be Occupied (2).
    
    # Check (7.0, 5.0) width inflation
    # We can't easily check inflation width from occupancy grid (just 2).
    
    # But we can check if "Overlap" occurred.
    # If separate trace: Area = Area(Main) + Area(Sense).
    # If overlap: Area < sum.
    
    # Main (4mm len * 2mm width) approx 8 sq mm.
    # Sense (4.5mm len * 0.2mm width) approx 0.9 sq mm.
    # Total ~9 sq mm.
    
    # If overlap, Sense is inside Main (mostly). Area ~ 8 sq mm.
    
    num_cells = len(route.cells)
    area = num_cells * (0.1 * 0.1)
    print(f"Total Routed Area: {area:.2f} mm^2")
    
    print(f"Total Route Length: {route.length:.2f}mm")
    
    if route.length > 9.0:
        print("SUCCESS: Route length indicates separate trace (Kelvin connection).")
        print("Star Point topology successfully enforced disjoint paths.")
    else:
        print("FAIL: Route length suggests mid-trace tapping (Shortest geometric path).")

if __name__ == "__main__":
    components = [
        Component("R", "RES", (1.0,1.0), (5.0, 5.0), 0, [Pin("1","1","NET_KELVIN",(0,0))]),
        Component("LOAD", "CONN", (1.0,1.0), (9.0, 5.0), 0, [Pin("1","1","NET_KELVIN",(0,0))]),
        Component("MCU", "PIN", (0.5,0.5), (7.0, 9.0), 0, [Pin("1","1","NET_KELVIN",(0,0))])
    ]
    # Re-run run_experiment with these components if needed, but run_experiment creates its own.
    # We will modify run_experiment to use these coords.
    run_experiment()
