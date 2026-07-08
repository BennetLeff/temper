---
title: "fix: Resolve PCL constraint refs to match board components + decisive-result measurement run"
type: fix
status: active
date: 2026-07-06
origin: docs/reports/2026-07-06-umbrella-status.md
---

# fix: Resolve PCL Constraint Refs + Decisive-Result Measurement Run

## Summary

The CP-SAT placement pipeline produces 118 DRC errors vs 29 baseline because the PCL constraint file (`configs/pcl/temper_induction.yaml`) uses component refs that don't match the board's actual component refs. The encoder logs "cannot resolve components" for every constraint — none are enforced. This plan maps the stale refs to the board's actual refs (verified from `power_pcb_dataset/corpus/temper/temper.kicad_pcb`), re-runs the placement pipeline, and measures the F2/F4 decisive results (DRC violation count + UNSAT audit on an over-constrained PCL variant).

---

## Problem Frame

The umbrella status report (`docs/reports/2026-07-06-umbrella-status.md`) identified the gap: F1/F3/F5 merged with decisive results satisfied, but F2 and F4 share one root cause — constraint refs don't match board components. The encoder's `_resolve_to_indices` in `pcl/resolver.py` handles ref resolution; the constraint file just needs correct refs. This is a data-quality pass on one YAML file, not a code change.

**Verified ref mismatches** (PCL ref → board actual ref, from `temper.kicad_pcb` `property "Reference"` lines):

