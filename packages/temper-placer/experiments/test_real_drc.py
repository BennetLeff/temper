"""
Test actual KiCad DRC integration.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 70)
print("Testing Real KiCad DRC Integration")
print("=" * 70)

temper_pcb = Path(__file__).parent.parent.parent.parent / "pcb" / "temper_routed.kicad_pcb"

if not temper_pcb.exists():
    print(f"❌ PCB not found: {temper_pcb}")
    sys.exit(1)

print(f"\n📄 PCB: {temper_pcb.name}")

# Test 1: Run actual KiCad DRC
print("\n" + "=" * 70)
print("TEST 1: Run Actual KiCad DRC")
print("=" * 70)

from temper_placer.io.kicad_drc import run_drc_and_report

result = run_drc_and_report(temper_pcb, verbose=True)

# Test 2: Check if clean
print("\n" + "=" * 70)
print("TEST 2: Check if PCB is Clean")
print("=" * 70)

from temper_placer.io.kicad_drc import check_pcb_clean

is_clean = check_pcb_clean(temper_pcb, verbose=True)

if is_clean:
    print("\n✅ PCB is DRC clean!")
else:
    print(f"\n❌ PCB has {result.error_count} DRC errors")

# Test 3: Analyze violations
print("\n" + "=" * 70)
print("TEST 3: Violation Analysis")
print("=" * 70)

if result.total_count > 0:
    print(f"\nViolation breakdown:")
    print(f"  Total:    {result.total_count}")
    print(f"  Errors:   {result.error_count}")
    print(f"  Warnings: {result.warning_count}")
    
    # Group by severity
    errors = [v for v in result.violations if v.is_error]
    warnings = [v for v in result.violations if v.is_warning]
    
    if errors:
        print(f"\n🔴 Errors ({len(errors)}):")
        for v in errors[:10]:  # Show first 10
            print(f"   - {v.type}: {v.description[:60]}")
    
    if warnings:
        print(f"\n⚠️  Warnings ({len(warnings)}):")
        for v in warnings[:10]:  # Show first 10
            print(f"   - {v.type}: {v.description[:60]}")
else:
    print("\n✅ No violations!")

# Test 4: Compare with old report
print("\n" + "=" * 70)
print("TEST 4: Compare with Previous Report")
print("=" * 70)

old_report = Path(__file__).parent.parent.parent.parent / "working-drc.json"
if old_report.exists():
    from temper_placer.io.kicad_drc import parse_drc_report
    
    old_result = parse_drc_report(old_report)
    
    print(f"\nOld report (from file):")
    print(f"  Total: {old_result.total_count}")
    print(f"  Errors: {old_result.error_count}")
    
    print(f"\nNew report (actual KiCad DRC):")
    print(f"  Total: {result.total_count}")
    print(f"  Errors: {result.error_count}")
    
    if result.total_count == old_result.total_count:
        print(f"\n✅ Violation counts match!")
    else:
        print(f"\n⚠️  Violation counts differ")
        print(f"   Difference: {result.total_count - old_result.total_count}")
else:
    print(f"\n⚠️  No old report found at {old_report}")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

print(f"""
✅ KiCad DRC integration working!
   - Using actual kicad-cli command
   - Not just reading old reports
   - Real-time DRC checking

Results for {temper_pcb.name}:
   Total violations: {result.total_count}
   Errors: {result.error_count}
   Warnings: {result.warning_count}
   
   Clean: {'✅ YES' if is_clean else '❌ NO'}
""")
