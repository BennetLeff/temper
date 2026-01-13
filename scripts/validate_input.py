#!/usr/bin/env python3
"""
Input Validator for KiCad Router V6.

Checks if the input PCB is clean and if the environment (libraries) is correctly set up.
Run this BEFORE starting the router.
"""

import os
import json
import subprocess
import sys
from pathlib import Path


def run_drc(pcb_path: Path, project_root: Path) -> dict:
    """Run KiCad DRC CLI."""
    output_json = project_root / "drc_input_check.json"

    # Ensure absolute paths
    pcb_abs = pcb_path.resolve()
    proj_abs = project_root.resolve()

    # Set KIPRJMOD to the directory containing the project/board
    # env = os.environ.copy()
    # env["KIPRJMOD"] = str(proj_abs)
    # Removing manual KIPRJMOD override as it causes "Failed to load board"
    env = os.environ.copy()

    # ISOLATION: Force KiCad to ignore global user config (prevent /opt/homebrew paths)
    import tempfile
    import shutil

    temp_home = tempfile.mkdtemp(prefix="kicad_test_env_")
    env["KICAD_CONFIG_HOME"] = temp_home

    # Nuclear Option: Copy local fp-lib-table to Global Config
    # And resolve ${KIPRJMOD} to absolute path
    local_table = project_root / "fp-lib-table"
    global_table = Path(temp_home) / "fp-lib-table"

    if local_table.exists():
        content = local_table.read_text()
        # Replace variable with absolute path
        # Use simple string replace
        # KIPRJMOD -> /Users/bennet/Desktop/temper/pcb
        abs_path = str(project_root.resolve())
        content = content.replace("${KIPRJMOD}", abs_path)
        global_table.write_text(content)
        print(f"Injected global fp-lib-table into {temp_home}")

    cmd = [
        "kicad-cli",
        "pcb",
        "drc",
        str(pcb_abs),
        "--output",
        str(output_json),
        "--format",
        "json",
        "--schematic-parity",  # Check schematic parity too if possible, but maybe schematic is missing
    ]

    print(f"Running DRC on {pcb_path}...")
    try:
        # We don't check=True because DRC returns non-zero on violations
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"DRC CLI returned code {result.returncode}")
            # print(f"STDOUT: {result.stdout}")
            # print(f"STDERR: {result.stderr}")
            # Usually KiCad returns exit code != 0 if violations found, but still writes report.
            # But if it crashed (segfault or load error), report might be missing.
    except FileNotFoundError:
        print("Error: kicad-cli not found in PATH.")
        sys.exit(1)

    if not output_json.exists():
        print("Error: DRC failed to generate report. Output JSON missing.")
        print(f"STDOUT:\n{result.stdout}")
        print(f"STDERR:\n{result.stderr}")
        sys.exit(1)

    with open(output_json) as f:
        return json.load(f)


def validate():
    root_dir = Path(__file__).parent.parent
    pcb_dir = root_dir / "pcb"
    pcb_file = pcb_dir / "temper.kicad_pcb"
    # pcb_file = pcb_dir / "temper_router_v6_output.kicad_pcb" # Test Output file

    # 1. Check Environment
    if not (pcb_dir / "fp-lib-table").exists():
        print("FAIL: pcb/fp-lib-table not found.")
        print("Run 'python3 tools/setup_kicad_env.py' first.")
        sys.exit(1)

    # 2. Run DRC
    report = run_drc(pcb_file, pcb_dir)

    # 3. Analyze
    violations = report.get("violations", [])

    lib_missing = [v for v in violations if "footprint library" in v.get("description", "")]
    shorts = [v for v in violations if "shorting" in v.get("description", "")]

    print(f"\nValidation Results for {pcb_file.name}:")
    print(f"  Total Violations: {len(violations)}")
    print(f"  Library Missing Errors: {len(lib_missing)}")
    print(f"  Short Circuits (Pre-existing): {len(shorts)}")

    if lib_missing:
        print("\nCRITICAL: Missing Libraries detected!")
        print("The router will be BLIND to these components.")
        print("Example missing libs:")
        for v in lib_missing[:3]:
            print(f"  - {v['description']}")

    if shorts:
        print("\nWARNING: Input board contains short circuits!")
        print("The router cannot fix placement errors.")
        print("Example shorts:")
        for v in shorts[:3]:
            print(f"  - {v['description']}")

    if not lib_missing and not shorts:
        print("\nPASS: Input board is clean and environment is valid.")
        sys.exit(0)
    else:
        print("\nFAIL: Fix errors before routing.")
        sys.exit(1)


if __name__ == "__main__":
    validate()
