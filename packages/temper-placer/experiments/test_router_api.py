"""Test Router V6 Pipeline API directly."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 70)
print("TEST: Router V6 Pipeline API")
print("=" * 70)

temper_pcb = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_routed.kicad_pcb"

if not temper_pcb.exists():
    print(f"⚠️  PCB not found: {temper_pcb}")
    print("Looking for alternative PCB files...")
    # Try to find any PCB file
    pcb_dir = Path(__file__).parent.parent.parent.parent / "pcb"
    pcb_files = list(pcb_dir.glob("*.kicad_pcb"))
    if pcb_files:
        temper_pcb = pcb_files[0]
        print(f"Found: {temper_pcb.name}")
    else:
        print("❌ No PCB files found")
        sys.exit(1)

print(f"\n📄 PCB: {temper_pcb.name}")
print(f"🔄 Running router pipeline...")

try:
    from temper_placer.router_v6.pipeline import RouterV6Pipeline
    import time
    
    pipeline = RouterV6Pipeline(
        verbose=False,
        enable_routability_analysis=False,
    )
    
    start = time.time()
    result = pipeline.run(temper_pcb)
    elapsed = time.time() - start
    
    print(f"\n{'='*70}")
    print("RESULTS")
    print(f"{'='*70}")
    print(f"Components:   {len(result.pcb.components)}")
    print(f"Layers:       {len(result.stage2.skeletons)}")
    print(f"Widths:       {len(result.stage2.channel_widths)}")
    print(f"Runtime:      {elapsed:.2f}s")
    
    # Show layer details
    print(f"\nLayer Details:")
    for layer_name, skeleton in result.stage2.skeletons.items():
        print(f"  {layer_name:10s}: {skeleton.graph.number_of_nodes()} nodes, {skeleton.graph.number_of_edges()} edges")
    
    # Check design rules
    if result.pcb.design_rules:
        dr = result.pcb.design_rules
        print(f"\nDesign Rules:")
        print(f"  Default trace: {dr.default_trace_width_mm:.3f}mm")
        print(f"  Default clear: {dr.default_clearance_mm:.3f}mm")
        print(f"  Net classes:   {len(dr.net_classes)}")
    
    print(f"\n✅ Router pipeline API works correctly!")
    sys.exit(0)
    
except Exception as e:
    print(f"\n❌ Pipeline failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
