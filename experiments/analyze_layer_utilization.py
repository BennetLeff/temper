import sys
from pathlib import Path

# Add packages to path
sys.path.insert(0, str(Path("packages/temper-placer/src").absolute()))

from temper_placer.io.kicad_parser import parse_kicad_pcb

def analyze_layer_utilization(pcb_path: str):
    try:
        result = parse_kicad_pcb(Path(pcb_path))
        traces = result.traces
        vias = result.vias
    except Exception as e:
        print(f"Failed to parse PCB: {e}")
        return

    print(f"--- Layer Utilization for {pcb_path} ---")
    print(f"Total trace segments: {len(traces)}")
    print(f"Total vias: {len(vias)}")
    
    layer_lengths = {}
    for t in traces:
        length = ((t.start[0]-t.end[0])**2 + (t.start[1]-t.end[1])**2)**0.5
        layer_lengths[t.layer] = layer_lengths.get(t.layer, 0.0) + length
        
    print("\nTrace Length by Layer:")
    for layer, length in sorted(layer_lengths.items()):
        print(f"  {layer:<10}: {length:8.2f} mm")
        
    if vias:
        print("\nVias by Layer Pair:")
        via_layers = {}
        for v in vias:
            layers = tuple(sorted(v.layers))
            via_layers[layers] = via_layers.get(layers, 0) + 1
        for layers, count in sorted(via_layers.items()):
            print(f"  {' <-> '.join(layers):<20}: {count:4d}")

if __name__ == "__main__":
    pcb = "routed_v3.kicad_pcb"
    if len(sys.argv) > 1:
        pcb = sys.argv[1]
    analyze_layer_utilization(pcb)
