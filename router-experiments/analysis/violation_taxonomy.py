#!/usr/bin/env python3
"""
Violation Taxonomy Script (temper-caqw.1)

Analyzes routing violations from the test board and categorizes them by type
and root cause to identify where the real leverage is for fixes.

Usage:
    python violation_taxonomy.py <pcb_file>

Example:
    python violation_taxonomy.py ../routed_v5_test.kicad_pcb
"""

import sys
import argparse
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Dict, Tuple
import subprocess
import json
import shutil


class ViolationCategory(Enum):
    """Taxonomy categories for routing violations."""
    ZONE_BLEEDING = auto()       # HV clearance incorrectly applied in signal areas
    VIA_PLACEMENT = auto()        # Via-to-via, via-to-trace, via-to-pad conflicts
    TRACE_CROSSING = auto()       # Same-layer trace intersections
    CLEARANCE_INSUFFICIENT = auto()  # Trace-to-trace too close
    PAD_ENTRY = auto()            # Violations at component pads
    LAYER_CONFLICT = auto()       # Wrong layer usage for net class
    UNKNOWN = auto()              # Uncategorized


@dataclass
class CategorizedViolation:
    """A violation with its assigned category and metadata."""
    category: ViolationCategory
    violation_type: str
    description: str
    nets: List[str]
    position: Tuple[float, float] | None
    severity: str
    
    
@dataclass
class TaxonomyReport:
    """Aggregate taxonomy analysis results."""
    total_violations: int
    by_category: Dict[ViolationCategory, int]
    by_net: Dict[str, int]
    by_quadrant: Dict[str, int]
    violations: List[CategorizedViolation]


def find_kicad_cli() -> Path | None:
    """Find kicad-cli executable."""
    # Check PATH first
    cli_path = shutil.which("kicad-cli")
    if cli_path:
        return Path(cli_path)
    
    # Check standard locations
    standard_paths = [
        "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
        "/Applications/KiCad 8.0/KiCad.app/Contents/MacOS/kicad-cli",
        "/Applications/KiCad 7.0/KiCad.app/Contents/MacOS/kicad-cli",
        "/usr/bin/kicad-cli",
        "/usr/local/bin/kicad-cli",
    ]
    
    for path_str in standard_paths:
        path = Path(path_str)
        if path.exists():
            return path
    
    return None


