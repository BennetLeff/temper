---
date: 2026-07-02
topic: physics-oracle-weight-balance-experiment
---

# Physics Oracle: Weight-Balance Experiment

## Summary

A two-phase experiment to produce a clean verdict on whether the optimizer can reach the human floor at balanced weights. Phase 1: a manual thermal-weight sweep (3-4 weights, 1 seed each, full per-term instrumentation) to find where thermal's gradient share drops below ~50%. Phase 2: a 20-seed convergence-run at the balanced weight, with inflation_ramp enabled, C-CAP on, early_stopping disabled, and the optimizer's own converged flag as the gate. Decision rule pre-registered against the re-baselined human floor (clr6=0.133, thermal=0.50).

---

## Problem Frame

Three rounds of the multi-seed experiment produced one solid conclusion: thermal weight 4000 controls 99.7% of the optimizer's gradient, making the other four loss terms (clearance, overlap, boundary, wirelength) inaudible. The optimizer isn't stuck or trapped — it's a thermal monovariable optimizer wearing a multi-objective costume. Every prior conclusion ("optimizer is below human," "local minimum," "C-CAP doesn't help") was interpreted through a loss landscape where only one term had gradient influence.

The probes confirmed two independent findings:
- **inflation_ramp eliminates overlap** (97k→0 for seed 0) but doesn't fix clearance or thermal — the anti-entanglement tool is real but treating it alone isn't enough.
- **The loss function has no usable gradient signal from the minor terms** — loss(spread)/loss(seed9) = 1.002 because thermal is identical across all configs. Weight rebalancing is the prerequisite for any experiment to be interpretable.

The prior experiment's pre-registered INCONCLUSIVE verdict correctly triggered this round. The decision rule fired as designed, the instrumentation proved the dominant confound (thermal weight), and the next step is weight rebalancing — not a new optimizer architecture.

Two corrections from the prior round fold in:
- The re-baselined human floor is clr6=0.133 with 22 violations against 6.0mm (not 0.91 against 3.0mm). The human fails its own DRC. The decision rule's target shifts accordingly.
- The convergence criterion moves from a post-hoc plateau check (`|slope| < 1e-4`) to the optimizer's own converged flag. The prior plateau check was too strict for 10k epochs, and relaxing it post-hoc is the same class of error the pre-registered rule exists to prevent.

---

## Actors

