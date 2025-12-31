# Experiment Report: 01 - Pitchfork Blocking Logic

**Date:** 2025-12-30
**Script:** `router-experiments/pitchfork.py`
**Objective:** Investigate and fix artificial blocking of neighboring pads in `maze_router.py`.

## Problem Statement
The "Pitchfork" benchmark revealed that the router was failing to route between standard 2.54mm pitch headers, reporting the path as blocked. This should be trivial for any router.

**Hypothesis:** The margin calculation logic in `maze_router.py` was overly pessimistic, double-counting clearances or expanding blockage zones excessively due to grid quantization.

## Diagnosis
Relevant code in `maze_router.py`:
1.  **Margin Calculation:** `_compute_grid_safe_margin` included a term `+ (self.cell_size / 2)`.
    *   *Issue:* This assumes the worst-case scenario where a trace center is at the very edge of a cell. While safe, it adds 0.25mm-0.5mm of extra padding on *both* sides, closing valid channels.
2.  **Grid Quantization:** `block_pads` used `round()` to convert world coordinates to grid indices.
    *   *Issue:* Rounding can "snap" a blockage boundary outward to the next cell unnecessarily, blocking valid neighbors.

## Solution Implemented
1.  **Strict Blocking:** Changed `block_pads` to use `math.ceil` for minimums and `math.floor` for maximums. This ensures we only block cells that strictly overlap the restricted zone.
2.  **Reduced Margin:** Removed the `cell_size / 2` term from the margin calculation. The router's collision check (at trace generation time) handle the finer details; the grid blockage should represent the "hard" no-go zone.

## Results

| Pitch | Grid | Old Result | New Result | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **2.54mm** | 0.5mm | **FAIL (6/10)** | **PASS (10/10)** | Issue resolved. Standard headers now route. |
| **1.27mm** | 0.5mm | FAIL (7/10) | FAIL (6/10) | Expected. Physical gap (0.47mm) < Req Channel (0.6mm). |
| **1.27mm** | 0.25mm | FAIL (6/10) | FAIL (9/10) | Improvement, but still constrained by physics (see Exp 01-B). |

## Conclusion
The fix successfully removed the artificial pessimism in the router's blocking logic. The router now correctly respects the physical geometry, allowing routing where physics permits (2.54mm) and blocking where it physically conflicts (1.27mm with standard rules).
