"""
EXP-24: Piantor Keyboard Benchmark - Real-World Open Source PCB Routing

This experiment series benchmarks the router against the Piantor split keyboard,
a real manufactured open-source KiCad project.

Sub-experiments:
  A) Full board routing (all 33 nets)
  B) Keyboard matrix (key switch net subset)
  C) MCU cluster (ProMicro breakout)

Prerequisites:
  Clone Piantor to /tmp: git clone https://github.com/beekeeb/piantor.git /tmp/piantor
"""

import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.deterministic.stages.clearance_grid import ClearanceGridStage
from temper_placer.deterministic.stages.layer_assignment import LayerAssignmentStage
from temper_placer.deterministic.stages.net_ordering import NetOrderingStage
from temper_placer.deterministic.stages.sequential_routing import SequentialRoutingStage
from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.pipeline import DeterministicPipeline

# Piantor PCB paths
PIANTOR_RIGHT = Path("/tmp/piantor/pcb/right/keyboard_pcb.kicad_pcb")
PIANTOR_LEFT = Path("/tmp/piantor/pcb/left/keyboard_pcb.kicad_pcb")


def check_piantor_available():
    """Verify Piantor repo is cloned."""
    if not PIANTOR_RIGHT.exists():
        print("ERROR: Piantor not cloned. Run:")
        print("  git clone https://github.com/beekeeb/piantor.git /tmp/piantor")
        return False
    return True


def run_exp_24a_full_board():
    """
    EXP-24A: Full Board Routing
    
    Route ALL nets on the Piantor Right keyboard, excluding nets that have
    copper pour zones (these are handled by zone fill, not trace routing).
    
    Expected metrics:
    - Completion: 100% (zone nets counted separately)
    - Runtime: < 60 seconds
    """
    print("\n" + "=" * 60)
    print("EXP-24A: Full Board Routing (Piantor Right)")
    print("=" * 60)
    
    if not check_piantor_available():
        return {"status": "SKIP", "reason": "Piantor not cloned"}
    
    # Parse
    start = time.time()
    result = parse_kicad_pcb(PIANTOR_RIGHT)
    parse_time = time.time() - start
    
    print(f"Board: {result.board.width:.0f}x{result.board.height:.0f}mm")
    print(f"Components: {len(result.netlist.components)}")
    print(f"Total nets: {len(result.netlist.nets)}")
    print(f"Parse time: {parse_time:.2f}s")
    
    # Detect zone nets (nets that have copper pour zones in the PCB)
    zone_nets = set()
    for z in result.board.zones:
        # Zone.net_classes contains the net names for this zone
        for net_name in z.net_classes:
            if net_name and net_name != "Signal":  # Skip generic class names
                zone_nets.add(net_name)
    
    print(f"Zone nets (copper pour): {zone_nets}")
    
    # Filter out zone nets from trace routing
    trace_nets = [n for n in result.netlist.nets if n.name not in zone_nets]
    print(f"Nets to trace-route: {len(trace_nets)} (excluding {len(zone_nets)} zone nets)")
    
    # Verify positions
    positioned = [c for c in result.netlist.components if c.initial_position != (0, 0)]
    print(f"Components with positions: {len(positioned)}/{len(result.netlist.components)}")
    
    if len(positioned) < len(result.netlist.components):
        return {"status": "FAIL", "reason": "Missing component positions"}
    
    # Create filtered netlist for trace routing only
    from temper_placer.core.netlist import Netlist
    filtered_netlist = Netlist(
        components=result.netlist.components,
        nets=trace_nets,
    )
    
    state = BoardState(board=result.board, netlist=filtered_netlist)
    pipeline = DeterministicPipeline(stages=[
        ClearanceGridStage(cell_size_mm=0.25, layer_count=2),
        LayerAssignmentStage(),  # Assign nets to layers
        NetOrderingStage(),
        SequentialRoutingStage(),
    ])
    
    # Route
    start = time.time()
    final_state = pipeline.run(state)
    route_time = time.time() - start
    
    # Count successful routes from state.routes dict
    routed_nets = len([r for r in final_state.routes.values() if r])
    trace_total = len(trace_nets)
    zone_total = len(zone_nets)
    
    # Total completion includes zone nets (assumed connected via pour)
    total_routed = routed_nets + zone_total
    grand_total = len(result.netlist.nets)
    completion = (total_routed / grand_total * 100) if grand_total > 0 else 0
    
    print(f"Trace routes: {routed_nets}/{trace_total}")
    print(f"Zone nets (via copper pour): {zone_total}")
    print(f"Total completion: {total_routed}/{grand_total} ({completion:.1f}%)")
    print(f"Route time: {route_time:.1f}s")
    
    status = "PASS" if completion >= 80 else "FAIL"
    print(f"Status: {status}")
    
    return {
        "status": status,
        "completion": completion,
        "trace_routes": routed_nets,
        "zone_nets": zone_total,
        "total": grand_total,
        "time_s": route_time,
    }


