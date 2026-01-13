#!/usr/bin/env python3
"""Demo script showing ConstraintBuilder fluent API.

This demonstrates how AI agents can programmatically create constraints
using the fluent Python API instead of writing YAML.
"""

from temper_placer.constraints import ConstraintBuilder


def main():
    """Build constraints programmatically."""

    print("=== Building Constraints with Fluent API ===\n")

    # Build a complete set of constraints for a power electronics board
    constraints = (
        ConstraintBuilder()
        # Hard thermal isolation between high-power MOSFETs
        .add_spacing("Q1", "Q2", 15.0, tier="hard", description="Thermal isolation between MOSFETs")
        # Soft spacing preference between regulators
        .add_spacing(
            "U_15V", "U_3V3", 10.0, tier="soft", description="Prefer spacing between regulators"
        )
        # Hard proximity: gate driver must be close to MOSFET
        .add_proximity(
            "U_GATE",
            "Q1",
            8.0,
            tier="hard",
            description="Minimize gate drive loop",
            group_name="gate_drive",
        )
        .add_proximity("U_GATE", "Q2", 8.0, tier="hard", group_name="gate_drive")
        # MCU needs escape routing clearance
        .add_escape_clearance(
            "U_MCU",
            10.0,
            priority_sides=["bottom", "right"],
            tier="hard",
            description="QFN-56 pin escape routing",
        )
        # USB differential pair needs clear path
        .add_routing_corridor(
            "usb_path",
            "J_USB",
            "U_MCU",
            width_mm=6.0,
            keep_clear=True,
            nets=["USB_D+", "USB_D-"],
            tier="hard",
        )
        # High-power components prefer board edge for cooling
        .add_thermal_constraint(["Q1", "Q2"], prefer_edge=True, max_distance_from_edge_mm=20.0)
        # MCU subsystem should stay together
        .add_group(
            "mcu_subsystem",
            ["U_MCU", "Y1", "C_MCU_1", "C_MCU_2"],
            max_spread_mm=25.0,
            zone="MCU",
            description="Keep MCU circuitry compact",
        )
        .build()
    )

    print("✅ Created constraints with fluent API\n")

    # Show summary
    print("Summary:")
    print(f"  - {len(constraints.component_spacing_rules)} spacing rules")
    print(f"  - {len(constraints.component_groups)} component groups")
    print(f"  - {len(constraints.escape_clearances)} escape clearances")
    print(f"  - {len(constraints.routing_corridors)} routing corridors")
    print(f"  - {len(constraints.thermal_constraints)} thermal constraints")
    print()

    # Validate against component list
    print("=== Validation ===\n")
    components = [
        "Q1",
        "Q2",
        "U_GATE",
        "U_MCU",
        "J_USB",
        "U_15V",
        "U_3V3",
        "Y1",
        "C_MCU_1",
        "C_MCU_2",
        "C_BOOT",
    ]
    zones = ["HV", "Power", "Signal", "MCU"]

    builder = ConstraintBuilder(constraints)
    errors = builder.validate(
        board_width=100.0,
        board_height=150.0,
        available_components=components,
        available_zones=zones,
    )

    if errors:
        print("❌ Validation errors:")
        for err in errors:
            print(f"   - {err}")
    else:
        print("✅ All constraints validated successfully")
    print()

    # Export to YAML
    print("=== YAML Export ===\n")
    yaml_str = builder.to_yaml()
    print(yaml_str)

    # Show how to use with compiler and reporter
    print("=== Usage with Compiler & Reporter ===\n")
    print("```python")
    print("from temper_placer.constraints import ConstraintCompiler, ConstraintReporter")
    print()
    print("# Compile to filter/scorer")
    print("compiler = ConstraintCompiler(constraints)")
    print("filter_fn = compiler.compile_to_slot_filter()")
    print("scorer_fn = compiler.compile_to_slot_scorer()")
    print()
    print("# Run placement (hypothetical)")
    print("placements = run_placement(netlist, filter_fn, scorer_fn)")
    print()
    print("# Check constraints")
    print("reporter = ConstraintReporter(constraints, board_bounds)")
    print("report = reporter.check(placements)")
    print("print(report.to_text())")
    print("```")


if __name__ == "__main__":
    main()
