#!/usr/bin/env python3
"""
Analyze which GND connections are unrouted by comparing DSN net definition
with routed wires in SES file.
"""

import re
from pathlib import Path
from collections import defaultdict

def parse_dsn_placements(dsn_path: Path) -> dict:
    """Extract component positions from DSN."""
    content = dsn_path.read_text()
    placements = {}

    # Find (place COMP X Y ...)
    for match in re.finditer(r'\(place\s+(\S+)\s+([\d.]+)\s+([\d.]+)', content):
        comp, x, y = match.groups()
        placements[comp] = (float(x) / 100, float(y) / 100)  # Convert to mm

    return placements


def parse_gnd_pins(dsn_path: Path) -> list:
    """Extract GND net pins from DSN."""
    content = dsn_path.read_text()

    # Find GND net definition
    match = re.search(r'\(net GND \(pins ([^)]+)\)', content)
    if not match:
        return []

    pins_str = match.group(1)
    return pins_str.split()


def parse_ses_gnd_wires(ses_path: Path) -> list:
    """Extract GND wire endpoints from SES."""
    if not ses_path.exists():
        return []

    content = ses_path.read_text()
    wires = []

    # Find GND net section
    gnd_match = re.search(r'\(net GND(.*?)(?=\(net |\)\s*\)\s*\))', content, re.DOTALL)
    if not gnd_match:
        return []

    gnd_section = gnd_match.group(1)

    # Find all wire paths
    for wire_match in re.finditer(r'\(path\s+\S+\s+[\d.]+\s+([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)\s+([\d.-]+)', gnd_section):
        x1, y1, x2, y2 = map(float, wire_match.groups())
        wires.append(((x1/100, y1/100), (x2/100, y2/100)))  # Convert to mm

    return wires


def find_connected_pins(wires: list, pin_positions: dict, tolerance: float = 1.0) -> set:
    """Find which pins are connected by wires."""
    connected = set()

    # Build set of all wire endpoints
    wire_points = set()
    for (x1, y1), (x2, y2) in wires:
        wire_points.add((round(x1, 1), round(y1, 1)))
        wire_points.add((round(x2, 1), round(y2, 1)))

    # Check which pins have wire endpoints nearby
    for pin, (px, py) in pin_positions.items():
        for wx, wy in wire_points:
            if abs(px - wx) < tolerance and abs(py - wy) < tolerance:
                connected.add(pin)
                break

    return connected


def main():
    dsn_path = Path("pcb/temper_fixed_layers.dsn")
    ses_path = Path("pcb/temper_fixed_layers.ses")

    print("=== GND Connection Analysis ===\n")

    # Get placements and GND pins
    placements = parse_dsn_placements(dsn_path)
    gnd_pins = parse_gnd_pins(dsn_path)

    print(f"GND net has {len(gnd_pins)} pins:")

    # Calculate pin positions
    pin_positions = {}
    for pin_ref in gnd_pins:
        parts = pin_ref.rsplit('-', 1)
        if len(parts) == 2:
            comp, pin_num = parts
            if comp in placements:
                x, y = placements[comp]
                pin_positions[pin_ref] = (x, y)
                print(f"  {pin_ref:20} @ ({x:6.1f}, {y:6.1f}) mm")

    # Sort by Y position to understand vertical distribution
    sorted_pins = sorted(pin_positions.items(), key=lambda x: x[1][1])

    print(f"\n--- Sorted by Y position (bottom to top) ---")
    for pin, (x, y) in sorted_pins:
        print(f"  {pin:20} Y={y:6.1f}mm")

    # Analyze wires
    print(f"\n--- Wire Analysis ---")
    wires = parse_ses_gnd_wires(ses_path)
    print(f"GND has {len(wires)} wire segments")

    if wires:
        # Find Y range of wires
        all_y = []
        for (x1, y1), (x2, y2) in wires:
            all_y.extend([y1, y2])

        print(f"Wire Y range: {min(all_y):.1f} to {max(all_y):.1f} mm")

        # Find gaps in coverage
        pin_ys = [y for _, (_, y) in sorted_pins]
        print(f"Pin Y range: {min(pin_ys):.1f} to {max(pin_ys):.1f} mm")

        # Identify likely unconnected pins (those far from wire endpoints)
        print(f"\n--- Potentially Unconnected Pins ---")
        connected = find_connected_pins(wires, pin_positions, tolerance=2.0)
        unconnected = set(pin_positions.keys()) - connected

        if unconnected:
            for pin in sorted(unconnected, key=lambda p: pin_positions[p][1]):
                x, y = pin_positions[pin]
                print(f"  {pin:20} @ ({x:6.1f}, {y:6.1f}) mm")
        else:
            print("  All pins appear to have nearby wires (may still have routing gaps)")

    # Calculate distances between pins to identify routing challenges
    print(f"\n--- Largest Pin-to-Pin Gaps ---")
    if len(sorted_pins) > 1:
        gaps = []
        for i in range(len(sorted_pins) - 1):
            pin1, (x1, y1) = sorted_pins[i]
            pin2, (x2, y2) = sorted_pins[i + 1]
            gap = y2 - y1
            gaps.append((gap, pin1, pin2, y1, y2))

        gaps.sort(reverse=True)
        for gap, pin1, pin2, y1, y2 in gaps[:5]:
            print(f"  {gap:5.1f}mm gap: {pin1} (Y={y1:.1f}) -> {pin2} (Y={y2:.1f})")


if __name__ == "__main__":
    main()
