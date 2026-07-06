---
date: 2026-07-02
topic: physics-oracle-tuning
---

# Physics Oracle Loss Weight Tuning

## Summary

Tune the three physics loss weights in `physics_oracle.py` — loop_area (currently dominating at 30.0), thermal (30.0), and clearance (100.0, was calibrated when dark) — to achieve a balanced trade-off on the temper induction board. The three live metrics produce real signal and the trade-off is visible in the scores: loop_area_score = 0.9996 (dominating, pulling components too close together), hv_lv_clearance_score = 0.43 (too low — safety risk), thermal_score = 0.12 (IGBTs not reaching the heatsink edge). Wire the long-deferred KiCad DRC differential cross-check (R7 from `physics-derived-oracle-temper`) as ground-truth validation in parallel with weight tuning, so the clearance metric is calibrated against an independent tool before we trust the tuning.

---

## Problem Frame

The placer's composite loss function has three physics-aware terms with weights set to initial guesses: ThermalLoss weight = 30.0, ComponentLoopAreaLoss weight = 30.0, ClearanceLoss weight = 100.0. The clearance weight was calibrated when HV/LV classification was dark (no pairs existing), so it has never been tuned against a live constraint. The three terms compete for influence over component positions, and the current balance produces a lopsided result:

- **loop_area_score = 0.9996**: nearly perfect — the optimizer is pulling components into tight clusters, minimizing polygon areas aggressively. This is over-constrained: the score is so high that the loss is squeezing components together, working against clearance and thermal.
- **hv_lv_clearance_score = 0.43**: below the IPC-2221 safety threshold. The optimizer is not pushing HV and LV components apart, which is a real safety risk for a mains-powered induction burner.
- **thermal_score = 0.12**: IGBTs Q1/Q2 are not reaching the TOP edge for heatsink mounting. The thermal constraint is being overpowered.

The root cause is not that any single loss is broken — all three produce real, non-dark signal — but that the loop_area loss gradient dominates because its penalty grows quadratically with excess area and its weight (30.0) plus the aggressive `weight_schedule` (full strength after 60% of training) overwhelms the other terms. The clearance and thermal losses are fighting against a force that wants all components collapsed into the smallest possible polygon.

The fix is a weight rebalance, not a new metric. Adding a fourth metric or a pin-level LoopAreaLoss would add complexity without addressing the core trade-off. The three existing terms can produce a balanced placement if their relative strengths are right.

---

## Actors

- A1. **Maintainer (tuner)**: adjusts loss weights in the physics oracle runner, runs the optimizer, reads quality scores, and iterates toward the target balance.
- A2. **KiCad DRC**: provides independent ground-truth clearance validation via `pcbnew` DRC on the placed board. Agree = metric is calibrated, proceed with tuning. Disagree = fix the metric before tuning.
- A3. **Placer optimizer**: runs with the rebalanced weights and produces a placement that the three metrics evaluate.

---

## Key Flows

- F1. **KiCad DRC cross-check (validation gate)**
  - **Trigger:** maintainer runs the physics oracle on a placement and gets a clearance score.
  - **Actors:** A1, A2
  - **Steps:**
    1. Export the placer's placement to a `.kicad_pcb` file (post-optimization positions).
    2. Run KiCad's DRC (`pcbnew` CLI or scripted equivalent) and collect clearance violation counts.
    3. Compare: does the metric's worst clearance (edge-to-edge) match the DRC's reported minimum clearance? Do the violation pairs agree?
    4. If agreement is within a tolerance (±10% of the IPC-2221 threshold), the metric is calibrated — proceed to weight tuning (F2).
    5. If disagreement exceeds tolerance, investigate and fix the clearance metric before tuning weights.
  - **Outcome:** the clearance metric is validated against an independent ground truth. Trust in the metric's directional signal is established before any weight is changed.
  - **Covered by:** R1