def run_exp_A_reversed_order():
    """
    EXPERIMENT A: Reverse Net Order
    
    Scientific Method Test:
    - Hypothesis: Routing /k00 first (instead of last) will allow it to succeed
    - Control: Standard NetOrderingStage puts /k00 at position #32
    - Treatment: Reverse the order so /k00 routes first
    
    Expected outcome: /k00 routes successfully, total routed nets increases from 28 to 29+
    """
    print("\n" + "=" * 60)
    print("EXPERIMENT A: Reversed Net Order")
    print("=" * 60)
    
    if not check_piantor_available():
        return {"status": "SKIP", "reason": "Piantor not cloned"}
    
    from dataclasses import replace as dc_replace
    
    result = parse_kicad_pcb(PIANTOR_RIGHT)
    
    # Detect zone nets
    zone_nets = set()
    for z in result.board.zones:
        for net_name in z.net_classes:
            if net_name and net_name != "Signal":
                zone_nets.add(net_name)
    
    # Filter trace nets
    trace_nets = [n for n in result.netlist.nets if n.name not in zone_nets]
    
    from temper_placer.core.netlist import Netlist
    filtered_netlist = Netlist(
        components=result.netlist.components,
        nets=trace_nets,
    )
    
    state = BoardState(board=result.board, netlist=filtered_netlist)
    
    # Phase 1: Build grid and assign layers
    grid_stage = ClearanceGridStage(cell_size_mm=0.25, layer_count=2)
    layer_stage = LayerAssignmentStage()
    net_stage = NetOrderingStage()
    
    state = grid_stage.run(state)
    state = layer_stage.run(state)
    state = net_stage.run(state)
    
    # TREATMENT: Reverse the net order
    original_order = list(state.net_order)
    reversed_order = tuple(reversed(original_order))
    
    print(f"Original first 5: {original_order[:5]}")
    print(f"Reversed first 5: {list(reversed_order[:5])}")
    print(f"Original /k00 position: {original_order.index('/k00') if '/k00' in original_order else 'N/A'}")
    print(f"Reversed /k00 position: {list(reversed_order).index('/k00') if '/k00' in reversed_order else 'N/A'}")
    
    state = dc_replace(state, net_order=reversed_order)
    
    # Phase 2: Route with reversed order
    routing_stage = SequentialRoutingStage()
    
    start = time.time()
    final_state = routing_stage.run(state)
    route_time = time.time() - start
    
    # Count results
    try:
        routed_nets = len([r for r in final_state.routes.values() if r])
    except AttributeError:
        # routes might be a frozenset
        routed_nets = len(final_state.routes) if final_state.routes else 0
    
    trace_total = len(trace_nets)
    zone_total = len(zone_nets)
    total_routed = routed_nets + zone_total
    grand_total = len(result.netlist.nets)
    completion = (total_routed / grand_total * 100) if grand_total > 0 else 0
    
    print(f"\nRESULTS:")
    print(f"Trace routes: {routed_nets}/{trace_total}")
    print(f"Zone nets: {zone_total}")
    print(f"Total: {total_routed}/{grand_total} ({completion:.1f}%)")
    print(f"Time: {route_time:.1f}s")
    
    # Compare to baseline
    baseline_routed = 28  # From previous experiments
    delta = routed_nets - baseline_routed
    print(f"\nDelta vs baseline: {'+' if delta >= 0 else ''}{delta} nets")
    
    status = "PASS" if routed_nets > baseline_routed else "INCONCLUSIVE" if routed_nets == baseline_routed else "FAIL"
    print(f"Status: {status}")
    
    return {
        "status": status,
        "completion": completion,
        "trace_routes": routed_nets,
        "baseline": baseline_routed,
        "delta": delta,
        "time_s": route_time,
    }


