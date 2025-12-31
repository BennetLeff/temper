# Experiment Report: 01-B - Neckdown Strategy

**Date:** 2025-12-30
**Script:** `router-experiments/exp_1_b_neckdown.py`
**Objective:** Verify that `temper-placer` can route fine-pitch (1.27mm) components when appropriate "neckdown" design rules are applied.

## Context
In Experiment 01, we confirmed that 1.27mm pitch headers cannot be routed with standard design rules:
*   **Pitch:** 1.27mm
*   **Pad Width:** 0.8mm
*   **Available Gap:** 1.27 - 0.8 = **0.47mm**
*   **Standard Rule Req:** Trace (0.2) + 2*Clearance (0.2) = **0.60mm**
*   **Conflict:** 0.47mm < 0.60mm (Physics Violation)

## Experiment Setup
We tested three "Neckdown" strategies to fit the trace through the 0.47mm gap.

### Cases Tested

1.  **Standard Rules (Reference)**
    *   Width: 0.2mm, Clearance: 0.2mm (Req: 0.6mm)
    *   Expected: FAIL

2.  **Neckdown 6-mil (0.15mm) + Coarse Grid**
    *   Width: 0.15mm, Clearance: 0.15mm (Req: 0.45mm)
    *   **Slack:** 0.47mm - 0.45mm = **0.02mm**
    *   Grid: 0.05mm
    *   *Hypothesis:* The 0.02mm slack is smaller than the grid size, leading to aliasing failures.

3.  **Neckdown 6-mil (0.15mm) + Fine Grid**
    *   Rules: Same as above (Req: 0.45mm)
    *   Grid: **0.01mm**
    *   *Hypothesis:* Fine grid should resolve the 0.02mm slack.

4.  **Neckdown 5-mil (0.127mm) + Coarse Grid**
    *   Width: 0.127mm, Clearance: 0.127mm (Req: 0.381mm)
    *   **Slack:** 0.47mm - 0.381mm = **~0.09mm**
    *   Grid: 0.05mm
    *   *Hypothesis:* The 0.09mm slack is large enough to be resolved by a standard 0.05mm grid.

## Results

| Strategy | Rule (W/C) | Grid | Channel Req | Gap | Result | Time |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Standard** | 0.2mm | 0.05mm | 0.60mm | 0.47mm | **FAIL** (6/10) | 0.38s |
| **6-mil** | 0.15mm | 0.05mm | 0.45mm | 0.47mm | **FAIL** (9/10) | 0.53s |
| **6-mil** | 0.15mm | **0.01mm** | 0.45mm | 0.47mm | **PASS (10/10)** | 20.46s |
| **5-mil** | 0.127mm | 0.05mm | 0.38mm | 0.47mm | **PASS (10/10)** | 0.55s |

## Conclusion
The router handles fine-pitch components correctly **only if**:
1.  **Physics checks pass:** The reduced rules (neckdown) must fit within the physical gap.
2.  **Grid Resolution matches Tolerance:**
    *   If the slack (Gap - Req) is tiny (0.02mm), a very fine grid (0.01mm) is required, costing runtime.
    *   If the rules are relaxed further (5-mil) to create more slack (0.09mm), a standard grid (0.05mm) suffices, retaining fast performance.

**Recommendation:** For 1.27mm pitch components in `temper-placer`, use **5-mil (0.127mm) neckdown rules** to allow efficient routing on standard grids.
