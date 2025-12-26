"""
Record internal baseline metrics for the Temper board.
"""

from pathlib import Path
import json
import numpy as np
import jax.numpy as jnp

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.core.state import PlacementState
from temper_placer.metrics.physics import (
    measure_geometric,
    measure_emi,
    measure_thermal,
    measure_routability,
    PhysicsReport
)

def analyze_pcb(pcb_path: Path, output_json: Path | None = None) -> PhysicsReport:
    if not pcb_path.exists():
        raise FileNotFoundError(f"{pcb_path} not found")

    print(f"Analyzing {pcb_path}...")
    result = parse_kicad_pcb(pcb_path)
    board = result.board
    netlist = result.netlist
    
    # Extract current positions into PlacementState
    positions = []
    for comp in netlist.components:
        if comp.initial_position:
            positions.append(comp.initial_position)
        else:
            positions.append((0.0, 0.0))
    
    state = PlacementState.from_positions(jnp.array(positions))
    
    # Assign net classes from spec if possible
    for comp in netlist.components:
        if comp.ref in ["Q1", "Q2", "D1", "D2", "J_AC", "C_BUS1"]:
            comp.net_class = "HighVoltage"
        else:
            comp.net_class = "Signal"
            
    # 1. Geometric
    geo = measure_geometric(state, netlist, board)
    
    # 2. EMI
    loop_refs = [
        ["Q1", "Q2", "C_BUS1"],  # Commutation loop
    ]
    emi = measure_emi(state, netlist, loop_refs=loop_refs)
    
    # 3. Thermal
    power = {"Q1": 15.0, "Q2": 15.0}
    thermal = measure_thermal(state, netlist, board, power_dissipation=power)
    
    # 4. Routability
    routability = measure_routability(state, netlist, board)
    
    report = PhysicsReport(
        geometric=geo,
        emi=emi,
        thermal=thermal,
        routability=routability
    )
    
    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        print(f"Metrics saved to {output_json}")
        
    return report

def main():
    import sys
    pcb_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("pcb/temper.kicad_pcb")
    output_path = Path("metrics") / f"{pcb_path.stem}_metrics.json"
    
    try:
        report = analyze_pcb(pcb_path, output_path)
        print(f"  Overlap Count: {report.geometric.overlap_count}")
        print(f"  Max Tj: {report.thermal.max_junction_temp_c:.1f} C")
        print(f"  Max Congestion: {report.routability.max_congestion:.2f}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