def run_exp_24b_keyboard_matrix():
    """
    EXP-24B: Keyboard Matrix Routing Only
    
    Route only the key switch matrix nets (names starting with /k).
    These are the row/column connections between switch footprints.
    
    Expected metrics:
    - Completion: 100%
    - These are short local routes
    """
    print("\n" + "=" * 60)
    print("EXP-24B: Keyboard Matrix Only")
    print("=" * 60)
    
    if not check_piantor_available():
        return {"status": "SKIP", "reason": "Piantor not cloned"}
    
    result = parse_kicad_pcb(PIANTOR_RIGHT)
    
    # Filter to keyboard matrix nets (start with /k)
    matrix_nets = [n for n in result.netlist.nets if n.name.startswith("/k")]
    print(f"Matrix nets: {len(matrix_nets)} (out of {len(result.netlist.nets)} total)")
    
    # Print sample
    for n in matrix_nets[:5]:
        print(f"  {n.name}: {len(n.pins)} pins")
    
    # Create filtered netlist
    from temper_placer.core.netlist import Netlist
    filtered_netlist = Netlist(
        components=result.netlist.components,
        nets=matrix_nets,
    )
    
    state = BoardState(board=result.board, netlist=filtered_netlist)
    pipeline = DeterministicPipeline(stages=[
        ClearanceGridStage(cell_size_mm=0.25, layer_count=2),
        LayerAssignmentStage(),  # Assign nets to layers
        NetOrderingStage(),
        SequentialRoutingStage(),
    ])
    
    start = time.time()
    final_state = pipeline.run(state)
    route_time = time.time() - start
    
    routes = len(final_state.routes)
    total = len(matrix_nets)
    completion = (routes / total * 100) if total > 0 else 0
    
    print(f"Routes: {routes}/{total} ({completion:.1f}%)")
    print(f"Route time: {route_time:.1f}s")
    
    status = "PASS" if completion >= 90 else "FAIL"
    print(f"Status: {status}")
    
    return {
        "status": status,
        "completion": completion,
        "routes": routes,
        "total": total,
        "time_s": route_time,
    }


def run_exp_24c_power_rails():
    """
    EXP-24C: Power Rail Routing (GND, VCC)
    
    Route only the power/ground nets.
    These are high-fanout nets that stress the star-point algorithm.
    
    Expected metrics:
    - GND has ~60 pins - challenging without copper pour
    - VCC typically has fewer pins
    """
    print("\n" + "=" * 60)
    print("EXP-24C: Power Rails (GND, VCC)")
    print("=" * 60)
    
    if not check_piantor_available():
        return {"status": "SKIP", "reason": "Piantor not cloned"}
    
    result = parse_kicad_pcb(PIANTOR_RIGHT)
    
    # Filter to power nets
    power_nets = [n for n in result.netlist.nets if n.name in ("GND", "VCC", "+5V", "+3V3", "RAW")]
    print(f"Power nets: {len(power_nets)}")
    
    for n in power_nets:
        print(f"  {n.name}: {len(n.pins)} pins")
    
    if not power_nets:
        print("No power nets found")
        return {"status": "SKIP", "reason": "No power nets"}
    
    from temper_placer.core.netlist import Netlist
    filtered_netlist = Netlist(
        components=result.netlist.components,
        nets=power_nets,
    )
    
    state = BoardState(board=result.board, netlist=filtered_netlist)
    pipeline = DeterministicPipeline(stages=[
        ClearanceGridStage(cell_size_mm=0.25, layer_count=2),
        LayerAssignmentStage(),  # Assign nets to layers
        NetOrderingStage(),
        SequentialRoutingStage(),
    ])
    
    start = time.time()
    final_state = pipeline.run(state)
    route_time = time.time() - start
    
    routes = len(final_state.routes)
    total = len(power_nets)
    completion = (routes / total * 100) if total > 0 else 0
    
    print(f"Routes: {routes}/{total} ({completion:.1f}%)")
    print(f"Route time: {route_time:.1f}s")
    
    # Power rails are hard without copper pour - 50% is acceptable
    status = "PASS" if completion >= 50 else "FAIL"
    print(f"Status: {status} (50% threshold for power nets)")
    
    return {
        "status": status,
        "completion": completion,
        "routes": routes,
        "total": total,
        "time_s": route_time,
    }


def main():
    """Run all EXP-24 experiments."""
    print("\n" + "#" * 60)
    print("# EXP-24: PIANTOR KEYBOARD BENCHMARK SERIES")
    print("#" * 60)
    
    results = {}
    results["24A_full_board"] = run_exp_24a_full_board()
    results["24B_keyboard_matrix"] = run_exp_24b_keyboard_matrix()
    results["24C_power_rails"] = run_exp_24c_power_rails()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, r in results.items():
        print(f"  {name}: {r['status']}")
        if r['status'] != "SKIP":
            print(f"    Completion: {r.get('completion', 'N/A'):.1f}%")
    
    return results


if __name__ == "__main__":
    main()
