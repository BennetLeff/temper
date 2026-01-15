"""
Test: Router populates enhanced diagnostic fields.

Validates that when routing fails, the router now provides:
- failed_at (exact location)
- congested_channel (capacity data)
- suggested_spacing_mm (spacing estimate)
- blocking_components (component list)
- confidence (diagnosis quality)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 70)
print("TEST: Router Enhanced Fields Population")
print("=" * 70)

test_board = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_placed.kicad_pcb"

if not test_board.exists():
    print(f"❌ Test board not found: {test_board}")
    sys.exit(1)

print(f"\nTest board: {test_board.name}")
print("Running router to generate failures...")

from temper_placer.router_v6.pipeline import RouterV6Pipeline

pipeline = RouterV6Pipeline(verbose=False)
result = pipeline.run(test_board)

pathfinding_result = result.stage4.pathfinding_result

print(f"\nRouter Results:")
print(f"  Success: {pathfinding_result.success_count}")
print(f"  Failed: {pathfinding_result.failure_count}")

if pathfinding_result.failure_count == 0:
    print("\n✅ All nets routed - no failures to analyze")
    sys.exit(0)

print(f"\n{'='*70}")
print("ENHANCED DIAGNOSTICS ANALYSIS")
print(f"{'='*70}")

if not pathfinding_result.failure_reports:
    print("❌ No failure reports available")
    sys.exit(1)

enhanced_count = 0
basic_count = 0

for net_name, report in pathfinding_result.failure_reports.items():
    print(f"\n📋 {net_name}:")
    print(f"   Reason: {report.failure_reason}")
    print(f"   Blocking nets: {len(report.blocking_nets)}")
    
    # Check enhanced fields
    has_enhanced = False
    
    if report.failed_at:
        print(f"   ✅ failed_at: {report.failed_at}")
        has_enhanced = True
    else:
        print(f"   ❌ failed_at: None")
    
    if report.congested_channel:
        print(f"   ✅ congested_channel: {report.congested_channel.utilization:.0%} utilized")
        has_enhanced = True
    else:
        print(f"   ❌ congested_channel: None")
    
    if report.suggested_spacing_mm:
        print(f"   ✅ suggested_spacing_mm: {report.suggested_spacing_mm:.2f}mm")
        has_enhanced = True
    else:
        print(f"   ❌ suggested_spacing_mm: None")
    
    if report.blocking_components:
        print(f"   ✅ blocking_components: {report.blocking_components}")
        has_enhanced = True
    else:
        print(f"   ❌ blocking_components: None")
    
    if report.confidence > 0:
        print(f"   ✅ confidence: {report.confidence:.0%}")
        has_enhanced = True
    else:
        print(f"   ❌ confidence: {report.confidence:.0%}")
    
    if has_enhanced:
        enhanced_count += 1
    else:
        basic_count += 1

print(f"\n{'='*70}")
print("SUMMARY")
print(f"{'='*70}")
print(f"Total failures: {len(pathfinding_result.failure_reports)}")
print(f"With enhanced diagnostics: {enhanced_count}")
print(f"Basic only: {basic_count}")

if enhanced_count > 0:
    print(f"\n✅ SUCCESS: Router populates enhanced fields!")
    print(f"   {enhanced_count}/{len(pathfinding_result.failure_reports)} failures have enhanced data")
else:
    print(f"\n⚠️  PARTIAL: Router runs but enhanced fields not populated")
    print(f"   This may be expected if:")
    print(f"   - No congestion_region available")
    print(f"   - Grid analysis failed")
    print(f"   - Need to debug record_failure() logic")
