---
date: 2026-07-02
topic: physics-oracle-metric-fix-and-c-cap-experiment
---

# Physics Oracle: Metric Fix + C-CAP Experiment

## Summary

Fix the clearance metric (dual: worst-pair severity + violation count, both 3.0mm regulatory and 6.0mm design-margin rails) and the C-CAP wiring bug (constraints pass-through + `ccap_enabled=True`) in parallel, then run a pre-registered multi-seed experiment (10 seeds × C-CAP on/off, fixed weights, run-to-convergence) against the corrected metric to settle whether the "optimizer problem" conclusion is real or an artifact of a single seed with the feasibility projector switched off.

---

## Problem Frame

The physics oracle report (`RESULTS.md`) concluded "the optimizer is below human on both clearance and thermal — this is an optimizer problem, not a metric or weight problem." A code-level audit found that conclusion unearned:

- **Single seed.** The 0.72/0.46 numbers come from one `train_multiphase` call (`physics_oracle.py:69`, `seed=42`). Multi-start machinery (`MultiSeedConfig`, `train_dpp_multiseed`) exists but defaults to `enabled=False` and was never called. "Local minimum" is inherently a multi-start claim — from one seed you cannot separate "local minimum" from "wrong weights" from "under-trained."

- **C-CAP exists but was switched off.** `ccap.py` is a 968-line Dykstra alternating-projection feasibility pump that explicitly pushes HV↔LV pairs apart and edge-mounts thermal components — precisely the "10 HV parts stacked at one edge, infeasible at step 0" problem the report said "would need to be built." It's wired into `train.py:406` behind `if config.initialization.ccap_enabled and constraints is not None:`. Both conditions fail: `ccap_enabled` defaults to `False` (`config.py:206`) AND the oracle passes `constraints=None` (`physics_oracle.py:315`). The tool that finding #4 said "would need to be built" already exists and was never turned on.

- **Clearance metric is miscalibrated.** `hv_lv_clearance_score` (`quality.py:229–251`) takes the single worst HV-LV pair and linear-ramps it against a 3.0mm IEC threshold. It is blind to violation count (one violation and nineteen score identically), and the 3.0mm threshold disagrees with the DRC's 6.0mm netclass rule by 2×. The oracle's 0.91 score for the human placement decodes to a worst pair of 2.73mm — below even the oracle's own 3.0mm threshold. The human reference being calibrated against fails its own DRC (19 violations, 0.0–5.8mm vs 6.0mm).

- **Coarse weight sweep.** Thermal weight was swept coarsely (100→4000) along one axis. A 1-D coarse sweep doesn't rule out a 2-D trade-off or a schedule fix.

The oracle is real and the wiring work is solid. But the headline conclusion outruns its evidence. This work turns each critique into a testable action with a pre-registered decision rule, so the next conclusion cannot be under-instrumented.

---

## Actors

- A1. **Experimenter**: runs the multi-seed experiment, logs results, applies the pre-registered decision rule.
- A2. **C-CAP feasibility projector**: the 968-line Dykstra alternating-projection in `ccap.py`. Either converges to a feasible starting point or reports its own failure — both are signal.
- A3. **Clearance metric**: the corrected dual-rail score function in `quality.py`. Reports worst-pair severity AND violation count against both 3.0mm and 6.0mm thresholds.
- A4. **ClearanceLoss**: the optimizer's loss term in `losses/clearance.py`. Must push all violating pairs toward the 6.0mm design-rule rail, not just the worst pair toward 3.0mm.

---

## Key Flows

- F1. **Metric fix (correctness first)**
  - **Trigger:** start of work — prerequisite to all experiments.
  - **Actors:** A3, A4
  - **Steps:**
    1. Add a violation-count metric alongside the existing worst-pair score: for each threshold rail (3.0mm, 6.0mm), count HV-LV pairs below the threshold.
    2. Surface both rails in `compute_quality_report`: `clearance_score_3mm` (worst-pair/3.0), `clearance_score_6mm` (worst-pair/6.0), `violations_3mm` (count), `violations_6mm` (count).
    3. Verify `ClearanceLoss` pushes all violating pairs, not just the worst — and that it targets the 6.0mm design-rule rail, not 3.0mm. If it only pushes the worst pair, fix it to aggregate.
    4. Re-score `temper.kicad_pcb` (human placement) under the new dual-rail metric. Record the new baseline.
  - **Outcome:** the oracle reports both severity and count against both thresholds; the loss term's aggregation matches the metric's philosophy.
  - **Covered by:** R1, R2, R3, R4, R5

