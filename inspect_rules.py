
import sys
from pathlib import Path

# Add temper-placer to path
sys.path.insert(0, str(Path.cwd() / "packages" / "temper-placer" / "src"))

from temper_placer.io.kicad_parser import parse_kicad_pcb_v6

def inspect_rules():
    pcb = parse_kicad_pcb_v6(Path("pcb/temper.kicad_pcb"))
    print(f"Board size: {pcb.board.width}x{pcb.board.height} mm")
    print("\nNet Classes:")
    for nc_name, rules in pcb.design_rules.net_classes.items():
        print(f"  {nc_name}: Clearance {rules.clearance_mm}mm, Width {rules.trace_width_mm}mm")
    
    print("\nNet Assignments (subset):")
    for net, cls in list(pcb.design_rules.net_class_assignments.items())[:20]:
        print(f"  {net} -> {cls}")

if __name__ == "__main__":
    inspect_rules()