| PCL ref (stale) | Board actual ref | Constraint(s) affected |
|---|---|---|
| `U_GATE_DRV` | `U_GATE` | AdjacentConstraint (gate driver → Q1) |
| `C_DC` | `[C_BUS1, C_BUS2]` | EnclosingConstraint (HV zone inner list — split single fake ref into two actual DC bus caps per `pcb_spec.yaml`'s `loop_components`) |
| `C1, C2, C3, C4` | `C_MCU_1, C_MCU_2, C_MCU_3, C_MCU_4` | AlignedConstraint (MCU decoupling caps alignment) |
| `J_AC` | `J_AC_IN` | OnSideConstraint (connectors on left edge) |
| `loop_name: commutation` | `commutation_loop` (in `pcb_spec.yaml`'s `loop_components` dict) | LoopAreaConstraint — the `loop_name` key doesn't match `netlist.loop_components.get(constraint.loop_name)`'s key `commutation_loop` |

Refs that already match (no change needed): `Q1`, `Q2`, `D1`, `U_MCU`, `HV_ZONE`, `MCU_ZONE`, `J_COIL`.

**DRC bar:** F2/F4 pass if CP-SAT placement produces DRC errors ≤ the 29-violation human baseline (umbrella R4 strictly says "zero violations" but the human reference itself has 29 — we measure against baseline, not against an ideal). Strict-zero is a stretch goal, noted in the report.

---

## Requirements

- R1. All constraint refs in `configs/pcl/temper_induction.yaml` map to actual board component refs (verified against `power_pcb_dataset/corpus/temper/temper.kicad_pcb`'s `property "Reference"` lines).
- R2. The CP-SAT encoder logs show constraints being encoded (not "cannot resolve components" warnings) for every constraint in the file.
- R3. The decisive-result measurement run produces: (a) DRC violation count from `kicad-cli drc` on the placed+routed temper board, (b) UNSAT report from an over-constrained PCL variant (`max_area_mm2=10`) verifying the minimal core names the loop-area constraint AND its `because` field cites the IGBT overvoltage rationale.
- R4. Results recorded in a report at `docs/reports/2026-07-06-decisive-result-measurement.md`.

---

## Implementation Units

### U1. Apply ref mapping to temper_induction.yaml

**Goal:** Update all stale refs in `configs/pcl/temper_induction.yaml` to match the board's actual component refs.

**Requirements:** R1

**Dependencies:** None

**Files:**
- Modify: `packages/temper-placer/configs/pcl/temper_induction.yaml`

**Approach:**
Apply the verified ref mapping:
- `U_GATE_DRV` → `U_GATE` (line 20: `a: U_GATE_DRV` → `a: U_GATE`)
- `C_DC` → split into `C_BUS1` and `C_BUS2` (line 40: `inner: [Q1, Q2, D1, C_DC]` → `inner: [Q1, Q2, D1, C_BUS1, C_BUS2]` — the enclosing constraint's inner list gains the second DC bus cap; the CP-SAT encoder's `EnclosingConstraint` handler adds region-bounds for each component in the list)
- `C1, C2, C3, C4` → `C_MCU_1, C_MCU_2, C_MCU_3, C_MCU_4` (line 47: `components: [C1, C2, C3, C4]` → `components: [C_MCU_1, C_MCU_2, C_MCU_3, C_MCU_4]`)
- `J_AC` → `J_AC_IN` (line 55: `components: [J_AC, J_COIL]` → `components: [J_AC_IN, J_COIL]`)
- `loop_name: commutation` → `loop_name: commutation_loop` (line 71: matches `pcb_spec.yaml`'s `loop_components` dict key)

No other constraints need changes — `Q1`, `Q2`, `D1`, `U_MCU`, `HV_ZONE`, `MCU_ZONE`, `J_COIL` already match.

**Test expectation:** none -- pure config data fix; verification is the encoder-resolution check in U2.

**Verification:**
- `rg "U_GATE_DRV\|C_DC\b\|C1\b\|C2\b\|C3\b\|C4\b\|J_AC\b" configs/pcl/temper_induction.yaml` returns zero matches (no stale refs remain)
- `rg "U_GATE\b\|C_BUS1\|C_BUS2\|C_MCU_1\|J_AC_IN\|commutation_loop" configs/pcl/temper_induction.yaml` returns matches for all (new refs present)

---

### U2. Verify encoder resolution + run decisive-result measurement

**Goal:** Confirm the encoder resolves all constraint refs (no "cannot resolve" warnings), run the full CP-SAT placement pipeline on the temper board, measure DRC violations, and exercise the UNSAT report on an over-constrained variant.

**Requirements:** R2, R3

**Dependencies:** U1

**Files:**
- Create: `docs/reports/2026-07-06-decisive-result-measurement.md`

**Approach:**

**Step 1 — Encoder resolution check:**
Run `temper optimize temper.kicad_pcb --config pcl/temper_induction.yaml --placer cp-sat` (or equivalent test invocation). Check the encoder logs: every constraint type (adjacent, separated, enclosing, aligned, on_side, anchored, loop_area) should show an "encoded constraint" log, not a "cannot resolve components" warning. If any constraint still logs a resolution warning, the ref mapping has a remaining gap — return to U1.

**Step 2 — DRC measurement (F2/F4 decisive result):**
On the CP-SAT placed board (post-routing via router_v6), run `kicad-cli drc` with the real 6mm design rules. Record:
- Total DRC error count
- Total DRC warning count
- Comparison vs 29-violation human baseline (from `docs/reports/2026-07-06-umbrella-status.md`)
- Whether F2's bar (≤ baseline) is met

**Step 3 — UNSAT audit (F4 R6b decisive result):**
Create a temporary over-constrained PCL variant: copy `temper_induction.yaml` to `temper_induction_overconstrained.yaml` and change `max_area_mm2: 500` to `max_area_mm2: 10` on the loop_area constraint. Run `temper optimize ... --config pcl/temper_induction_overconstrained.yaml --placer cp-sat --unsat-report unsat.json`. Record:
- Solver status (INFEASIBLE expected)
- UNSAT report's minimal core: does it name the loop_area constraint?
- Does the `because` field cite the IGBT overvoltage rationale (per the updated `commutation.yaml`)?
- Whether F4's R6b bar (UNSAT report names constraint + surfaces physics `because`) is met

**Step 4 — Report:**
Write `docs/reports/2026-07-06-decisive-result-measurement.md` with:
- Encoder resolution status (all 8 constraint types encoded)
- DRC measurement table (CP-SAT vs baseline)
- UNSAT audit findings
- F2/F4 decisive-result status (pass/partial/fail per the umbrella's table)
- Any remaining gaps

**Test scenarios:**
- Happy path: CP-SAT placement with corrected refs produces fewer DRC errors than the 29-violation baseline
- Happy path: UNSAT report on over-constrained PCL names loop_area constraint with IGBT overvoltage `because` text
- Edge case: if kicad-cli is unavailable, document the oracle-proxy DRC result and flag the truth-gate as deferred
- Edge case: if a constraint still logs "cannot resolve" after U1, identify the remaining ref gap and fix in a follow-up

**Verification:**
- Encoder logs show zero "cannot resolve components" warnings
- DRC error count recorded in the report
- UNSAT report file (`unsat.json`) exists and contains the minimal core with the loop_area constraint
- `docs/reports/2026-07-06-decisive-result-measurement.md` exists with all four sections (encoder status, DRC, UNSAT, overall status)

---

## Scope Boundaries

- **Code changes** — out of scope. The encoder, resolver, audit, UNSAT extraction, and DRC runner are all complete (verified in the umbrella status report). This plan is a data-quality fix on one YAML file plus a measurement run.
- **Strict-zero DRC bar** — stretch goal, not gating. The umbrella's R4 says "zero violations" but the human reference has 29; we measure against baseline first and flag strict-zero as a follow-up if the gap is small.
- **F1/F3/F5 re-verification** — out of scope. Those workstreams passed their decisive results independently of the ref gap.
- **Multi-board corpus** — out of scope. This plan targets the temper board only.
- **`viz-server` worktree** — out of scope per the umbrella.