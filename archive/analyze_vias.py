
import sys
from pathlib import Path
import math
from collections import defaultdict

# Add package path
sys.path.append(str(Path.cwd() / "packages" / "temper-placer" / "src"))

from kiutils.board import Board
from kiutils.items.brditems import Via

TARGET_PCB = Path("piantor_production.kicad_pcb")

def analyze_vias(pcb_path):
    if not pcb_path.exists():
        print(f"Error: {pcb_path} not found")
        return
        
    board = Board.from_file(str(pcb_path))
    
    vias_by_net = defaultdict(list)
    net_names = {} # code -> name
    
    # helper to find net name
    for net in board.nets:
        net_names[net.number] = net.name
        
    total_vias = 0
    for item in board.traceItems:
        if isinstance(item, Via):
            net_code = item.net
            net_name = net_names.get(net_code, f"Net-{net_code}")
            vias_by_net[net_name].append(item)
            total_vias += 1
            
    print(f"Total Vias: {total_vias}")
    print("-" * 60)
    print(f"{'Net':<20} | {'Count':<5} | {'Notes'}")
    print("-" * 60)
    
    clusters_found = 0
    
    for net, vias in vias_by_net.items():
        count = len(vias)
        notes = []
        
        # Check for clustering (potential reuse)
        if count > 1:
            # Simple N^2 check
            min_dist = float('inf')
            for i in range(count):
                for j in range(i+1, count):
                    v1 = vias[i]
                    v2 = vias[j]
                    dx = v1.position.X - v2.position.X
                    dy = v1.position.Y - v2.position.Y
                    dist = math.sqrt(dx*dx + dy*dy)
                    min_dist = min(min_dist, dist)
            
            if min_dist < 2.0: # Less than 2mm apart
                notes.append(f"Cluster: {min_dist:.2f}mm")
                clusters_found += 1
                
        if count > 2:
            notes.append("High Count")
            
        note_str = ", ".join(notes)
        print(f"{net:<20} | {count:<5} | {note_str}")
        
    print("-" * 60)
    print("Analysis:")
    if clusters_found > 0:
        print(f"Found {clusters_found} nets with clustered vias (dist < 2mm).")
        print("Recommendation: Enable 'Via Reuse' optimization or manual merge.")
    else:
        print("No obvious clustering found. Vias are well distributed.")
        
    print("\nGlobal Optimization Potential:")
    print("1. Increase via_cost in A* to discourage layer changes (reduce bouncing).")
    print("2. Implement 'Steiner Tree' routing to share vias for branches.")

if __name__ == "__main__":
    analyze_vias(TARGET_PCB)
