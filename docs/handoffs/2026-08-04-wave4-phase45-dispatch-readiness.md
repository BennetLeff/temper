# Wave-4 Phase 4/5 Dispatch Readiness — 2026-08-04

**Date:** 2026-08-04
**Measured at:** `origin/main` `aece7c372` (via scratch worktree `/private/tmp/wt4-investigate`, source-only; inventory script was scratch, not committed)
**Scope:** investigation to make Phases 4 and 5 dispatchable to worker agents. Per-module numbers come from the AST import inventory (LOC per file, first-order intra-package importers), the pyo3 boundary scan, and the verdict ledger.
**Ledger authority:** `docs/wave4-verdicts.yaml` IS the phase assignment (guide's own words). Where the guide (`docs/MIGRATION_PHASE_GUIDE.md`) and the ledger disagree, the ledger wins (see discrepancies below).

## Already in flight / landed — do NOT dispatch

| Item | Status |
|---|---|
| #701 board/netlist contracts (Phase 3 cand 1 / Phase 2 in-flight) | open PR, 8.1k+ lines, 3 inherited-red gates only |
| #694 DSN emitter (Phase 3 cand 6) | open PR |
| #697 metrics/ quality analyzers (Phase 4) | open PR |
| #695 geometry drc_inflate + GEOS R3-keeps (Phase 4) | open PR |
| #692 R7 UNDECIDED backlog close, #693 verdict-coverage CI gate | open PRs |
| metrics/quality_score, metrics/routing_quality, physics/device_power, physics/thermal.junction_temp, physics/inductance | landed |
| geometry/ — 9 of 10 files already import `temper_geometry` | mostly Rust-backed already |

## Phase 4 — remaining candidates, in dispatch order

Seed crates exist for every row; R24 (physics) applies where flagged.

| # | Candidate | LOC (main) | Seed crate | Physics-gated (R24) | Notes |
|---|---|---|---|---|---|
| 1 | `physics/` kernels: tj_cross_check 537, parameter_bounds 482, copper_coverage 269, heat_removal 157, emi 69, safety 60 | ~1,570 | temper-thermal (19 pyfn; 5 landed precedents) | **YES — full R24 discipline** | **UPDATE 2026-08-04: #713 LANDED thermal_potential + operating_point** (merged `facaed149`, 21:25Z). Remaining six: only emi.py+safety.py (129 LOC) are fully non-delegating; copper_coverage/heat_removal/parameter_bounds/tj_cross_check already have temper_* delegation to extend. KTD9 keeps stay: loop_area 240 + thermal_fdm 523 hold scipy.spsolve Python-side. |
| 2 | `validation/` DRC-check slice: drc_oracle 650, geometric 607, drc 577, drc_runner 391, drc_fence 484, trace_analyzer 105, tht_check 66 | ~2,900 | temper-drc-rs (9,013 rs, 2 pyfn — target shape) | thermal_scorer/rtd_safety/battery_run are gated, not this slice | The `rules/*` dirs in temper-drc-rs already cover clearance/courtyard/creepage/etc — the Python slice maps onto them. |
| 3 | `constraints/`: compiler 530, builder 441, reporter 599 | 1,570 | temper-constraint-compiler (3,471 rs, 11 PyAny) | no | Smallest self-contained surface; ledger-assigned Phase 4. |
| 4 | `topological/`: graph 327, initial_placement 394, force_refinement 290, zone_solver 220, propagation 199 | 1,430 | none named — needs home decision | some (thermal-aware init) | **DO NOT DISPATCH — #714 in flight (2026-08-04)**: fails CI on a real parity defect — perf A/B arms disagree at 120 iterations / lr 0.05, a combination the differential doesn't cover. Surface is owned until that PR resolves. |
| 5 | `fields/` 253 + `manufacturing/` 631 + `extraction/` hypergraph_factory 119 | ~1,000 | fields: none named; extraction: hypergraph uses scipy | extraction: scipy boundary | extraction/hypergraph_factory.py uses scipy (`core/hypergraph.py` too) — expect a keep-Python boundary call, same pattern as KTD9. |
| ? | `regression/` 3,113 (drc_ratchet 579, physics_oracle 468, closure_test 455, corpus_runner 395, …) | 3,113 | n/a | physics_oracle | **Verdict question, not a build**: gate/harness support surface. Migrating makes the harness depend on the boundary it checks — the same reasoning as the `testing/`/`fixtures/` JUSTIFIED-KEEPs. Recommend an R3 JUSTIFIED-KEEP discussion before any agent touches it. |
| ? | `placer/cp_sat/**` (11,257) + `placer/` remainder 8,894 total | — | ortools | — | Ledger says `placer/**` UNDECIDED "gated on Phase 1" — stale: the Phase 1 KEEP verdict landed (handoff, evidence doc 2026-08-01). Needs a verdict update: solver boundary JUSTIFIED-KEEP w/ the ortools blocker; non-solver compute Phase 4. #692 may cover; verify. |
| deferred | `validation/drc_types.py` 581 + `drc_result.py` 779 | 1,360 | — | no | Phase 2 **contracts** (ledger note), not Phase 4 compute — fold into the next contracts wave, not the compute wave. |

## Phase 5 — ordering by boundary crossings removed (not LOC)

Total surface ≈ 49k python LOC: router_v6 23,785, deterministic 6,115, pipeline 4,899, heuristics 4,148, cli 1,416, requirements 851, report 623, adapters 368, explainability 2,106, temper-workflow 458, `_adapter_convert.py` (not present at main — check at pull time; ledger lists it in the plan's scope).

The "callers will migrate" test (guide's measured warning: a Rust kernel behind a per-call marshalling boundary can be net-negative, 1.9× slower at n≈256): prioritize modules whose importers are already Rust or migrate in the same wave.

| Order | Slice | Why first | Notes |
|---|---|---|---|
| 1 | `deterministic/stages/*` leaf compute (≈5,900 of 6,115): courtyard_check 186, clearance_grid 42, via_placement 59, zone_geometry 98, drc_sweep 249, drc_validation 70, … | All imp=0 leaves (registry-invoked) → no consumer adaptations; map 1:1 onto temper-drc-rs / temper-geometry rule kernels | Do `deterministic/state.py` (imp 21) + `stages/base.py` (imp 16) last — the hubs. `apply_placements.py` (33) is the `dataclasses.replace()` regression site from the guide — budget a consumer-semantics pin for it. |
| 2 | `pipeline/stages/*` leaves + observers (41–247 each) | Same leaf logic; DAG spine (dag_types imp 11, state imp 7, dag_engine 471) last | `pipeline/feedback.py` uses scipy — boundary call expected. |
| 3 | `router_v6/` first slices: astar_core 654 (imp 11) + astar_core_rust 242 (bridge precedent already exists) → temper-rust-router-core (7,525 rs, 0 pyfn); stage0_data 188 (imp 29, data hub, contract-like) | astar_core already has a Rust twin; stage0_data is the data hub every stage consumes | **Keeps**: channel_skeleton (shapely Voronoi spike-gated), constraint_model + routing_results (Phase 2 contracts; handoff recorded JUSTIFIED-KEEP for routing_results w/ 9-unmigrated-types blocker). |
| 4 | `cli/` 1,416, `adapters/` 368, `report/` 623, `requirements/` 851, `explainability/` 2,106, `temper-workflow` 458, `heuristics/` decision points 4,148 | Strangler wrappers + dispatch flags — the pyo3 boundary finally collapses here | The last wave; heuristics are the decision points the guide calls out. |
| after | `router_v6/` orchestration remainder (~20k) | — | Largest single surface; per-module boundary scan at pull time. |

Boundary density re-measured at main (guide cited ~512 markers/44k rs): 240 `#[pyfunction]` + 48 `#[pyclass]` + 59 `Py<PyAny>` across 48.7k rs LOC. PyAny is the "not-really-migrated" form: design-bundle 28, constraint-compiler 11, rust-router 10, io-types 3, quality-oracle 4, drc-rs 2, placer 1.

## Ledger discrepancies found (decide before dispatching into them)

1. **heuristics/** + **explainability/** — ledger says **Phase 5**; the guide's Phase 4 section lists them under Phase 4 (its 4,319/2,182 numbers). Ledger wins; the guide's Phase 4 LOC totals are off by those two surfaces.
2. **pcl/** + **_constraint_types/** — ledger still `MIGRATE phase 2` (even after #692); the 2026-08-03 handoff recorded `pcl/constraints.py` JUSTIFIED-KEEP'd with blockers. One of them is stale — resolve before building pcl.
3. **placer/** — ledger UNDECIDED is stale vs the landed Phase 1 KEEP verdict (see above).
4. **regression/** — recommend R3 JUSTIFIED-KEEP discussion (harness surface).

## Non-reimplementable library boundaries (keep-Python pattern, argue in-source)

- **scipy** (14 users): physics/loop_area + thermal_fdm (KTD9 recorded), core/hypergraph, router_v6/_astar_heuristics, _zone_pour_stitch, channel_widths, constraints_spatial_index, routability_check, zone_emission, validation/mfem_compare, thermal_scorer, trace_analyzer, pipeline/feedback, extraction/hypergraph_factory.
- **shapely/GEOS** (~20 users): the guide's buffer(r).bounds trap (169/169 mismatch); router_v6/channel_skeleton spike-gated; geometry/drc_inflate (#695 in flight).
- **np.linalg.eigh**: core/netlist.py (stays Python, recorded in #701).

## Suggested next dispatch batch (after the 4 in-flight Phase 3 agents report)

Batch 1 (compute, seeds exist): physics kernels → temper-thermal (R24); validation DRC-check slice → temper-drc-rs; constraints/ → temper-constraint-compiler.
Batch 2 (Phase 5 first slice): deterministic leaf stages → temper-drc-rs/temper-geometry; pipeline leaves; router_v6 astar_core + stage0_data.
Batch 3: topological (after home decision), fields/manufacturing/extraction, then the orchestration collapse.
Parallel with all: the four ledger items above (decision work, not builds — fits the R7 procedure).