def run_kicad_drc(pcb_path: Path) -> List[Dict]:
    """
    Run KiCad DRC and return violations as JSON.
    
    Args:
        pcb_path: Path to .kicad_pcb file
        
    Returns:
        List of violation dictionaries from KiCad DRC JSON output
    """
    kicad_cli = find_kicad_cli()
    if not kicad_cli:
        print("ERROR: kicad-cli not found!")
        print("Please install KiCad 7+ or add kicad-cli to your PATH.")
        sys.exit(1)
    
    print(f"Using kicad-cli: {kicad_cli}")
    
    # Create temp file for JSON output
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tf:
        output_path = Path(tf.name)
    
    try:
        # Run DRC
        cmd = [
            str(kicad_cli),
            "pcb",
            "drc",
            "--format", "json",
            "--severity-all",
            "--units", "mm",
            "--output", str(output_path),
            str(pcb_path),
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        
        if result.returncode != 0:
            print(f"ERROR: kicad-cli failed with code {result.returncode}")
            if result.stderr:
                print(f"stderr: {result.stderr}")
            if result.stdout:
                print(f"stdout: {result.stdout}")
            sys.exit(1)
        
        # Read JSON output from file
        if not output_path.exists():
            print(f"ERROR: DRC output file not created: {output_path}")
            sys.exit(1)
        
        json_text = output_path.read_text()
        drc_data = json.loads(json_text)
        violations = drc_data.get("violations", [])
        
        return violations
        
    except subprocess.TimeoutExpired:
        print("ERROR: DRC timed out after 120 seconds")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse DRC JSON output: {e}")
        if output_path.exists():
            print(f"JSON content preview: {output_path.read_text()[:500]}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Failed to run DRC: {e}")
        sys.exit(1)
    finally:
        # Cleanup temp file
        if output_path.exists():
            output_path.unlink()


def categorize_violation(violation: Dict, board_size: Tuple[float, float]) -> ViolationCategory:
    """
    Categorize a DRC violation based on its type and context.
    
    Args:
        violation: Violation dict from KiCad DRC JSON
        board_size: (width, height) of board in mm
        
    Returns:
        ViolationCategory enum value
    """
    vtype = violation.get("type", "").lower()
    desc = violation.get("description", "").lower()
    
    # Extract merged description from items too
    items = violation.get("items", [])
    item_descs = " ".join([it.get("description", "").lower() for it in items])
    full_text = f"{desc} {item_descs}"
    
    # Zone bleeding: HV clearance issues
    if any(keyword in full_text for keyword in ["zone", "copper pour", "fill", "pour"]):
        return ViolationCategory.ZONE_BLEEDING
    
    # Via placement issues  
    if any(keyword in full_text for keyword in ["via", "hole to hole", "buried", "blind"]):
        return ViolationCategory.VIA_PLACEMENT
    
    if any(keyword in vtype for keyword in ["hole_clearance", "hole_near_hole", "via_dangling"]):
        return ViolationCategory.VIA_PLACEMENT
    
    # Trace crossing / shorts
    if any(keyword in vtype for keyword in ["short", "track"]):
        return ViolationCategory.TRACE_CROSSING
    
    if any(keyword in full_text for keyword in ["track", "trace", "segment"]):
        # Check if it's actually a crossing
        if "short" in vtype or "shorting" in desc:
            return ViolationCategory.TRACE_CROSSING
    
    # Pad entry issues
    if any(keyword in full_text for keyword in ["pad to pad", "pad on layers", "footprint"]):
        return ViolationCategory.PAD_ENTRY
    
    if any(keyword in vtype for keyword in ["pad_near", "padstack", "footprint_type_mismatch"]):
        return ViolationCategory.PAD_ENTRY
    
    # Clearance issues
    if "clearance" in vtype:
        # Try to distinguish zone bleeding from normal clearance
        # High voltage or critical power nets often involve zone issues or creepage
        hv_nets = ["vcc_hv", "ac_l", "ac_n", "gate_h", "gate_l", "sw_node", "pgnd", "hv_", "dc_bus"]
        if any(hv in full_text for hv in hv_nets):
            return ViolationCategory.ZONE_BLEEDING
        return ViolationCategory.CLEARANCE_INSUFFICIENT
    
    # Unconnected or layer issues
    if any(keyword in vtype for keyword in ["unconnected", "starved", "copper_sliver", "isolated"]):
        return ViolationCategory.LAYER_CONFLICT
    
    # Silkscreen and courtyard are typically not routing issues
    if any(keyword in vtype for keyword in ["silk", "courtyard", "text"]):
        return ViolationCategory.PAD_ENTRY
    
    # Default: unknown
    return ViolationCategory.UNKNOWN


def extract_nets_from_violation(violation: Dict) -> List[str]:
    """
    Extract net names from a DRC violation.
    
    Args:
        violation: Violation dict from KiCad DRC JSON
        
    Returns:
        List of net names involved
    """
    nets = []
    
    # Check items array
    items = violation.get("items", [])
    for item in items:
        # Item may have format like "Track [GND] on F.Cu" or "Track (GND) on F.Cu"
        desc = str(item.get("description", "")) if isinstance(item, dict) else str(item)
        
        # Check for [Net] or (Net)
        for opener, closer in [("[", "]"), ("(", ")")]:
            if opener in desc and closer in desc:
                start = desc.index(opener)
                end = desc.index(closer, start)
                net_name = desc[start+1:end]
                if net_name and net_name not in nets:
                    nets.append(net_name)
    
    # Also check top-level description for any net mentions
    full_desc = violation.get("description", "")
    for part in full_desc.replace("(", " ").replace(")", " ").replace("[", " ").replace("]", " ").split():
        if part.startswith("Net-") or part.startswith("net-"):
            net = part.replace("Net-", "").replace("net-", "").rstrip(".,;:")
            if net and net not in nets:
                nets.append(net)
    
    return nets


def get_board_quadrant(position: Tuple[float, float] | None, board_size: Tuple[float, float]) -> str:
    """
    Determine which quadrant of the board a position is in.
    
    Args:
        position: (x, y) in mm
        board_size: (width, height) in mm
        
    Returns:
        Quadrant name (e.g., "Top-Left", "Bottom-Right")
    """
    if position is None:
        return "Unknown"
    
    x, y = position
    w, h = board_size
    
    mid_x = w / 2
    mid_y = h / 2
    
    if x < mid_x:
        horiz = "Left"
    else:
        horiz = "Right"
    
    if y < mid_y:
        vert = "Top"
    else:
        vert = "Bottom"
    
    return f"{vert}-{horiz}"


def analyze_violations(pcb_path: Path) -> TaxonomyReport:
    """
    Analyze all violations in a PCB file.
    
    Args:
        pcb_path: Path to .kicad_pcb file
        
    Returns:
        TaxonomyReport with categorized violations
    """
    print(f"Loading PCB file: {pcb_path}")
    
    # Use a default board size (Temper board is approximately 100mm x 150mm)
    board_size = (100.0, 150.0)
    print(f"  Assumed board size: {board_size[0]}mm x {board_size[1]}mm")
    
    # Run KiCad DRC
    print("\nRunning KiCad DRC...")
    violations_raw = run_kicad_drc(pcb_path)
    
    print(f"  Found {len(violations_raw)} DRC violations")
    
    # Categorize violations
    print("\nCategorizing violations...")
    categorized: List[CategorizedViolation] = []
    by_category: Dict[ViolationCategory, int] = defaultdict(int)
    by_net: Dict[str, int] = defaultdict(int)
    by_quadrant: Dict[str, int] = defaultdict(int)
    
    debug_count = 0
    for violation in violations_raw:
        # Skip exclusions
        severity = violation.get("severity", "error")
        if severity == "exclusion":
            continue
        
        items = violation.get("items", [])
        
        # Extract position
        pos_data = violation.get("pos", None)
        if pos_data and isinstance(pos_data, dict):
            position = (pos_data.get("x", 0), pos_data.get("y", 0))
        elif items and isinstance(items[0], dict) and "pos" in items[0]:
            # Fallback to first item position
            it_pos = items[0]["pos"]
            position = (it_pos.get("x", 0), it_pos.get("y", 0))
        else:
            position = None
        
        # Categorize
        category = categorize_violation(violation, board_size)
        nets = extract_nets_from_violation(violation)
        quadrant = get_board_quadrant(position, board_size)
        
        categorized.append(CategorizedViolation(
            category=category,
            violation_type=violation.get("type", "unknown"),
            description=violation.get("description", ""),
            nets=nets,
            position=position,
            severity=severity,
        ))
        
        # Update counters
        by_category[category] += 1
        for net in nets:
            by_net[net] += 1
        by_quadrant[quadrant] += 1
    
    total = len(categorized)
    
    return TaxonomyReport(
        total_violations=total,
        by_category=dict(by_category),
        by_net=dict(by_net),
        by_quadrant=dict(by_quadrant),
        violations=categorized,
    )


def format_report(report: TaxonomyReport) -> str:
    """
    Format taxonomy report as human-readable text.
    
    Args:
        report: TaxonomyReport with analysis results
        
    Returns:
        Formatted report string
    """
    lines = [
        "=" * 60,
        "VIOLATION TAXONOMY REPORT",
        "=" * 60,
        "",
        f"Total violations: {report.total_violations}",
        "",
    ]
    
    # By Category
    lines.append("By Category:")
    sorted_cats = sorted(report.by_category.items(), key=lambda x: -x[1])
    for cat, count in sorted_cats:
        pct = 100.0 * count / report.total_violations if report.total_violations > 0 else 0
        cat_name = cat.name.replace("_", " ").title()
        lines.append(f"  {cat_name:25s} {count:4d} ({pct:5.1f}%)")
    
    lines.append("")
    
    # By Net (top 10)
    lines.append("By Net (Top 10):")
    sorted_nets = sorted(report.by_net.items(), key=lambda x: -x[1])
    for net, count in sorted_nets[:10]:
        lines.append(f"  {net:25s} {count:4d} violations")
    
    if len(sorted_nets) > 10:
        lines.append(f"  ... and {len(sorted_nets) - 10} more nets")
    
    lines.append("")
    
    # By Location
    lines.append("By Location (Grid Quadrant):")
    sorted_quads = sorted(report.by_quadrant.items(), key=lambda x: -x[1])
    for quad, count in sorted_quads:
        pct = 100.0 * count / report.total_violations if report.total_violations > 0 else 0
        lines.append(f"  {quad:15s} {count:4d} ({pct:5.1f}%)")
    
    lines.append("")
    
    # Top 3 Root Causes with Recommendations
    lines.append("Top 3 Root Causes:")
    for i, (cat, count) in enumerate(sorted_cats[:3], 1):
        pct = 100.0 * count / report.total_violations if report.total_violations > 0 else 0
        cat_name = cat.name.replace("_", " ").title()
        
        # Recommendation based on category
        if cat == ViolationCategory.ZONE_BLEEDING:
            fix = "Complete zone integration in A* pathfinding (consider zones as obstacles)"
        elif cat == ViolationCategory.VIA_PLACEMENT:
            fix = "Implement via consolidation pass and via keepout checking"
        elif cat == ViolationCategory.CLEARANCE_INSUFFICIENT:
            fix = "Enable net-class-aware pathfinding with proper trace width inflation"
        elif cat == ViolationCategory.TRACE_CROSSING:
            fix = "Add same-layer crossing detection in routing cost function"
        elif cat == ViolationCategory.PAD_ENTRY:
            fix = "Improve pad escape routing and entry angle constraints"
        elif cat == ViolationCategory.LAYER_CONFLICT:
            fix = "Enforce strict layer assignment by net class"
        else:
            fix = "Manual review required"
        
        lines.append(f"  {i}. {cat_name} ({pct:.0f}%) - Fix: {fix}")
    
    lines.append("")
    lines.append("=" * 60)
    
    return "\n".join(lines)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze and categorize routing violations"
    )
    parser.add_argument(
        "pcb_file",
        type=Path,
        help="Path to .kicad_pcb file to analyze"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output report file (default: print to stdout)"
    )
    
    args = parser.parse_args()
    
    if not args.pcb_file.exists():
        print(f"ERROR: File not found: {args.pcb_file}")
        sys.exit(1)
    
    # Analyze violations
    report = analyze_violations(args.pcb_file)
    
    # Format report
    report_text = format_report(report)
    
    # Output
    if args.output:
        args.output.write_text(report_text)
        print(f"\nReport written to: {args.output}")
    else:
        print("\n" + report_text)
    
    # Summary
    unknown_count = report.by_category.get(ViolationCategory.UNKNOWN, 0)
    unknown_pct = 100.0 * unknown_count / report.total_violations if report.total_violations > 0 else 0
    
    print(f"\n✓ Analysis complete!")
    print(f"  Total categorized: {report.total_violations}")
    print(f"  Unknown: {unknown_count} ({unknown_pct:.1f}%)")
    
    if unknown_pct < 5.0:
        print("  ✓ SUCCESS: Unknown category < 5%")
    else:
        print(f"  ⚠ WARNING: Unknown category >= 5% - manual review recommended")


if __name__ == "__main__":
    main()
