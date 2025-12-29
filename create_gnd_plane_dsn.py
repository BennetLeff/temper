#!/usr/bin/env python3
"""Create GND-excluded DSN file from temper_fixed_layers.dsn"""
import re
from pathlib import Path

# Read source DSN
src = Path("pcb/temper_fixed_layers.dsn")
content = src.read_text()

# Remove (net GND ...) pattern - this is a nested structure so we need to be careful
# The pattern is: (net GND (pins ...))
gnd_pattern = r'\(net GND \(pins [^)]+\)\)'
content_no_gnd = re.sub(gnd_pattern, '', content)

# Also remove GND from the power class list if present
# The class line will look like: (class power VCC_BOOT DC_BUS_PLUS CGND _PLUS15V PGND _PLUS5V _PLUS3V3 GND ...)
# We need to remove just the GND token (not CGND or PGND)
content_no_gnd = re.sub(r'(\(class power[^)]*) GND ', r'\1 ', content_no_gnd)

# Write output
dst = Path("pcb/temper_gnd_plane.dsn")
dst.write_text(content_no_gnd)

# Verify
has_gnd_net = "(net GND" in content_no_gnd
print(f"Created: {dst}")
print(f"GND net present: {has_gnd_net}")
print(f"Original nets: {len(re.findall(r'\\(net ', content))}")
print(f"New nets: {len(re.findall(r'\\(net ', content_no_gnd))}")
