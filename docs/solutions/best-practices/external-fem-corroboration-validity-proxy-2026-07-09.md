---
title: External-FEM corroboration is a validity-proxy, not a soundness proof — the three-target verification ladder
date: "2026-07-09"
category: best-practices
module: temper_placer
problem_type: best_practice
component: verification
severity: high
applies_when:
  - "adding a second genuinely-independent physical model to corroborate a production solver"
  - "two solvers from different families (FDM vs FEM) agree and you want to interpret the result"
  - "building a verification ladder that spans correctness, soundness, and validity"
tags:
  - verification
  - multi-model-corroboration
  - validity-proxy
  - thermal
  - elmer
  - fem
---

# External-FEM corroboration is a validity-proxy, not a soundness proof

## Context

The thermal FDM solver is correctness-proven (MMS, 2nd-order) and soundness-proven
(verified-interval bounds). The lumped-R_theta cross-check (U11) corroborates
device T_j via a 0-D resistor network. But both instruments share the same model
family (distributed conduction PDE with effective-medium k_eff). A genuinely
independent 3-D FEM solver — different mesh (unstructured tetrahedral vs structured
2-D), different element type (FEM vs FDM), different codebase (Elmer vs scipy),
and additional physics (through-plane convection, radiation) — provides a new
axis of evidence: the **validity-proxy** rung.

## Guidance

The three-target correctness/soundness/validity ladder:

| Rung | Instrument | What it proves | Strength | Limitation |
|------|------------|---------------|----------|------------|
| **Correctness** | MMS (manufactured T* → Q* → solve → ‖T_h − T*‖) | The solver converges at the right order to the right answer for the given PDE. | Gold-standard for implementation bugs. | Assumes the PDE is the right model. |
| **Soundness** | Verified-interval bounds (BMC + k-induction over property space) | The solver's output maintains physical invariants (conservation, monotonicity, maximum principle) under all inputs up to N. | Algebraic guarantee — no statistical sampling. | Bounded to the property class; doesn't cover model error. |
| **Validity-proxy** | External-FEM corroboration (Elmer 3-D vs FDM 2-D) | An independent model with different physics approximates the same full-field temperature within a pre-registered tolerance. | Two-model corroboration is the strongest non-hardware evidence. | Still proxy evidence — shared assumptions remain (k_eff, vias-as-bulk, board-geometry fidelity). Hardware is the closing instrument. |

**Apply the three-target ladder:**

1. **Correctness first.** MMS proves the solver converges to the right answer.
   Without it, corroboration agreement proves nothing — two wrong solvers can agree.
2. **Soundness next.** Verified-interval bounds prove the solver's output maintains
   physical invariants under all inputs. A corroboration discrepancy with a
   soundness-level invariant intact locates the gap to model assumptions, not
   bugs.
3. **Validity-proxy last.** External-FEM corroboration brings a genuinely
   different physical model (3-D conduction, through-plane convection, radiation)
   — not just a different linear solve of the same stencil. Agreement across model
   families strengthens the claim that the 2-D model captures the dominant physics;
   disagreement with spatial attribution localises the physics gap.

**When Elmer is absent (not installed):** the corroboration gate returns
`UNMEASURED` (fail-closed, never a silent pass). This is the same discipline as
the `NgspiceValidator.check_ngspice()` preflight — absence of the instrument is
information, not a pass.

## Why This Matters

Two implementations agreeing (solver independence) is not evidence of physical
correctness — this is the lesson of `solver-independence-is-not-model-independence`.
Two genuinely different physical models agreeing (model independence) IS evidence
that the dominant physics is captured — the multi-model corroboration closes the
gap that MMS and soundness bounds leave open. But it's still proxy evidence: the
power-on hardware measurement (deferred, per the model-vs-reality scope boundary)
is the closing instrument.

## When to Apply

- When a production solver is MMS-verified and soundness-proven, and you need a
  third axis of evidence before hardware.
- When building a verification ladder for a physics-informed EDA feature — the
  three-rung ladder provides defence-in-depth.
- When the external tool is unavailable (CI skip, missing CLI, cross-platform
  issues): fail-closed `UNMEASURED` is the correct behaviour, never a silent
  `CLEAN`.

## Examples

- **ElmerCorroborationGate**: runs preflight → mesh conversion → Elmer solve →
  full-field ΔT map → gate result (CLEAN/VIOLATIONS with spatial attribution map/
  UNMEASURED). When Elmer is absent, returns `UNMEASURED`. When present but the
  fields disagree beyond the pre-registered tolerance, returns `VIOLATIONS` with
  spatial attribution (device, near-heatsink, far-field, copper-plane).
- **NgspiceValidator**: same fail-closed preflight discipline — `check_ngspice()`
  returns False when the binary is missing or non-functional.

## Related

- `docs/solutions/best-practices/mms-proves-correctness-converge-to-right-answer-2026-07-09.md` (correctness rung)
- `docs/solutions/best-practices/verified-monotonicity-ladder-soundness-property-2026-07-09.md` (soundness rung, extrapolated)
- `docs/solutions/best-practices/solver-independence-is-not-model-independence-2026-07-09.md` (oracle independence)
- `docs/physics-verification-methodology.md` (full three-target ladder)
- `docs/plans/2026-07-09-002-feat-external-elmer-fem-corroboration-plan.md` (implementation plan)
