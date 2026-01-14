#!/usr/bin/env python3
"""
Diagnostic script to compare piantor_left vs piantor_right routing behavior.
Identifies which nets fail on left and investigates root causes.
"""
from pathlib import Path
from temper_placer.router_v6.pipeline import RouterV6Pipeline

def run_comparison():
    """Compare routing results between left and right boards."""
    
    left_path = Path('tests/fixtures/external/.cache/piantor_left/keyboard_pcb.kicad_pcb')
    right_path = Path('tests/fixtures/external/.cache/piantor_right/piantor_right_unrouted.kicad_pcb')
    
    print("=" * 60)
    print("PIANTOR LEFT vs RIGHT ROUTING COMPARISON")
    print("=" * 60)
    
    # Run both pipelines
    pipeline = RouterV6Pipeline(verbose=False)
    
    print("\n[1/2] Running piantor_right...")
    right_result = pipeline.run(right_path)
    
    print("\n[2/2] Running piantor_left...")
    left_result = pipeline.run(left_path)
    
    # Extract routing results
    right_routed = set(right_result.stage4.pathfinding_result.routed_paths.keys())
    right_failed = set(right_result.stage4.pathfinding_result.failed_nets)
    
    left_routed = set(left_result.stage4.pathfinding_result.routed_paths.keys())
    left_failed = set(left_result.stage4.pathfinding_result.failed_nets)
    
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    
    print(f"\nPiantor Right:")
    print(f"  Routed: {len(right_routed)}")
    print(f"  Failed: {len(right_failed)}")
    
    print(f"\nPiantor Left:")
    print(f"  Routed: {len(left_routed)}")
    print(f"  Failed: {len(left_failed)}")
    
    # Find discrepancies
    failed_only_on_left = left_failed - right_failed
    failed_only_on_right = right_failed - left_failed
    failed_on_both = left_failed & right_failed
    
    print("\n" + "=" * 60)
    print("DISCREPANCY ANALYSIS")
    print("=" * 60)
    
    if failed_only_on_left:
        print(f"\n❌ Nets that FAIL on left but SUCCEED on right ({len(failed_only_on_left)}):")
        for net in sorted(failed_only_on_left):
            print(f"    {net}")
    
    if failed_only_on_right:
        print(f"\n❌ Nets that FAIL on right but SUCCEED on left ({len(failed_only_on_right)}):")
        for net in sorted(failed_only_on_right):
            print(f"    {net}")
    
    if failed_on_both:
        print(f"\n⚠ Nets that fail on BOTH boards ({len(failed_on_both)}):")
        for net in sorted(failed_on_both):
            print(f"    {net}")
    
    # Investigate failure reports for left-only failures
    if failed_only_on_left:
        print("\n" + "=" * 60)
        print("FAILURE REPORT DETAILS (Left-only failures)")
        print("=" * 60)
        
        for net in sorted(failed_only_on_left):
            report = left_result.stage4.pathfinding_result.failure_reports.get(net)
            if report:
                print(f"\n  {net}:")
                print(f"    Reason: {report.failure_reason}")
                print(f"    Blocking Nets: {report.blocking_nets}")
                print(f"    Congestion: {report.congestion_region}")
            else:
                print(f"\n  {net}: No failure report available")
    
    # Compare channel paths for failing nets
    if failed_only_on_left:
        print("\n" + "=" * 60)
        print("CHANNEL PATH COMPARISON (Left-only failures)")
        print("=" * 60)
        
        for net in sorted(failed_only_on_left):
            left_channel = left_result.stage4.channel_mapping.channel_paths.get(net)
            right_channel = right_result.stage4.channel_mapping.channel_paths.get(net)
            
            print(f"\n  {net}:")
            if left_channel:
                print(f"    Left waypoints: {len(left_channel.waypoints)}")
                print(f"    Left length: {left_channel.total_length:.2f}mm")
                print(f"    Left layer: {left_channel.preferred_layer}")
            if right_channel:
                print(f"    Right waypoints: {len(right_channel.waypoints)}")
                print(f"    Right length: {right_channel.total_length:.2f}mm")
                print(f"    Right layer: {right_channel.preferred_layer}")
    
    # Check board geometry differences
    print("\n" + "=" * 60)
    print("BOARD GEOMETRY COMPARISON")
    print("=" * 60)
    
    left_pcb = left_result.stage0.parsed_pcb
    right_pcb = right_result.stage0.parsed_pcb
    
    print(f"\nLeft board bounds: {left_pcb.board_outline.bounds if left_pcb.board_outline else 'N/A'}")
    print(f"Right board bounds: {right_pcb.board_outline.bounds if right_pcb.board_outline else 'N/A'}")
    print(f"\nLeft component count: {len(left_pcb.components)}")
    print(f"Right component count: {len(right_pcb.components)}")
    print(f"\nLeft net count: {len(left_pcb.nets)}")
    print(f"Right net count: {len(right_pcb.nets)}")

if __name__ == "__main__":
    run_comparison()
