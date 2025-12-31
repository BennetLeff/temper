"""
EXP-02-E: BGA Concentric Ring Escape Benchmark

Tests escape routing on a realistic BGA pattern with concentric rings.
Uses programmatic netlist creation to avoid PCB parsing issues.
"""

import sys
import time
import numpy as np
import argparse
from pathlib import Path
from kiutils.board import Board as KiBoard
from kiutils.footprint import Footprint, Pad
from kiutils.items.common import Position, Net as KiNet
from kiutils.items.gritems import GrRect

sys.path.append(str(Path(__file__).parent / "packages" / "temper-placer" / "src"))

from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.layer_assignment import assign_layers, Layer, LayerConstraint
from temper_placer.routing.fanout import FanoutGenerator, FanoutConfig
from temper_placer.core.netlist import Netlist, Component, Pin, Net


def create_footprint(ref: str, x: float, y: float, net_name: str) -> Footprint:
    """Create a simple SMD pad footprint."""
    fp = Footprint()
    fp.position = Position(X=str(x), Y=str(y))
    fp.libId = "Test:SMD"
    fp.properties = {"Reference": ref, "Value": "SMD"}

    pad = Pad()
    pad.number = "1"
    pad.position = Position(X="0", Y="0")
    pad.size = Position(X="0.6", Y="0.6")
    pad.type = "smd"
    pad.shape = "circle"
    pad.layers = ["F.Cu", "F.Mask"]
    pad.drill = None
    pad.net = KiNet(name=net_name)
    fp.pads.append(pad)
    return fp


def create_bga_netlist(
    rings: int = 5,
    pitch: float = 1.0,
) -> tuple[Netlist, list[tuple[float, float]]]:
    """Create a netlist with BGA-style concentric ring pins."""
    components = []
    nets = []
    positions = []

    net_counter = 0
    comp_counter = 0

    for ring in range(1, rings + 1):
        radius = ring * pitch
        corners = 4 * ring

        for i in range(corners):
            angle = (i / corners) * 2 * np.pi
            x = radius * np.cos(angle)
            y = radius * np.sin(angle)

            net_counter += 1
            net_name = f"NET_{net_counter:03d}"

            nets.append(Net(name=net_name, pins=[(f"C{comp_counter}", "1")]))

            comp = Component(
                ref=f"C{comp_counter}",
                footprint="BGA",
                bounds=(0.6, 0.6),
                initial_position=(x, y),
                initial_rotation=0,
                pins=[Pin(name="1", position=(0.0, 0.0), number="1")],
            )
            components.append(comp)
            positions.append((x, y))
            comp_counter += 1

    netlist = Netlist(
        components=components,
        nets=nets,
    )

    return netlist, positions


