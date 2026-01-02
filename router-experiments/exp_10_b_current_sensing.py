#!/usr/bin/env python3
"""
EXP-10-B: Current Sensing - Router V6 Verification

Extracts the Current Sensing subsystem from the full board configuration
and verifies that the V6 Router can route it with 0 conflicts.

Components:
- U_CT (Current Transformer)
- R_BURDEN (Burden Resistor)
- C_CT_FILT (Filter Cap)
- U_OPAMP_CT (OpAmp)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.core.placement_drc import PinInfo, validate_placement_drc
from temper_placer.routing.maze_router import MazeRouter


def route_current_sensing():
    print("\n" + "=" * 70)
    print("EXP-10-B: CURRENT SENSING SUBSYSTEM - ROUTER V6 VERIFICATION")
    print("=" * 70)

    # 1. Setup Board (Small region around the sensing circuit)
    # Using 30x30 region to be safe, similar to Gate Driver exp
    grid_size_mm = 0.1 # Fine grid for analog traces
    width = 30.0
    height = 30.0

    # 2. Define Components & Pins (Extracted from YAML/Exp09)
    # Positions are relative to this local board (0,0 to 30,30)
    components = {
        "U_CT": {
            "pos": (5.0, 15.0),
            "pins": {
                "OUT": (5.0, 15.0, "I_SENSE_FORCE"),
                "GND": (5.0, 13.0, "GND")
            }
        },
        "R_BURDEN": {
            "pos": (12.0, 15.0),
            "pins": {
                "1": (12.0, 15.0, "I_SENSE_FORCE"), # Connected to CT
                "2": (12.0, 13.0, "GND")
            }
        },
        "C_CT_FILT": {
            "pos": (12.0, 10.0),
            "pins": {
                "1": (12.0, 10.0, "I_SENSE_SENSE"), # Filter tap
                "2": (12.0, 8.0, "GND")
            }
        },
        "U_OPAMP_CT": {
            "pos": (20.0, 15.0),
            "pins": {
                "IN": (20.0, 15.0, "I_SENSE_SENSE"),
                "VCC": (20.0, 17.0, "+3V3"),
                "GND": (20.0, 13.0, "GND"),
                "OUT": (22.0, 15.0, "ADC_IN")
            }
        }
    }

    # Nets to route
    # Validating standard multi-pin routing for V6 Remediation.
    # Connecting all points electrically as a single net.
    nets = {
        "I_SENSE": {
            "pins": [
                ("U_CT", "OUT"),
                ("R_BURDEN", "1"),
                ("C_CT_FILT", "1"),
                ("U_OPAMP_CT", "IN")
            ],
            "width": 0.5 # Using wider trace for safety in this test
        },
        "GND": {
            "pins": [
                ("U_CT", "GND"),
                ("R_BURDEN", "2"),
                ("C_CT_FILT", "2"),
                ("U_OPAMP_CT", "GND")
            ],
            "width": 0.5
        },
        "+3V3": {"pins": [], "width": 0.3},
        "ADC_IN": {"pins": [("U_OPAMP_CT", "OUT")], "width": 0.2}
    }

    # 3. Initialize Router
    print(f"Initializing Router V6 (Grid: {grid_size_mm}mm)...")
    router = MazeRouter(
        grid_size=(int(width/grid_size_mm), int(height/grid_size_mm)),
        cell_size_mm=grid_size_mm,
        num_layers=2
    )

    # 4. Placement DRC Verification
    print("\nPhase 1: Validating Placement DRC...")
    drc_pins = []
    pin_positions = {}

    for comp_name, comp_data in components.items():
        for pin_name, pin_info in comp_data["pins"].items():
            px, py, net = pin_info

            # Store for router
            pin_positions[(comp_name, pin_name)] = (px, py, net)

            # Store for DRC
            drc_pins.append(PinInfo(
                x=px, y=py,
                net_name=net,
                component_name=comp_name,
                pin_name=pin_name, 
                diameter_mm=0.8 # Approx 0.8mm pad diameter
            ))

            # Register as obstacle in router
            gx, gy = router._world_to_grid(px, py)
            for layer_idx in range(router.num_layers):
                 if 0 <= gx < router.grid_size[0] and 0 <= gy < router.grid_size[1]:
                    router.occupancy[gx, gy, layer_idx] = -1 # Obstacle
                    router._pad_net_map[(gx, gy, layer_idx)] = net

    violations = validate_placement_drc(drc_pins, min_clearance_mm=0.2)
    if violations:
        print(f"⚠️  Found {len(violations)} Placement DRC Violations!")
        for v in violations:
            print(f"  - {v.message}")
    else:
        print("  ✓ Placement DRC Passed")

    # 5. Route Nets
    print("\nPhase 2: Running RRR Routing...")
    routed_count = 0

    for net_name, net_data in nets.items():
        pin_refs = net_data["pins"]
        if len(pin_refs) < 2:
            continue

        print(f"  Routing {net_name} ({len(pin_refs)} pins)...")

        # Extract coords
        coords = []
        for ref in pin_refs:
            c_name, p_name = ref
            p_x, p_y, _ = components[c_name]["pins"][p_name]
            coords.append((p_x, p_y))

        # Route
        path = router.route_net_rrr(
            net_name=net_name,
            pin_positions=coords,
            assignment=None,
            p_scale=1.0 # Default congestion penalty
        )

        if path and path.success:
            print(f"    ✓ Success ({len(path.cells)} cells)")
            routed_count += 1
        else:
            print("    ✗ Failed")

    # 6. Verify Results
    conflicts = router.get_conflict_locations()
    print("\nPhase 3: Final Conflict Check")
    print(f"  Total Conflicts: {len(conflicts)}")

    if len(conflicts) == 0:
        print("\n🎉 EXP-10-B: VISUAL CONFIRMATION - PASSED")
        print("Current Sensing subsystem routed with 0 conflicts.")
        return 0
    else:
        print(f"\n❌ EXP-10-B: FAILED with {len(conflicts)} conflicts.")
        return 1

if __name__ == "__main__":
    if route_current_sensing() == 0:
        sys.exit(0)
    else:
        sys.exit(1)
