#!/usr/bin/env python3
"""
Fix placement for better routing of USB and SPI signals.

The current placement has:
- J_USB at bottom (y=5), U_MCU at middle (y=63.75) = 58mm USB signal path
- SPI devices (U_CT, MAX31865) far from U_MCU

This script adjusts positions to reduce critical signal lengths.
"""

import re
import sys
from pathlib import Path


def parse_position(content: str, ref: str) -> tuple[float, float, float] | None:
    """Extract position (x, y, rotation) for a component reference."""
    # Match footprint with reference
    pattern = rf'\(footprint "[^"]*"\s+\(layer "[^"]+"\)\s+\(uuid [^)]+\)\s+\(at ([\d.]+) ([\d.]+)(?: ([\d.]+))?\)'

    # Find the footprint block containing this reference
    fp_pattern = rf'\(footprint "[^"]*"[^)]*\(property "Reference" "{ref}"[^)]*\)'

    # Simpler approach: find (at X Y [R]) after the reference
    ref_pattern = rf'\(property "Reference" "{ref}"[^)]*\).*?\(at ([\d.]+) ([\d.]+)(?: ([\d.]+))?'

    # Actually, let's parse more carefully by finding the footprint block
    for match in re.finditer(rf'\(footprint\s+"[^"]+"\s+\(layer\s+"[^"]+"\)', content):
        start = match.start()
        # Find matching closing paren
        depth = 1
        pos = match.end()
        while depth > 0 and pos < len(content):
            if content[pos] == '(':
                depth += 1
            elif content[pos] == ')':
                depth -= 1
            pos += 1

        block = content[start:pos]
        if f'"Reference" "{ref}"' in block:
            at_match = re.search(r'\(at ([\d.]+) ([\d.]+)(?: ([\d.]+))?\)', block)
            if at_match:
                x = float(at_match.group(1))
                y = float(at_match.group(2))
                r = float(at_match.group(3)) if at_match.group(3) else 0.0
                return (x, y, r)
    return None


def update_position(content: str, ref: str, new_x: float, new_y: float, new_r: float | None = None) -> str:
    """Update the position of a component in the PCB content."""
    # Find the footprint block containing this reference
    for match in re.finditer(rf'\(footprint\s+"[^"]+"\s+\(layer\s+"[^"]+"\)', content):
        start = match.start()
        depth = 1
        pos = match.end()
        while depth > 0 and pos < len(content):
            if content[pos] == '(':
                depth += 1
            elif content[pos] == ')':
                depth -= 1
            pos += 1

        block = content[start:pos]
        if f'"Reference" "{ref}"' in block:
            # Found the block, now update the (at ...) within it
            at_match = re.search(r'\(at ([\d.]+) ([\d.]+)(?: ([\d.]+))?\)', block)
            if at_match:
                old_at = at_match.group(0)
                if new_r is not None:
                    new_at = f"(at {new_x} {new_y} {new_r})"
                elif at_match.group(3):
                    new_at = f"(at {new_x} {new_y} {at_match.group(3)})"
                else:
                    new_at = f"(at {new_x} {new_y})"

                new_block = block.replace(old_at, new_at, 1)
                content = content[:start] + new_block + content[pos:]
                return content

    print(f"Warning: Could not find component {ref}")
    return content


def main():
    if len(sys.argv) < 2:
        print("Usage: python fix_placement.py <input.kicad_pcb> [output.kicad_pcb]")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else input_path.with_stem(input_path.stem + "_fixed")

    content = input_path.read_text()

    # Current positions (from DSN analysis):
    # J_USB: (50, 5) - bottom center
    # U_MCU: (27, 63.75) - middle left
    # U_CT: (33.6, 86.25) - upper middle
    # MAX31865: (12.85, 110) - upper left

    # Strategy:
    # 1. Move U_MCU down and right, closer to USB
    # 2. Move SPI devices (U_CT, MAX31865) closer to new U_MCU position
    # 3. Keep power section (Q1, Q2, etc.) in upper area

    print("Current positions:")
    for ref in ["J_USB", "U_MCU", "U_CT", "MAX31865", "J_DEBUG"]:
        pos = parse_position(content, ref)
        if pos:
            print(f"  {ref}: ({pos[0]:.1f}, {pos[1]:.1f}, rot={pos[2]:.0f})")

    # New positions to reduce signal lengths:
    # Move U_MCU closer to USB (from y=63.75 to y=25)
    # This reduces USB signal length from 58mm to ~20mm

    adjustments = [
        # (ref, new_x, new_y, new_rotation or None)
        ("U_MCU", 40.0, 25.0, None),      # Move MCU down and right, near USB
        ("C_MCU_1", 50.0, 30.0, None),    # Move decoupling caps with MCU
        ("C_MCU_2", 55.0, 30.0, None),
        ("C_MCU_3", 45.0, 30.0, None),
        ("C_MCU_4", 52.5, 30.0, None),
        ("U_CT", 55.0, 45.0, None),       # Move current transformer IC closer to MCU
        ("R_BURDEN", 50.0, 50.0, None),   # Move CT support components
        ("C_CT_FILT", 48.0, 52.0, None),
        ("U_OPAMP_CT", 45.0, 55.0, None),
        ("MAX31865", 30.0, 45.0, None),   # Move temp sensor IC closer to MCU
        ("J_NTC", 25.0, 55.0, None),      # Move NTC connector with MAX31865
    ]

    print("\nApplying adjustments:")
    for ref, new_x, new_y, new_r in adjustments:
        old_pos = parse_position(content, ref)
        if old_pos:
            content = update_position(content, ref, new_x, new_y, new_r)
            print(f"  {ref}: ({old_pos[0]:.1f}, {old_pos[1]:.1f}) -> ({new_x:.1f}, {new_y:.1f})")
        else:
            print(f"  {ref}: NOT FOUND")

    output_path.write_text(content)
    print(f"\nWrote adjusted placement to: {output_path}")

    # Verify new positions
    content = output_path.read_text()
    print("\nNew positions:")
    for ref in ["J_USB", "U_MCU", "U_CT", "MAX31865"]:
        pos = parse_position(content, ref)
        if pos:
            print(f"  {ref}: ({pos[0]:.1f}, {pos[1]:.1f})")


if __name__ == "__main__":
    main()
