# temper-a98v Experiment Report: Spread Loss Edge Effects

**Date:** 2025-12-22  
**Experiment:** temper-a98v  
**Topic:** Investigation of SpreadLoss Edge Effects on Routing Completion

## 1. Overview

This experiment investigated whether the `SpreadLoss` function in `temper-placer` was inadvertently pushing components to the board edges, thereby reducing routing completion rates. Previous observations (temper-h0n9.6) showed a negative correlation (r=-0.40) between spread loss and routing completion.

We hypothesized that adding an `EdgeAvoidanceLoss` would counteract this effect, keeping components away from the edges while still allowing `SpreadLoss` to distribute them, ultimately improving routing completion.

## 2. Hypotheses

*   **H0 (Null):** There is no difference in routing completion between baseline (spread_weight=1.0), Option A (spread_weight=0.3), and Option C (EdgeAvoidanceLoss).
*   **H1 (Alternative):** Option C (EdgeAvoidanceLoss with spread_weight=1.0) produces higher routing completion than baseline or Option A (target improvement: ≥10 percentage points).

## 3. Methodology

*   **Test Fixture:** `packages/temper-placer/tests/fixtures/medium_board.kicad_pcb` (25 components, 18 nets).
*   **Conditions:**
    *   **Baseline:** Standard config (`spread_weight=1.0`, no edge avoidance).
    *   **Option A:** Reduced spread (`spread_weight=0.3`, no edge avoidance).
    *   **Option C:** Edge Avoidance (`spread_weight=1.0`, `edge_avoidance_weight=0.5`).
*   **Parameters:**
    *   Epochs: 2000
    *   Sample Size: 30 runs per condition (90 total)
    *   Router: Internal MazeRouter (A* pathfinding)
*   **Metrics:**
    *   Routing Completion Rate (%)
    *   Minimum Distance to Board Edge (mm)

## 4. Results

### Summary Statistics (N=30 per condition)

| Condition | Routing % (Mean ± SD) | Min Edge Dist (mm) (Mean ± SD) |
| :--- | :--- | :--- |
| **Baseline** | 12.59% ± 4.60% | 4.69 ± 1.06 |
| **Option A** | 12.96% ± 4.91% | 5.15 ± 1.61 |
| **Option C** | **12.59% ± 4.82%** | **6.32 ± 1.54** |

### Statistical Analysis

1.  **Routing Completion (ANOVA):**
    *   F-statistic: 0.0600
    *   p-value: 0.9418
    *   **Result:** No significant difference between groups.

2.  **Minimum Edge Distance (ANOVA):**
    *   F-statistic: 10.4598
    *   p-value: 0.0001
    *   **Result:** Significant difference detected. Option C keeps components significantly further from edges.

## 5. Conclusions

1.  **Routing Hypothesis (H1) Rejected:** Adding `EdgeAvoidanceLoss` did **not** improve routing completion in this specific test setup (medium board, 2000 epochs). The completion rates were identical to the baseline (12.59%).
2.  **Edge Avoidance Confirmed:** The new `EdgeAvoidanceLoss` works as intended. It successfully increased the minimum distance of components from the board edge from ~4.7mm to ~6.3mm (p=0.0001).
3.  **Root Cause of Routing Failure:** The low routing completion across all groups (~12%) suggests that edge crowding was **not** the primary bottleneck for this board's routability. Other factors (congestion, net ordering, or the simple maze router's limitations) are likely more dominant.

## 6. Recommendations

*   **Retain EdgeAvoidanceLoss:** While it didn't solve the routing issue here, keeping components away from edges is generally good practice for manufacturing and handling. It works reliably and should be available in the toolbox.
*   **Investigate Other Bottlenecks:** Future experiments should focus on congestion management or net ordering to improve routing.
*   **Update Defaults:** Consider enabling `EdgeAvoidanceLoss` with a low weight by default to prevent extreme edge placement without constraining the optimizer too much.
