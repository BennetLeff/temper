# Operation Clearance: Debugging & Fixing Static DRC Violations

## Problem Statement
Despite implementing "Exact SDF" and "Path Simplification", the router produces traces that short against static obstacles (e.g., `AC_L` vs `CGND`).
**Suspect**: The geometric clearance condition is mathematically incorrect or the obstacle map is incomplete.

---

## Hypotheses

### H1: The "Centerline Fallacy" (High Probability)
**Theory**: We verify that the trace *centerline* is `clearance_mm` away from obstacles.
**Reality**: The trace has width $W$. The centerline must be $W/2 + \text{clearance}$ away.
**Evidence**: Current code uses `min_clearance_margin = default_clearance_mm`.
**Prediction**: Adding `trace_width / 2` to the margin will fix ~90% of shorts.

### H2: Missing Obstacles
**Theory**: The `RoutingSpace` extractor ignores certain features (e.g., edge cuts, complex pad shapes, or locked traces).
**Test**: Visual audit of the generated SDF vs the actual board.

### H3: Sampling Aliasing
**Theory**: The 0.1mm step size in `PathSimplifier` hops over small obstacle corners.
**Test**: Reduce step size to 0.01mm or implementation "Capsule" intersection checks.

---

## Testing Plan

### Phase 1: Verify & Fix Logic (H1)
1.  **Review Code**: Check `pipeline.py` calculation of `min_clearance_margin`.
2.  **Experiment Fix**: Update the margin to include `width/2`.
3.  **Run Profile**: Route 5 nets.
4.  **Verify**: Check if `AC_L` shorts are gone.

### Phase 2: Diagnostic Visualization (If H1 fails)
1.  **Tool**: Create `scripts/debug_sdf.py` to visualize the SDF and obstacle map.
2.  **Output**: `sdf_layer_name.png` with overlay of the routed path.
3.  **Analysis**:
    *   If path goes through "safe" SDF (green) but shorts in KiCad -> **H2 (Missing Obstacle)**.
    *   If path goes through "unsafe" SDF (red) -> **H3 (Simplifier Bug)**.

### Phase 3: Regression Suite
1.  **Unit Test**: Create `tests/routing/test_clearance_math.py`.
    *   Setup: Obstacle at (10, 10). Trace width 0.5mm, Clearance 0.2mm.
    *   Test: Path at (10.4, 0) -> (10.4, 20).
    *   Expected: Invalid (Dist 0.4 < 0.25 + 0.2).
    *   Current Behavior: Valid (Dist 0.4 > 0.2).

---

## Execution Order
1.  **Immediate**: Fix H1 (Add width/2 to margin).
2.  **Verify**: Run `run_router_v6.py --max-nets 5` + `check_drc_v6.py`.
3.  **Fallback**: If shorts persist, execute Phase 2 (Visualization).
