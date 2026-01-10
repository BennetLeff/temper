
import sys
from pathlib import Path
import math

# Add package path
sys.path.append(str(Path.cwd() / "packages" / "temper-placer" / "src"))

from kiutils.board import Board
from temper_placer.io.kicad_parser import parse_kicad_pcb

from kiutils.items.brditems import Segment, Via

TARGET_PCB = Path("piantor_production.kicad_pcb")
REF_PCB = Path("/tmp/piantor/pcb/right/keyboard_pcb.kicad_pcb")

def get_metrics(pcb_path):
    if not pcb_path.exists():
        print(f"Error: {pcb_path} not found")
        return None
        
    board = Board.from_file(str(pcb_path))
    
    total_length = 0.0
    via_count = 0
    segment_count = 0
    
    # Filter only signal tracks (ignore graphical lines on F.SilkS etc)
    # kiutils stores tracks in board.traceItems
    
    for item in board.traceItems:
        if isinstance(item, Via):
            via_count += 1
        elif isinstance(item, Segment):
            # Calculate length
            dx = item.end.X - item.start.X
            dy = item.end.Y - item.start.Y
            length = math.sqrt(dx*dx + dy*dy)
            total_length += length
            segment_count += 1
            
    return {
        "length_mm": total_length,
        "vias": via_count,
        "segments": segment_count
    }

def main():
    print("Analying Difference: Generated vs Ground Truth")
    print("-" * 50)
    
    gen_metrics = get_metrics(TARGET_PCB)
    ref_metrics = get_metrics(REF_PCB)
    
    if not gen_metrics or not ref_metrics:
        return
        
    print(f"{'Metric':<20} | {'Generated':<15} | {'Ground Truth':<15} | {'Diff (%)':<10}")
    print("-" * 70)
    
    for key in ["length_mm", "vias", "segments"]:
        gen_val = gen_metrics[key]
        ref_val = ref_metrics[key]
        diff = gen_val - ref_val
        diff_pct = (diff / ref_val * 100) if ref_val > 0 else 0
        
        # Format
        if key == "vias" or key == "segments":
            fmt = "{:d}"
        else:
            fmt = "{:.2f}"
            
        gen_s = fmt.format(gen_val)
        ref_s = fmt.format(ref_val)
        diff_s = f"{diff_pct:+.1f}%"
        
        print(f"{key:<20} | {gen_s:<15} | {ref_s:<15} | {diff_s:<10}")

    print("-" * 70)
    print("Interpretation:")
    if gen_metrics["length_mm"] > ref_metrics["length_mm"]:
        print(f"  - Generated traces are {gen_metrics['length_mm'] - ref_metrics['length_mm']:.1f}mm longer (Less efficient).")
    else:
        print(f"  - Generated traces are {ref_metrics['length_mm'] - gen_metrics['length_mm']:.1f}mm shorter (More efficient?).")
        
    if gen_metrics["vias"] > ref_metrics["vias"]:
        print(f"  - Generated uses {gen_metrics['vias'] - ref_metrics['vias']} more vias (Fragmented routing).")
    else:
        print(f"  - Generated uses {ref_metrics['vias'] - gen_metrics['vias']} fewer vias.")

if __name__ == "__main__":
    main()