- F2. **Weight tuning (manual bisection)**
  - **Trigger:** KiCad DRC cross-check passes (clearance metric is calibrated).
  - **Actors:** A1, A3
  - **Steps:**
    1. Start from the current weights: `clearance=100.0, thermal=30.0, loop_area=30.0`. Record baseline scores.
    2. **Phase 1 — Clearance floor**: increase `clearance` weight (try 200.0). If clearance_score climbs toward 0.8+ but loop_area_score drops below 0.85, the loop_area weight is too low — adjust proportionally.
    3. **Phase 2 — Thermal pull**: increase `thermal` weight (try 50.0, then 100.0). If IGBTs approach the heatsink edge but loop_area_score degrades below 0.85, add a minimum-separation floor to loop_area (see R4).
    4. **Phase 3 — Fine balance**: once clearance ≥ 0.8 and thermal ≥ 0.7, reduce `loop_area` weight if its score is still 0.999+ — the target is loop_area_score ≥ 0.9, not 0.9996. If loop_area_score drops below 0.85, check whether the loop polygons actually exceed the EMI spec or the optimizer is just looser.
    5. Each step: run the optimizer, record the three scores, compare to targets. One weight change per iteration.
  - **Outcome:** a weight triple that yields clearance ≥ 0.8, thermal ≥ 0.7, loop_area ≥ 0.9 on the temper board.
  - **Covered by:** R3, R4

- F3. **Post-tuning sanity check (A/B comparison)**
  - **Trigger:** a candidate weight triple passes the target scores.
  - **Actors:** A1
  - **Steps:**
    1. Run the existing `run_ab_diff` with old weights vs. new weights.
    2. Verify that the new placement has: (a) larger HV-LV minimum distance, (b) IGBTs closer to TOP edge, (c) commutation loops still tight.
    3. Re-run the KiCad DRC cross-check (F1) on the new placement to confirm the clearance score improvement corresponds to real DRC-passing clearance.
  - **Outcome:** the weight change produces a real, measurable improvement in both the oracle metrics and an independent DRC check.
  - **Covered by:** R5

---

## Requirements

**Validation gate (KiCad DRC cross-check)**

- R1. Before any weight is changed, the clearance metric is validated against KiCad's own DRC on the current (untuned) placement. The comparison checks: (a) does the metric's minimum edge-to-edge clearance match the DRC's minimum clearance within ±10% of the IPC-2221 threshold? (b) do the pairs with violations overlap? If the metric disagrees with KiCad DRC beyond the tolerance, fix the clearance metric before tuning weights. If they agree, the metric is calibrated — proceed.

**Weight tuning**

- R2. Tuning uses manual bisection with physics rationale — one weight change per iteration, recording all three scores. No grid search, no Bayesian optimization, no automated sweeps. The problem has three degrees of freedom and clear directional signal; manual bisection is faster and builds intuition.

- R3. Target scores for the temper board (the success criteria that define "done" for tuning):
  - `hv_lv_clearance_score ≥ 0.8` (from 0.43)
  - `thermal_score ≥ 0.7` (from 0.12)
  - `loop_area_score ≥ 0.9` but not 0.9996 (from 0.9996)

**Minimum-separation floor for loop area**

- R4. A minimum-separation penalty is added to the ComponentLoopAreaLoss configuration to prevent the loop-area loss from collapsing components into a single point when its weight is reduced. The floor is a `min_separation_mm` parameter on each loop (default 2.0mm): if any pair of components in the same loop is closer than this threshold, an additive penalty activates. This is NOT a fourth metric — it is a guardrail parameter within the existing ComponentLoopAreaLoss, analogous to the `margin` parameter already present. It prevents the optimizer from exploiting the "zero area = perfect score" behavior by stacking components on top of each other. The floor is relaxed (only activates below 2.0mm) — it does not change the loss landscape for well-separated components.

**Post-tuning validation**

- R5. After a candidate weight triple is found, the KiCad DRC cross-check (R1) is re-run. The placement with the new weights must show real clearance improvement (larger minimum clearance, fewer DRC violations) compared to the old weights. A score improvement that does not correspond to a real DRC improvement is a metric calibration bug, not a valid tuning.

**Non-requirements (scope boundaries)**

- Do NOT add a fourth metric. The three live metrics produce real signal and the trade-off is visible. Balance first, expand later.
- Do NOT add a pin-level LoopAreaLoss. The existing component-level loop area loss matches what `loop_area_score` measures. Pin-level precision is an enrichment for a future pass.
- Do NOT add grid search or Bayesian optimization. Manual bisection is sufficient and faster for a 3-weight problem with clear directional signal.
- Do NOT modify the loss function architecture — only the weight values and the loop `min_separation_mm` guardrail.

---

## Acceptance Examples

