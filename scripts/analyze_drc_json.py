from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.routing.constraints.drc_oracle import DRCOracle, Violation
from temper_placer.core.design_rules import DesignRules
from temper_placer.routing.constraints.spatial_index import PCBGeometry, Track, Via, Pad
from temper_placer.routing.constraints.geometry import Point
import sys
import collections
from pathlib import Path
from kiutils.board import Board as KiBoard

def analyze(pcb_path):
    print(f"Loading {pcb_path}...")
    res = parse_kicad_pcb(Path(pcb_path))
    
    rules = DesignRules() 
    geometry = PCBGeometry()
    
    count_t = 0
    # Populate Tracks
    for trace in res.traces:
        # Ignore non-copper layers if necessary, but parser handles layers
        width = trace.width if trace.width else 0.2
        # Simple layer map: F.Cu -> 0, In1.Cu -> 1, In2.Cu -> 2, B.Cu -> 3??
        # MazeRouter uses indices. DRCOracle typically checks layer index equality.
        # We need to ensure layer mapping is consistent.
        # Let's assume standard 4-layer stackup or just use string hash? 
        # Track.layer is int.
        
        layer_id = 0
        if "B.Cu" in trace.layer: layer_id = 3
        elif "In1.Cu" in trace.layer: layer_id = 1
        elif "In2.Cu" in trace.layer: layer_id = 2
        
        geometry.add_track(Track(
            start=Point(trace.start[0], trace.start[1]),
            end=Point(trace.end[0], trace.end[1]),
            width=width,
            layer=layer_id, 
            net=trace.net or "unknown",
            id=f"track_{count_t}"
        ))
        count_t += 1
        
    # Populate Vias (Not extracted by parse_kicad_pcb? Check parser)
    # The parser seems to not fully extract via locations in top level.
    # _extract_traces_from_pcb only gets "traceItems" with start/end.
    # Kiutils has viaItems?
    # Let's check if we can get vias. parse_kicad_pcb result has "traces" and "pads".
    # Vias might be missing from ParseResult.
    
    # Check ki_board object directly if possible? No, we only get ParseResult.
    # We might need to extend parser or cheat.
    # Assuming vias are missing for now, we will see track-track violations only.
    # But wait, we want to analyze VIA violations.
    
    # We can use kiutils directly here then.
    ki_board = KiBoard.from_file(pcb_path)
    
    count_v = 0
    # Extract Vias manually using kiutils
    if hasattr(ki_board, 'traceItems'):
        for item in ki_board.traceItems:
            if item.type == 'via':
                # Map net
                net_name = "unknown"
                 # (Logic to extract net name similar to parser)
                if item.net and hasattr(item.net, 'name'): net_name = item.net.name
                
                geometry.add_via(Via(
                    center=Point(item.position.X, item.position.Y),
                    diameter=item.size,
                    drill=item.drill,
                    net=net_name,
                    id=f"via_{count_v}"
                ))
                count_v += 1
    
    # Populate Pads
    count_p = 0
    for pad in res.pads:
         # Pads need to be in geometry for clearance checks against them
         # Pad (center, size_x, size_y, layer, net)
         # Pad shape? geometry.Pad assumes circle/rect?
         # Let's assume rectangular for simple bbox check or circular for radius
         # geometry.Pad definition:
         # center: Point, radius: float, net: str ...
         # It seems geometry.Pad is simplified to circle?
         # Let's check geometry.py/spatial_index.py definition of Pad
         
         # Assuming circular approx for now: radius = min(w,h)/2
         r = min(pad.size[0], pad.size[1]) / 2.0
         geometry.add_pad(Pad(
             center=Point(pad.position[0], pad.position[1]),
             radius=r, # Approximate
             net=pad.net or "",
             id=f"pad_{count_p}"
         ))
         count_p += 1
         
    print(f"Loaded {count_t} tracks, {count_v} vias, {count_p} pads.")
    geometry.rebuild_index()
    
    oracle = DRCOracle(rules, geometry)
    print("Validating...")
    violations = oracle.validate_all()
    
    print(f"\nTotal Violations: {len(violations)}")
    
    by_type = collections.defaultdict(list)
    for v in violations:
        by_type[v.type].append(v)
        
    for vtype, vs in by_type.items():
        print(f"  {vtype}: {len(vs)}")
        avg_severity = sum(v.severity for v in vs) / len(vs)
        print(f"    Avg Severity: {avg_severity:.3f}")
        
        nets = collections.defaultdict(int)
        for v in vs:
            pair = tuple(sorted((v.net_a, v.net_b)))
            nets[pair] += 1
            
        print(f"    Top offending net pairs:")
        sorted_nets = sorted(nets.items(), key=lambda x: x[1], reverse=True)[:5]
        for pair, count in sorted_nets:
            print(f"      {pair}: {count}")

if __name__ == "__main__":
    analyze(sys.argv[1])