- F2. **C-CAP wiring fix (parallel with F1)**
  - **Trigger:** start of work — independent of F1 (different code paths).
  - **Actors:** A2
  - **Steps:**
    1. Pass real `PlacementConstraints` through `physics_oracle.py:315` instead of `constraints=None`.
    2. Set `ccap_enabled=True` in the oracle's `OptimizerConfig`.
    3. Add logging: did `project_to_feasible` converge? How many Dykstra cycles? What was the post-projection clearance at step 0?
    4. If C-CAP fails to converge (2-cycle oscillation per `ccap-mathematical-basis.md`), record that as a finding — it's a different problem than "descent gets stuck."
  - **Outcome:** C-CAP is available as an experiment variable; its own convergence is observable.
  - **Covered by:** R6, R7, R8

- F3. **Multi-seed experiment (after F1 + F2)**
  - **Trigger:** F1 and F2 both complete.
  - **Actors:** A1
  - **Steps:**
    1. Freeze weights at current values (tw=4000, cw=200, lw=1, overlap=200, boundary=100, wirelength=20, spread=5) across all runs.
    2. Run 10 seeds × {C-CAP on, C-CAP off} = 20 runs against the corrected metric.
    3. Log per run: loss curve (for convergence check), final clearance_score_3mm, clearance_score_6mm, violations_3mm, violations_6mm, thermal_score, C-CAP convergence status + post-projection clearance.
    4. Assert convergence per run: loss curve must plateau (slope below threshold over last N% of epochs) or run to a convergence criterion. A run that hasn't converged is excluded and flagged, not silently included.
    5. Compute mean±std for each condition.
    6. Apply the pre-registered decision rule (R10).
  - **Outcome:** a clean verdict — the conclusion dissolves, holds, or is inconclusive — backed by variance data and convergence proof.
  - **Covered by:** R9, R10, R11, R12

---

## Requirements

**Metric fix: dual-rail clearance scoring**

- R1. `compute_quality_report` surfaces four clearance numbers per run: `clearance_score_3mm` (worst-pair severity against 3.0mm IEC regulatory floor), `clearance_score_6mm` (worst-pair severity against 6.0mm DRC design-rule), `violations_3mm` (count of HV-LV pairs below 3.0mm), `violations_6mm` (count of HV-LV pairs below 6.0mm). Both rails are reported independently — neither is "the" gate.
- R2. The violation-count metric counts every HV-LV pair whose edge-to-edge distance is below the threshold, not just the single worst pair. A board with 19 violations scores differently from a board with 1 violation.

**Metric fix: loss-metric alignment**

- R3. `ClearanceLoss` pushes all violating pairs toward compliance, not just the single worst pair. The loss aggregation matches the metric philosophy: if the metric reports violation count, the loss term must penalize every contributing pair.
- R4. `ClearanceLoss` targets the 6.0mm design-rule rail (the threshold the board was designed against), not the 3.0mm regulatory floor. The 3.0mm rail is for reporting; the 6.0mm rail is for optimization. If the loss targets 3.0mm, it under-constrains the optimizer relative to the design intent — recreate the metric-vs-optimization divergence that started this mess.

**Metric fix: re-baseline the human reference**

- R5. `temper.kicad_pcb` (the human placement) is re-scored under the corrected dual-rail metric. The result is recorded as a named deliverable — the human baseline in the new units. The old 0.91 (worst-pair-only, 3.0mm) is superseded; the new baseline states worst-pair score AND violation count against both rails. The human is a "best known" floor that itself has violations, not a passing target.

**C-CAP wiring fix**

- R6. `physics_oracle.py` passes real `PlacementConstraints` (derived from `pcb_spec.yaml` → `derive_constraints_from_spec`) through to `train_multiphase` instead of `constraints=None`.
- R7. `ccap_enabled=True` in the oracle's `OptimizerConfig`. The feasibility projector runs before gradient descent.
- R8. Per-run logging records: did `project_to_feasible` converge, how many Dykstra cycles, what was the post-projection clearance at step 0. If C-CAP fails to converge (2-cycle oscillation), this is recorded as a finding — "C-CAP cannot reach feasibility on the temper board" is a different conclusion than "descent gets stuck."

**Multi-seed experiment**

