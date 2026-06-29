#!/usr/bin/env python3
"""
Simple BOM-based diff tool for atopile builds.
Handles grouped designators (e.g., "U1,U2").
"""
import csv
import sys
from pathlib import Path


def load_bom(bom_path: Path) -> dict[str, dict[str, str]]:
    components: dict[str, dict[str, str]] = {}
    if not bom_path or not bom_path.exists():
        return components
    with open(bom_path, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            designator_str = row.get('Designator', '')
            # Split designators like "U1,U2" or "U1, U2"
            designators = [d.strip() for d in designator_str.replace('"', '').split(',')]
            for des in designators:
                if des:
                    components[des] = row
    return components

def diff_boms(bom1_path: Path, bom2_path: Path):
    bom1 = load_bom(bom1_path)
    bom2 = load_bom(bom2_path)

    if not bom1 and bom2:
        print(f"BOM 1 ({bom1_path}) is empty or missing. All components in BOM 2 are new.")

    all_designators = set(bom1.keys()) | set(bom2.keys())

    added = []
    removed = []
    changed = []

    for des in sorted(all_designators):
        if des not in bom1:
            added.append(des)
        elif des not in bom2:
            removed.append(des)
        else:
            # Compare footprints or MPN
            if bom1[des].get('Footprint') != bom2[des].get('Footprint') or \
               bom1[des].get('Comment') != bom2[des].get('Comment'):
                changed.append(des)

    print(f"--- Logical Diff: {bom1_path} vs {bom2_path} ---")
    if added:
        print(f"Added components ({len(added)}): {', '.join(added)}")
    if removed:
        print(f"Removed components ({len(removed)}): {', '.join(removed)}")
    if changed:
        print(f"Modified properties ({len(changed)}): {', '.join(changed)}")

    if not (added or removed or changed):
        print("No logical changes detected in components.")

def main():
    if len(sys.argv) < 3:
        print("Usage: ato_diff.py <bom1.csv> <bom2.csv>")
        sys.exit(1)

    diff_boms(Path(sys.argv[1]), Path(sys.argv[2]))

if __name__ == "__main__":
    main()
