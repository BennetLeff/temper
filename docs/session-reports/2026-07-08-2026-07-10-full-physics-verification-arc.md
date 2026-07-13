# Session Report — Full Physics Verification Arc

Date: 2026-07-08 / 2026-07-10
PR: [#145](https://github.com/BennetLeff/temper/pull/145) — single integration PR containing all work
Issues: 20+ opened, closed, or tracked
Branch: `integrate/physics-onto-main` (rebase of the full stack onto post-JAX-retirement `main`)

---

## Executive Summary

A physics-informed placement/routing thermal feature was built, verified with an invariant/PBT/BMC battery, had its safety-path inputs walked from garbage to real values (133,225 °C → 114.9 °C with real copper, real device power, a real heatsink model, and a real heatsink reference), and was re-framed into a three-target verification ladder (correctness/soundness/validity) with an external MFEM-FEM corroboration climbing the validity rung. The claimed-vs-enforced gap was made a first-class, measured, ticketed quantity. Every learning is either an executable CI gate or a documented scope boundary with a named instrument.

---

## What was built

### 1. Physics feature (10 units)
Thermal cost field driving A* routing and the W5 fixed-point loop. Includes pre-registration & kill-criterion artifact, margin scorecard, helps-battery A/B harness (kill-capable by construction), `CostField`/fail-closed `FieldResult`, thermal FDM solver (geometry-faithful, reads real routed copper), operating-point gate, independent scorer, A* cost injection via existing kernel seam, fixed-point field feedback, and helps-battery run orchestrator.

### 2. Verification rigor (10-unit plan, ~500 tests)
Two soundness fixes made the verdict non-provisional: operating-point bounding (added continuous coupling model + monotonicity proof + interior-sampling safeguard) and the scorer was rebuilt from solver-independent to model-independent (convective-boundary variant). Invariant batteries: energy conservation, M-matrix monotonicity, discrete max principle, SPD well-posedness, metamorphic symmetry, order-of-accuracy refinement ladder, A*-vs-Dijkstra same-cost oracle (BMC-exhaustive + PBT), loop termination-vs-convergence split, counter-invariant stateful PBT, verdict totality/monotonicity/kill-reachability, fail-closed sum-type + prereg-ordering fuzz. Methodology documented and CI-wired.

### 3. The safety-path temperature ladder
The thermal verdict started at **189,000 °C** (pure-FR4 garbage) and ended at **114.9 °C** (conservative lumped) / **~94 °C** (FDM with copper spreading) with **+35 °C margin** to T_j_max 150 °C. Each step was a real input replacing an assumption:

| # | Gap | Fix | Peak T_j |
|---|-----|-----|----------|
| #137 | Zero copper → pure-FR4 solver | Real copper from board stackup planes | 133,225 → 303 °C |
| #140 | Placeholder device power (60 W) | Datasheet-grounded per-device conduction+switching loss | 303 → 649 °C (grid confound; power was neutral) |
| #141 | No through-plane heatsink path | Fin/screened-Poisson sink term from R_θCS+R_θSA config | 649 → 124 °C |
| #142 | R_θSA = 2.0 K/W placeholder | **1.0 K/W** — Wakefield 694-100 extrusion family, 75mm, natural convection, de-rated 1.25× for induction-cooker enclosure | 155 → 115 °C (lumped), +35 °C margin |

A conservative-T_j safety ceiling was added to U11: the gate now independently enforces `max(T_j_fdm, T_j_lumped) ≤ T_j_max` — the conservative estimate decides whether a switch survives.

### 4. Three-target verification ladder
The verification was reframed into three distinct targets with different instruments. This replaced the earlier "hardware is the only real validation" framing and clarified what could be attacked in-box:

| Target | Instruments (built this session) | Status |
|--------|----------------------------------|--------|
| **Correctness** (code ↔ model) | MMS (solver converges to the right solution at 2nd order, not just the right rate), conservation + max-principle + symmetry invariants | **Gate** ✅ |
| **Soundness** (claims ↔ logic) | Verified-interval bounds: all four thermal parameters provably monotone via M-matrix property; corner-bound is a mathematical guarantee | **Gate** ✅ |
| **Validity** (model ↔ physics) | Datasheet-R_θ lumped cross-check (U11 — 0-D resistor network vs 2-D distributed PDE, +35 °C margin). External MFEM-FEM corroboration (compiled, tested, gate fail-closed when absent). Hardware power-on measurement (deferred, documented) | **Partial** (U11 + MFEM scaffold; hardware deferred) |

### 5. External MFEM-FEM corroboration
Evaluated Elmer vs MFEM for the external independent-model corroboration. MFEM won decisively: zero-dependency serial build (`make serial -j4` in <1 min), `brew install mfem` in ~30s, BSD license, Poisson example maps directly to steady-state thermal conduction. A custom MFEM solver was compiled (writes CSV output), four Python modules were built (runner/mesh/compare/gate), the pipeline shape was proven correct via an Elmer scaffold (subsequently removed), and 14 MFEM tests pass — the gate correctly returns UNMEASURED when the binary is absent (fail-closed).

### 6. Compound knowledge cluster
A 13-doc knowledge cluster in `docs/solutions/` capturing the reusable principles:
- **Bugs found and fixed:** 1st-order Dirichlet BC (refinement ladder), endpoint bounding (monotonicity proof), cycle-detector false-positive (converging field misread as oscillation).
- **Techniques:** MMS correctness, verified-interval soundness, Dijkstra-same-cost oracle, termination-vs-convergence.
- **Methodology:** Invariants verify the model not reality, solver-independence vs model-independence, the three-target verification ladder, external-FEM evaluation criteria.
- All internally cross-referenced. The three-target ladder is the organizing taxonomy.

### 7. Integration onto post-JAX-retirement main
`origin/main` advanced 20 commits (JAX retirement) while the physics stack was in-flight. A delete/modify conflict on `multi_seed_experiment.py` was resolved (the U8 `decide_verdict` refactor had already decoupled the battery). Overlapping edits on `loop.py`, `thermal_potential.py`, `.loc-allowlist.txt` and auto-merged collisions on `physics_oracle.py` / `astar_pathfinding.py` / `pipeline.py` were resolved. Stacked PRs #125 and #135 superseded by single integration PR #145. ~500 feature tests pass on the integrated tree.

### 8. Backlog resolution
Every claimed-vs-enforced gap was measured, ticketed, and tracked to closure: L2 worst-case-perturbation guard (#133), latent P2 fail-closed/type traps (#138), vulture hygiene (#128), LOC-cap hygiene (#129), R_θSA heatsink reference (#142), U11 cross-check (#131), Elmer→MFEM conversion. The gap is now a first-class, measurable quantity — the discipline self-applying.

---

## State of the repo

One mergeable PR to `main`: [#145](https://github.com/BennetLeff/temper/pull/145) (`integrate/physics-onto-main`). ~500 tests pass; import-boundary, LOC-cap, vulture (our files), and actionlint clean. Type-check pre-existing red on main (not our gate). Two non-blocking pre-existing-cleanup issues open: [#146](https://github.com/BennetLeff/temper/issues/146) (complete JAX retirement) and [#147](https://github.com/BennetLeff/temper/issues/147) (tracked run-artifact cleanup). Code work is complete. A human review/approval is needed to merge.

The safety-path thermal verdict is now corroborated by real inputs at every layer of the fidelity ladder, MMS-proven for correctness, verified-interval-bounded for soundness, and MFEM-scaffolded for the validity-proxy rung. The power-on hardware measurement remains the deferred closing instrument — correctly, not as an oversight.
