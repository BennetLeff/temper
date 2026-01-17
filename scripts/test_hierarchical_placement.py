"""
Test script for Hierarchical Benders Placement.
"""
import sys
import os
from pathlib import Path

# Add src to path
sys.path.append(os.path.abspath("packages/temper-placer/src"))

from temper_placer.placement.hierarchical_loop import HierarchicalBendersLoop

def main():
    print("Testing Hierarchical Benders Loop...")
    
    input_json = "packages/temper-placer/data/benders_input.json"
    pcb_file = "pcb/temper.kicad_pcb"
    
    loop = HierarchicalBendersLoop(input_json, pcb_file)
    result = loop.run()
    
    print("\n=== Result ===")
    print(f"Status: {result.status}")
    print(f"Time: {result.solve_time_sec:.2f}s")
    print(f"Placed Components: {len(result.final_positions)}")
    
    # Check if critical components are placed
    critical = ["U_MCU", "J_AC_IN", "Q1", "Q2"]
    missing = [c for c in critical if c not in result.final_positions]
    if missing:
        print(f"FAILED: Missing components {missing}")
        sys.exit(1)
        
    print("SUCCESS: Full placement generated.")
    
    # Save positions to a debug file to inspect
    import json
    with open("hierarchical_result.json", "w") as f:
        json.dump(result.final_positions, f, indent=2)

if __name__ == "__main__":
    main()
