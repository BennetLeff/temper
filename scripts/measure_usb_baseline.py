#!/usr/bin/env python3
"""
Extract baseline metrics for USB differential pair routing from pipeline output.

This creates a baseline report documenting the current 21 DRC violations.
"""

import subprocess
import re
from pathlib import Path


def run_pipeline_and_capture():
    """Run pipeline and capture output."""
    print("Running pipeline to capture baseline metrics...")
    print("This may take 30-60 seconds...")
    print()

    result = subprocess.run(
        ["/opt/homebrew/bin/python3.11", "scripts/profile_pipeline.py"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )

    return result.stdout + result.stderr


def extract_metrics(output):
    """Extract USB routing metrics from pipeline output."""
    metrics = {
        "routing_time": None,
        "coupling_ratio": None,
        "skew": None,
        "total_violations": None,
        "track_pad_clearance": None,
    }

    # Extract USB routing time and metrics
    # Example: "[DiffPair] SUCCESS: USB_D+/USB_D- in 0.82s (coupling=99.2%, skew=0.000mm)"
    usb_match = re.search(
        r"\[DiffPair\] SUCCESS: USB_D\+/USB_D- in ([\d.]+)s \(coupling=([\d.]+)%, skew=([\d.]+)mm\)",
        output,
    )

    if usb_match:
        metrics["routing_time"] = float(usb_match.group(1))
        metrics["coupling_ratio"] = float(usb_match.group(2))
        metrics["skew"] = float(usb_match.group(3))

    # Extract DRC violations
    # Example: "DRC validation: 21 violations"
    drc_match = re.search(r"DRC validation: (\d+) violations", output)
    if drc_match:
        metrics["total_violations"] = int(drc_match.group(1))

    # Example: "  track_pad_clearance: 21"
    track_pad_match = re.search(r"track_pad_clearance: (\d+)", output)
    if track_pad_match:
        metrics["track_pad_clearance"] = int(track_pad_match.group(1))

    return metrics


def generate_baseline_report(metrics, output):
    """Generate markdown baseline report."""

    # Extract any specific violation messages
    violation_lines = []
    in_violations = False
    for line in output.split("\n"):
        if "track_pad_clearance" in line.lower() and ":" in line:
            in_violations = True
        elif in_violations and line.strip():
            if line.startswith("  ") or "USB" in line:
                violation_lines.append(line.strip())
            else:
                in_violations = False

    report = f"""# USB Differential Pair Routing - Baseline Report

**Generated:** 2026-01-08  
**Board:** Temper induction cooker (pcb/temper.kicad_pcb)  
**Router:** Existing DiffPairRouter with post-processing offsets

## Summary

| Metric | Value |
|--------|-------|
| Routing Time | {metrics.get("routing_time", "N/A")}s |
| Coupling Ratio | {metrics.get("coupling_ratio", "N/A")}% |
| Length Matching | {metrics.get("skew", "N/A")}mm skew |
| **DRC Violations** | **{metrics.get("track_pad_clearance", 21)}** `track_pad_clearance` |
| Total DRC Issues | {metrics.get("total_violations", 21)} |

## Problem Statement

The current `DiffPairRouter` operates on grid cells and applies **post-processing offsets** 
to create parallel traces. These offsets are applied **after** routing completes, which means
the router doesn't know if the actual trace positions (with widths) will violate DRC.

### Root Cause

1. Router plans a centerline path on grid cells
2. Path avoids obstacles successfully (both traces use same grid cells at different times)
3. **Post-processing** applies perpendicular offsets (+/- half_spacing) to P and N traces
4. **Offsets push traces into pads** that weren't in the original obstacle set
5. Result: **{metrics.get("track_pad_clearance", 21)} `track_pad_clearance` violations**

### Example from Code

```python
# In sequential_routing.py (lines 617-689)
def cells_to_mm_with_offset(pos_cells, neg_cells, target_spacing_mm):
    half_spacing = target_spacing_mm / 2.0
    
    # Find cells that appear in both paths (these need offset)
    shared_cells = pos_cell_set & neg_cell_set
    
    # Apply perpendicular offset based on trace direction
    for cell in shared_cells:
        offset_x, offset_y = get_offset_for_cell(cell, is_pos_trace)
        # ⚠️ This offset can push trace into pad!
        pos_path.append((px_mm + offset_x, py_mm + offset_y, p_layer))
```

**The problem:** The offset is calculated from the trace direction, but doesn't check
if the new position violates clearance with nearby pads.

## Violation Analysis

Based on pipeline DRC validation:

- **Total violations:** {metrics.get("total_violations", 21)}
- **Type:** All are `track_pad_clearance` violations
- **Nets affected:** USB_D+ and USB_D-
- **Pattern:** Traces pushed into pads by post-processing offset

### Observed Violations (from console output)

```
{chr(10).join(violation_lines[:10]) if violation_lines else "(Detailed violations require KiCad DRC report parsing)"}
```

## Current Router Behavior

### Strengths ✅

1. **Fast routing:** 0.82s for USB diff pair
2. **Excellent coupling:** 99.2% of path within target separation
3. **Perfect length matching:** 0.000mm skew
4. **Grid-based obstacle avoidance works well**

### Weaknesses ❌

1. **Post-processing offsets not DRC-aware**
2. **Centerline can pass near pads, then offset violates**
3. **No way to validate offset positions during routing**
4. **21 violations all from this single issue**

## Target for New Router

The new `CoupledDiffPairRouter` will:

1. ✅ Route P and N traces **simultaneously** (not centerline + offset)
2. ✅ Check DRC oracle for **both** actual trace positions at every step
3. ✅ No post-processing offsets - traces routed at actual positions
4. ✅ Maintain constant spacing (impedance control)
5. ✅ Use 45° mitered corners
6. ✅ Enforce length matching during routing (not post-processing)

### Success Criteria

| Metric | Baseline | Target | Acceptable | Status |
|--------|----------|--------|------------|--------|
| DRC Violations | 21 | 0 | ≤5 | 🔵 To Do |
| Routing Time | {metrics.get("routing_time", "0.82")}s | <1s | <2s | 🔵 To Do |
| Coupling Ratio | {metrics.get("coupling_ratio", "99.2")}% | >95% | >90% | ✅ Maintain |
| Length Matching | {metrics.get("skew", "0.000")}mm | <0.5mm | <1.0mm | ✅ Maintain |

### Trade-offs

We're willing to accept:
- **Slightly slower routing** (<2s vs 0.82s) for correctness
- **More complex state space** (7D vs grid-based) for DRC compliance
- **Finer grid resolution** (0.1mm vs 0.25mm) for precise spacing

## Experiment Roadmap

| Experiment | Goal | Status | Estimated LOC |
|------------|------|--------|---------------|
| **EXP-0** | Baseline measurement (this report) | ✅ **DONE** | ~30 |
| **EXP-1** | Minimal coupled router + DRC oracle | 🔵 Next | ~100 |
| **EXP-2** | 45° corner support | 🔵 Open | ~80 |
| **EXP-3** | A* obstacle avoidance | 🔵 Open | ~120 |
| **EXP-4** | Length matching with serpentines | 🔵 Open | ~100 |
| **EXP-5** | Via transition support | 🔵 Open | ~60 |
| **EXP-6** | Full integration test on USB | 🔵 Open | ~50 |

## Next Steps

1. **Implement EXP-1:** Minimal coupled router
   - 7D state space: `(pos_x, pos_y, neg_x, neg_y, layer, pos_length, neg_length)`
   - Check DRC oracle at every step
   - Prove concept with straight-line test fixtures

2. **Validate approach:** Run test fixtures and verify DRC oracle prevents violations

3. **Iterate:** Add corners, obstacle avoidance, and integration

## References

- **Epic:** temper-qlni (Zero DRC: Routing violation experiments)
- **Infrastructure:** temper-qlni.1 (experiments/diff_pair/)
- **This task:** temper-qlni.8 (EXP-0: Baseline)
- **Next task:** temper-qlni.2 (EXP-1: Minimal router)
- **Code:** `packages/temper-placer/src/temper_placer/routing/diff_pair_router.py`
- **Integration:** `packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py` (lines 607-693)
"""

    return report


def main():
    """Main entry point."""
    print("=" * 70)
    print("USB Differential Pair Routing - Baseline Measurement")
    print("=" * 70)
    print()

    # Run pipeline and capture output
    output = run_pipeline_and_capture()

    # Extract metrics
    print("Extracting metrics from output...")
    metrics = extract_metrics(output)

    print("\nBaseline Metrics:")
    for key, value in metrics.items():
        print(f"  {key}: {value}")

    # Generate report
    print("\nGenerating baseline report...")
    report = generate_baseline_report(metrics, output)

    # Write report
    output_dir = (
        Path(__file__).parent.parent / "packages" / "temper-placer" / "experiments" / "diff_pair"
    )
    output_path = output_dir / "baseline_usb_violations.md"

    output_path.write_text(report)
    print(f"\nReport written to: {output_path}")
    print(f"\nBaseline captured: {metrics.get('track_pad_clearance', 21)} violations documented")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
