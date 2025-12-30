#!/usr/bin/env python3
"""
Compare two KiCad DRC reports and show the delta in violations.
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict


@dataclass
class DRCDelta:
    """Change in violations between two DRC runs."""
    violation_type: str
    before: int
    after: int

    @property
    def delta(self) -> int:
        return self.after - self.before

    @property
    def improvement(self) -> bool:
        return self.delta < 0


def compare_drc_reports(before_json: Path, after_json: Path) -> Dict[str, DRCDelta]:
    """Compare two DRC reports and show improvements."""
    
    with open(before_json) as f:
        before = json.load(f)
    with open(after_json) as f:
        after = json.load(f)
    
    def count_violations(report):
        counts = {}
        for v in report.get("violations", []):
            vtype = v.get("type", "unknown")
            counts[vtype] = counts.get(vtype, 0) + 1
        return counts
    
    before_counts = count_violations(before)
    after_counts = count_violations(after)
    
    all_types = set(before_counts.keys()) | set(after_counts.keys())
    deltas = {}
    
    for vtype in all_types:
        deltas[vtype] = DRCDelta(
            violation_type=vtype,
            before=before_counts.get(vtype, 0),
            after=after_counts.get(vtype, 0)
        )
    
    return deltas


def print_comparison(deltas: Dict[str, DRCDelta]):
    """Pretty print DRC comparison."""
    print("\n📊 DRC Improvement Report")
    print("=" * 60)
    print(f"{ 'Violation Type':<30} {'Before':>10} {'After':>10} {'Δ':>8}")
    print("-" * 60)
    
    sorted_deltas = sorted(deltas.values(), key=lambda d: d.delta)
    
    for delta in sorted_deltas:
        symbol = "✓" if delta.improvement else ("✗" if delta.delta > 0 else "−")
        print(f"{symbol} {delta.violation_type:<28} {delta.before:>10} {delta.after:>10} {delta.delta:>+8}")
    
    total_before = sum(d.before for d in deltas.values())
    total_after = sum(d.after for d in deltas.values())
    total_delta = total_after - total_before
    
    print("-" * 60)
    print(f"{ 'TOTAL':<30} {total_before:>10} {total_after:>10} {total_delta:>+8}")
    print("=" * 60)
    
    if total_delta < 0:
        pct_improvement = abs(total_delta) / total_before * 100 if total_before > 0 else 0
        print(f"\n🎉 {pct_improvement:.1f}% reduction in violations!")
    else:
        print(f"\n⚠️  Violations increased by {total_delta}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/compare_drc_reports.py <before.json> <after.json>")
        sys.exit(1)
        
    before_path = Path(sys.argv[1])
    after_path = Path(sys.argv[2])
    
    deltas = compare_drc_reports(before_path, after_path)
    print_comparison(deltas)
