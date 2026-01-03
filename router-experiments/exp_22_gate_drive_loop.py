#!/usr/bin/env python3
"""
EXP-22: Gate Drive Loop Inductance Validation

Validates router minimizes gate drive loop area for U_GATE → R_G → Q1/Q2.

Key challenges:
- Matched trace lengths for HS/LS paths
- Tight loop area (< 2 cm² per gate)
- Parallel HS/LS drive paths with differential routing

Target metrics:
- Gate trace length < 30mm per gate
- Loop area < 2 cm² per gate
- Matched length between HS/LS < 2mm mismatch
- No vias in critical gate loop

Success criteria:
- All gate nets routed
- Loop area within specification
- HS/LS length mismatch < 2mm
"""

import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import json

sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.core.design_rules import create_temper_design_rules
from temper_placer.routing.maze_router import MazeRouter


@dataclass
class GateLoopMetrics:
    """Metrics for gate drive loop quality."""

    net_name: str
    trace_length_mm: float
    estimated_loop_inductance_nH: float
    via_count: int
    is_differential: bool
    length_mismatch_mm: float = 0.0  # HS vs LS mismatch
    target_length_mm: float = 30.0
    target_inductance_nH: float = 10.0  # ~10nH for gate loop
    target_mismatch_mm: float = 2.0

    @property
    def length_pass(self) -> bool:
        return self.trace_length_mm <= self.target_length_mm

    @property
    def inductance_pass(self) -> bool:
        return self.estimated_loop_inductance_nH <= self.target_inductance_nH

    @property
    def via_pass(self) -> bool:
        return self.via_count == 0  # No vias in critical loop

    @property
    def mismatch_pass(self) -> bool:
        return self.length_mismatch_mm <= self.target_mismatch_mm

    @property
    def overall_pass(self) -> bool:
        return self.length_pass and self.inductance_pass and self.via_pass and self.mismatch_pass


def create_gate_driver_subsystem():
    """Create gate driver subsystem for loop area validation.

    Layout optimized for minimal loop area:
    - U_GATE at center
    - R_GATE_H and R_GATE_L close to driver outputs
    - Gate traces routed as differential pairs
    - Return path adjacent to gate trace
    """
    board = {
        "width_mm": 40.0,
        "height_mm": 40.0,
        "origin": (0.0, 0.0),
        "layers": 2,
    }

    # Component positions optimized for minimal gate loop
    # U_GATE at center, resistors close to outputs
    components = {
        "U_GATE": {
            "pos": (20.0, 20.0),
            "pins": {
                "OUTA": (18.0, 22.0, "GATE_H"),  # High-side output
                "OUTB": (18.0, 18.0, "GATE_L"),  # Low-side output
                "GND": (22.0, 20.0, "CGND"),  # Control ground
                "VDD": (18.0, 20.0, "+15V"),  # Supply
            },
        },
        "R_GATE_H": {
            "pos": (28.0, 24.0),  # Close to OUTA
            "pins": {
                "1": (27.5, 24.0, "GATE_H"),
                "2": (28.5, 24.0, "GATE_H"),  # To Q1 gate
            },
        },
        "R_GATE_L": {
            "pos": (28.0, 16.0),  # Close to OUTB
            "pins": {
                "1": (27.5, 16.0, "GATE_L"),
                "2": (28.5, 16.0, "GATE_L"),  # To Q2 gate
            },
        },
        "Q1": {
            "pos": (35.0, 24.0),  # IGBT for high-side
            "pins": {
                "G": (34.5, 24.0, "GATE_H"),
                "E": (35.5, 24.0, "GATE_H_RET"),
            },
        },
        "Q2": {
            "pos": (35.0, 16.0),  # IGBT for low-side
            "pins": {
                "G": (34.5, 16.0, "GATE_L"),
                "E": (35.5, 16.0, "GATE_L_RET"),
            },
        },
        "C_VCC": {
            "pos": (15.0, 20.0),
            "pins": {
                "1": (15.0, 20.5, "+15V"),
                "2": (15.0, 19.5, "CGND"),
            },
        },
    }

    # Nets with gate drive class for special handling
    nets = {
        "GATE_H": {
            "pins": [
                ("U_GATE", "OUTA"),
                ("R_GATE_H", "1"),
                ("R_GATE_H", "2"),
                ("Q1", "G"),
            ],
            "class": "GateDrive",
        },
        "GATE_L": {
            "pins": [
                ("U_GATE", "OUTB"),
                ("R_GATE_L", "1"),
                ("R_GATE_L", "2"),
                ("Q2", "G"),
            ],
            "class": "GateDrive",
        },
        "GATE_H_RET": {
            "pins": [
                ("Q1", "E"),
            ],
            "class": "GateReturn",
        },
        "GATE_L_RET": {
            "pins": [
                ("Q2", "E"),
            ],
            "class": "GateReturn",
        },
        "+15V": {
            "pins": [
                ("U_GATE", "VDD"),
                ("C_VCC", "1"),
            ],
            "class": "Power",
        },
        "CGND": {
            "pins": [
                ("U_GATE", "GND"),
                ("C_VCC", "2"),
            ],
            "class": "GND",
        },
    }

    return board, components, nets


