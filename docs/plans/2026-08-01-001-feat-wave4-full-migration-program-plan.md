---
title: Wave 4 Python → Rust Full-Migration Program — Plan
type: feat
date: 2026-08-01
topic: wave4-full-migration-program
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
---

# Wave 4 Python → Rust Full-Migration Program — Plan

## Goal Capsule

**Objective:** Define the full-migration program that carries every remaining Python surface in the repo to a decided end state — migrated to Rust, retired, or kept with a written justification. The measured product surface is `packages/temper-placer/src/temper_placer` (122,466 LOC at origin/main `f4a183d52`, excluding `_constraint_types` and `profiling`), plus the wider repo Python: `packages/temper-workflow` (458), top-level `benchmarks/` (3,790), `scripts/` top-level (~33k) and its `tests/` (15,002) and `_lib/` (792) subtrees, `packages/temper-placer/{benchmarks 1,342, scripts 1,942, experiments 684, spikes 364}`, and the test suite (155,455 LOC). The durable artifact is the per-migration discipline contract: every migration carries a mandatory behavioral A/B and performance A/B, both of which must pass before merge. Each phase of the program is pulled into execution as a separate decision, interleaved with the board path.

**Product authority:** temper-placer + temper-geometry/temper-thermal maintainers, with the residual-decision procedure (R3) reviewed at the parent roadmap's product authority.

**Open blockers:** the ortools CP-SAT solver boundary (the placer solver, ~9.3k LOC of `placer/` plus the pipeline around it) is the one surface with no mature Rust drop-in; its fate is an explicit spike phase with a decision gate (R4). kiutils KiCad parse/export, shapely Voronoi, networkx min-cut, scipy spsolve, and scipy EDT carry recorded verdicts (see Dependencies/Assumptions) and become decisions under R3, not deferrals.

---

## Product Contract

### Summary

Wave 4 is the consolidation program's terminal wave: after Waves 1–3 moved the compute kernels to Rust, the remaining 122,466 LOC is delegation, orchestration, contracts, IO, and residuals — and every line of it is now a decided outcome, not a default. The program's spine is the discipline contract (behavioral A/B + performance A/B mandatory per migration); its pivot is contracts-as-pyclasses, which makes formats and orchestration tractable; its governance is a gated roadmap that commits no engineering capacity against the board path.

### Problem Frame

The migration program has proven its pattern across three waves: pure compute moves to Rust as pyo3 pyfunctions, the Python module keeps its public API and delegates, and differential tests pin bit-exact parity against a verbatim copy of the pre-migration implementation (20 `test_*_rust_differential.py` files at origin/main `f4a183d52`; 59 `*_pbt.py` modules; 4 crates with VERIFICATION.md induction proofs). Wave 1 (hot paths), Wave 2 (safety surface), and Wave 3 (remaining surface: ClearanceGrid, bottleneck geometry, clearance validator, R24 audit, creepage check, thermal scorer) all landed; the compute kernels are Rust and the remaining Python is measured at 122,466 LOC at origin/main — representative top-level modules: router_v6 29,804 · validation 12,629 · placer 9,287 · deterministic 9,134 · io 9,131 · core 7,848 · visualization 6,086 · pipeline 4,966 · pcl 4,773 · heuristics 4,319 · physics 4,224 · regression 3,176 · geometry 2,630 · cli 2,223 · explainability 2,182 · metrics 1,623. The listed modules sum to 114,035; the remaining ~8.4k is `report/`, `requirements/`, `adapters/`, `analysis/`, `topological/`, `manufacturing/`, `fields/` and module-level detail, all verified 2026-08-01 at origin/main.

