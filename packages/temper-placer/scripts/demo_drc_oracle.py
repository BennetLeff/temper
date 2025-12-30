#!/usr/bin/env python3
"""
DRCOracle Demo - Validate a KiCad PCB file and produce a report.

This script demonstrates the DRCOracle by:
1. Loading geometry from a routed KiCad PCB file
2. Validating all tracks and vias for DRC violations
3. Producing a summary report

Usage:
    cd packages/temper-placer
    uv run python scripts/demo_drc_oracle.py [path/to/board.kicad_pcb]

Epic: temper-lueu
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from kiutils.board import Board

# Add src to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from temper_placer.routing.constraints import (
    ClearanceMatrix,
    DesignRulesParser,
    DRCOracle,
    Pad,
    Point,
    Track,
    Via,
)

# Layer name to index mapping (simplified)
LAYER_MAP = {
    "F.Cu": 0,
    "In1.Cu": 1,
    "In2.Cu": 2,
    "B.Cu": 3,
}


def load_pcb_geometry(pcb: Board, oracle: DRCOracle) -> dict:
    """Load geometry from KiCad PCB into the oracle.
    
    Returns stats about loaded geometry.
    """
    stats = {"tracks": 0, "vias": 0, "pads": 0}
    
    # Load tracks
    if hasattr(pcb, "traceItems") and pcb.traceItems:
        for item in pcb.traceItems:
            if hasattr(item, "start") and hasattr(item, "end"):
                # It's a segment/track
                layer = LAYER_MAP.get(item.layer, 0) if hasattr(item, "layer") else 0
                net_name = f"net_{item.net}" if hasattr(item, "net") else "unknown"
                width = item.width if hasattr(item, "width") else 0.2
                
                track = Track(
                    start=Point(item.start.X, item.start.Y),
                    end=Point(item.end.X, item.end.Y),
                    width=width,
                    net=net_name,
                    layer=layer,
                )
                oracle.geometry.add_track(track)
                stats["tracks"] += 1
            elif hasattr(item, "position"):
                # It's a via
                net_name = f"net_{item.net}" if hasattr(item, "net") else "unknown"
                diameter = item.size if hasattr(item, "size") else 0.6
                drill = item.drill if hasattr(item, "drill") else 0.3
                
                via = Via(
                    center=Point(item.position.X, item.position.Y),
                    diameter=diameter,
                    drill=drill,
                    net=net_name,
                )
                oracle.geometry.add_via(via)
                stats["vias"] += 1
    
    # Load pads from footprints
    if hasattr(pcb, "footprints") and pcb.footprints:
        for fp in pcb.footprints:
            if hasattr(fp, "pads") and fp.pads:
                for pad_obj in fp.pads:
                    if hasattr(pad_obj, "position"):
                        # Get absolute position (fp position + pad position)
                        fp_x = fp.position.X if hasattr(fp, "position") else 0
                        fp_y = fp.position.Y if hasattr(fp, "position") else 0
                        pad_x = pad_obj.position.X if hasattr(pad_obj.position, "X") else 0
                        pad_y = pad_obj.position.Y if hasattr(pad_obj.position, "Y") else 0
                        
                        net_name = f"net_{pad_obj.net.number}" if hasattr(pad_obj, "net") and pad_obj.net else "nonet"
                        
                        size = (1.0, 1.0)  # Default
                        if hasattr(pad_obj, "size"):
                            size = (
                                pad_obj.size.X if hasattr(pad_obj.size, "X") else 1.0,
                                pad_obj.size.Y if hasattr(pad_obj.size, "Y") else 1.0,
                            )
                        
                        pad = Pad(
                            center=Point(fp_x + pad_x, fp_y + pad_y),
                            shape="circle",
                            size=size,
                            net=net_name,
                            layer=0,
                        )
                        oracle.geometry.add_pad(pad)
                        stats["pads"] += 1
    
    # Rebuild spatial index
    oracle.geometry.rebuild_index()
    
    return stats


def main():
    parser = argparse.ArgumentParser(description="DRCOracle Demo - Validate PCB DRC")
    parser.add_argument(
        "pcb_file",
        nargs="?",
        default=None,
        help="Path to KiCad PCB file (default: uses test geometry)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("DRCOracle Validation Demo")
    print("Epic: temper-lueu")
    print("=" * 60)
    print()
    
    # Create oracle with default rules
    rules = DesignRulesParser.create_default()
    oracle = DRCOracle(rules)
    
    if args.pcb_file:
        # Load from PCB file
        pcb_path = Path(args.pcb_file)
        if not pcb_path.exists():
            print(f"Error: File not found: {pcb_path}")
            sys.exit(1)
        
        print(f"Loading: {pcb_path.name}")
        start = time.time()
        pcb = Board.from_file(str(pcb_path))
        load_time = (time.time() - start) * 1000
        
        stats = load_pcb_geometry(pcb, oracle)
        print(f"  Loaded in {load_time:.1f}ms")
        print(f"  Tracks: {stats['tracks']}")
        print(f"  Vias: {stats['vias']}")
        print(f"  Pads: {stats['pads']}")
    else:
        # Create test geometry with known violations
        print("Using synthetic test geometry (no PCB file specified)")
        print()
        
        # Add some tracks that violate clearance
        track1 = Track(Point(0, 0), Point(10, 0), width=0.2, net="SIG1", layer=0)
        track2 = Track(Point(5, 0.15), Point(15, 0.15), width=0.2, net="SIG2", layer=0)  # Too close!
        track3 = Track(Point(0, 5), Point(10, 5), width=0.2, net="SIG3", layer=0)  # OK
        track4 = Track(Point(0, 5.1), Point(10, 5.1), width=0.2, net="SIG4", layer=0)  # Violation!
        
        oracle.geometry.add_track(track1)
        oracle.geometry.add_track(track2)
        oracle.geometry.add_track(track3)
        oracle.geometry.add_track(track4)
        
        # Add vias with one violation
        via1 = Via(Point(20, 20), diameter=0.8, drill=0.4, net="VIA_NET1")
        via2 = Via(Point(20.5, 20), diameter=0.8, drill=0.4, net="VIA_NET2")  # Too close!
        via3 = Via(Point(30, 20), diameter=0.8, drill=0.4, net="VIA_NET3")  # OK
        
        oracle.geometry.add_via(via1)
        oracle.geometry.add_via(via2)
        oracle.geometry.add_via(via3)
        
        oracle.geometry.rebuild_index()
        
        print(f"  Tracks: {len(oracle.geometry.tracks)}")
        print(f"  Vias: {len(oracle.geometry.vias)}")
    
    print()
    
    # Validate all geometry
    print("Validating DRC...")
    start = time.time()
    violations = oracle.validate_all()
    validate_time = (time.time() - start) * 1000
    
    print(f"  Completed in {validate_time:.1f}ms")
    print()
    
    # Report results
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print()
    
    if violations:
        print(f"Found {len(violations)} violation(s):")
        print()
        
        # Group by type
        by_type: dict[str, list] = {}
        for v in violations:
            by_type.setdefault(v.type, []).append(v)
        
        for vtype, vlist in by_type.items():
            print(f"  {vtype}: {len(vlist)}")
        
        print()
        print("Top 5 violations:")
        for i, v in enumerate(violations[:5], 1):
            print(f"  {i}. {v.type}: {v.geometry_a_id} <-> {v.geometry_b_id}")
            print(f"     Actual: {v.clearance_actual:.3f}mm, Required: {v.clearance_required:.3f}mm")
            print(f"     Severity: {v.severity:.1%}")
    else:
        print("✓ No DRC violations found!")
    
    print()
    
    # Test query performance
    print("=" * 60)
    print("PERFORMANCE TEST")
    print("=" * 60)
    print()
    
    import random
    
    n_queries = 100
    start = time.time()
    for _ in range(n_queries):
        oracle.can_place_track_segment(
            (random.uniform(0, 100), random.uniform(0, 100)),
            (random.uniform(0, 100), random.uniform(0, 100)),
            layer=0,
            net="TEST",
            width=0.2,
        )
    query_time = (time.time() - start) * 1000
    
    avg_ms = query_time / n_queries
    print(f"  {n_queries} queries in {query_time:.1f}ms")
    print(f"  Average: {avg_ms:.3f}ms per query")
    
    if avg_ms < 1.0:
        print(f"  ✓ PASS: <1ms per query target met!")
    else:
        print(f"  ✗ FAIL: >1ms per query ({avg_ms:.2f}ms)")
    
    print()
    print("=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
