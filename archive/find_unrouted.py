#!/usr/bin/env python3
"""
Run FreeRouter on temper_gnd_plane.dsn and capture the unrouted net.
"""
import subprocess
import re
import tempfile
import os

DSN_PATH = "pcb/temper_gnd_plane.dsn"
JAR_PATH = os.path.expanduser("~/tools/freerouting.jar")

# Check if FreeRouter exists
if not os.path.exists(JAR_PATH):
    print(f"ERROR: FreeRouter not found at {JAR_PATH}")
    exit(1)

# Create temp file for session output
with tempfile.NamedTemporaryFile(suffix='.ses', delete=False) as f:
    ses_path = f.name

print(f"Running FreeRouter on {DSN_PATH}...")
print(f"Session output: {ses_path}")

cmd = [
    "java",
    "-Djava.awt.headless=true",
    "-jar", JAR_PATH,
    "-de", DSN_PATH,
    "-do", ses_path,
    "-mp", "30",  # 30 passes should be enough
]

result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

print("\n=== STDOUT ===")
print(result.stdout[:5000] if result.stdout else "(empty)")

print("\n=== STDERR ===")
print(result.stderr[:5000] if result.stderr else "(empty)")

# Parse output for unrouted info
output = result.stdout + result.stderr

# Look for unrouted count
unrouted_match = re.search(r'(\d+) unrouted', output, re.IGNORECASE)
if unrouted_match:
    print(f"\n>>> UNROUTED: {unrouted_match.group(1)}")

# Look for specific net names in unrouted messages
for line in output.split('\n'):
    if 'unrouted' in line.lower():
        print(f">>> {line}")
    if 'unable' in line.lower():
        print(f">>> {line}")
    if 'failed' in line.lower():
        print(f">>> {line}")

# Check session file for routed nets
if os.path.exists(ses_path):
    with open(ses_path) as f:
        ses_content = f.read()
    
    # Extract routed net names
    routed_nets = re.findall(r'\(net (\S+)', ses_content)
    print(f"\n>>> Routed nets ({len(set(routed_nets))}): {sorted(set(routed_nets))}")
    
    # DSN nets for comparison
    with open(DSN_PATH) as f:
        dsn_content = f.read()
    dsn_nets = re.findall(r'\(net (\S+) \(pins', dsn_content)
    print(f">>> DSN nets ({len(dsn_nets)}): {sorted(dsn_nets)}")
    
    # Find unrouted
    unrouted = set(dsn_nets) - set(routed_nets)
    print(f"\n>>> UNROUTED NETS: {unrouted if unrouted else 'NONE - 100%!'}")
    
    os.unlink(ses_path)
else:
    print("No SES file created - routing may have failed")