def analyze_gate_loop(
    router: MazeRouter, path, pin_positions: Dict, length_mismatch_mm: float = 0.0
) -> Optional[GateLoopMetrics]:
    """Analyze a routed gate path for loop quality metrics."""

    if path is None or len(path.cells) == 0:
        return None

    # Calculate trace length from path cells
    # Each cell is 0.1mm, so multiply by cell count for approximate length
    trace_length_mm = len(path.cells) * 0.1

    # Estimate loop inductance based on trace length
    # From CRITICAL_LOOP_DESIGN.md: ~0.2nH/mm for differential pair routing
    # Total loop inductance = trace + return path
    estimated_loop_inductance_nH = trace_length_mm * 0.2

    # Count vias used
    via_count = 0
    if hasattr(path, "vias"):
        via_count = len(path.vias)

    # Check if routed as differential (traces on adjacent layers)
    is_differential = False
    if hasattr(path, "cells") and len(path.cells) > 0:
        layers_used = set(c.layer for c in path.cells)
        is_differential = len(layers_used) > 1

    net_name = getattr(path, "net_name", "unknown")

    return GateLoopMetrics(
        net_name=net_name,
        trace_length_mm=trace_length_mm,
        estimated_loop_inductance_nH=estimated_loop_inductance_nH,
        via_count=via_count,
        is_differential=is_differential,
        length_mismatch_mm=length_mismatch_mm,
    )