- R9. 10 seeds × {C-CAP on, C-CAP off} = 20 runs. Weights frozen at current values (tw=4000, cw=200, lw=1, overlap=200, boundary=100, wirelength=20, spread=5) across all runs — weight search is deferred, so weights must not vary or C-CAP-effect and weight-effect confound.
- R10. **Pre-registered decision rule** (defined before running, numeric, not post-hoc):
    - **Conclusion DISSOLVED** if C-CAP-on mean `clearance_score_6mm` ≥ 0.85 with std < 0.05 across 10 seeds AND mean `thermal_score` ≥ 0.45 — the "optimizer problem" was an artifact of one seed with feasibility projection off.
    - **Conclusion HOLDS** if C-CAP-on best-of-10 `clearance_score_6mm` still < the human floor (R5's re-baselined value) AND best-of-10 `thermal_score` < 0.45 — the optimizer genuinely cannot reach the human floor even with C-CAP and multiple seeds.
    - **INCONCLUSIVE** if neither threshold is met — escalate to weight search (finer 2-D sweep) as the next experiment, using the oracle as the steering wheel.
- R11. **Convergence check.** Per run, log the loss curve and assert plateau: slope of loss over the last 20% of epochs must be below a threshold (e.g., Δloss < 1e-4 per epoch). A run that hasn't converged is excluded from the mean±std and flagged — "under-convergence" must not be confounded with "seed variance."
- R12. **C-CAP own outcome recorded.** For each C-CAP-on run, record: convergence status (converged / oscillation / failed), Dykstra cycles run, post-projection clearance at step 0. If C-CAP fails to converge on the temper board across all 10 seeds, that is itself the finding — the feasibility projector cannot reach a feasible point, which is a different problem than "gradient descent gets stuck" and requires a different fix.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R5.** Given `temper.kicad_pcb` (human placement), when `compute_quality_report` runs under the corrected metric, then the report shows four numbers: `clearance_score_3mm`, `clearance_score_6mm`, `violations_3mm`, `violations_6mm` — and `violations_6mm` is ≥ 1 (the human placement has DRC violations against the 6.0mm design rule). The old 0.91 is superseded.
- AE2. **Covers R3, R4.** Given a fixture with 5 HV-LV pairs below 6.0mm (but only 1 below 3.0mm), when `ClearanceLoss` runs, then the loss penalizes all 5 violating pairs against the 6.0mm rail, not just the 1 pair below 3.0mm. The loss aggregation matches the metric's violation-count philosophy.
- AE3. **Covers R6, R7.** Given the oracle runs with `ccap_enabled=True` and real constraints passed through, when `train_multiphase` is called, then `project_to_feasible` executes before gradient descent (visible in logs) and the post-projection clearance at step 0 is recorded.
- AE4. **Covers R8.** Given C-CAP fails to converge on a run (2-cycle oscillation detected), when the run completes, then the log records "C-CAP did not converge — oscillation at cycle N" and the run is included in the experiment report as a C-CAP failure (not silently excluded).
- AE5. **Covers R9, R11.** Given 10 seeds × 2 conditions = 20 runs, when the experiment completes, then every run's loss curve is logged and each run is asserted to have converged (plateau in last 20% of epochs). A run that hasn't converged is flagged and excluded from the mean±std.
- AE6. **Covers R10.** Given the 20 runs complete and converge, when the mean±std is computed for each condition, then the pre-registered decision rule fires: DISSOLVED, HOLDS, or INCONCLUSIVE — with the numeric thresholds checked against the actual data, not a post-hoc interpretation.

---

## Success Criteria

- The corrected clearance metric reports both severity and count against both threshold rails — a board with 19 violations is distinguishable from a board with 1 violation, and the 3.0mm/6.0mm disagreement is visible in the report, not hidden.
- The loss term's aggregation matches the metric's philosophy — `ClearanceLoss` pushes all violating pairs toward the 6.0mm design-rule rail, not just the worst pair toward 3.0mm.
- The human reference is re-scored under the new metric — the floor is stated in the new units, and the doc does not reference the old 0.91 as if it were a passing target.
- The multi-seed experiment produces a clean verdict via the pre-registered decision rule — DISSOLVED, HOLDS, or INCONCLUSIVE — backed by variance data (mean±std over 10 seeds), convergence proof (loss curve plateau per run), and C-CAP's own outcome (converged / oscillated / failed).
- No confound remains: weights frozen, convergence checked, C-CAP's own outcome recorded, metric and loss aligned. The next conclusion cannot be under-instrumented for the same reasons the last one was.

---

## Scope Boundaries

- No weight search. Weights are frozen across all 20 runs. A finer 2-D weight sweep is the follow-up only if the verdict is INCONCLUSIVE.
- No new optimizer architecture. C-CAP alternatives, multi-start beyond `train_dpp_multiseed`, or a different descent schedule are only if the verdict is HOLDS (the optimizer genuinely cannot reach the floor even with C-CAP and multiple seeds).
- No additional physics metrics (congestion, zone compliance). The three existing metrics produce real signal; adding another before resolving the optimizer question adds noise.
- No gate-drive pin-based loop. Deferred until the gate driver component is in the netlist with named pins.
- No corpus baseline regeneration. Re-extracting baselines after R16 is separate work; this experiment uses the oracle, not the corpus gate.

---

## Key Decisions

- **Both threshold rails surfaced independently.** The 3.0mm IEC regulatory floor and the 6.0mm DRC design rule answer different questions — "can this be certified?" vs. "does this meet the designer's intent?" Surfacing both lets you see whether the placer meets certification vs. design margin independently. Neither is "the" gate.
- **Dual clearance metric (worst-pair + violation count).** The worst pair captures severity (how far below threshold). The violation count captures systematicity (how many pairs are below). Both matter: a single 2.9mm near-miss is an edge case; nineteen 2.9mm pairs is a systematically bad placement. The loss term must penalize all violating pairs, not just the worst — otherwise the optimizer fixes one pair and stops.
- **Loss targets 6.0mm design-rule rail, metric reports both.** The loss term optimizes against the design rule (6.0mm) because that's what the board was designed against. The 3.0mm regulatory floor is for reporting — it tells you whether the product can be certified. If the loss targets 3.0mm, it under-constrains relative to design intent and recreates the metric-vs-optimization divergence.
- **Pre-registered decision rule.** The numeric thresholds (≥ 0.85 clearance, ≥ 0.45 thermal, std < 0.05) are defined before running. The verdict is not post-hoc. This is the same principle as "calibrate against human before setting targets" — define what counts as success before you see the numbers.
- **Convergence check per run.** A single-seed 0.72 could be under-trained at 10k epochs, not stuck. Multi-seed at the same budget inherits the under-training and you'd misread it as seed variance. Every run's loss curve is logged and asserted to plateau; a non-converged run is excluded and flagged.
- **C-CAP's own outcome is a first-class deliverable.** The feasibility pump may fail to reach a feasible point on the temper board (10 HV parts, tight outline, 2-cycle oscillation risk). If it fails, that's the finding — "C-CAP cannot reach feasibility" — and it's a different problem than "gradient descent gets stuck." Recording C-CAP's convergence status separately prevents conflating the two.
- **Weights frozen.** The experiment is 2 conditions × 10 seeds, corrected metric, fixed weights, run-to-convergence. Varying weights alongside C-CAP and seed would confound C-CAP-effect with weight-effect. Weight search is deferred to a follow-up only if the verdict is INCONCLUSIVE.

---

## Dependencies / Assumptions

- `PlacementConstraints` derived from `pcb_spec.yaml` → `derive_constraints_from_spec` is compatible with `project_to_feasible`'s expected input. The C-CAP wiring fix (R6) depends on this flow being intact. Verify during planning.
- `project_to_feasible` in `ccap.py` handles the temper board's 10 HV/AC components without silent failure — it either converges, detects oscillation, or raises. The 2-cycle oscillation detection is documented in `ccap-mathematical-basis.md`. Verify during planning that the detection is wired and surfaces to the caller.
- `ClearanceLoss` in `losses/clearance.py` can be configured to target 6.0mm and aggregate all violating pairs. If the current implementation only pushes the worst pair, R3 requires a code change to the loss function. Verify the current aggregation shape during planning.
- The 10-seed × 2-condition experiment at 10k+ epochs per run is computationally feasible on the target hardware. 20 runs × 10k epochs × ~10s per run ≈ 3–5 minutes if the per-run time holds; verify during planning.
- The convergence plateau threshold (Δloss < 1e-4 per epoch over last 20%) is a reasonable proxy for convergence on this loss landscape. Verify during planning — if the loss curve has a long shallow tail, the threshold may need adjustment.

---

## Outstanding Questions

### Resolve Before Planning

- *None.*

### Deferred to Planning

- [Affects R3][Technical] Does `ClearanceLoss` currently aggregate all violating pairs or only the worst? The implementation in `losses/clearance.py` needs to be read to determine whether R3 is a config change or a code change.
- [Affects R4][Technical] Can `ClearanceLoss` be configured to target 6.0mm instead of 3.0mm, or does the threshold need to be a constructor parameter? Currently `default_hv_lv_clearance: float = 10.0` is the constructor default; the oracle passes the derived threshold. Verify the threshold flows through to the loss correctly.
- [Affects R8][Needs research] Does `project_to_feasible` surface its convergence status (converged / oscillation / failed) to the caller, or does it silently return the best-found state? The logging requirement in R8 depends on the API shape.
- [Affects R11][Technical] What is the right convergence plateau threshold for this loss landscape? 1e-4 per epoch over the last 20% is a starting point; planning should verify against actual loss curves from the single-seed run.
- [Affects R12][Technical] How is C-CAP's convergence status propagated from `ccap.py` through `train_multiphase` to the oracle's logging? If the status isn't surfaced, R8 and R12 require a plumbing change.
