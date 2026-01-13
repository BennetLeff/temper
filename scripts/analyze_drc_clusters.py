import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class ViolationCluster:
    violation_type: str
    items: tuple[str, str]
    count: int
    examples: List[Dict[str, Any]]


def analyze_drc(report_path: str):
    try:
        with open(report_path, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Report file {report_path} not found.")
        return

    violations = data.get("violations", [])
    clusters = defaultdict(list)

    for v in violations:
        desc = v.get("description", "Unknown")
        items = []
        for item in v.get("items", []):
            # Extract relevant info (net, type)
            txt = item.get("item", "Unknown")
            if "net" in item:
                txt += f" ({item['net']})"
            items.append(txt)

        items_key = tuple(sorted(items))
        key = (desc, items_key)
        clusters[key].append(v)

    # Summarize
    print(f"Loaded {len(violations)} violations.")
    print("-" * 60)

    sorted_clusters = sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True)

    category_counts = defaultdict(int)

    for (desc, items), v_list in sorted_clusters:
        count = len(v_list)
        category_counts[desc] += count

        # Determine specific reason category
        reason = "Unknown"
        if "shorting" in desc:
            reason = "Short Circuit"
        elif "Clearance" in desc:
            val_match = [
                x for x in desc.split() if "actual" in desc and x.replace(".", "").isdigit()
            ]
            reason = "Clearance Violation"
        elif "footprint library" in desc:
            reason = "Library Missing"
        elif "solder mask" in desc:
            reason = "Mask Bridge"
        elif "unconnected end" in desc:
            reason = "Dangling Track"

        print(f"[{reason}] Count: {count}")
        print(f"  Type: {desc}")
        print(f"  Items: {', '.join(items)}")

        # Detailed dump for high-priority errors
        if reason in ["Short Circuit", "Clearance Violation", "Dangling Track"]:
            print("  Locations:")
            for i, v in enumerate(v_list[:5]):  # Show first 5
                print(f"    Violation {i + 1}:")
                for item in v.get("items", []):
                    print(
                        f"      - {item.get('description', 'Unknown')} at {item.get('pos', 'Unknown')}"
                    )
        print("-" * 40)


if __name__ == "__main__":
    analyze_drc("drc_results/drc_report_temper_router_v6_output.json")
