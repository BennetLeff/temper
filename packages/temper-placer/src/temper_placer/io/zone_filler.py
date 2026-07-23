"""
Zone filling utility using KiCad Python API.

Re-exported from temper_io_types (Rust / pyo3).
"""

from temper_io_types import fill_zones_if_present, fill_zones_pcbnew

__all__ = [
    "fill_zones_pcbnew",
    "fill_zones_if_present",
]

# OLD: import subprocess
# OLD: import sys
# OLD: from pathlib import Path
# OLD:
# OLD:
# OLD: def fill_zones_pcbnew(pcb_file: Path) -> bool:
# OLD:     """
# OLD:     Fill all zones in a KiCad PCB file using the pcbnew Python API.
# OLD:
# OLD:     This function creates a temporary Python script and executes it using
# OLD:     the system Python (which should have pcbnew available if KiCad is installed).
# OLD:
# OLD:     Args:
# OLD:         pcb_file: Path to .kicad_pcb file
# OLD:
# OLD:     Returns:
# OLD:         True if zones were filled successfully, False otherwise
# OLD:
# OLD:     Example:
# OLD:         >>> fill_zones_pcbnew(Path("output.kicad_pcb"))
# OLD:         True
# OLD:     """
# OLD:     # Create a temporary script file
# OLD:     script_path = pcb_file.parent / "_zone_fill_temp.py"
# OLD:
# OLD:     script_content = f"""#!/usr/bin/env python3
# OLD: import sys
# OLD:
# OLD: try:
# OLD:     import pcbnew
# OLD: except ImportError:
# OLD:     print("ERROR: pcbnew module not available. KiCad Python API is required.", file=sys.stderr)
# OLD:     print("Zone filling skipped. Zones will need to be filled manually in KiCad.", file=sys.stderr)
# OLD:     sys.exit(0)  # Exit gracefully - this is not a critical error
# OLD:
# OLD: # Load the board
# OLD: board = pcbnew.LoadBoard(r"{pcb_file}")
# OLD:
# OLD: # Get all zones
# OLD: zones = list(board.Zones())
# OLD:
# OLD: if len(zones) == 0:
# OLD:     print("No zones found in PCB - nothing to fill")
# OLD:     sys.exit(0)
# OLD:
# OLD: print(f"Found {{len(zones)}} zones in PCB")
# OLD:
# OLD: # Get the zone filler
# OLD: filler = pcbnew.ZONE_FILLER(board)
# OLD:
# OLD: # Fill all zones
# OLD: print(f"Filling {{len(zones)}} zones...")
# OLD: try:
# OLD:     filler.Fill(zones)
# OLD:     board.Save(r"{pcb_file}")
# OLD:     print(f"✓ Successfully filled {{len(zones)}} zones")
# OLD: except Exception as e:
# OLD:     print(f"ERROR filling zones: {{e}}", file=sys.stderr)
# OLD:     sys.exit(1)
# OLD: """
# OLD:
# OLD:     try:
# OLD:         # Write the script
# OLD:         script_path.write_text(script_content)
# OLD:
# OLD:         # Execute it
# OLD:         result = subprocess.run(
# OLD:             [sys.executable, str(script_path)],
# OLD:             capture_output=True,
# OLD:             text=True,
# OLD:             timeout=30
# OLD:         )
# OLD:
# OLD:         # Clean up
# OLD:         script_path.unlink(missing_ok=True)
# OLD:
# OLD:         # Print output
# OLD:         if result.stdout:
# OLD:             print(result.stdout.strip())
# OLD:         if result.stderr:
# OLD:             print(result.stderr.strip(), file=sys.stderr)
# OLD:
# OLD:         return result.returncode == 0
# OLD:
# OLD:     except subprocess.TimeoutExpired:
# OLD:         script_path.unlink(missing_ok=True)
# OLD:         print("Zone filling timed out after 30 seconds", file=sys.stderr)
# OLD:         return False
# OLD:     except Exception as e:
# OLD:         script_path.unlink(missing_ok=True)
# OLD:         print(f"Error filling zones: {e}", file=sys.stderr)
# OLD:         return False
# OLD:
# OLD:
# OLD: def fill_zones_if_present(pcb_file: Path, verbose: bool = True) -> bool:
# OLD:     """
# OLD:     Fill zones in PCB file if zones are present, otherwise skip silently.
# OLD:
# OLD:     This function is designed to be called from the export pipeline and will
# OLD:     gracefully handle cases where:
# OLD:     - The PCB has no zones
# OLD:     - The pcbnew module is not available
# OLD:     - Zone filling fails for any reason
# OLD:
# OLD:     Args:
# OLD:         pcb_file: Path to .kicad_pcb file
# OLD:         verbose: If True, print status messages
# OLD:
# OLD:     Returns:
# OLD:         True if successful or no zones present, False on critical error
# OLD:     """
# OLD:     if not pcb_file.exists():
# OLD:         if verbose:
# OLD:             print(f"PCB file not found: {pcb_file}", file=sys.stderr)
# OLD:         return False
# OLD:
# OLD:     if verbose:
# OLD:         print("\n=== Zone Filling ===")
# OLD:         print(f"PCB: {pcb_file.name}")
# OLD:
# OLD:     success = fill_zones_pcbnew(pcb_file)
# OLD:
# OLD:     if verbose and success:
# OLD:         print("=== Zone Filling Complete ===\n")
# OLD:
# OLD:     return success