- AE1. **Covers R1.** Given the current (untuned) placement on the temper board, when the KiCad DRC cross-check runs, then either (a) the clearance metric agrees with DRC within ±10% (proceed to tuning) or (b) the metric disagrees (fix the metric first). The result is a decision, not a pass/fail.
- AE2. **Covers R3.** Given the tuned weights, when the physics oracle runs on the temper board, then `hv_lv_clearance_score ≥ 0.8`, `thermal_score ≥ 0.7`, and `loop_area_score ≥ 0.9` (but not 0.9996).
- AE3. **Covers R4.** Given a loop with components spaced ≥ 2.0mm apart, when the ComponentLoopAreaLoss computes its penalty, then the minimum-separation floor adds zero penalty (it only activates below the threshold).
- AE4. **Covers R5.** Given the tuned placement, when the KiCad DRC cross-check re-runs, then the DRC-reported minimum clearance is larger than on the untuned placement, and the DRC violation count is lower or unchanged.

---

## Success Criteria

- The clearance metric is validated against KiCad DRC on the current placement. Either we trust the metric and tune weights, or we fix the metric first — no tuning in a blind spot.
- The three target scores are met on the temper board: clearance ≥ 0.8, thermal ≥ 0.7, loop_area ≥ 0.9 but not 0.9996.
- The minimum-separation floor prevents loop-area loss from collapsing components below 2.0mm without changing the loss surface for normal placements.
- The A/B diff shows directional improvement in HV-LV distance, IGBT edge proximity, and DRC clearance.

---

## Key Decisions

- **Manual bisection, not grid search or Bayesian opt.** Three weights, clear directional signal, fast iteration. Automated methods add infrastructure complexity without proportional benefit for this scope.
- **Minimum-separation floor within existing loss, not a fourth metric.** The floor is a guardrail parameter on ComponentLoopAreaLoss, not a new loss term. It prevents the collapse mode without adding architectural complexity.
- **KiCad DRC cross-check as validation gate, not a metric.** R7 from the physics-derived-oracle doc is finally wired — but as a pre-tuning calibration check and post-tuning sanity check, not as a training loss. The placer does not need DRC in its loss function; it needs a calibrated clearance metric.
- **No pin-level loop area.** The component-level loss matches the metric and is sufficient to produce the trade-off. Pin-level precision would require correct pin names in the netlist, which is a separate effort.

---

## Dependencies / Assumptions

- KiCad's `pcbnew` Python API (or a scripted equivalent) can run DRC on a `.kicad_pcb` file and report minimum clearance and violation counts. Verify that the CI environment has KiCad CLI (`kicad-cli`) available, or that a headless `pcbnew` DRC script can be run.
- The clearance metric's edge-to-edge distance calculation (axis-aligned, bounding-box approximation) is close enough to KiCad's polygon-level clearance check to produce correlated results. The ±10% tolerance accounts for the approximation difference.
- The `ComponentLoopAreaLoss.weight_schedule` (introducing loop area after 40% of training, ramping to full strength at 60%) interacts with the weight change. A heavier weight arriving later may produce a different trajectory than a lighter weight arriving at the same time. Document the schedule interaction during tuning.
- The existing A/B diff (`run_ab_diff` in `physics_oracle.py`) can be reused for post-tuning validation. It currently includes only loop area, wirelength, overlap, boundary, spread — but not thermal. Extend it to include all three physics terms for the post-tuning diff.

---

## Outstanding Questions

### Resolve Before Tuning

- [Affects R1][Technical] How do we run KiCad DRC headlessly? `kicad-cli` exists but may not be in the CI image. Fallback: a Python script using `pcbnew` that loads the board and runs `BOARD::DRC()`.
- [Affects R4][Technical] What is a reasonable default for `min_separation_mm`? 2.0mm is a starting guess — should be verified against component sizes. If the smallest component is 3mm wide, the floor could be higher.

### Deferred to Tuning

- [Affects R3][Technical] The clearance score target of ≥ 0.8 is a heuristic. The IPC-2221 threshold is the hard pass condition; 0.8 corresponds to worst-pair clearance being at least 80% of the required minimum. Verify this is acceptable during the first tune pass.
- [Affects R3][Technical] The thermal score of ≥ 0.7 with IGBTs at the TOP edge. If the heatsink mounting requires IGBT centers within 3mm of the edge (not 5mm), the thermal_loss margin (currently 2.0) and max_distance (5.0) may need adjustment alongside the weight.
- [Affects R1][Needs research] What is the actual IPC-2221 threshold mm value for the temper board's mains voltage and pollution degree? This determines the clearance score baseline and the DRC comparison tolerance.
