"""
EXP-02-D: QFP-44 Peripheral Routing Benchmark

Tests routing of a QFP-44 package (44 pins on 4 edges) to verify baseline
routing performance when NO escape routing is needed. All pins are on the
perimeter, so direct routing should achieve 100% completion with 0 conflicts.

This benchmark establishes the baseline before testing more complex BGA
escape scenarios in EXP-02-E and EXP-02-F.
"""

import sys
from pathlib import Path
import time

# Ensure imports work
sys.path.append(str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from kiutils.board import Board as KiBoard
from kiutils.footprint import Footprint, Pad
from kiutils.items.common import Position, Net
from kiutils.items.gritems import GrRect

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.layer_assignment import assign_layers, Layer, LayerConstraint


def create_qfp44_footprint(ref: str, x: float, y: float) -> Footprint:
    """Create a QFP-44 (10x10mm body, 0.8mm pitch) footprint.
    
    Pin layout:
    - 11 pins per side
    - 0.8mm pitch  
    - Pins centered on each edge
    """
    fp = Footprint()
    fp.position = Position(X=x, Y=y)
    fp.libId = "Package_QFP:LQFP-44_10x10mm_P0.8mm"
    fp.properties = {"Reference": ref, "Value": "QFP44"}
    fp.pads = []
    
    pitch = 0.8  # mm
    body_size = 10.0  # mm
    
    # Calculate starting offset (center the 11 pins on each edge)
    num_pins_per_side = 11
    total_span = (num_pins_per_side - 1) * pitch
    start_offset = -total_span / 2
    
    pin_number = 1
    
    # Top edge (pins 1-11): Y = +5mm
    for i in range(num_pins_per_side):
        px = start_offset + i * pitch
        py = body_size / 2
        
        pad = Pad()
        pad.number = str(pin_number)
        pad.position = Position(X=px, Y=py)
        pad.size = Position(X=0.4, Y=0.4)
        pad.type = "smd"
        pad.layers = ["F.Cu", "F.Paste", "F.Mask"]
        fp.pads.append(pad)
        pin_number += 1
    
    # Right edge (pins 12-22): X = +5mm
    for i in range(num_pins_per_side):
        px = body_size / 2
        py = -start_offset - i * pitch  # Reverse direction
        
        pad = Pad()
        pad.number = str(pin_number)
        pad.position = Position(X=px, Y=py)
        pad.size = Position(X=0.4, Y=0.4)
        pad.type = "smd"
        pad.layers = ["F.Cu", "F.Paste", "F.Mask"]
        fp.pads.append(pad)
        pin_number += 1
    
    # Bottom edge (pins 23-33): Y = -5mm
    for i in range(num_pins_per_side):
        px = -start_offset - i * pitch  # Reverse direction
        py = -body_size / 2
        
        pad = Pad()
        pad.number = str(pin_number)
        pad.position = Position(X=px, Y=py)
        pad.size = Position(X=0.4, Y=0.4)
        pad.type = "smd"
        pad.layers = ["F.Cu", "F.Paste", "F.Mask"]
        fp.pads.append(pad)
        pin_number += 1
    
    # Left edge (pins 34-44): X = -5mm
    for i in range(num_pins_per_side):
        px = -body_size / 2
        py = start_offset + i * pitch
        
        pad = Pad()
        pad.number = str(pin_number)
        pad.position = Position(X=px, Y=py)
        pad.size = Position(X=0.4, Y=0.4)
        pad.type = "smd"
        pad.layers = ["F.Cu", "F.Paste", "F.Mask"]
        fp.pads.append(pad)
        pin_number += 1
    
    return fp


def create_test_pcb(output_path: str):
    """Create a test PCB with QFP-44 and test nets."""
    board = KiBoard()
    board.general.thickness = 1.6
    
    # Board outline (60x60mm)
    board.graphicItems = [
        GrRect(start=Position(X=0, Y=0), end=Position(X=60, Y=60), layer="Edge.Cuts", width=0.1)
    ]
    
    # Create QFP-44 at center
    qfp = create_qfp44_footprint("U1", x=30.0, y=30.0)
    board.footprints = [qfp]
    
    # Create nets
    nets = []
    net_code = 1
    
    # Cross-chip horizontal nets (top to bottom)
    for i in range(1, 12):
        opposite_pin = i + 22
        net = Net(number=net_code, name=f"NET_CROSS_H{i}")
        nets.append(net)
        
        # Assign net to pads
        qfp.pads[i-1].net = net
        qfp.pads[opposite_pin-1].net = net
        net_code += 1
    
    # Cross-chip vertical nets (left to right)
    for i in range(11):
        left_pin = 34 + i
        right_pin = 12 + i
        net = Net(number=net_code, name=f"NET_CROSS_V{i+1}")
        nets.append(net)
        
        qfp.pads[left_pin-1].net = net
        qfp.pads[right_pin-1].net = net
        net_code += 1
    
    # Diagonal nets
    net = Net(number=net_code, name="NET_DIAG_1")
    nets.append(net)
    qfp.pads[0].net = net  # Pin 1
    qfp.pads[32].net = net  # Pin 33
    net_code += 1
    
    net = Net(number=net_code, name="NET_DIAG_2")
    nets.append(net)
    qfp.pads[10].net = net  # Pin 11
    qfp.pads[22].net = net  # Pin 23
    net_code += 1
    
    board.nets = nets
    
    # Save
    board.to_file(output_path)
    return output_path


def run_experiment():
    """Run QFP-44 routing experiment."""
    print("=" * 80)
    print("EXP-02-D: QFP-44 Peripheral Routing Benchmark")
    print("=" * 80)
    print("")
    
    # Create test PCB
    print("Creating QFP-44 test PCB...")
    pcb_path = "/tmp/exp_02_d_qfp44.kicad_pcb"
    create_test_pcb(pcb_path)
    print(f"  - PCB created: {pcb_path}")
    print(f"  - Component: U1 (QFP-44, 44 pins)")
    print(f"  - Nets: 24 total")
    print(f"    - Cross-chip horizontal: 11")
    print(f"    - Cross-chip vertical: 11")
    print(f"    - Diagonal: 2")
    print("")
    
    # Parse PCB
    print("Parsing PCB...")
    board, netlist = parse_kicad_pcb(pcb_path)
    print(f"  - Board size: {board.width}mm x {board.height}mm")
    print(f"  - Components: {len(netlist.components)}")
    print(f"  - Nets: {len(netlist.nets)}")
    print("")
    
    # Create router
    print("Initializing 4-layer MazeRouter...")
    router = MazeRouter.from_board(
        board,
        cell_size_mm=0.5,
        num_layers=4,
        via_cost=2.0,
        soft_blocking=True,
        min_clearance=0.2,
        wrong_way_penalty=2.0,
        strict_mode=False
    )
    print(f"  - Grid size: {router.grid_size}")
    print(f"  - Cell size: {router.cell_size}mm")
    print("")
    
    # Layer assignment
    print("Assigning layers (Manhattan topology)...")
    constraints = [
        LayerConstraint(
            net_pattern="NET_CROSS_H.*",
            allowed_layers={Layer.L1_TOP},
            preferred_layer=Layer.L1_TOP,
            reason="Horizontal nets on top"
        ),
        LayerConstraint(
            net_pattern="NET_CROSS_V.*",
            allowed_layers={Layer.L4_BOT},
            preferred_layer=Layer.L4_BOT,
            reason="Vertical nets on bottom"
        ),
        LayerConstraint(
            net_pattern="NET_DIAG.*",
            allowed_layers={Layer.L1_TOP, Layer.L2_GND, Layer.L3_PWR, Layer.L4_BOT},
            preferred_layer=Layer.L2_GND,
            reason="Diagonal nets on inner layers"
        ),
    ]
    
    assignments_list = assign_layers(netlist, constraints)
    assignments = {a.net: a for a in assignments_list}
    
    for a in assignments_list[:5]:
        print(f"  - {a.net}: {a.primary_layer.name}")
    print(f"  ... ({len(assignments_list)} total)")
    print("")
    
    # Route
    print("Routing nets with RRR...")
    start_time = time.perf_counter()
    
    net_order = [net.name for net in netlist.nets]
    routed_paths = router.rrr_route_all_nets(
        netlist=netlist,
        positions=board.component_positions,
        net_order=net_order,
        assignments=assignments,
        max_iterations=5,
        p_scale_start=1.0,
        p_scale_step=2.0,
        incremental=True
    )
    
    route_time = time.perf_counter() - start_time
    
    print("")
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    
    # Analyze
    total_nets = len(routed_paths)
    successful = sum(1 for p in routed_paths.values() if p.success)
    failed = total_nets - successful
    total_vias = sum(p.via_count for p in routed_paths.values())
    
    print(f"Routing Time: {route_time:.2f}s")
    print(f"Routing Completion: {successful}/{total_nets} ({100*successful/total_nets:.1f}%)")
    print(f"Failed Nets: {failed}")
    print(f"Total Vias: {total_vias}")
    print("")
    
    # Conflicts
    conflicts = router.get_conflict_locations()
    print(f"Conflicts: {len(conflicts)}")
    
    if conflicts:
        print("\nConflict Details (first 10):")
        for conf in conflicts[:10]:
            print(f"  - ({conf['x']}, {conf['y']}, L{conf['layer']+1}): {', '.join(conf['nets'])}")
    
    print("")
    print("=" * 80)
    print("EXPECTED OUTCOME")
    print("=" * 80)
    print("For QFP-44 (peripheral pins only):")
    print("  ✓ Routing completion: 100%")
    print("  ✓ Conflicts: 0")
    print("  ✓ All pins directly accessible")
    print("")
    
    if successful == total_nets and len(conflicts) == 0:
        print("✅ BENCHMARK PASSED: QFP-44 routed successfully!")
        return 0
    else:
        print("❌ BENCHMARK FAILED")
        if failed > 0:
            print(f"  - {failed} nets failed to route")
        if len(conflicts) > 0:
            print(f"  - {len(conflicts)} conflicts detected")
        return 1


if __name__ == "__main__":
    sys.exit(run_experiment())
