"""
Zone filling utility using KiCad Python API.

This module provides automated zone filling for PCB copper pours
using the pcbnew API, eliminating manual KiCad GUI steps.
"""

import subprocess
import sys
from pathlib import Path


def fill_zones_pcbnew(pcb_file: Path) -> bool:
    """
    Fill all zones in a KiCad PCB file using the pcbnew Python API.
    
    This function creates a temporary Python script and executes it using
    the system Python (which should have pcbnew available if KiCad is installed).
    
    Args:
        pcb_file: Path to .kicad_pcb file
        
    Returns:
        True if zones were filled successfully, False otherwise
        
    Example:
        >>> fill_zones_pcbnew(Path("output.kicad_pcb"))
        True
    """
    # Create a temporary script file
    script_path = pcb_file.parent / "_zone_fill_temp.py"
    
    script_content = f"""#!/usr/bin/env python3
import sys

try:
    import pcbnew
except ImportError:
    print("ERROR: pcbnew module not available. KiCad Python API is required.", file=sys.stderr)
    print("Zone filling skipped. Zones will need to be filled manually in KiCad.", file=sys.stderr)
    sys.exit(0)  # Exit gracefully - this is not a critical error

# Load the board
board = pcbnew.LoadBoard(r"{pcb_file}")

# Get all zones
zones = list(board.Zones())

if len(zones) == 0:
    print("No zones found in PCB - nothing to fill")
    sys.exit(0)

print(f"Found {{len(zones)}} zones in PCB")

# Get the zone filler
filler = pcbnew.ZONE_FILLER(board)

# Fill all zones
print(f"Filling {{len(zones)}} zones...")
try:
    filler.Fill(zones)
    board.Save(r"{pcb_file}")
    print(f"✓ Successfully filled {{len(zones)}} zones")
except Exception as e:
    print(f"ERROR filling zones: {{e}}", file=sys.stderr)
    sys.exit(1)
"""
    
    try:
        # Write the script
        script_path.write_text(script_content)
        
        # Execute it
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Clean up
        script_path.unlink(missing_ok=True)
        
        # Print output
        if result.stdout:
            print(result.stdout.strip())
        if result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
        
        return result.returncode == 0
            
    except subprocess.TimeoutExpired:
        script_path.unlink(missing_ok=True)
        print("Zone filling timed out after 30 seconds", file=sys.stderr)
        return False
    except Exception as e:
        script_path.unlink(missing_ok=True)
        print(f"Error filling zones: {e}", file=sys.stderr)
        return False


def fill_zones_if_present(pcb_file: Path, verbose: bool = True) -> bool:
    """
    Fill zones in PCB file if zones are present, otherwise skip silently.
    
    This function is designed to be called from the export pipeline and will
    gracefully handle cases where:
    - The PCB has no zones
    - The pcbnew module is not available
    - Zone filling fails for any reason
    
    Args:
        pcb_file: Path to .kicad_pcb file
        verbose: If True, print status messages
        
    Returns:
        True if successful or no zones present, False on critical error
    """
    if not pcb_file.exists():
        if verbose:
            print(f"PCB file not found: {pcb_file}", file=sys.stderr)
        return False
    
    if verbose:
        print(f"\n=== Zone Filling ===")
        print(f"PCB: {pcb_file.name}")
    
    success = fill_zones_pcbnew(pcb_file)
    
    if verbose and success:
        print(f"=== Zone Filling Complete ===\n")
    
    return success
