---
title: Three-target verification ladder separates what instruments can close in-box from what needs hardware
date: "2026-07-10"
category: best-practices
module: temper_placer
problem_type: best_practice
component: testing_framework
severity: high
applies_when:
  - "building a verification strategy for a physics or numerical model"
  - "treating 'hardware measurement' as the only real validation and under-investing in in-box targets"
  - "a verification claim conflates different targets (e.g. calling a solver check 'validated')"
tags:
  - verification
  - correctness
  - soundness
  - validity
  - map-vs-territory
  - methodology
---

# Three-target verification ladder separates what instruments can close in-box from what needs hardware

## Context

A physics-simulation verification effort was framed as three separate but complementary targets, rather than a single binary "verified vs not." Treating model-correctness (code ↔ model), claim-soundness (claims ↔ logic), and physical-validity (model ↔ physics) as three distinct rungs clarified what could be attacked with in-box instruments and what genuinely required hardware — preventing both over-claiming ("the invariants close map-vs-territory") and under-investing ("hardware is the only real validation, so why build anything else").

## Guidance

Separate the verification ladder into three targets with different instruments:

| Target | Question | Closable in-box? | Instruments |
|--------|----------|------------------|-------------|
| **Correctness** | Does the code solve the model right? (code ↔ model) | **Yes** — near-rigorous without hardware | Method of Manufactured Solutions (MMS): pick an analytic solution, derive the source that produces it, feed it to the solver, check recovery. Conservation invariants. Maximum-principle invariants. Symmetry checks. |
| **Soundness** | Are the claims/bounds logically valid? (claims ↔ logic) | **Yes** — mathematically sound without hardware | Verified-interval bounds: if the response is provably monotone in uncertain parameters (M-matrix property), the worst-case corner is a mathematical guarantee, not a sample. Monotonicity proofs for swept parameters. |
| **Validity** | Does the model match reality? (model ↔ physics) | **No** — only hardware closes this | External-FEM corroboration (a genuinely different solver family and codebase), datasheet-based cross-checks (lumped R_θ vs distributed k_eff), physical measurement (thermocouple/IR on instrumented boards). |

Each rung earns its own claim. "Two different solvers of the same discretization agree" is not validity evidence — it only recertifies the numerical solve. "MMS proves convergence to the right solution" is a correctness claim, not a validity claim. "The corner-bound holds for all parameter configurations" is a soundness claim. Keeping the targets separate prevents each rung from masquerading as a stronger one.

## Why This Matters

Conflating the three is how map-vs-territory failures survive verification — a solver-convergence check labeled "validation," or invariants that pass on a physically wrong field cited as correctness evidence. Separating them makes over-claiming visible ("correctness, not validity") and also prevents the symmetry error of treating hardware as the only instrument worth building: correctness and soundness are fully attackable in-box, and investing there raises the evidence floor for any eventual hardware test to clear.

## When to Apply

- Any verification strategy for a simulation or numerical model where "verified" is being used as a single undifferentiated claim.
- When a team is either under-investing in in-box checks (waiting for hardware) or over-claiming what in-box checks establish (calling solver agreement "validation").
- Before writing a success criterion that includes "verified" or "validated" — classify which rung is being claimed.

## Examples

For a 2-D thermal FDM solver on a PCB:
- **Correctness:** MMS with manufactured analytic T(x,y) and spatially-varying k confirms the solver converges to the right solution at 2nd order. Conservation (heat in = flux out) and maximum-principle invariants pass. Neither requires hardware.
- **Soundness:** All four thermal parameters (power, conductivity, ambient, through-plane sink) are provably monotone via the M-matrix property. The worst-case corner of the uncertainty box is a mathematical bound — if the verdict holds there, it holds everywhere. No sampling required.
- **Validity (proxy):** A lumped datasheet-R_θ cross-check (different model form: 0-D resistor network vs 2-D distributed PDE) corroborates per-device T_j to within ~20 °C. An external 3-D FEM (MFEM, different solver family, different codebase) corroborates the full temperature field. Neither closes the gap — the power-on hardware measurement (thermocouple/IR vs prediction) is the only instrument for physical correspondence.

## Related

- `docs/solutions/best-practices/invariants-verify-model-not-reality-2026-07-09.md` (the L5 scope boundary — invariants close model-consistency, not physical correspondence)
- `docs/solutions/best-practices/mms-proves-correctness-converge-to-right-answer-2026-07-09.md` (MMS as the correctness instrument)
- `docs/solutions/best-practices/verified-monotonicity-bounds-close-sweep-soundness-2026-07-09.md` (verified-interval bounds as the soundness instrument)
- `docs/physics-verification-methodology.md` (the full three-target ladder documented)
