---
title: Choosing an external independent-model FEM — install simplicity and zero-dependency build dominate over feature matrix
date: "2026-07-10"
category: tooling-decisions
module: temper_placer
problem_type: tooling_decision
component: tooling
severity: medium
applies_when:
  - "choosing between external FEM solvers for multi-model corroboration"
  - "evaluating a tool that will be invoked as a subprocess from Python in CI"
  - "weighing install complexity vs feature richness for an infrequently-invoked verification instrument"
tags:
  - fem
  - tool-evaluation
  - mfem
  - subprocess
  - ci
  - independence
---

# Choosing an external independent-model FEM — install simplicity and zero-dependency build dominate over feature matrix

## Context

An external finite-element solver was needed as a second genuinely-independent model to corroborate the in-house 2-D thermal FDM. Two candidates were evaluated: **Elmer** (CSC Finland, established, full-featured multiphysics FEM) and **MFEM** (LLNL, BSD license, lightweight C++ finite-element library). Both are open-source, both solve steady-state thermal conduction, both output parseable results. The decision turned on a dimension that feature matrices don't capture.

## Guidance

For an infrequently-invoked, subprocess-based verification instrument — one that will be called from Python in CI, and whose primary purpose is *independence* (different solver, different codebase) rather than feature coverage — **install simplicity and build reliability dominate over the solver's physics feature set.** The evaluation criteria, in priority order:

1. **Install friction.** Can the tool be installed with one command (`brew install`, `apt install`) with no manual dependency hunting? A complex build chain is a maintenance tax paid on every CI runner provision, every dev machine setup, every macOS/Linux version bump.
2. **Zero-dependency serial build.** If the tool must be built from source, does the serial build have *zero* external dependencies? A `make serial -j` that completes in <1 minute without hunting for `umfpack.h` is more valuable than a solver with radiation physics that requires a 15-minute dependency chase.
3. **PDE-to-example mapping.** Does the tool ship an example that maps directly to the PDE being solved? A Poisson example (steady-state heat conduction) that compiles and runs with one command is more useful than a general-purpose solver that requires mastering a custom input format.
4. **Output format.** Is the output standard and parseable (CSV, VTK) with no post-processing dependencies?
5. **Licence and provenance.** BSD over GPL for an infrequently-invoked instrument; LLNL/HPC-validated over community-maintained.

Feature richness (3-D elements, convection, radiation, multiphysics coupling) only matters *after* criteria 1–4 are met — a solver that can't be installed or built reliably is not a verification instrument, regardless of its physics capabilities.

## Why This Matters

The dominant failure mode for an external-FEM corroboration is not that the solver lacks physics — it's that the solver can't be *run*. A complex install chain that breaks on a CI runner upgrade, a macOS version bump, or a dependency conflict silently degrades the gate to `UNMEASURED` (correct fail-closed posture, but the instrument provides no corroboration). The value of the corroboration is the *corroboration* — the solver that runs is infinitely more valuable than the solver that doesn't.

## When to Apply

- Choosing between two open-source tools where both are functionally adequate but differ in install/build complexity.
- Any verification instrument that will be a subprocess call from Python in CI.
- An infrequently-invoked corroboration layer, as distinct from a pipeline-stage solver that runs on every placement.

## Examples

MFEM over Elmer for the temper-placer external-FEM corroboration:

| Criterion | MFEM | Elmer |
|-----------|------|-------|
| Install | `brew install mfem` (~30s, bottle) | `brew install elmer` (source build, ~10–15 min, fragile deps) |
| Serial build | `make serial -j4` in <1 min, zero external deps | Multi-step build chain, multiple deps |
| PDE example | ex1 = Poisson (steady thermal), compiles with `make ex1 -j` | Native heat eq solver, `.sif` input format |
| Output | Custom solver writes CSV (trivial to parse) | VTU/CSV via ElmerGrid |
| Licence | BSD (LLNL) | GPL |

MFEM won on criteria 1 and 2 decisively. The custom Poisson solver compiled in <1 minute and runs on any mesh file, writing CSV output. The feature gap (Elmer has native radiation/convection) was immaterial — both solve steady-state conduction, which is the same-objective requirement for the corroboration.

## Related

- `docs/solutions/best-practices/solver-independence-is-not-model-independence-2026-07-09.md` (why a second solver of the same model is insufficient — the evaluation here is about choosing a *genuinely independent* model)
- `docs/solutions/best-practices/three-target-verification-ladder-correctness-soundness-validity-2026-07-10.md` (the validity rung this external-FEM corroboration serves)
- `docs/plans/2026-07-09-002-feat-external-mfem-fem-corroboration-plan.md` (the implementation plan)