Wave 4 exists now because the consolidation promise (parent roadmap R3: "one coherent migration of the surface, not three separate initiatives") is incomplete until the residuals are decided, not deferred. The blockers are recorded in-repo: ortools CP-SAT (no mature Rust drop-in — the only genuine solver boundary), kiutils KiCad parse/export (`io/`, with temper-design-bundle + temper-io-types as Rust seeds), shapely Voronoi (`router_v6/channel_skeleton.py`, spike-gated per Wave 3 Q5), networkx min-cut (partition-order follow-up recorded in `packages/temper-geometry/VERIFICATION.md`), scipy spsolve (KTD9: solver deliberately kept, measured ~5e-13 K parity), scipy EDT (KTD8: `edt` crate rejected), and the Plotly/HTML board renderer (`visualization/board_renderer.py`, 1,012 LOC). The A/B precedent is proven in-repo: the former `TEMPER_SAT_BACKEND` and `TEMPER_ASTAR_BACKEND` dispatch flags delivered identical completion rate and bit-identical route length under A/B routing (Wave 1 plan; the ASTAR flag was removed in cleanup C1 once parity was proven), and the same dispatch pattern is how Wave 4's behavioral A/B runs. The honest perf framing from Wave 3 carries: most of this surface is NOT hot loops — the drivers are consolidation and safety-confidence, and the program's gates protect correctness, not speed.

### Key Decisions

