---
title: "fix: Physics Oracle Metric Fix and C-CAP Experiment"
type: fix
status: stale
date: 2026-07-02
origin: docs/brainstorms/2026-07-02-physics-oracle-metric-fix-and-c-cap-experiment-requirements.md
swept: 2026-07-25
swept_basis: "insufficient evidence - needs human triage"
---

# fix: Physics Oracle Metric Fix and C-CAP Experiment

## Summary

Fix the clearance metric to report worst-pair severity and violation count against both 3.0mm IEC and 6.0mm DRC rails, wire the C-CAP feasibility projector into the physics oracle (passing real `PlacementConstraints` with `ccap_enabled=True`), and build a pre-registered multi-seed experiment runner with convergence checks and a frozen decision rule — then run it against the corrected metric to settle whether the "optimizer problem" conclusion dissolves, holds, or is inconclusive.

---

## Problem Frame

The physics oracle concluded "the optimizer is below human on clearance and thermal" from a single seed with C-CAP switched off and a clearance metric that was blind to violation count. The metric reported only the single worst HV-LV pair against a 3.0mm threshold (half the DRC's 6.0mm netclass rule), the loss's threshold disagreed with the metric's threshold, and the C-CAP feasibility projector — a 968-line Dykstra alternating-projection that explicitly pushes HV↔LV pairs apart — existed but was never activated. This plan fixes each of those confounds, then runs a 20-run experiment with a pre-registered numeric verdict so the next conclusion cannot be under-instrumented.

---

## Requirements

- R1. `compute_quality_report` surfaces four clearance numbers: `clearance_score_3mm` (worst-pair/3.0mm), `clearance_score_6mm` (worst-pair/6.0mm), `violations_3mm` (count below 3.0mm), `violations_6mm` (count below 6.0mm)
- R2. The violation-count metric counts every HV-LV pair below threshold, not just the worst
- R3. `ClearanceLoss` pushes all violating pairs toward compliance, not just the worst — aggregation matches metric philosophy
- R4. `ClearanceLoss` targets 6.0mm DRC design-rule rail; the 3.0mm rail is for reporting only
- R5. `temper.kicad_pcb` is re-scored under the corrected dual-rail metric; old 0.91 is superseded
- R6. `physics_oracle.py` passes real `PlacementConstraints` through to `train_multiphase` instead of `constraints=None`
- R7. `ccap_enabled=True` in the oracle's `OptimizerConfig`
- R8. Per-run logging records C-CAP convergence status, Dykstra cycles, and post-projection clearance at step 0
- R9. 10 seeds × {C-CAP on, C-CAP off} = 20 runs, weights frozen at current values
- R10. Pre-registered decision rule: DISSOLVED if C-CAP-on mean clearance_score_6mm ≥ 0.85 and thermal ≥ 0.45 (std < 0.05); HOLDS if best-of-10 still below human floor on both; INCONCLUSIVE otherwise
- R11. Convergence check per run: loss curve must plateau (Δloss < 1e-4/epoch over last 20%); non-converged runs excluded and flagged
- R12. C-CAP convergence status (converged / oscillation / failed) recorded per run; failure across all 10 seeds is itself the finding

**Origin actors:** A1 (Experimenter), A2 (C-CAP feasibility projector), A3 (Clearance metric), A4 (ClearanceLoss)
**Origin flows:** F1 (Metric fix), F2 (C-CAP wiring fix), F3 (Multi-seed experiment)
**Origin acceptance examples:** AE1 (Covers R1, R2, R5), AE2 (Covers R3, R4), AE3 (Covers R6, R7), AE4 (Covers R8), AE5 (Covers R9, R11), AE6 (Covers R10)

---

## Scope Boundaries

- No weight search. Weights frozen at current values (tw=4000, cw=200, lw=1, overlap=200, boundary=100, wirelength=20, spread=5) across all 20 runs.
- No new optimizer architecture. C-CAP alternatives or different descent schedules are follow-up only if verdict is HOLDS.
- No additional physics metrics (congestion, zone compliance).
- No gate-drive pin-based loop.
- No corpus baseline regeneration.

### Deferred to Follow-Up Work

- Weight search (finer 2-D sweep): if verdict is INCONCLUSIVE
- Optimizer architecture changes: if verdict is HOLDS
- Results report write-up summarizing experiment outcome

---

## Context & Research

### Relevant Code and Patterns

| Component | File | Key detail |
|-----------|------|------------|
| Physics oracle | `packages/temper-placer/src/temper_placer/regression/physics_oracle.py` | `constraints=None` at line 315; constructs `ClearanceLoss(default_hv_lv_clearance=threshold_mm)` at line 254 |
| Clearance metric | `packages/temper-placer/src/temper_placer/metrics/quality.py` | `hv_lv_clearance_score` (lines 178-251) scores single worst pair; default threshold 8.0mm |
| ClearanceLoss | `packages/temper-placer/src/temper_placer/losses/clearance.py` | `_compute_hv_lv_penalty` (line 110) sums `jnp.sum(violations**2)` across ALL pairs; `default_hv_lv_clearance=10.0` constructor param |
| C-CAP | `packages/temper-placer/src/temper_placer/optimizer/ccap.py` | `CcapResult.converged` and `.oscillation_detected` surfaced (lines 74-92); no-op when `constraints is None` (line 856) |
| train.py wiring | `packages/temper-placer/src/temper_placer/optimizer/train.py` | C-CAP gated at line 406: `if ccap_enabled and constraints is not None`; status logged but not used for control flow |
| Config | `packages/temper-placer/src/temper_placer/optimizer/config.py` | `ccap_enabled=False` (line 206); `MultiSeedConfig.enabled=False` (line 305) |
| Derivation | `packages/temper-placer/src/temper_placer/pipeline/derivation.py` | `derive_constraints_from_spec` returns `dict`, not `PlacementConstraints` |
| PlacementConstraints | `packages/temper-placer/src/temper_placer/io/config_loader.py` | ~30-field dataclass starting at line 666 |
| Oracle tests | `packages/temper-placer/tests/regression/test_physics_oracle.py` | 524 lines; three-case clearance, thermal TDD, A/B diff smoke |
| C-CAP tests | `packages/temper-placer/tests/unit/test_ccap.py` | 470 lines; Dykstra invariants, oscillation detection, convergence, pre-flight |

### Institutional Learnings

- **Dark metrics pattern** (`docs/solutions/architecture-patterns/wiring-dark-physics-metrics-oracle-2026-07-02.md`): Every physics metric has a 6-link chain; if any link breaks, the metric returns a default that can't fail. The clearance metric was "dark" (returning 1.0) until recently wired. Proving liveness requires A/B diffs.
- **Calibrate against human first** (`docs/solutions/best-practices/calibrate-physics-targets-against-human-reference-2026-07-02.md`): Always compute the human reference score before setting optimizer targets. Rule of thumb: if human already satisfies (≥ 0.8), maintain; if human fails (< 0.5), target matching human first.
- **C-CAP architecture** (`docs/solutions/architecture-patterns/alternating-projections-constraint-feasibility-optimization-init-2026-07-01.md`): 7 pure-JAX projection operators with Dykstra algorithm, 2-cycle oscillation detection, unresolved component flagging. Typically converges in 5-8 cycles.
- **Multi-seed DPP** (`docs/solutions/architecture-patterns/dpp-diversified-multi-seed-triage-gate-placement-2026-07-01.md`): Multi-seed exists with `MultiSeedConfig` but defaults to `enabled=False`. Uses triage evaluation (30 iter) to avoid full-optimization cost per seed.
- **Never swallow exceptions in measurement code** (`docs/solutions/logic-errors/baseline-extractor-four-silent-fail-metrics-2026-07-01.md`): `try/except Exception: pass` is a critical bug pattern in this codebase. Per-run logging failures must propagate, not silently exclude runs.

---

## Key Technical Decisions

- **ClearanceLoss threshold becomes 6.0mm in the oracle.** `ClearanceLoss(default_hv_lv_clearance=6.0)` instead of the derived `threshold_mm` (currently 6.5mm from spec). The 6.0mm value matches the DRC design rule. The 3.0mm IEC rail is for metric reporting only, consistent with origin's decision that loss targets design-rule and metric reports both rails independently.
- **Dual-rail metric is a new function, not a modification of the existing single-rail metric.** Adding a new `dual_rail_clearance_report` function that returns a dict of four numbers keeps the existing `hv_lv_clearance_score` intact for backward compatibility while `compute_quality_report` adopts the new function. This avoids breaking the corpus oracle and other consumers of the single-score metric.
- **PlacementConstraints constructed in the oracle, not in `derive_constraints_from_spec`.** Building a minimal `PlacementConstraints` inside `physics_oracle.py` from the derived dict + board geometry + netlist net-class data keeps the change localized. `derive_constraints_from_spec` retains its lightweight dict contract; the oracle is the integration point that assembles the richer dataclass C-CAP needs.
- **Multi-seed experiment uses the existing `train_multiphase` loop with seed sweep, not `train_dpp_multiseed`.** The DPP multi-seed infrastructure does triage evaluation (30 iter) with diversity selection — great for finding one best seed, but the experiment needs all 10 seeds run to convergence with their full loss curves logged. A simple seed loop calling `train_multiphase` with fixed config and `train_dpp_multiseed` disabled is the right tool.
- **Convergence check is a post-hoc log analysis utility, not a training-mode change.** Per R11, convergence is checked from the logged loss curve after each run completes. No modification to `early_stopping` or `train_multiphase` is needed — the plateau criterion is applied to the loss history the training loop already records.

---

## Open Questions

### Resolved During Planning

- **Does ClearanceLoss aggregate all pairs or just the worst?** All pairs. `_compute_hv_lv_penalty` sums `jnp.sum(violations**2)` across all HV-LV pairs. R3 is verified — no code change needed to the loss aggregation.
- **Can ClearanceLoss target 6.0mm?** Yes. Constructor param `default_hv_lv_clearance` controls the threshold. The oracle already passes a derived value; changing it to 6.0 satisfies R4.
- **Does CcapResult surface convergence/oscillation?** Yes. `CcapResult.converged` (bool) and `CcapResult.oscillation_detected` (bool) are populated by `project_to_feasible` and already logged in `train.py:426`. R8 only requires the oracle to surface this log line.
- **How to bridge `derive_constraints_from_spec` (dict) to `PlacementConstraints` (dataclass)?** Build the dataclass in the oracle from board geometry, netlist net-class data, and the derived spec dict values. See U4 approach.

### Deferred to Implementation

- **Exact convergence plateau threshold for this loss landscape.** 1e-4 per epoch over the last 20% is the starting point. Adjust during implementation if actual loss curves show a long shallow tail.
- **Whether C-CAP's oscillation detection triggers a loop break.** Currently `_detect_oscillation` sets a flag but continues running. For the experiment, this is fine — the flag is logged. If C-CAP oscillation proves common, modifying the loop break behavior is deferred.
- **Multi-seed reproducibility with float seeds.** JAX PRNG is deterministic, but `seed` values may need to be carefully chosen to avoid collisions.

---

## Implementation Units

### U1. Dual-rail clearance scoring metric

**Goal:** Add a dual-rail clearance report that scores worst-pair severity and violation count against both 3.0mm and 6.0mm thresholds, then integrate it into `compute_quality_report`.

**Requirements:** R1, R2, R5

**Dependencies:** None

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/metrics/quality.py`
- Test: `packages/temper-placer/tests/regression/test_physics_oracle.py`

**Approach:**
- Add `dual_rail_clearance_report(state, netlist, hv_components, lv_components)` that computes all four numbers in a single pass through HV-LV pairs, returning a dict of `{clearance_score_3mm, clearance_score_6mm, violations_3mm, violations_6mm}`
- Both worst-pair scores use the existing `min_found_clearance / threshold` linear ramp (clamped [0, 1])
- Violation counts tally every HV-LV pair whose edge-to-edge distance is below the threshold
- The existing `hv_lv_clearance_score` is preserved; `compute_quality_report` calls the new function and surfaces the four numbers alongside (or in place of) the old single score
- The old single-score field (`hv_lv_clearance_score` in the report dict) remains for backward compatibility with corpus oracle consumers; the dual-rail fields are added as new keys

**Patterns to follow:**
- Existing `hv_lv_clearance_score` in `quality.py:178-251` for the pairwise iteration and edge-to-edge distance computation
- Existing `compute_quality_report` in `quality.py:485-562` for the report dict structure

**Test scenarios:**
- Happy path: fixture with 2 HV components and 5 LV components, all pairs above 6.0mm → `clearance_score_3mm=1.0, clearance_score_6mm=1.0, violations_3mm=0, violations_6mm=0`
- Happy path: fixture with one pair at 1.5mm (below both), one at 4.5mm (below 6.0mm only), rest above 6.0mm → `violations_3mm=1, violations_6mm=2`, worst-pair scores proportional to 1.5mm
- Edge case: fixture with 0 HV or 0 LV components → all scores 1.0, violation counts 0
- Edge case: all pairs exactly at threshold (3.0mm and 6.0mm) → edge-to-edge exactly equals threshold counts as non-violation (or passes, per existing behavior)
- Covers AE1: `temper.kicad_pcb` scored with new dual-rail metric produces four numbers with `violations_6mm ≥ 1`

**Verification:**
- `python -m pytest packages/temper-placer/tests/regression/test_physics_oracle.py::test_dual_rail_clearance_report -xvs` passes
- Human reference re-scored under new metric (U3 confirms)

---

### U2. ClearanceLoss threshold verification

**Goal:** Confirm that `ClearanceLoss` aggregates all violating pairs (already true from code audit) and wire the oracle to pass `default_hv_lv_clearance=6.0` for the design-rule rail.

**Requirements:** R3, R4

**Dependencies:** None (can be done in parallel with U1)

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/regression/physics_oracle.py`
- Test: `packages/temper-placer/tests/regression/test_physics_oracle.py`

**Approach:**
- Change `ClearanceLoss(default_hv_lv_clearance=threshold_mm)` at `physics_oracle.py:254` to `ClearanceLoss(default_hv_lv_clearance=6.0)` — hardcoded to the DRC design-rule rail
- Add a targeted unit test that constructs `ClearanceLoss` with a fixture having multiple violating pairs at different distances and asserts the loss value changes when a non-worst pair is moved (proving aggregation)
- The oracle's existing `threshold_mm` derived from spec (6.5mm) is still used for metric reporting; only the loss threshold changes

**Execution note:** Write the aggregation test first — the loss already aggregates all pairs, so the test should pass immediately, serving as a characterization guard.

**Patterns to follow:**
- Existing `ClearanceLoss` constructor usage in `physics_oracle.py:254`
- Existing test patterns in `tests/regression/test_physics_oracle.py` for constructing loss functions with fixtures

**Test scenarios:**
- Covers AE2: fixture with 5 pairs below 6.0mm (only 1 below 3.0mm) → loss value is proportional to sum of squared violations from all 5 pairs, not just the 1 below 3.0mm
- Happy path: loss decreases when the worst violating pair is moved apart
- Happy path: loss also decreases when a non-worst (but still violating) pair is moved apart
- Edge case: all pairs above 6.0mm → loss is zero
- Integration: oracle run with `ccap_enabled=False` (baseline) produces `ClearanceLoss` with 6.0mm threshold — verified via log output showing non-zero loss for placements with violations below 6.0mm

**Verification:**
- `python -m pytest packages/temper-placer/tests/regression/test_physics_oracle.py::test_clearance_loss_aggregates_all_pairs -xvs` passes
- Oracle log shows `ClearanceLoss(default_hv_lv_clearance=6.0)` in the loss construction string

---

### U3. Human baseline re-scoring

**Goal:** Score `temper.kicad_pcb` under the corrected dual-rail metric and record the four numbers as the new human floor.

**Requirements:** R5

**Dependencies:** U1

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/regression/physics_oracle.py`
- Modify: the oracle's `RESULTS.md` (or equivalent report output)

**Approach:**
- Add a `--score-human-reference` CLI flag (or a dedicated function) to the physics oracle that loads `temper.kicad_pcb`, computes `dual_rail_clearance_report`, and prints the four numbers
- Update the oracle's human-reference scoring path to use the new dual-rail metric instead of `hv_lv_clearance_score`
- Include the human baseline in the experiment output so the decision rule in U5 can compare against it

**Test scenarios:**
- Covers AE1 (together with U1): `temper.kicad_pcb` scored with dual-rail metric produces `violations_6mm ≥ 1` and the four numbers are logged
- The old 0.91 single-score field is still present but the new dual-rail numbers are the authoritative baseline
- Deterministic: same PCB scored twice produces identical numbers

**Verification:**
- Run the oracle against `temper.kicad_pcb` with the dual-rail metric; verify the four numbers are non-trivial (not all 1.0 or all 0.0) and `violations_6mm ≥ 1`

---

### U4. C-CAP wiring in physics oracle

**Goal:** Pass real `PlacementConstraints` through `train_multiphase` with `ccap_enabled=True` so the feasibility projector runs before gradient descent, and surface convergence status in per-run logs.

**Requirements:** R6, R7, R8

**Dependencies:** None (parallel with U1, U2)

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/regression/physics_oracle.py`
- Test: `packages/temper-placer/tests/regression/test_physics_oracle.py`

**Approach:**
- Construct a minimal `PlacementConstraints` inside the oracle's training setup:
  - `board_width_mm` / `board_height_mm` from parsed board geometry
  - `board_margin_mm` from config or default (e.g., 2.0mm)
  - `zones` from `pcb_spec.yaml` (if present) or empty list
  - `hv_clearance_mm` set to the derived `threshold_mm` (6.5mm from spec, or 6.0mm)
  - `net_classes`: classify nets into HV / Signal categories using the existing `_TEMPER_NET_ASSIGNMENTS` dict and netlist net-class data
  - All optional fields default to `None` or empty containers; C-CAP skips operators whose input data is missing
- Pass this `PlacementConstraints` to `train_multiphase` instead of `constraints=None`
- Set `config.initialization.ccap_enabled = True` in the oracle's `OptimizerConfig`
- After `train_multiphase` returns, extract `CcapResult` convergence/oscillation from the training result (if available) or add a log statement in the oracle capturing the C-CAP status from the training logs
- If `train_multiphase` does not return `CcapResult` to the caller, add a log interceptor or post-hoc check: parse the log output for `"C-CAP: converged=..."` lines

**Patterns to follow:**
- C-CAP wiring in `train.py:406-428` for the `if ccap_enabled and constraints is not None` pattern
- Existing `PlacementConstraints` usage patterns in `tests/unit/test_ccap.py` for minimal construction
- Existing log statements in `physics_oracle.py` for the per-run logging style

**Test scenarios:**
- Covers AE3: oracle run with `ccap_enabled=True` and real constraints → log output shows C-CAP execution before gradient descent, post-projection clearance at step 0 is recorded
- Covers AE4: oracle run with constraints that cause C-CAP oscillation → log records "C-CAP oscillation detected" and the run continues (not silently excluded)
- Happy path: oracle run with feasible constraints → C-CAP converges in ≤ 15 cycles, log records `converged=True, cycles=N`
- Edge case: oracle run with `ccap_enabled=True` but empty zone/keepout data → C-CAP runs identity projections, converges in 1 cycle
- Integration: the existing `test_temper_oracle_produces_real_score` smoke test still passes with C-CAP enabled (score may differ from baseline — that's expected and the test should update its expected range if needed)

**Verification:**
- `python -m pytest packages/temper-placer/tests/regression/test_physics_oracle.py::test_temper_oracle_produces_real_score -xvs` passes
- Manual oracle run with `--ccap-enabled` flag shows C-CAP log line before the first training epoch

---

### U5. Multi-seed experiment runner

**Goal:** Build the experiment harness that runs 10 seeds × {C-CAP on, C-CAP off} = 20 full `train_multiphase` runs against the corrected metric, applies convergence checks per run, and fires the pre-registered decision rule.

**Requirements:** R9, R10, R11, R12

**Dependencies:** U1, U2, U3, U4 (all four must be complete before the experiment can produce valid results)

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/regression/physics_oracle.py`
- Test: `packages/temper-placer/tests/regression/test_physics_oracle.py`

**Approach:**
- Add a `--multi-seed-experiment` mode to the physics oracle that:
  1. Loads the PCB spec, netlist, and board once
  2. Constructs the corrected loss factory (U2 threshold) and config (U4 ccap_enabled)
  3. Loops `seeds = [0, 1, ..., 9]` × `ccap = [True, False]` = 20 runs, calling `train_multiphase` with fixed weights and `train_dpp_multiseed` disabled
  4. After each run, extracts the loss curve (from the training history), computes plateau convergence (Δloss < 1e-4/epoch over last 20% of epochs), and flags non-converged runs
  5. For C-CAP-on runs, extracts C-CAP convergence status and post-projection clearance from logs or training result
  6. Scores each run with the dual-rail metric (U1) and thermal score
  7. Computes mean ± std for each condition (C-CAP on, C-CAP off) across converged runs only
  8. Applies the decision rule from R10 and prints the verdict: DISSOLVED, HOLDS, or INCONCLUSIVE — with the numeric values that triggered it
- Weights frozen at: thermal=4000, clearance=200, loop_area=1, overlap=200, boundary=100, wirelength=20, spread=5
- Epochs at a configurable value (default: 10000) with convergence check as a separate gate
- Output a structured summary dict (or JSON lines log) with per-run fields: `seed, ccap_on, converged, ccap_convergence_status, ccap_cycles, ccap_post_projection_clearance, clearance_score_3mm, clearance_score_6mm, violations_3mm, violations_6mm, thermal_score, plateau_check_passed`

**Technical design:**
> *Directional guidance — the convergence check is a post-hoc analysis of the training history, not a modification to the training loop itself. The plateau check computes the linear regression slope of the loss over the last 20% of epochs and asserts the absolute slope is below the threshold. Implementation sketch:*
> ```
> loss_history = result.loss_history[-n_last:]
> slope = linear_regression(range(len(loss_history)), loss_history)
> converged = abs(slope) < plateau_threshold
> ```

**Patterns to follow:**
- Existing seed loop pattern: use `jax.random.PRNGKey(seed)` for each run with `cfg = replace(config, seed=seed)`
- Existing `compute_quality_report` and `thermal_score` extraction in `physics_oracle.py:375-388`
- Logging conventions from the existing oracle's per-run output

**Test scenarios:**
- Covers AE5: experiment with 2 seeds × 2 conditions = 4 runs, each with a pre-recorded loss curve that plateaus → all runs pass convergence check, mean±std computed from all 4
- Covers AE5: experiment with a loss curve that has non-zero slope in last 20% → that run flagged non-converged, excluded from mean±std, included in summary with a `converged=False` flag
- Covers AE6: experiment produces DISSOLVED verdict when mean clearance_score_6mm=0.88 (±0.03) and mean thermal_score=0.48 (±0.02)
- Covers AE6: experiment produces HOLDS verdict when best-of-10 clearance_score_6mm=0.55 and best thermal_score=0.35 (both below human floor)
- Covers AE6: experiment produces INCONCLUSIVE when mean clearance_score_6mm=0.88 but std > 0.05
- Edge case: all 10 C-CAP-on runs show oscillation → verdict is INCONCLUSIVE (best-of-10 can't reach threshold with oscillating C-CAP), C-CAP failure recorded as finding per R12

**Verification:**
- `python -m pytest packages/temper-placer/tests/regression/test_physics_oracle.py::test_multi_seed_experiment -xvs` passes with synthetic fixtures
- Manual dry run with 2 seeds × 2 conditions at low epochs (e.g., 100) produces the structured summary without crashing

---

## System-Wide Impact

- **Interaction graph:** `physics_oracle.py` is a regression/analysis tool, not part of the training pipeline. Changes are isolated to the oracle and the metric module. No production training path is affected unless the oracle's config changes propagate to defaults (they should not).
- **Error propagation:** Per-run failures (C-CAP divergence, non-convergence, metric computation errors) must not crash the full 20-run experiment. Each run is wrapped to catch exceptions, log the failure, and continue to the next seed.
- **State lifecycle risks:** None — the oracle constructs fresh state per run.
- **Unchanged invariants:** The existing single-rail `hv_lv_clearance_score` function and its consumers (corpus oracle, other reports) are preserved. `derive_constraints_from_spec` retains its dict return contract. `ClearanceLoss` aggregation logic is unchanged (already aggregates all pairs). The `train_multiphase` signature is unchanged — only the oracle's call site changes from `constraints=None` to a constructed `PlacementConstraints`.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| C-CAP oscillation on the temper board (10 HV components in tight outline) may make all C-CAP-on runs infeasible | R12 captures this as a first-class finding — the experiment still produces a verdict (INCONCLUSIVE or HOLDS) and the oscillation finding is separately recorded, not silently lost |
| Constructing a minimal `PlacementConstraints` may miss fields that C-CAP silently requires | C-CAP gracefully degrades: operators whose input data is missing run identity projections. Test with the existing `test_ccap.py` fixtures to verify minimal construction |
| The loss plateau threshold (1e-4/epoch) may be too strict or too loose for this loss landscape | Deferred to implementation — calibrated from the first oracle run's actual loss curve. The threshold is a tunable constant in the experiment runner, not hardcoded in the training loop |
| Changing the loss threshold from 6.5mm to 6.0mm may produce worse clearance scores than the current oracle | Expected — a stricter threshold makes the clearance task harder. The dual-rail metric reports both rails, so the 3.0mm (IEC) score provides a safety floor. The decision rule uses 6.0mm scores |
| 20 runs × 10k epochs may be computationally expensive | Flag `--epochs` is configurable. Start with shorter runs (2k epochs) to validate the harness, then scale up. The experiment mode accepts an `--epochs N` override |

---

## Sources & References

- **Origin document:** [docs/brainstorms/2026-07-02-physics-oracle-metric-fix-and-c-cap-experiment-requirements.md](../brainstorms/2026-07-02-physics-oracle-metric-fix-and-c-cap-experiment-requirements.md)
- Related code: `packages/temper-placer/src/temper_placer/regression/physics_oracle.py`
- Related code: `packages/temper-placer/src/temper_placer/metrics/quality.py`
- Related code: `packages/temper-placer/src/temper_placer/losses/clearance.py`
- Related code: `packages/temper-placer/src/temper_placer/optimizer/ccap.py`
- Related code: `packages/temper-placer/src/temper_placer/optimizer/train.py`
- Related code: `packages/temper-placer/src/temper_placer/optimizer/config.py`
- Learnings: `docs/solutions/architecture-patterns/wiring-dark-physics-metrics-oracle-2026-07-02.md`
- Learnings: `docs/solutions/architecture-patterns/alternating-projections-constraint-feasibility-optimization-init-2026-07-01.md`
- Learnings: `docs/solutions/best-practices/calibrate-physics-targets-against-human-reference-2026-07-02.md`
- Learnings: `docs/solutions/architecture-patterns/dpp-diversified-multi-seed-triage-gate-placement-2026-07-01.md`
- C-CAP mathematical basis: `docs/solutions/ccap-mathematical-basis.md`