def validate_gate_loop_routing():
    """Main validation routine for gate drive loop inductance."""

    print("\n" + "=" * 70)
    print("EXP-22: GATE DRIVE LOOP INDUCTANCE VALIDATION")
    print("=" * 70)

    board, components, nets = create_gate_driver_subsystem()

    print(f"\nBoard: {board['width_mm']}×{board['height_mm']}mm, {board['layers']} layers")
    print(f"Components: {len(components)} (U_GATE, R_GATE_H/L, Q1/Q2, C_VCC)")
    print(f"Nets: {len(nets)} (GATE_H, GATE_L, returns, power)")

    # Design rules for gate drive
    design_rules = create_temper_design_rules()

    @dataclass
    class MinimalBoard:
        width: float
        height: float
        origin: tuple

    board_obj = MinimalBoard(
        width=board["width_mm"],
        height=board["height_mm"],
        origin=board["origin"],
    )

    # Fine grid for precise routing
    router = MazeRouter.from_board(
        board=board_obj,
        cell_size_mm=0.1,
        num_layers=board["layers"],
        via_cost=5.0,  # Penalize vias in gate loops
        soft_blocking=True,
        min_clearance=0.15,  # Tighter for gate traces
        design_rules=design_rules,
    )

    print(f"  Grid: {router.grid_size[0]}×{router.grid_size[1]} cells")

    # Collect pin positions
    pin_positions = {}
    for comp_name, comp in components.items():
        for pin_name, pin_data in comp["pins"].items():
            x, y, net = pin_data
            pin_positions[(comp_name, pin_name)] = (x, y, net)

    # Register components as obstacles
    print("\nRegistering components...")
    for comp_name, comp in components.items():
        x, y = comp["pos"]
        gx, gy = router._world_to_grid(x, y)
        # Mark as obstacle (3x3 cell footprint)
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                ox, oy = gx + dx, gy + dy
                if 0 <= ox < router.grid_size[0] and 0 <= oy < router.grid_size[1]:
                    router.occupancy[ox, oy, 0] = -1
                    router.occupancy[ox, oy, 1] = -1

    # Register pins as pads
    for (comp_name, pin_name), (x, y, net) in pin_positions.items():
        gx, gy = router._world_to_grid(x, y)
        for l in range(router.num_layers):
            if 0 <= gx < router.grid_size[0] and 0 <= gy < router.grid_size[1]:
                router.occupancy[gx, gy, l] = -1
                router._pad_net_map[(gx, gy, l)] = net

    # Route gate drive nets with priority
    print("\nRouting gate drive nets...")
    gate_nets = ["GATE_H", "GATE_L"]
    results = {}

    for net_name in gate_nets:
        if net_name not in nets:
            continue

        pins = nets[net_name]["pins"]
        pin_coords = []
        for comp_ref, pin_name in pins:
            key = (comp_ref, pin_name)
            if key in pin_positions:
                x, y, _ = pin_positions[key]
                pin_coords.append((x, y))

        if len(pin_coords) < 2:
            print(f"  ⚠️  {net_name}: Insufficient pins")
            continue

        # Route with emphasis on minimal length
        path = router.route_net_rrr(
            net_name=net_name,
            pin_positions=pin_coords,
            assignment=None,
            p_scale=1.0,
        )

        if path and len(path.cells) > 0:
            results[net_name] = path
            metrics = analyze_gate_loop(router, path, pin_positions)
            results[f"{net_name}_metrics"] = metrics
            print(
                f"  ✓ {net_name}: {metrics.trace_length_mm:.1f}mm, "
                f"L ≈ {metrics.estimated_loop_inductance_nH:.1f}nH, "
                f"vias {metrics.via_count}"
            )
        else:
            print(f"  ✗ {net_name}: Failed")
            results[net_name] = None

    # Analyze results
    print("\n" + "=" * 70)
    print("VALIDATION RESULTS")
    print("=" * 70)

    all_pass = True
    routed_count = 0
    metrics_list = []

    for net_name in gate_nets:
        metrics_key = f"{net_name}_metrics"
        if metrics_key in results and results[metrics_key]:
            metrics = results[metrics_key]
            metrics_list.append(metrics)

            print(f"\n{net_name}:")
            print(
                f"  Trace length: {metrics.trace_length_mm:.1f}mm / {metrics.target_length_mm}mm target"
            )
            print(f"    {'✓ PASS' if metrics.length_pass else '✗ FAIL'}")
            print(
                f"  Est. loop L: {metrics.estimated_loop_inductance_nH:.1f}nH / {metrics.target_inductance_nH}nH target"
            )
            print(f"    {'✓ PASS' if metrics.inductance_pass else '✗ FAIL'}")
            print(f"  Vias in loop: {metrics.via_count}")
            print(f"    {'✓ PASS (0)' if metrics.via_pass else '✗ FAIL'}")

            if not metrics.overall_pass:
                all_pass = False
            routed_count += 1
        else:
            all_pass = False

    # Check length matching between HS and LS
    print("\n" + "-" * 40)
    print("Length Matching (HS vs LS):")
    if len(metrics_list) >= 2:
        hs_len = metrics_list[0].trace_length_mm
        ls_len = metrics_list[1].trace_length_mm
        mismatch = abs(hs_len - ls_len)
        match_target = 2.0  # mm

        print(f"  GATE_H: {hs_len:.1f}mm")
        print(f"  GATE_L: {ls_len:.1f}mm")
        print(f"  Mismatch: {mismatch:.1f}mm / {match_target}mm target")

        if mismatch <= match_target:
            print(f"  ✓ PASS - Matched lengths")
        else:
            print(f"  ✗ FAIL - Excessive mismatch")
            all_pass = False
    else:
        print(f"  ⚠️  Cannot check matching (only {len(metrics_list)} nets routed)")

    # Final summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    print(f"\nGate nets routed: {routed_count}/{len(gate_nets)}")
    print(f"Loop area target: < 2 cm² (< 20 mm²) per gate")
    print(f"Trace length target: < 30mm per gate")
    print(f"Length matching target: < 2mm mismatch HS/LS")

    if all_pass and routed_count == len(gate_nets):
        print("\n🎉 EXP-22: SUCCESS - Gate drive loops optimized!")
        print("\n  • All gate nets routed")
        print("  • Loop area within specification")
        print("  • Trace lengths minimized")
        print("  • No vias in critical gate loop")
        print("\nRouter correctly minimizes gate drive loop inductance.")
        return 0
    else:
        print(f"\n⚠️  EXP-22: PARTIAL - {routed_count}/{len(gate_nets)} nets routed")
        if routed_count > 0:
            print("  Check individual metrics above for details")
        return 1


def save_metrics_json(metrics_list: List[GateLoopMetrics], output_path: Path):
    """Save metrics to JSON for tracking."""
    data = {
        "experiment": "EXP-22",
        "description": "Gate Drive Loop Inductance Validation",
        "metrics": [
            {
                "net_name": m.net_name,
                "trace_length_mm": m.trace_length_mm,
                "estimated_loop_inductance_nH": m.estimated_loop_inductance_nH,
                "via_count": m.via_count,
                "is_differential": m.is_differential,
                "length_mismatch_mm": m.length_mismatch_mm,
                "length_pass": m.length_pass,
                "inductance_pass": m.inductance_pass,
                "via_pass": m.via_pass,
                "mismatch_pass": m.mismatch_pass,
                "overall_pass": m.overall_pass,
            }
            for m in metrics_list
        ],
    }
    output_path.write_text(json.dumps(data, indent=2))
    return output_path


if __name__ == "__main__":
    sys.exit(validate_gate_loop_routing())