def run_bga_escape_benchmark(
    name: str = "EXP02E_BGA_Escape",
    rings: int = 5,
    pitch: float = 1.0,
    cell_size: float = 0.1,
):
    """Run the BGA escape routing benchmark."""
    cwd = Path(".")
    output_dir = cwd / "router-experiments" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    pcb_path = output_dir / f"{name}_input.kicad_pcb"

    print(f"\n{'=' * 60}")
    print(f"BGA Escape Routing Benchmark: {rings} rings, {pitch}mm pitch")
    print(f"{'=' * 60}")

    print(f"\nCreating netlist with {rings} rings...")
    netlist, positions = create_bga_netlist(rings, pitch)

    num_pads = sum(1 for c in netlist.components)
    print(f"  Created {num_pads} components, {len(netlist.nets)} nets")

    print(f"\nGenerating PCB file...")
    b = KiBoard.create_new()

    nets = []
    footprints = []

    for net in netlist.nets:
        nets.append(KiNet(number=len(nets) + 1, name=net.name))

    for i, comp in enumerate(netlist.components):
        net_name = None
        for net in netlist.nets:
            for comp_ref, pin_name in net.pins:
                if comp_ref == comp.ref:
                    net_name = net.name
                    break
            if net_name:
                break
        if not net_name:
            net_name = "NET_UNCONNECTED"
        fp = create_footprint(comp.ref, positions[i][0], positions[i][1], net_name)
        footprints.append(fp)

    b.nets = nets
    b.footprints = footprints

    boundary = (rings + 2) * pitch + 5
    b.graphicItems.append(
        GrRect(
            start=Position(X=str(-boundary / 2), Y=str(-boundary / 2)),
            end=Position(X=str(boundary / 2), Y=str(boundary / 2)),
            layer="Edge.Cuts",
            width="0.1",
        )
    )

    b.to_file(str(pcb_path))
    print(f"  Saved PCB to {pcb_path}")

    boundary = (rings + 2) * pitch + 5
    b.width = boundary
    b.height = boundary
    b.origin = (0.0, 0.0)

    print(f"\nInitializing Router...")
    router = MazeRouter.from_board(
        b,
        cell_size_mm=cell_size,
        num_layers=4,
        via_cost=5.0,
        min_clearance=0.1,
        wrong_way_penalty=2.0,
        soft_blocking=True,
    )

    pos_array = np.array(positions)
    router.block_pads(netlist.components, pos_array, netlist, clearance=0.1)

    print(f"\nRunning Fanout Generator with Staggered Via Placement...")
    fanout_config = FanoutConfig(
        pitch=pitch,
        via_drill=0.3,
        via_size=0.6,
        trace_width=0.2,
        strategy="staggered",
        via_clearance=0.15,
    )

    fanout_gen = FanoutGenerator(board=b, netlist=netlist, config=fanout_config)
    fanout_positions = fanout_gen.generate_fanouts()

    total_vias = sum(len(v) for v in fanout_positions.values())
    print(f"  Generated {total_vias} fanout vias")

    print(f"\nAssigning Layers...")
    assignments = assign_layers(
        netlist,
        component_positions=pos_array,
    )

    print(f"\nRouting {len(netlist.nets)} nets with RRR...")
    start_time = time.time()

    net_order = [n.name for n in netlist.nets if n.name]

    results = router.rrr_route_all_nets(
        netlist=netlist,
        positions=pos_array,
        net_order=net_order,
        assignments=assignments,
        max_iterations=20,
        p_scale_step=0.5,
        component_margin=0.2,
    )

    duration = time.time() - start_time

    routed_count = sum(1 for r in results.values() if r.success)
    failed_count = len(results) - routed_count

    conflicts = router.get_conflict_locations()

    print(f"\n{'=' * 60}")
    print("BENCHMARK RESULTS")
    print(f"{'=' * 60}")
    print(f"  Total Nets: {len(results)}")
    print(f"  Routed: {routed_count}")
    print(f"  Failed: {failed_count}")
    print(f"  Conflicts: {len(conflicts)}")
    print(f"  Completion: {routed_count / len(results) * 100:.1f}%")
    print(f"  Time: {duration:.2f}s")
    print(f"{'=' * 60}")

    success = (routed_count == len(results)) and (len(conflicts) == 0)
    print(f"  STATUS: {'SUCCESS' if success else 'FAILED'}")

    return {
        "success": success,
        "routed": routed_count,
        "total": len(results),
        "conflicts": len(conflicts),
        "duration": duration,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BGA Escape Routing Benchmark")
    parser.add_argument("--rings", type=int, default=5, help="Number of pin rings")
    parser.add_argument("--pitch", type=float, default=1.0, help="Pin pitch (mm)")
    parser.add_argument("--cell", type=float, default=0.1, help="Router cell size (mm)")
    parser.add_argument("--name", type=str, default="EXP02E_BGA_Escape", help="Experiment name")
    args = parser.parse_args()

    run_bga_escape_benchmark(args.name, args.rings, args.pitch, args.cell)
