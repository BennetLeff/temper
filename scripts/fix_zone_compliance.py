#!/usr/bin/env python3
"""
Quick Manual Placement Fix: Zone Compliance
============================================

Moves components to their correct zones per temper_constraints.yaml:
- control_zone: Y < 70mm
- driver_zone: Y = 70-110mm
- power_zone: Y > 110mm

This tests the hypothesis that proper zone enforcement eliminates routing islands.
"""

import sys
from pathlib import Path
from kiutils.board import Board


def main():
    pcb_path = Path("pcb/temper.kicad_pcb")
    backup_path = Path("pcb/temper_before_zone_fix.kicad_pcb")

    print("=" * 70)
    print(" MANUAL ZONE COMPLIANCE FIX")
    print("=" * 70)

    # Backup original
    import shutil

    shutil.copy(pcb_path, backup_path)
    print(f"\n✓ Backup saved to: {backup_path}")

    # Load board
    board = Board.from_file(str(pcb_path))

    # Define zone-compliant target positions
    # Based on temper_constraints.yaml zones
    fixes = {
        # Control zone (Y < 70mm) - bottom third
        "U_MCU": {"y": 50.0, "reason": "control_zone: Y < 70mm"},
        "C_MCU_1": {"y": 45.0, "reason": "control_zone: near U_MCU"},
        "C_MCU_2": {"y": 55.0, "reason": "control_zone: near U_MCU"},
        "C_MCU_3": {"y": 45.0, "reason": "control_zone: near U_MCU"},
        "C_MCU_4": {"y": 55.0, "reason": "control_zone: near U_MCU"},
        "J_USB": {"y": 30.0, "reason": "control_zone: interface"},
        "J_DEBUG": {"y": 20.0, "reason": "control_zone: interface"},
        "U_LDO_3V3": {"y": 60.0, "reason": "control_zone: power supply"},
        "U_BUCK": {"y": 65.0, "reason": "control_zone: power supply"},
        # Driver zone (Y = 70-110mm) - middle third
        "U_GATE": {"y": 95.0, "reason": "driver_zone: gate driver"},
        "C_BOOT": {"y": 90.0, "reason": "driver_zone: near U_GATE"},
        "C_VCC": {"y": 100.0, "reason": "driver_zone: near U_GATE"},
        "R_GATE_H": {"y": 90.0, "reason": "driver_zone: gate resistor"},
        "R_GATE_L": {"y": 100.0, "reason": "driver_zone: gate resistor"},
        "U_CT": {"y": 80.0, "reason": "driver_zone: current sensor"},
        "U_OPAMP_CT": {"y": 85.0, "reason": "driver_zone: CT amplifier"},
        "R_BURDEN": {"y": 75.0, "reason": "driver_zone: CT burden"},
        "C_CT_FILT": {"y": 80.0, "reason": "driver_zone: CT filter"},
        "MAX31865": {"y": 105.0, "reason": "driver_zone: temp sensor"},
        "U_LDO_5V": {"y": 70.0, "reason": "driver_zone: power supply"},
        "C_BUS1": {"y": 108.0, "reason": "driver_zone: DC bus cap (near boundary)"},
        "C_BUS2": {"y": 108.0, "reason": "driver_zone: DC bus cap (near boundary)"},
        # Power zone (Y > 110mm) - top third
        "Q1": {"y": 120.0, "reason": "power_zone: high-side IGBT"},
        "Q2": {"y": 130.0, "reason": "power_zone: low-side IGBT"},
        "J_COIL": {"y": 140.0, "reason": "power_zone: load connection"},
        # Rectifier diodes - keep in current position (driver zone)
        # D1/D2 are at Y=60-75, which is reasonable for AC input processing
    }

    print("\nApplying zone compliance fixes:")
    moved_count = 0

    for fp in board.footprints:
        ref = fp.properties.get("Reference", None)
        if not ref:
            continue

        ref_str = ref.value if hasattr(ref, "value") else str(ref)

        if ref_str in fixes:
            old_y = fp.position.Y if fp.position else 0
            new_y = fixes[ref_str]["y"]
            reason = fixes[ref_str]["reason"]

            if abs(old_y - new_y) > 0.1:  # Only report significant moves
                print(f"  {ref_str:12s}: Y={old_y:6.1f} → {new_y:6.1f} ({reason})")
                fp.position.Y = new_y
                moved_count += 1

    # Save fixed board
    board.to_file(str(pcb_path))

    print(f"\n✓ Moved {moved_count} components to zone-compliant positions")
    print(f"✓ Updated PCB saved to: {pcb_path}")

    print("\n" + "=" * 70)
    print(" ZONE COMPLIANCE SUMMARY")
    print("=" * 70)

    # Verify zones
    positions = {}
    for fp in board.footprints:
        ref = fp.properties.get("Reference", None)
        if ref:
            ref_str = ref.value if hasattr(ref, "value") else str(ref)
            y = fp.position.Y if fp.position else 0
            positions[ref_str] = y

    control = [r for r, y in positions.items() if y < 70]
    driver = [r for r, y in positions.items() if 70 <= y <= 110]
    power = [r for r, y in positions.items() if y > 110]

    print(f"\nControl zone (Y < 70mm): {len(control)} components")
    print(f"Driver zone (Y 70-110mm): {len(driver)} components")
    print(f"Power zone (Y > 110mm): {len(power)} components")

    print("\n" + "=" * 70)
    print(" NEXT STEPS")
    print("=" * 70)
    print("\n1. Run router test: python3 scripts/run_phase3_router_test.py")
    print("2. Check if routing islands are eliminated")
    print("3. Verify net routing success improves from 72% baseline")
    print(f"\nTo revert: cp {backup_path} {pcb_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
