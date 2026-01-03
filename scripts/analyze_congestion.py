
import sys
import math
from pathlib import Path
from collections import defaultdict
import numpy as np
from kiutils.board import Board
from kiutils.items.brditems import Segment, Via as KiVia

from temper_placer.routing.constraints import DRCOracle, DesignRulesParser, Track, Via, Pad
from temper_placer.routing.constraints.geometry import Point, LineSegment, segment_to_segment_distance

def analyze_congestion(pcb_path: str):
    board = Board.from_file(pcb_path)
    rules = DesignRulesParser.create_default()
    oracle = DRCOracle(rules)
    
    print(f"Loading geometry from {pcb_path}...")
    
    # 1. Load Tracks
    track_count = 0
    # Map layers: F.Cu->0, In1->1, In2->2, B.Cu->3
    layer_map = {"F.Cu": 0, "In1.Cu": 1, "In2.Cu": 2, "B.Cu": 3}
    
    for item in board.traceItems:
        if isinstance(item, Segment):
             l_idx = layer_map.get(item.layer, 0)
             net_name = board.nets[item.net].name if item.net < len(board.nets) else "Unknown"
             
             t = Track(
                 start=Point(item.start.X, item.start.Y),
                 end=Point(item.end.X, item.end.Y),
                 width=item.width,
                 layer=l_idx,
                 net=net_name
             )
             oracle.geometry.add_track(t)
             track_count += 1
             
        elif isinstance(item, KiVia):
             net_name = board.nets[item.net].name if item.net < len(board.nets) else "Unknown"
             v = Via(
                 center=Point(item.position.X, item.position.Y),
                 diameter=item.size,
                 drill=item.drill,
                 net=net_name
             )
             oracle.geometry.add_via(v)

    # 2. components & Pads
    components = []
    for fp in board.footprints:
        # KiUtils footprint position is absolute
        fx, fy = fp.position.X, fp.position.Y
        rot = fp.position.angle if fp.position.angle else 0.0
        rad = math.radians(rot)
        
        comp_info = {
            "ref": fp.properties.get("Reference", "UNKNOWN"),
            "center": (fx, fy),
            "pads": []
        }
        
        for p in fp.pads:
            # Pad pos is relative to footprint (usually)
            # Simple rotation/translation
            px, py = p.position.X, p.position.Y
            
            # Rotate
            rx = px * math.cos(rad) - py * math.sin(rad)
            ry = px * math.sin(rad) + py * math.cos(rad)
            
            abs_x = fx + rx
            abs_y = fy + ry
            
            # Register pad in oracle to check clearance
            # Kiutils Pad.net is a Net object
            net_name = p.net.name if p.net else "Unknown"
            # Approx pad as circle for now to simple constraints
            # (In reality Rect/RoundRrc needs shape handling)
            pad_r = min(p.size.X, p.size.Y) / 2
            
            oracle_pad = Pad(
                center=Point(abs_x, abs_y),
                shape="circle", # Approximation
                size=(pad_r*2, pad_r*2),
                net=net_name,
                layer=0 # component usually top
            )
            oracle.geometry.add_pad(oracle_pad)
            
        components.append(comp_info)

    oracle.geometry.rebuild_index()
    print(f"Loaded {track_count} tracks, {len(components)} components.")
    
    # 3. Analyze Violations
    print("Scanning for violations (Sampled)...")
    violation_counts = defaultdict(int) # Raw segments per component
    
    # Clustering Logic
    # Key: Tuple[str, str] (sorted net names) -> List of Point
    violation_clusters = defaultdict(list) 
    unique_violations = 0
    total_violations = 0
    
    all_tracks = oracle.geometry.tracks
    import random
    # Sample more to be sure
    sampled_tracks = all_tracks # Check all for accuracy? Or substantial sample
    if len(all_tracks) > 10000:
        print(f"Sampling 10,000 tracks from {len(all_tracks)}...")
        sampled_tracks = random.sample(all_tracks, 10000)
    
    for t1 in sampled_tracks:
        # Check against nearby tracks
        search_r = 1.0 # 1mm search
        nearby = oracle.geometry.query_tracks_near(t1.start, search_r, t1.layer)
        
        for t2 in nearby:
            if t1.id >= t2.id: continue
            if t1.net == t2.net: continue
            
            # Clearance check
            req = rules.get_clearance(t1.net, t2.net)
            gap = segment_to_segment_distance(LineSegment(t1.start, t1.end), LineSegment(t2.start, t2.end))
            eff = req + t1.width/2 + t2.width/2
            
            if gap < eff - 0.001: # Tolerance
                total_violations += 1
                
                # Clustering
                pair_key = tuple(sorted((t1.net, t2.net)))
                mid = t1.start # approx location
                
                # Check if this is a new cluster or part of existing
                is_new_cluster = True
                for existing_pt in violation_clusters[pair_key]:
                    if mid.distance_to(existing_pt) < 2.0: # 2mm merge radius
                        is_new_cluster = False
                        break
                
                if is_new_cluster:
                    violation_clusters[pair_key].append(mid)
                    unique_violations += 1
                
                # Attribute to component
                nearest = min(components, key=lambda c: (c["center"][0]-mid.x)**2 + (c["center"][1]-mid.y)**2)
                # Use property access for Reference
                ref = nearest.get("ref") or nearest.get("properties", {}).get("Reference", "UNK")
                violation_counts[ref] += 1
                
    print(f"\nAnalysis Results:")
    print(f"  Total Geometric Violations (Segments): {total_violations}")
    print(f"  Unique Constraint Clusters (Problems): {unique_violations}")
    if unique_violations > 0:
        ratio = total_violations / unique_violations
        print(f"  Duplication Factor: {ratio:.1f}x (violations per problem)")

    print("\nTop Congested Components (Raw Violations):")
    for ref, count in sorted(violation_counts.items(), key=lambda x: -x[1])[:20]:
        print(f"{ref}: {count}")
    
    # Print top clusters
    print("\nTop Conflict Pairs (Unique Clusters):")
    cluster_counts = {k: len(v) for k, v in violation_clusters.items()}
    for pair, count in sorted(cluster_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"{pair}: {count} locations")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_congestion.py <pcb_file>")
        sys.exit(1)
    analyze_congestion(sys.argv[1])
