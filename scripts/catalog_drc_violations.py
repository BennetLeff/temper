#!/usr/bin/env python3
"""
Catalog and classify DRC violations from KiCad PCB files.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# Add packages/temper-placer/src to sys.path
sys.path.append(str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

try:
    from temper_placer.validation.drc import KiCadDRCValidator
except ImportError as e:
    print(f"Error: Missing dependencies. {e}")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Catalog and classify DRC violations")
    parser.add_argument("--pcb", type=str, required=True, help="Path to .kicad_pcb file")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    pcb_path = Path(args.pcb)
    if not pcb_path.exists():
        print(f"Error: PCB file not found: {pcb_path}")
        sys.exit(1)

    validator = KiCadDRCValidator()
    if not validator.is_available():
        print("Error: kicad-cli not available")
        sys.exit(1)

    print(f"Running DRC on {pcb_path}...")
    result = validator.run_drc(pcb_path)

    if not result.success:
        print(f"Error: DRC failed. {result.raw_output}")
        sys.exit(1)

    # Aggregate by type
    type_counts = Counter([v.violation_type.value for v in result.violations])
    
    # Aggregate by component
    comp_counts = Counter()
    for v in result.violations:
        for ref in v.affected_items:
            comp_counts[ref] += 1

    if args.json:
        output = {
            "pcb": str(pcb_path),
            "summary": {
                "errors": result.error_count,
                "warnings": result.warning_count,
                "total": result.total_violations
            },
            "by_type": dict(type_counts),
            "by_component": dict(comp_counts.most_common(20)),
            "violations": [v.to_dict() for v in result.violations]
        }
        print(json.dumps(output, indent=2))
    else:
        print("\n" + "="*50)
        print(f"DRC VIOLATION CATALOG: {pcb_path.name}")
        print("="*50)
        print(f"Total violations: {result.total_violations} ({result.error_count} errors, {result.warning_count} warnings)")
        
        print("\nBy Type:")
        for vtype, count in type_counts.most_common():
            print(f"  {vtype:<20}: {count}")
            
        print("\nTop Affected Components:")
        for ref, count in comp_counts.most_common(10):
            print(f"  {ref:<20}: {count}")

if __name__ == "__main__":
    main()