- D1. **A/B testing is BOTH, and both are mandatory merge gates** (session-settled: user-directed — chosen over a single behavioral A/B and over a single perf A/B: a migration that is correct but slow, or fast but subtly different, is not done; the repo has proven both patterns separately — the differential-oracle and the `pr-perf-check.yml` comparison — and Wave 4 makes them inseparable). Governs R1, R2.
- D2. **The ortools CP-SAT boundary is an explicit spike phase with a decision gate** (session-settled: user-directed — chosen over assuming the solver boundary stays Python and over assuming a Rust drop-in exists: no mature Rust CP-SAT drop-in exists today, so the boundary's fate is a measured verdict, and "done" is defined for each verdict — REPLACE lands a working Rust boundary through the R1 gates, KEEP records a named blocker, a version-locked solve contract, and the R24 audit holding across the boundary). Governs R4.
- D3. **Scope is everything; each residual is decided explicitly** (session-settled: user-directed — chosen over carrying forward the parent roadmap's and Wave 3 roadmap's deferrals of `scripts/`, visualization, contracts, and orchestration: nothing is assumed to stay Python; the deferrals become decisions under a defined procedure, and the program is complete only when every surface has a recorded verdict). Governs R3.
- D4. **Governance is a gated roadmap with opportunistic execution** (session-settled: user-directed — chosen over a committed execution schedule: the roadmap defines the full path, phases, gates, and the per-migration discipline contract, but each phase is pulled into execution as a separate decision interleaved with the board path, per parent R8 and STRATEGY.md's "critical path is design completion, not tooling"; the discipline contract, not the schedule, is the durable artifact). Governs R5.
- D5. **Phase order is dependency-driven, with contracts-as-pyclasses as the pivot** (session-settled by this plan — chosen over migrating the largest-LOC or highest-perf modules first, and over a formats-first alternative: the 122k LOC split is mostly contracts, IO, and orchestration; making the contract layer Rust first is what makes formats and orchestration tractable, and it is churn-heavy but zero-compute-risk, so it de-risks everything downstream. A formats-first order was rejected because parse output flows into the contract objects, so formats would re-map onto Python models first and then again onto Rust — one mapping layer either way, and contracts-first makes it one). Governs R6, R8.
- D6. **Residuals are decided by a written-evidence procedure, not by a default** (session-settled by this plan — chosen over a blanket "keep Python for glue": each residual gets MIGRATE / RETIRE / JUSTIFIED-KEEP, a JUSTIFIED-KEEP requires a named blocker or measured verdict, and "consolidation" alone is never sufficient — extending Wave 3 R7). Governs R3.

### Requirements

**The discipline contract (the durable artifact)**

- R1. Every migration carries the mandatory gate set, and all gates must pass before merge:
  - R1a. A behavioral A/B — the differential-oracle pattern, old vs new implementation on identical inputs with bit-identical outputs asserted, pinning a verbatim copy of the pre-migration implementation (the `test_*_rust_differential.py` convention, 20 files at origin/main `f4a183d52`).
  - R1b. A performance A/B — before/after wall time through the existing CI performance-comparison workflow (`.github/workflows/pr-perf-check.yml`, `scripts/pr_perf_compare.py`).
  - R1c. PBT with 5 non-vacuous properties per module, following the hypothesis-invariant suite pattern documented in `docs/solutions/best-practices/hypothesis-invariant-test-suite-pattern-2026-06-28.md`.
  - R1d. Metamorphic testing with >=3 invariant relations per module (translation/rotation/permutation/scale, honestly bounded).
  - R1e. A mathematical induction proof (base case + induction step) recorded in the crate's VERIFICATION.md, per the `packages/temper-geometry/VERIFICATION.md` convention — required where the module has recursive or computational structure; data-only modules (Phase 2 pyclasses, pure-delegation wrappers) record a structural proof or an explicit non-applicability note instead.
  - R1f. TDD — the differential test is written first, red to green.
  - R1g. The repo's Rust best practices — borrow over clone, no unwrap outside tests, catch_unwind at pyo3 boundaries.
  - R1h. For physics-gated surfaces, the R24 discipline from AGENTS.md — a Chebyshev-style soundness proof, BMC-exhaustive validation on small N, and the post-solve audit, per `docs/physics-verification-methodology.md`.
- R2. The A/B harness contract: the behavioral A/B and the performance A/B are both mandatory merge gates for every migration, with no carve-outs; the performance comparison uses the existing margins (`TIMING_MARGIN = 0.20`, `COMPLETION_MARGIN = 0.10`, `IMPROVEMENT_THRESHOLD = 0.10`) and Phase 0 wires it as a real hard gate — the comparison script exits non-zero on regression, the workflow's `continue-on-error` is removed, a required status check is configured, and a missing/empty baseline fails closed — replacing the current comment-only state and the shared `temper-N6-U8` stub ticket (the repo's own 2026-07-25-002 plan requires stubs be replaced with explicit dated decisions); where a module is pure delegation with no compute, the performance A/B is a "no regression beyond noise" comparison rather than a speedup claim, with the CI noise floor quantified in Phase 0; the performance trigger widens to cover `scripts/` and `benchmarks/` surfaces that carry migrated code.

**The residual decision procedure**

- R3. Every surface not migrated is decided by a written-evidence procedure: classify each residual as MIGRATE (assigned to a phase), RETIRE (dead or obsolete, deleted with justification), or JUSTIFIED-KEEP (a written reason naming a concrete blocker — e.g., no Rust drop-in, format churn, a library boundary, a recorded solver-kept verdict like KTD8/KTD9, or a written cost-benefit analysis showing migration net-negative); "consolidation" alone is never a sufficient justification; a JUSTIFIED-KEEP is re-decidable when evidence changes (a spike can overturn it); the procedure applies to visualization, `scripts/`, the test suite, the solver boundary, and every repo-Python surface not assigned to a phase, with each JUSTIFIED-KEEP reviewed at the product authority named in the Goal Capsule.
- R4. The ortools CP-SAT boundary is decided by an explicit spike with a decision gate: Phase 1 evaluates Rust CP-SAT replacement candidates, the effort/risk of each, and defines what "done" means for each verdict — if the gate says REPLACE, done is a working Rust solver boundary passing the R1 gate set; if the gate says KEEP a non-Rust solver boundary, done is a recorded verdict with a named blocker (no mature CP-SAT drop-in), a version-locked contract around the solve call, the R24 post-solve audit (already Rust-backed in `placer/cp_sat/audit.py`) enforcing soundness across the boundary, and a measured parity contract in the style of KTD9.

**Governance**

- R5. The program is a gated roadmap, not a committed schedule: it defines the full path, phases, gates, and the discipline contract, but each phase is pulled into execution as a separate decision, interleaved with the board path; parent R8 ("the roadmap commits no engineering capacity") and STRATEGY.md's "critical path is design completion, not tooling" are not overridden.
- R6. Contracts-as-pyclasses is the pivot phase: the churn-heavy contract layer (core models, pcl constraints, gate results, routing results, deterministic state) is migrated before formats/IO and orchestration, because parse output and orchestration calls both flow through these objects; the phase is zero-compute-risk and high-leverage.
- R7. Nothing is pre-excluded: every residual named in Scope Boundaries is a decision under R3, and the program is complete only when every surface has a recorded verdict — migrated, retired, or kept with a written justification.
- R8. Phase order is dependency-driven: Phase 0 (discipline contract + harness) precedes all migrations; Phase 1 (ortools spike) precedes the placer solver-boundary compute and the placer orchestration that delegates to it (contracts and the rest of placer compute do not wait on the gate); Phase 2 (contracts) precedes Phase 3 (formats/IO) and Phase 5 (orchestration); Phases 3 and 4 are mutually independent; Phase 6 (residuals) is last.

### Phased Migration Path

Phase LOC figures are planning decompositions of the measured 122,466 LOC total (verified 2026-08-01); per-module re-measurement happens when a phase is pulled. The per-phase ranges name representative modules, not exhaustive file lists, so they reconcile to the total only approximately — the residual gap between the phase estimates (~82–101k) and 122,466 is the module-level detail assigned at pull time. Day estimates are planning ranges, not commitments (R5).

#### Phase 0 — Discipline contract + A/B harness (the durable artifact)

| Scope | LOC | Days | Risk | Gates |
|---|---|---|---|---|
| The mandatory per-migration gate set (R1), the A/B harness contract (R2), and the residual decision procedure (R3), specified as repo documents; the CI wiring that makes the performance A/B a real hard gate (exit code, `continue-on-error` removed, required status check, fail-closed on missing baseline) | ~1–2k new harness/test LOC, 0 migrated | 3–5 | Low | The harness is validated by retrofitting the dual A/B onto one already-landed Wave 3 module — proof that both gates bite before anything is gated by them |

Dependency rationale: every other phase's acceptance is defined by this phase's contract; it ships first because it is the spine.

#### Phase 1 — Ortools CP-SAT spike + decision gate

| Scope | LOC | Days | Risk | Gates |
|---|---|---|---|---|
| Solver-replacement spike: survey Rust CP-SAT candidates (and honest coverage of their feature surface — implied constraints, search hints, assumption-based unsat cores as used by `placer/cp_sat/unsat.py`), effort/risk of each, and the recorded decision with the R4 "done" definitions for REPLACE vs KEEP | 0 migrated (spike artifacts) | 5–10 | High — decides the biggest boundary | Decision gate: the verdict is recorded under R3/R4 before any placer compute or orchestration phase is pulled |

Dependency rationale: the ortools boundary shapes how the `placer/` solver-boundary surface (the ortools model/solve wiring, ~1-2k of the 9,287 `placer/` LOC) delegates; no solver-boundary compute is pulled before the gate fires. The remaining placer compute (the constraint encoders' math and model arithmetic beyond the boundary) is assigned to Phase 4.

#### Phase 2 — Contracts as pyo3 pyclasses (the pivot)

| Scope | LOC | Days | Risk | Gates |
|---|---|---|---|---|
| `core/board.py`, `core/netlist.py`, `core/loop.py`, `core/design_rules.py`, `core/priority.py`, `core/net_types.py`, `pcl/constraints.py`, `placer/cp_sat/gates.py` Violation/GateResult, `router_v6/constraint_model.py`, `router_v6/routing_results.py`, `validation/drc_types.py`, `validation/drc_result.py`, deterministic state | ~7–9k | 15–25 | Medium — high churn, zero compute value; every call site touches these | R1 gate set (differential tests cover construction and round-trip field mapping, bit-identical); any contract that stays is a JUSTIFIED-KEEP under R3 |

Dependency rationale: formats (Phase 3) produce these objects and orchestration (Phase 5) calls them; migrating them first is what makes those phases tractable (D5).

#### Phase 3 — Formats / IO

| Scope | LOC | Days | Risk | Gates |
|---|---|---|---|---|
| KiCad parse/export via the existing Rust seeds (temper-design-bundle, temper-io-types): `io/kicad_parser.py`, `io/kicad_exporter.py`, `io/_parse_*.py`, `io/_write_*.py`, plus `io/config_loader.py`, `io/netclass_loader.py`, `io/footprint_parser.py` — kiutils leaves the boundary | ~6–8k of the 9,131 io/ total | 20–30 | High — the biggest structural chunk; format parity is finicky | R1 gate set with bit-identical round-trip fixtures on the canonical boards + corpus; the kiutils decision is itself under R3 (Wave 3 Q6's "likely stays Python" is a verdict to be earned, not inherited) |

Dependency rationale: parse output must flow into the Phase 2 contract pyclasses, so contracts land first.

#### Phase 4 — Remaining compute + data processing

| Scope | LOC | Days | Risk | Gates |
|---|---|---|---|---|
| `router_v6/channel_skeleton.py` (Voronoi — pre-spiked per the Wave 3 Q5 / KTD8 precedent), `metrics/` analyzers, `regression/`, remaining physics (`physics/thermal_potential.py`, `physics/operating_point.py`), the remaining `placer/` compute beyond the ortools boundary, `geometry/` remainder, `validation/geometric.py` and remaining pure-compute validators | ~12–17k | 25–40 | Medium-High — channel_skeleton spike; metrics/regression churn | R1 gate set; the channel_skeleton Voronoi spike is a pre-commit for that module (a third-party geometry library diverging is the recorded KTD8 failure mode) |

Dependency rationale: compute consumers call the Phase 2 contract objects; independent of Phase 3 (formats).

#### Phase 5 — Orchestration

| Scope | LOC | Days | Risk | Gates |
|---|---|---|---|---|
| `pipeline/`, deterministic stages and orchestration, `router_v6/_adapter_convert.py` and pipeline adapters, `cli/`, heuristics decision-points, router_v6 orchestration remainder | ~20–30k | 20–35 | Medium — where strangler wrappers and dispatch flags live; lowest compute value, highest call-site churn | R1 gate set; for pure-delegation modules the behavioral A/B is dispatch-parity and the performance A/B is "no regression beyond noise" (R2) |

Dependency rationale: orchestration must delegate to Rust everywhere it orchestrates, so Phases 2–4 precede it.

#### Phase 6 — Residuals decided

| Scope | LOC | Days | Risk | Gates |
|---|---|---|---|---|
| Visualization (`visualization/board_renderer.py` Plotly/HTML + status/loss_plots/live/model, 6,086 LOC): WASM/web vs retire vs JUSTIFIED-KEEP; `scripts/` top-level tooling (~33k): migrate vs retire vs keep (CI gates are churny by design — the parent roadmap's deferral becomes a written verdict); test suite (155,455 LOC in `packages/temper-placer/tests`): decide — Rust-side tests carry migrated-module coverage, the Python suite retains the differential oracles, and the suite's own fate is a verdict | ~39k + suite | 5–10 per decision; execution contingent on the verdicts | Low-Med | R3 applied to each residual: every verdict names a blocker or a retire rationale |

Dependency rationale: residuals are by definition the modules no phase claimed; they are decided last so the procedure (R3) sees the full program.

### Scope Boundaries

- Nothing is pre-excluded: the parent roadmap's deferral of `scripts/` and the Wave 3 roadmap's deferral of contracts, orchestration, heuristics, `metrics/`, `regression/`, and visualization are explicitly reversed here — each becomes a decision under R3.
- Every residual — visualization, `scripts/`, the test suite, the ortools solver boundary, the kiutils boundary, the shapely/networkx/scipy library boundaries — is a decision under R3, not a kept-by-default Python surface.
- Never in scope: firmware (a C codebase; the parent roadmap's exclusion carries unchanged).
- Deferred: a one-shot whole-surface migration — decomposition into dependency-ordered phases is the point of this plan (parent scope boundary, unchanged).
- Deferred: per-module bridge patterns beyond the established crate boundaries (temper-geometry, temper-thermal, temper-rust-router(-core), temper-drc-rs, temper-design-bundle, temper-io-types, temper-constraints) — planning's job when a phase is pulled.

### Dependencies / Assumptions

- **ortools CP-SAT (placer solver, ~9.3k LOC `placer/` + pipeline):** blocker with no mature Rust drop-in; the Phase 1 spike decides REPLACE vs KEEP under R4; the R24 post-solve audit (`placer/cp_sat/audit.py`, already Rust-backed) is the soundness invariant that holds across whichever boundary results.
- **kiutils KiCad parse/export (`io/`):** blocker; temper-design-bundle + temper-io-types are the Rust seeds; the Phase 3 migration or a JUSTIFIED-KEEP verdict resolves it (Wave 3 Q6's lean is not a verdict).
- **shapely Voronoi (`router_v6/channel_skeleton.py`):** spike-gated per Wave 3 Q5; the KTD8 `edt`-crate outcome (third-party geometry library diverges from scipy) is the precedent for why the spike precedes the migration.
- **networkx min-cut (`router_v6/bottleneck_geometry.py`):** the Rust kernels landed in Wave 3; the min-cut partition itself stays networkx per the partition-order follow-up recorded in `packages/temper-geometry/VERIFICATION.md` — a JUSTIFIED-KEEP candidate under R3.
- **scipy spsolve (`validation/thermal_scorer.py`):** KTD9 verdict recorded — the solver is deliberately kept (measured ~5e-13 K parity, no perf win); the measured parity contract is the tolerance for any future change.
- **scipy EDT:** KTD8 verdict recorded — the `edt` crate was rejected (measured max diff 2.0–2.236); scipy stays; a Rust-native exact EDT is the recorded fallback.
- **Board-path posture:** parent R8 and STRATEGY.md's "critical path is design completion, not tooling" govern execution; this plan commits no engineering capacity.
- Assumption: migrated modules exit the Python coverage gate and import-linter contracts by the established pattern; stale `.coverage-allowlist` entries are removable per the monotonic-shrink rule (deletion from source).
- Assumption: `make extensions` / `make extensions-check` / `make venv-isolate` and `scripts/check_stale_extensions.py` remain the build discipline for every migrated phase.

### Outstanding Questions

Resolve Before Planning:

- Q1. Visualization product need: is a WASM/web board renderer a real product requirement or a nice-to-have? The answer shapes the Phase 6 verdict direction, though the verdict itself is deferred.

Deferred to Planning:

- Q2. The exact Rust CP-SAT candidate list and each candidate's feature coverage — the Phase 1 spike's first output (the spike is where candidates get named, not here).
- Q3. Per-module PBT/metamorphic counts beyond the R1c/R1d minima, and exact bridge patterns — the parent roadmap deferred the same, unchanged.
- Q4. The KiCad parse/export parity tolerance (the round-trip fixture set is already specified: canonical boards + corpus, bit-identical) — Phase 3 planning.
- Q5. Which test-suite slices retire versus convert to Rust-side tests as modules migrate — Phase 6.
- Q6. Exact home-crate assignments for Phase 4/5 surfaces beyond the established boundaries — planning per pulled phase.

Settled by the body (D4/R5, Phase 0): pull granularity is per phase, and the Phase 0 harness validates by retrofitting the dual A/B onto an already-landed Wave 3 module — both former Resolve-Before-Planning questions.

### Sources / Research

- Parent roadmap: `docs/plans/2026-07-23-003-perf-rust-migration-roadmap-plan.md` (R3/R8 governance, KTD8/KTD9, per-unit pull precedent).
- Wave 3 roadmap: `docs/plans/2026-07-31-001-feat-wave3-rust-migration-roadmap-plan.md` (Q5/Q6 spikes, R7 contract-layer rule, the deferrals this plan reverses).
- Wave 1 plan: `docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md` (TEMPER_SAT_BACKEND dispatch A/B precedent, strangler pattern).
- A/B harness: `.github/workflows/pr-perf-check.yml` + `scripts/pr_perf_compare.py` (margins; Phase 0 converts the comparison from comment-only to a hard gate, replacing the shared `temper-N6-U8` stub per the repo's own 2026-07-25-002 requirement).
- Recorded verdicts: `docs/evidence/2026-07-31-edt-crate-ktd8-spike-rejected.md`, `docs/evidence/2026-07-31-ktd9-faer-vs-scipy-spike.md`.
- Discipline anchors: `AGENTS.md` R24 (Chebyshev soundness proofs, BMC-exhaustive validation, post-solve audit); `docs/physics-verification-methodology.md` (four verification layers, independent-oracle rule, fail-capable rule); the `test_*_rust_differential.py` convention and VERIFICATION.md induction proofs in `packages/temper-geometry/`, `packages/temper-thermal/`, `packages/temper-rust-router-core/`, `packages/temper-placer/temper-constraints/`.
- Governance posture: `docs/STRATEGY.md` ("critical path is design completion, not tooling").
- LOC inventory measured 2026-08-01 at origin/main `f4a183d52` via `find ... | xargs wc -l` (122,466 product Python; 33,006 top-level `scripts/`; 155,455 `packages/temper-placer/tests`).
