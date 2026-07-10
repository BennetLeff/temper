---
title: Solver-independence is not model-independence for validation oracles
date: "2026-07-09"
category: best-practices
module: temper_placer
problem_type: best_practice
component: testing_framework
severity: high
applies_when:
  - "building an independent instrument to validate a physics or numerical solver (the 'does it help / is it right' oracle)"
  - "two implementations agree and you want to conclude the underlying model is correct"
  - "a validation claim (e.g. H6 'scored by an independent instrument') rests on two solvers agreeing"
tags:
  - validation
  - oracle-testing
  - independence
  - physics
  - map-vs-territory
---

# Solver-independence is not model-independence for validation oracles

## Context
The physics feature shipped an "independent" thermal scorer to validate the in-loop thermal field (claim H6: "scored by an instrument independent of the field being optimised"). The scorer used **Gauss-Seidel/SOR iteration** while the field used a **direct sparse solve** — genuinely different *solver families*. But both solved the **same PDE, same 5-point stencil, same conductivity reconstruction**. Its own docstring admitted "Same PDE … same physics."

## Guidance
For a validation oracle to test the **model**, it must differ from the system under test on a **model** axis, not merely a **solve-method** axis:

- **Solver-independent (insufficient):** direct vs iterative, dense vs sparse, different linear-algebra library. These converge to the *same discrete solution* — agreement only confirms the linear solve is bug-free, not that the discretisation/physics is right.
- **Model-independent (what H6 needs):** a different discretisation *or* a different physical model — e.g. add a convective (Robin) boundary term the in-loop solver omits, use a boundary/Green's-function method vs domain FDM, or a stochastic random-walk vs deterministic PDE. Now agreement carries information about the physics.

Also document the **shared assumptions that remain** (effective interface conductivity, conduction-only, vias-as-bulk, no 3-D gradient) — shared systematic bias is a limitation no falsifiability test can rule out. And write a **falsifiability test**: a constructed input where the two are *expected to disagree* by a quantified threshold, on a case where both are correct under their own assumptions (not where one simply ignores a term — that games the threshold).

## Why This Matters
This is the map-vs-territory failure hiding *inside* the validation layer. A solver-only-independent oracle gives false confidence: it will agree with a physically-wrong-but-consistently-discretised field, greenlight a bad board, and the error only surfaces at hardware bring-up. The whole keep/kill verdict rested on this instrument — a fake-independent oracle makes every downstream "it helps" conclusion untrustworthy.

## When to Apply
- Any "independent instrument" / oracle used to validate a solver, estimator, or model.
- Whenever a correctness or "helps" claim is justified by two implementations agreeing.
- Extends the same-objective rule (`bfs-oracle-cost-model-mismatch`) from cost models to physical models.

## Examples
The fix: rebuilt the scorer as a **convective-boundary FDM** — same in-plane stencil, but a Robin `h·(T−T_amb)` term at the non-heatsink edges (the in-loop solver treats those as adiabatic). Deterministic, cheap, and genuinely model-different. Falsifiability check on a high-Biot geometry: the two disagree by ~348 °C ≫ the 1 °C threshold, proving independence; on the closed-form limiting case they still agree (both correct there).

## Related
- `docs/solutions/best-practices/bfs-oracle-cost-model-mismatch-astar-validation-2026-06-28.md` (same-objective oracle rule)
- `docs/physics-verification-methodology.md` (independent-oracle rule)
