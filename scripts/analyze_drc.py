#!/usr/bin/env python3
"""
DRC Analysis Tool: Categorize and summarize DRC violations.

Produces a structured breakdown of:
1. Unconnected items by net category (Ground, Power, Signal)
2. Violation types (clearance, shorts, etc.)
3. Summary statistics for comparison
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# Net categorization
GROUND_NETS = {'GND', 'PGND', 'CGND', 'AGND', 'DGND'}
POWER_NETS = {'+3V3', '+5V', '+15V', '+12V', 'VCC', 'VDD', 'VCC_BOOT'}
HIGH_CURRENT_NETS = {'AC_L', 'AC_N', 'DC_BUS+', 'DC_BUS-', 'SW_NODE'}

def categorize_net(net_name: str) -> str:
    """Categorize a net by its type."""
    if net_name in GROUND_NETS:
        return "Ground"
    elif net_name in POWER_NETS:
        return "Power"
    elif net_name in HIGH_CURRENT_NETS:
        return "HighCurrent"
    else:
        return "Signal"

def extract_net_from_description(desc: str) -> str:
    """Extract net name from DRC item description."""
    # Format: "Pad X [NET_NAME] of COMPONENT on LAYER"
    import re
    match = re.search(r'\[([^\]]+)\]', desc)
    return match.group(1) if match else "Unknown"

def analyze_drc_report(report_path: Path) -> dict:
    """Analyze a DRC JSON report and return categorized summary."""
    with open(report_path) as f:
        report = json.load(f)
    
    result = {
        "source": report.get("source", "unknown"),
        "date": report.get("date", datetime.now().isoformat()),
        "unconnected": {
            "total": 0,
            "by_category": defaultdict(int),
            "by_net": defaultdict(int),
        },
        "violations": {
            "total": 0,
            "by_type": defaultdict(int),
        },
    }
    
    # Analyze unconnected items
    for item in report.get("unconnected_items", []):
        result["unconnected"]["total"] += 1
        for sub_item in item.get("items", []):
            net = extract_net_from_description(sub_item.get("description", ""))
            category = categorize_net(net)
            result["unconnected"]["by_net"][net] += 1
            result["unconnected"]["by_category"][category] += 1
    
    # Analyze other violations
    for item in report.get("violations", []):
        result["violations"]["total"] += 1
        vtype = item.get("type", "unknown")
        result["violations"]["by_type"][vtype] += 1
    
    # Convert defaultdicts to regular dicts for JSON serialization
    result["unconnected"]["by_category"] = dict(result["unconnected"]["by_category"])
    result["unconnected"]["by_net"] = dict(result["unconnected"]["by_net"])
    result["violations"]["by_type"] = dict(result["violations"]["by_type"])
    
    return result

def print_summary(analysis: dict, label: str = ""):
    """Print a formatted summary of the analysis."""
    print(f"\n{'='*60}")
    print(f"DRC Analysis: {label or analysis['source']}")
    print(f"Date: {analysis['date']}")
    print(f"{'='*60}")
    
    print(f"\n📍 UNCONNECTED ITEMS: {analysis['unconnected']['total']}")
    print("-" * 40)
    
    print("By Category:")
    for cat in ["Ground", "Power", "HighCurrent", "Signal"]:
        count = analysis["unconnected"]["by_category"].get(cat, 0)
        if count > 0:
            print(f"  {cat:12s}: {count:3d}")
    
    print("\nTop Nets:")
    sorted_nets = sorted(
        analysis["unconnected"]["by_net"].items(),
        key=lambda x: x[1],
        reverse=True
    )[:10]
    for net, count in sorted_nets:
        cat = categorize_net(net)
        print(f"  {net:15s}: {count:3d} ({cat})")
    
    if analysis["violations"]["total"] > 0:
        print(f"\n⚠️  OTHER VIOLATIONS: {analysis['violations']['total']}")
        print("-" * 40)
        for vtype, count in sorted(analysis["violations"]["by_type"].items()):
            print(f"  {vtype:20s}: {count:3d}")
    
    print()

def compare_reports(before: dict, after: dict, change_description: str):
    """Compare two DRC analyses and show delta."""
    print(f"\n{'#'*60}")
    print(f"CHANGE: {change_description}")
    print(f"{'#'*60}")
    
    before_total = before["unconnected"]["total"]
    after_total = after["unconnected"]["total"]
    delta = after_total - before_total
    
    print(f"\nUnconnected Items: {before_total} → {after_total} ({'+' if delta > 0 else ''}{delta})")
    
    print("\nBy Category Delta:")
    all_cats = set(before["unconnected"]["by_category"].keys()) | set(after["unconnected"]["by_category"].keys())
    for cat in ["Ground", "Power", "HighCurrent", "Signal"]:
        if cat in all_cats:
            b = before["unconnected"]["by_category"].get(cat, 0)
            a = after["unconnected"]["by_category"].get(cat, 0)
            d = a - b
            if d != 0:
                print(f"  {cat:12s}: {b:3d} → {a:3d} ({'+' if d > 0 else ''}{d})")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: analyze_drc.py <drc_report.json> [label]")
        print("       analyze_drc.py --compare <before.json> <after.json> <change_description>")
        sys.exit(1)
    
    if sys.argv[1] == "--compare" and len(sys.argv) >= 5:
        before = analyze_drc_report(Path(sys.argv[2]))
        after = analyze_drc_report(Path(sys.argv[3]))
        change_desc = " ".join(sys.argv[4:])
        compare_reports(before, after, change_desc)
    else:
        report_path = Path(sys.argv[1])
        label = sys.argv[2] if len(sys.argv) > 2 else ""
        analysis = analyze_drc_report(report_path)
        print_summary(analysis, label)