- A1. **Experimenter**: runs the calibration sweep and the main experiment, logs per-term instrumentation, applies the pre-registered decision rule.
- A2. **Optimizer**: runs at balanced weights with inflation_ramp enabled, C-CAP on, early_stopping disabled, to 50k epochs or convergence.
- A3. **Per-term instrumentation**: gradient norm per loss term, loss breakdown per term, per-pair center distances. Already exists in the codebase (`gradnorm.py`, `train.py`'s `loss_breakdown`) but was never wired to the oracle's logging.

---

## Key Flows

- F1. **Calibration sweep (Phase 1)**
  - **Trigger:** start of work.
  - **Actors:** A1, A2, A3
  - **Steps:**
    1. Run 3-4 thermal weight values (e.g., 100, 500, 1000, 2000) at 1 seed each (seed 0, the prior round's representative well-behaved seed).
    2. Full instrumentation per run: per-term gradient norms, loss breakdown (thermal, overlap, clearance, boundary, wirelength), final scores (clr3, clr6, violations_3mm, violations_6mm, thermal).
    3. Identify the thermal weight where thermal's gradient share drops below ~50% of the total gradient norm.
    4. Record the calibration result: the chosen weight and its gradient-ratio justification.
  - **Outcome:** a single balanced thermal weight for the main experiment, with a documented gradient-ratio rationale.
  - **Covered by:** R1, R2, R3

- F2. **Main experiment (Phase 2)**
  - **Trigger:** Phase 1 produces a balanced weight.
  - **Actors:** A1, A2, A3
  - **Steps:**
    1. Set thermal weight to the balanced value from Phase 1. All other weights frozen at current values (clearance=200, overlap=200, boundary=100, wirelength=20, spread=5, loop_area=1).
    2. Enable inflation_ramp (e.g., 0.3).
    3. C-CAP on, constraints passed through.
    4. Early_stopping disabled. Run to 50k epochs or the optimizer's converged flag.
    5. 20 seeds (0-19) at the balanced weight.
    6. Full instrumentation per run: per-term gradient norms, loss breakdown, per-pair center distances (to detect frozen coincident pairs), final scores, converged flag status.
    7. Compute mean±std across the 20 converged runs.
    8. Apply the pre-registered decision rule (R6).
  - **Outcome:** a clean verdict — DISSOLVED, HOLDS, or INCONCLUSIVE — backed by 20-seed variance data, convergence proof (optimizer's own flag), and per-term gradient instrumentation.
  - **Covered by:** R4, R5, R6, R7, R8

---

## Requirements

**Phase 1: calibration sweep**

- R1. Run 3-4 thermal weight values (candidates: 100, 500, 1000, 2000) at 1 seed each (seed 0), 50k epochs, inflation_ramp on, C-CAP on, early_stopping disabled. All other weights frozen at current values.
- R2. Per-run instrumentation logs: per-term gradient norms (thermal, overlap, clearance, boundary, wirelength), per-term loss breakdown, final scores (clr3, clr6, violations_3mm, violations_6mm, thermal), converged flag status. This uses the existing `gradnorm.py:compute_individual_loss_gradient_norms` and `train.py`'s `loss_breakdown` — wiring the existing instrumentation to the oracle's logging, not building new infrastructure.
- R3. The balanced thermal weight is the value where thermal's gradient share drops below ~50% of the total gradient norm. Record the gradient ratio at the chosen weight. If no weight in the sweep reaches ~50%, pick the lowest weight tested and note that the balance point is below the sweep range.

**Phase 2: main experiment**

- R4. 20 seeds (0-19) at the balanced thermal weight from Phase 1. All other weights frozen. inflation_ramp enabled (e.g., 0.3). C-CAP on. Early_stopping disabled. Run to 50k epochs or the optimizer's converged flag.
- R5. Per-run instrumentation (same as R2): per-term gradient norms, loss breakdown, per-pair center distances, final scores, converged flag. A run whose converged flag is False at 50k epochs is flagged and excluded from the mean±std — "under-convergence" must not be confounded with "seed variance."

**Decision rule (pre-registered)**

- R6. **Pre-registered decision rule** (defined before Phase 2 runs, numeric, not post-hoc). Target: re-baselined human floor (clr6=0.133, thermal=0.50).
    - **DISSOLVED** if C-CAP-on mean `clr6` ≥ 0.133 with std < 0.05 across converged runs AND mean `thermal_score` ≥ 0.45 — the "optimizer problem" was an artifact of thermal-weight dominance.
    - **HOLDS** if best-of-20 `clr6` < 0.133 — the optimizer cannot reach the human floor even at balanced weights with inflation_ramp and C-CAP.
    - **INCONCLUSIVE** if neither threshold is met — mean clr6 ≥ 0.133 but std ≥ 0.05 (high variance, bimodal), or best-of-20 ≥ 0.133 but mean < 0.133 (escape is possible but not reliable). Escalate to GradNorm adaptive balancing.

**Instrumentation wiring**

- R7. The per-term gradient norm logging uses the existing `gradnorm.py:compute_individual_loss_gradient_norms` — wired into the oracle's per-run output, not a new implementation. If the existing function's API doesn't match the oracle's logging shape, the wiring change is the adaptation, not a rewrite.
- R8. Per-pair center distances are logged per run to detect frozen coincident pairs (the `|Δ|≈0` vanishing-gradient condition identified in the overlap-loss analysis). A run where ≥ 2 HV components have center distance < 0.5mm at convergence is flagged — those pairs are frozen by the overlap formula and no weight change will separate them.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R3.** Given the calibration sweep runs (3-4 weights × 1 seed), when per-term gradient norms are logged, then the report shows thermal's gradient share at each weight and identifies the weight where it crosses ~50%.
- AE2. **Covers R4, R5.** Given 20 seeds run at the balanced weight to convergence (optimizer's converged flag), when a run's converged flag is False at 50k epochs, then it is flagged and excluded from the mean±std, and the report notes how many runs were excluded.
- AE3. **Covers R6.** Given the 20 converged runs complete, when mean±std is computed, then the pre-registered decision rule fires: DISSOLVED (mean clr6 ≥ 0.133, std < 0.05, thermal ≥ 0.45), HOLDS (best-of-20 < 0.133), or INCONCLUSIVE (neither) — with numeric thresholds checked against actual data.
- AE4. **Covers R8.** Given a run where ≥ 2 HV components have center distance < 0.5mm at convergence, when the run is logged, then the report flags it as "frozen coincident pairs — overlap vanishing-gradient condition" and notes that no weight change will separate them.
- AE5. **Covers R7.** Given the existing `gradnorm.py` function, when the oracle's per-run output is assembled, then per-term gradient norms are included in the output without a new gradient-norm implementation — the existing function is wired, not rebuilt.

---

## Success Criteria

- The calibration sweep identifies a balanced thermal weight with a documented gradient-ratio rationale — the chosen weight is not arbitrary, it's where thermal's gradient share crosses ~50%.
- The main experiment produces a clean verdict via the pre-registered decision rule — DISSOLVED, HOLDS, or INCONCLUSIVE — backed by 20-seed variance data, the optimizer's own converged flag, and per-term gradient instrumentation.
- No confound remains: weights frozen except thermal (calibrated), inflation_ramp on, C-CAP on, early_stopping disabled, convergence via the optimizer's own signal, per-term gradients logged. The next conclusion cannot be under-instrumented for the same reasons the last three were.
- Per-pair center distances are logged so the frozen-coincident-pair condition (overlap vanishing gradient at |Δ|≈0) is visible in the data, not hidden in an aggregate loss number.

---

## Scope Boundaries

- No GradNorm adaptive weight rebalancing. Deferred as fallback only if the verdict is INCONCLUSIVE.
- No C-CAP on/off as an experiment variable. Frozen on — the prior round showed its effect washes out at convergence.
- No new physics metrics. The three existing metrics produce real signal; adding another before resolving the optimizer question adds noise.
- No 2-D weight landscape search. The sweep is 1-D (thermal weight) with inflation_ramp as the only other lever. A 2-D thermal:overlap ratio sweep is deferred.
- No corpus baseline regeneration. Re-extracting baselines after R16 is separate work.
- No gate-drive pin-based loop. Deferred until the gate driver component is in the netlist.

---

## Key Decisions

- **Manual sweep then fixed-weight experiment over adaptive GradNorm.** The sweep finds the initial balance interpretably (where does thermal's gradient share cross 50%?); adaptive is overkill at this stage and introduces a second moving part alongside inflation_ramp. GradNorm's value is in maintaining balance as the landscape evolves, not in finding the initial balance — that's a simpler problem a fixed weight solves.
- **Fixed 50k epochs with the optimizer's converged flag over a tuned plateau threshold.** The prior round's `|slope| < 1e-4` was too strict for 10k epochs, and relaxing it post-hoc is the same class of error the pre-registered rule exists to prevent. The optimizer's own signal is designed for this landscape; if it fires too early or too late, that's a finding about the converged flag, not a confound.
- **Re-baselined human floor (clr6=0.133) as the decision-rule target.** The human is a "best known" floor, not a passing target — it fails its own DRC (22 violations against 6.0mm). Calibrating to clr6=1.0 (design rule) would make every outcome HOLDS, since the human itself scores 0.133. The human floor is the bar the prior experiment was implicitly using; correcting it to 0.133 is the metric fix, not a lowering of standards.
- **20 seeds over 10.** Doubles compute (~10-15 min) but tightens the std estimate and makes the std < 0.05 threshold more reachable if balanced weights reduce the collapse mode. The prior round's bimodality (8/10 collapse, 2/10 escape) needs more seeds to characterize reliably.
- **Freeze C-CAP on.** It proved it runs and changes the starting point. It's a fixed part of the pipeline now, not a variable. The prior round showed its effect washes out at convergence under thermal-dominant weights; at balanced weights, it may matter more or less — but that's a follow-up question, not this experiment's variable.
- **Per-term instrumentation as first-class output.** The prior three rounds each produced an under-instrumented conclusion because the dominant confound was invisible. Per-term gradient norms, loss breakdown, and per-pair center distances are logged per run so the next confound is visible before the conclusion is written.

---

## Dependencies / Assumptions

- `gradnorm.py:compute_individual_loss_gradient_norms` can be wired into the oracle's per-run output without a new implementation. If the function's API doesn't match the oracle's logging shape, the wiring adaptation is the change. Verify during planning.
- The optimizer's `converged` flag is a reliable convergence signal on this loss landscape at balanced weights. If it fires too early (before the plateau) or too late (after 50k epochs without firing), the experiment may exclude valid runs or include non-converged ones. Verify during planning by checking the flag's implementation against the loss curve from the prior single-seed run.
- `inflation_ramp=0.3` is a reasonable starting value (30% of epochs at reduced component sizes). The prior probe used 0.3 and eliminated overlap for seed 0. Verify during planning that 0.3 doesn't over-suppress overlap gradient at balanced weights.
- 20 seeds × 50k epochs at ~10s per run (prior 10k-epoch timing) is computationally feasible — roughly 10-15 minutes if per-run time scales linearly with epochs. Verify during planning; if 50k epochs take 50s each, total is ~17 minutes.
- The re-baselined human floor (clr6=0.133, thermal=0.50) is stable under the corrected dual-rail metric. Verify during planning that the human placement's score doesn't change with inflation_ramp enabled (the human placement is fixed; inflation_ramp affects the optimizer's component-size perception, not the metric's measurement of the human placement).

---

## Outstanding Questions

### Resolve Before Planning

- *None.*

### Deferred to Planning

- [Affects R2, R7][Technical] Does `compute_individual_loss_gradient_norms` accept the same `(positions, rotations, context)` signature the oracle uses, or does it need an adapter? The function exists in `gradnorm.py` but has never been called from the oracle path.
- [Affects R4][Technical] What is the optimizer's `converged` flag's implementation — is it a loss-change threshold, a gradient-norm threshold, or a custom criterion? Planning needs to read the implementation to confirm it's reliable at 50k epochs on this landscape.
- [Affects R8][Technical] How are per-pair center distances computed and logged? The oracle has HV/LV component sets; the logging needs to iterate pairs and record distances. Is there an existing helper, or is this a new logging column?
- [Affects R3][Needs research] If no weight in the sweep (100-2000) brings thermal's gradient share below 50%, the balance point is below 100. Is there a lower bound on thermal weight below which the optimizer stops pulling Q1/Q2 to the edge entirely? The human baseline (thermal=0.50) was achieved at weight 4000; at weight 100, the optimizer may not move them at all.