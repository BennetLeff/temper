#!/usr/bin/env python3
"""Demo script showing constraint satisfaction reporting.

This demonstrates how to use ConstraintReporter to check placements
and generate human-readable reports.
"""

from temper_placer.constraints import ConstraintReporter
from temper_placer.io.config_loader import (
    ComponentGroup,
    ComponentSpacingRule,
    EscapeClearance,
    PlacementConstraints,
    ProximityRule,
    RoutingCorridor,
)


def main():
    """Run constraint reporting demo."""

    # Define constraints
    constraints = PlacementConstraints(
        component_spacing_rules=[
            ComponentSpacingRule(
                component_a="Q1",
                component_b="Q2",
                min_separation_mm=15.0,
                tier="hard",
                description="Thermal isolation between MOSFETs",
            ),
            ComponentSpacingRule(
                component_a="U_15V",
                component_b="U_3V3",
                min_separation_mm=10.0,
                tier="soft",
                description="Prefer spacing between regulators",
            ),
        ],
        component_groups=[
            ComponentGroup(
                name="gate_drive",
                components=["U_GATE", "Q1", "Q2"],
                max_spread_mm=30.0,
                proximity_rules=[
                    ProximityRule(
                        component_a="U_GATE",
                        component_b="Q1",
                        max_distance_mm=8.0,
                        tier="hard",
                        description="Gate driver close to MOSFET",
                    ),
                ],
            ),
        ],
        escape_clearances=[
            EscapeClearance(
                component="U_MCU",
                clearance_mm=10.0,
                tier="hard",
                description="Keep escape zone clear for routing",
            ),
        ],
        routing_corridors=[
            RoutingCorridor(
                name="usb_path",
                from_component="J_USB",
                to_component="U_MCU",
                width_mm=6.0,  # allow-safety-constant: demo clearance
                keep_clear=True,
                tier="hard",
            ),
        ],
    )

    # Example placement with mixed violations
    placements = {
        # Power switches - violates hard spacing (12mm < 15mm)
        "Q1": (10.0, 50.0),
        "Q2": (22.0, 50.0),  # Only 12mm apart
        # Regulators - violates soft spacing (5mm < 10mm)
        "U_15V": (40.0, 30.0),
        "U_3V3": (45.0, 30.0),  # Only 5mm apart
        # Gate driver - satisfies hard proximity (7mm < 8mm)
        "U_GATE": (17.0, 50.0),  # 7mm from Q1
        # MCU and USB - violates hard escape clearance
        "U_MCU": (80.0, 50.0),
        "J_USB": (20.0, 80.0),
        "C1": (85.0, 50.0),  # Only 5mm from MCU (violates escape)
        # Component in USB path - violates hard corridor
        "R1": (50.0, 65.0),  # Close to USB->MCU path
    }

    board_bounds = (0.0, 0.0, 100.0, 100.0)

    # Create reporter and check constraints
    reporter = ConstraintReporter(constraints, board_bounds)
    report = reporter.check(placements)

    # Print text report
    print(report.to_text())
    print()

    # Print JSON summary
    print("JSON Summary:")
    import json

    data = json.loads(report.to_json())
    print(json.dumps(data["summary"], indent=2))
    print()

    # Check for violations that should fail CI
    if report.has_violations():
        print(f"❌ FAIL: {len(report.violations)} hard constraint violation(s)")
        for v in report.violations:
            print(f"   - {v.message}")
        return 1
    else:
        print("✅ PASS: All hard constraints satisfied")
        return 0


if __name__ == "__main__":
    exit(main())
