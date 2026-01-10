#!/usr/bin/env python3
"""Add power plane zones to KiCad PCB for better routing."""

import re
import sys
import uuid
from pathlib import Path


def generate_tstamp():
    """Generate a KiCad-style timestamp/UUID."""
    return str(uuid.uuid4())


def create_zone(net_num: int, net_name: str, layer: str,
                x1: float, y1: float, x2: float, y2: float,
                priority: int = 0, clearance: float = 0.3,
                min_thickness: float = 0.25) -> str:
    """Create a KiCad zone (copper pour) definition."""
    tstamp = generate_tstamp()

    # Inset the zone slightly from board edge to avoid edge clearance issues
    margin = 0.5
    x1, y1 = x1 + margin, y1 + margin
    x2, y2 = x2 - margin, y2 - margin

    zone = f'''  (zone (net {net_num}) (net_name "{net_name}") (layer "{layer}") (tstamp {tstamp}) (hatch edge 0.5)
    (priority {priority})
    (connect_pads (clearance {clearance}))
    (min_thickness {min_thickness})
    (filled_areas_thickness no)
    (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))
    (polygon
      (pts
        (xy {x1} {y1})
        (xy {x2} {y1})
        (xy {x2} {y2})
        (xy {x1} {y2})
      )
    )
  )
'''
    return zone


def add_power_planes(input_pcb: Path, output_pcb: Path):
    """Add GND and power plane zones to the PCB."""
    content = input_pcb.read_text()

    # Find board dimensions from Edge.Cuts
    edge_match = re.search(r'\(gr_rect \(start ([\d.]+) ([\d.]+)\) \(end ([\d.]+) ([\d.]+)\) \(layer "Edge\.Cuts"\)', content)
    if edge_match:
        x1, y1, x2, y2 = map(float, edge_match.groups())
    else:
        print("Warning: Could not find board outline, using defaults")
        x1, y1, x2, y2 = 0, 0, 100, 150

    print(f"Board dimensions: {x1},{y1} to {x2},{y2}")

    # Find net numbers
    net_nums = {}
    for match in re.finditer(r'\(net (\d+) "([^"]+)"\)', content):
        net_nums[match.group(2)] = int(match.group(1))

    print(f"Found nets: {list(net_nums.keys())}")

    # Create zones for power planes
    zones = []

    # GND plane on In2.Cu (highest priority - fills everywhere GND is needed)
    if "GND" in net_nums:
        zones.append(create_zone(
            net_nums["GND"], "GND", "In2.Cu",
            x1, y1, x2, y2,
            priority=1, clearance=0.3
        ))
        print("Added GND plane on In2.Cu")

    # PGND plane on In2.Cu as well (power ground for half-bridge)
    if "PGND" in net_nums:
        zones.append(create_zone(
            net_nums["PGND"], "PGND", "In2.Cu",
            x1, y1, x2, y2,
            priority=0, clearance=0.3  # Lower priority than GND
        ))
        print("Added PGND plane on In2.Cu")

    # +3V3 plane on In1.Cu (main logic power)
    if "+3V3" in net_nums:
        zones.append(create_zone(
            net_nums["+3V3"], "+3V3", "In1.Cu",
            x1, y1, x2, y2,
            priority=1, clearance=0.3
        ))
        print("Added +3V3 plane on In1.Cu")

    # +5V plane on In1.Cu
    if "+5V" in net_nums:
        zones.append(create_zone(
            net_nums["+5V"], "+5V", "In1.Cu",
            x1, y1, x2, y2,
            priority=0, clearance=0.3
        ))
        print("Added +5V plane on In1.Cu")

    # Insert zones before the closing parenthesis
    # Find the last footprint or segment and insert after
    insert_pos = content.rfind(')')
    if insert_pos > 0:
        content = content[:insert_pos] + '\n' + ''.join(zones) + content[insert_pos:]

    output_pcb.write_text(content)
    print(f"Wrote {output_pcb} with {len(zones)} power plane zones")


def main():
    if len(sys.argv) < 2:
        print("Usage: python add_power_planes.py <input.kicad_pcb> [output.kicad_pcb]")
        sys.exit(1)

    input_pcb = Path(sys.argv[1])
    output_pcb = Path(sys.argv[2]) if len(sys.argv) > 2 else input_pcb.with_stem(input_pcb.stem + "_planes")

    add_power_planes(input_pcb, output_pcb)


if __name__ == "__main__":
    main()
