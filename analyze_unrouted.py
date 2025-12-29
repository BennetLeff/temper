#!/usr/bin/env python3
"""
Analyze nets in the temper_gnd_plane.dsn to find the likely unrouted net.
Computes HPWL span for each net based on placement positions.
"""
import re

# Parse DSN content
dsn_path = "pcb/temper_gnd_plane.dsn"
with open(dsn_path) as f:
    content = f.read()

# Extract placements: (place REF X Y side rotation)
placements = {}
place_pattern = r'\(place (\w+) ([\d.]+) ([\d.]+) (\w+) ([\d.]+)\)'
for match in re.finditer(place_pattern, content):
    ref, x, y, side, rot = match.groups()
    placements[ref] = (float(x), float(y))

print(f"Found {len(placements)} component placements")

# Extract nets: (net NAME (pins PIN1 PIN2 ...))
net_pattern = r'\(net (\w+) \(pins ([^)]+)\)\)'
nets = []
for match in re.finditer(net_pattern, content):
    name = match.group(1)
    pins_str = match.group(2)
    pins = pins_str.split()
    nets.append((name, pins))

print(f"Found {len(nets)} nets\n")

# Compute HPWL span for each net
print(f"{'Net':<20} {'Pins':>6} {'Span (mm)':>12} {'Components':<40}")
print("-" * 80)

net_spans = []
for name, pins in nets:
    xs, ys = [], []
    components = set()
    for pin in pins:
        # Pin format: COMP-PIN_NUM
        parts = pin.rsplit('-', 1)
        if len(parts) == 2:
            comp_ref = parts[0]
            if comp_ref in placements:
                x, y = placements[comp_ref]
                # Note: This is component center, not exact pin location
                xs.append(x)
                ys.append(y)
                components.add(comp_ref)
    
    if len(xs) >= 2:
        span = (max(xs) - min(xs)) + (max(ys) - min(ys))
        # Convert from DSN units (10um) to mm
        span_mm = span / 100
    else:
        span_mm = 0
    
    net_spans.append((name, len(pins), span_mm, list(components)))

# Sort by span (longest first)
net_spans.sort(key=lambda x: -x[2])

for name, pin_count, span_mm, comps in net_spans:
    comp_str = ", ".join(sorted(comps)[:5])
    if len(comps) > 5:
        comp_str += "..."
    print(f"{name:<20} {pin_count:>6} {span_mm:>12.1f} {comp_str:<40}")

print("\n" + "=" * 80)
print("TOP 5 LONGEST NETS (most likely to fail routing):")
print("=" * 80)
for i, (name, pin_count, span_mm, comps) in enumerate(net_spans[:5], 1):
    print(f"\n{i}. {name} - {span_mm:.1f}mm span, {pin_count} pins")
    print(f"   Components: {', '.join(sorted(comps))}")
