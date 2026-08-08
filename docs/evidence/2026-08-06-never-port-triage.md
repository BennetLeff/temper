---
title: Never-Port Triage — Remaining Python Surface
type: evidence
date: 2026-08-06
topic: wave4-never-port-triage
---

<!-- provenance: commit=d5f4593142da87c75f9b21734e0e65d0e991f16d dirty=UNKNOWN -->

# Never-Port Triage — Remaining Python Surface

**This is a recommendation, not a decision.** It does not edit
`docs/wave4-verdicts.yaml` — that ledger is the user's alone — and no code was
migrated to produce it. Every LOC figure below comes from a command run in
this worktree against `origin/main` at commit `d5f459314`; commands are given
so the numbers reproduce. Where a verdict entry would be the natural home for
a recommendation below, this document says what verdict *should* be recorded
there, not what is.

## 0. Reproducing the 370-file / 82,310-LOC baseline

"Python remaining" is every `*.py` file under
`packages/temper-placer/src/temper_placer/` and
`packages/temper-workflow/src/temper_workflow/` containing **no direct
import** of one of the Rust extension modules.

The module list must come from a **single-level** glob,
`packages/*/pyproject.toml` — not a recursive `find`. A recursive search also
turns up `packages/temper-placer/temper-constraints/pyproject.toml` (module
name `temper_constraints`), nested one directory deeper. Using the
single-level glob (12 modules) reproduces the stated baseline **exactly**;
adding the 13th does not (see §5.1 — this matters and is not just pedantry).

```
$ grep -h module-name packages/*/pyproject.toml
module-name = "temper_drc_rs"
module-name = "temper_dsn"
module-name = "temper_constraint_compiler"
module-name = "temper_design_bundle_python"
module-name = "temper_ipc"
module-name = "temper_orchestration"
module-name = "temper_io_types"
module-name = "temper_geometry"
module-name = "temper_quality_oracle"
module-name = "temper_placement_topology"
module-name = "temper_thermal"
module-name = "temper_rust_router"
```

```python
import re, pathlib
modules = [...]  # the 12 above
pat = re.compile(r'^\s*(?:from|import)\s+(' + '|'.join(modules) + r')\b', re.MULTILINE)
for root in [pathlib.Path('packages/temper-placer/src/temper_placer'),
             pathlib.Path('packages/temper-workflow/src/temper_workflow')]:
    for f in root.rglob('*.py'):
        if not pat.search(f.read_text(errors='ignore')):
            ...  # counts toward 370 files / 82,310 LOC
```

Result: **370 files, 82,310 LOC** — matches the task's stated baseline exactly
(cross-checked per-area against the known table: `visualization/` 6,086,
`heuristics/` 4,378, `topological/` 1,308, `cli/` 2,464 total, `pipeline/`
4,273 for the top-level-only slice — see §1 for why `pipeline/stages/` is
counted separately).

## 1. Method for the per-area sweep

Every top-level (and, for the five largest areas, second-level) subdirectory
of the two roots above was measured the same way: `wc -l` per file, a grep for
dominant third-party imports (`numpy`, `scipy`, `networkx`, `shapely`,
`ortools`, `click`, `rich`, `kiutils`, `pydantic`), each file's leading
docstring, and its top-level `def`/`class` names. Every file was checked
against this rule before classifying:

- **PORT** — real compute. State roughly what the kernel is.
- **NEVER-PORT** — the module's substance is I/O, CLI, terminal/HTML/SVG
  rendering, plotting, orchestration/wiring glue, or a thin wrapper over a
  third-party library. Porting it moves code without moving correctness.
- **ALREADY-DONE** — an oracle+differential exists and passes, or the file's
  own docstring/imports show the compute already runs in Rust — miscounted by
  the no-direct-import measurement, not actually outstanding.

For every ambiguous file (roughly 120 of the 370), the file was opened and its
function bodies read, not just its name or docstring — file-name pattern
matching alone produces wrong answers here (see §5 for concrete cases where it
did). Files with no ambiguity (a `__init__.py` re-export, a `rich`-only CLI
module, a Pydantic `BaseModel` field list) were classified from the survey
pass without a full read.

## 2. Per-area classification

### 2.1 The five largest areas (broken out to file/cluster granularity)

**`router_v6/` — 24,320 LOC, 96 files.** The autorouter. Heavily
domain-specific (grid/graph/geometry), with orchestration and reporting glue
mixed in at roughly file granularity, not mixed within files.

| Cluster | LOC | Verdict | What it is |
|---|---:|---|---|
| Re-export/type shims (`__init__.py`, `_adapter_types.py`, `_pipeline_types.py`, `stage0_data.py`, `topology_extraction.py`, `topology_solver.py`, `tree_route_geometry.py`, `_check_report_base.py`) | 806 | NEVER-PORT | Protocol/dataclass declarations, no methods with logic. |
| Adapter I/O (`_adapter_convert.py`, `_adapter_core.py`, `adapter.py`, `_strip_copper.py`) | 1,484 | NEVER-PORT | `route_pcb` entry point, KiCad s-expression text writing/stripping, MazeRouter-compat shim — I/O and orchestration. |
| Pipeline/stage orchestration (`_pipeline_core.py`, `_pipeline_grid.py`, `_pipeline_verify.py`, `pipeline.py`, `stage2/4_orchestrator.py`, `stage_ledger.py`, `stage_validators.py`, `grid_prep_stage.py`, `net_prep_stage.py`, `result_aggregate_stage.py`, `route_stage.py`, `astar_pathfinding.py`, `routing_results.py`, `terminal_tree_execution.py`, `verifier.py`) | 2,624 | NEVER-PORT | `Stage`-style wiring classes; each calls into already-classified compute modules below and validates field presence. |
| Reporting/CLI/evidence/diagnostics (`benchmark.py`, `diagnostics.py`, `manufacturing_report.py`, `all_pad_evidence.py`, `audit_provenance.py`, `test_boards.py`, `_routing_reports.py`, `astar_monitor.py`, `kicad_connectivity.py`) | 2,177 | NEVER-PORT | Benchmark CLI, structured-diagnostics scoring/formatting, hash-based evidence validators, runtime monitors — reporting, not compute. |
| Net/trace classification config (`net_classification.py`) | 157 | NEVER-PORT | Keyword/regex lookup tables (`is_ground_net`/`is_power_net`), not numeric compute. |
| A* pathfinding kernel (`astar_core.py`, `_astar_search.py`, `_astar_reconstruct.py`, `_astar_theta_star.py`, `_astar_ordering.py`, `astar_grid.py`) | 2,433 | PORT | Grid A*/Theta*/Lazy-Theta* search, octile-distance heuristic, 3D fallback tier still on the live escape-via path (not dead — see §5.4). |
| A* heuristic + demand budget (`_astar_heuristics.py`) | 196 | NEVER-PORT | Recorded JUSTIFIED-KEEP precedent (KTD8): builds its EDT via `scipy.ndimage.distance_transform_edt`; the `edt` Rust crate was measured and rejected (max diff 2.0–2.236). Named as a KTD8 consumer in `docs/wave4-discipline-contract.md`. |
| Routability EDT check (`routability_check.py`) | 477 | NEVER-PORT | Same `scipy.ndimage.distance_transform_edt` boundary as KTD8 — but **not** in KTD8's recorded consumer list (`channel_widths.py:208`, `_astar_heuristics.py:101`). See §5.2. |
| Pour/zone emission geometry (`_zone_pour_stitch.py`, `zone_emission.py`) | 569 | PORT | Convex hull, clustering, chamfered pour-shaping — real geometry behind "adapter"/"emission" filenames. |
| Terminal-tree planning + path geometry (`terminal_extraction.py`, `terminal_tree.py`, `path_simplify.py`, `grid_converter.py`) | 390 | PORT | Manhattan-distance tree planning, collinearity/path-simplification, coordinate conversion + path-length computation. |
| Spatial DRC/connectivity/capacity/topology cluster (`constraints_drc_oracle.py`, `constraints_design_rules.py`, `constraints_spatial_index.py`, `constraint_model.py`, `channel_skeleton.py`, `channel_mapping.py`, `obstacle_map.py`, `occupancy_grid.py`, `clearance_engine.py`, `layer_assignment.py`, `layer_capacity.py`, `escape_via_generator.py`, `bottleneck_analysis.py`, `bundle_analyzer.py`, `capacity_check.py`, `resource_bound.py`, `connectivity.py`, `routing_space.py`, `net_ordering.py`, `dense_package_detection.py`, `diff_pair_inference.py`, `via_placement.py`, `trace_width_assignment.py`, `audit_tree_geometry.py`, `power_plane.py`) | 8,911 | PORT | The bulk of the router: medial-axis channel skeletons (networkx+shapely), spatial index/KD-tree clearance queries, resource-exhaustion bin-packing bound, layer assignment solving, functional power-plane geometry. |
| Congestion & placement-feedback (`congestion.py`, `congestion_analysis.py`, `congestion_heatmap.py`, `routing_demand.py`, `placement_suggestions.py`, `apply_suggestions.py`) | 1,336 | PORT | Grid demand estimation, congestion classification, numeric heatmap grid, damped position update. |
| Post-route DFM (`thermal_relief.py`, `acid_trap_detection.py`, `copper_balance.py`, `annular_ring_check.py`, `teardrop_generation.py`) | 1,551 | PORT | Real spoke/annular-ring/copper-area/teardrop geometry. |
| Quality metrics (`metrics/slop_linter.py`, `quality/via_count.py`, `metrics/__init__.py`, `quality/__init__.py`) | 607 | PORT | Hairpin/zigzag/isolated-via geometric pattern detection; via counting/classification. |
| Misc small real geometry (`placement_audit.py`, `placement_legalization.py`) | 128 | PORT | Shapely-based post-solve audit; collision guard. |

Subtotal: **PORT 16,424 / NEVER-PORT 7,896 = 24,320.**

> **A second, independently-derived router_v6 split exists and disagrees by
> ~3,100 LOC — flagged rather than silently reconciled.** A separate
> sub-investigation for this document worked from
> `docs/evidence/2026-08-04-router-v6-migration-survey.md` (v2, corrected
> across 9 follow-up PRs) and its `tools/measurements/router_v6_survey/classification.csv`
> — a survey that predates this triage and has had real scrutiny. Cross-checked
> against the same file list, that survey gives **PORT 13,317 / NEVER-PORT
> 9,859 / unresolved 1,144** — lower on PORT, mainly because it classifies
> some files as BLOCKED (third-party-library-bound, same class as KTD8/KTD9)
> that the cluster read above folds into PORT. One concrete, directly-verified
> case: `zone_emission.py` (206 of the 569 LOC in the "Pour/zone emission
> geometry" row above) is classified PORT here, but the survey's row for it
> reads *"the scipy blocker is DELETED... but the survey MISSED a GEOS
> boundary: `_convex_hull_from_positions` runs on every zone regardless of
> clustering — 2,141/3,904 byte flips with identical copper. Reclassified
> scipy → GEOS"* — i.e. it's BLOCKED on a GEOS convex-hull boundary, not a
> clean PORT candidate, confirmed by reading the function directly. Given the
> survey's nine rounds of correction against this exact file set, **it should
> be treated as the more authoritative source for `router_v6/` specifically**;
> this document's cluster-level read above is a coarser cross-check, useful
> for the surrounding areas but not fully reconciled against the survey file
> by file within the time available. The revised totals in §3 use this
> section's cluster numbers (16,424/7,896) for consistency with the rest of
> the document's methodology, but the true router_v6 PORT figure is more
> likely in the 13,300–16,400 range than a single point estimate — narrowing
> it further means walking the survey's SPLIT/UNKNOWN rows (`constraints_design_rules`,
> `topology_solver`, `topology_extraction`, `bundle_analyzer`, 1,144 LOC) to a
> single verdict each, which neither pass completed.

**`placer/cp_sat/` (+ `placer/` top-level) — 8,443 LOC, 34 files.** The
OR-Tools CP-SAT solver integration.

| Cluster | LOC | Verdict | What it is |
|---|---:|---|---|
| Encoder dispatch + validation (`cp_sat/__init__.py`, `_encoder_core.py`, `encoder.py`) | 584 | NEVER-PORT | Constraint-ref reconciliation and dispatch to the 8 handler modules below — orchestration. |
| CP-SAT solve entry (`_encoder_solve.py`) | 717 | NEVER-PORT | `solve_placement` invokes `ortools.CpSolver().Solve()` directly — the textbook "no mature Rust drop-in (ortools CP-SAT)" blocker named in `docs/wave4-discipline-contract.md` §3. **Contains one already-delegated micro-kernel** (`courtyard_clearance_mm` via `temper_constraints`) — see §5.1. |
| Constraint handlers (`handlers/*.py`, 8 files + protocol/registry/shared) | 590 | NEVER-PORT | Each `encode_X` builds `ortools.CpModel` `AddConstraint`/`NewIntervalVar` calls from geometric parameters — thin wrappers over the ortools API. `handlers/keepout.py` also calls an already-delegated micro-kernel (`keepout_rect_units_py`) — see §5.1. |
| CpModel wrapper (`model.py`) | 518 | NEVER-PORT | "CP-SAT model wrapper around OR-Tools CpModel" per its own docstring — the definitional thin wrapper. Two of its unit-conversion methods (`mm_to_units`/`units_to_mm`) already delegate — see §5.1. |
| UNSAT extraction + surfacing (`unsat.py`, `unsat_surface.py`) | 433 | NEVER-PORT | Calls ortools' own infeasible-assumption API; `unsat_surface.py` renders a `rich` panel — explicit terminal rendering. |
| Loop controller (`_loop_core.py`, `_loop_gates.py`, `_loop_routing.py`, `_loop_types.py`, `_loop_utils.py`, `loop.py`, `gate.py`, `delta_mapper.py`, `netclass_constraints.py`) | 2,238 | NEVER-PORT | Place→Route loop control flow, gate management, PCB construction glue, violation→delta dispatch table. |
| Loop stability/field detection (`_loop_stability.py`) | 168 | NEVER-PORT | **Corrected on re-read** (see note below): `_consecutive_stable_rounds`/`_detect_oscillation` are round-history bookkeeping (equality/threshold checks over prior rounds' recorded state), not a numeric kernel producing a new result — control-flow for the repair loop's stopping criteria. |
| Clearance repair (`clearance_repair.py`) | 757 | NEVER-PORT | **Corrected on re-read**: `run_clearance_repair_solve` is a round-loop wrapper — parses the board, calls `solve_placement` (already counted in `_encoder_solve.py`) repeatedly with overrides, catches audit failures, tracks rounds. No independent geometry math in this file; the geometry it repairs *toward* lives in the encoder/audit files already classified elsewhere. |
| Feedback classifier (`feedback.py`) | 477 | NEVER-PORT | **Corrected on re-read**: `_compute_heuristic_position`, the one function that sounds like compute, is `return (x, y - 5.0)` / `return (x, y + 5.0)` — a hardcoded ±5mm nudge, not geometric optimization. The rest is violation-type dispatch (`_handle_congestion`/`_handle_clearance_violation`/...) building `ConstraintDelta` objects — classification/dispatch, not a kernel. |
| Fixed-copper NoOverlap geometry (`fixed_copper.py`) | 1,452 | PORT | Pad rotation/half-extent/layer-resolution geometry feeding the constraint (largest cp_sat file); the geometry, not the final `AddNoOverlap2D` call, is the substance. Both independent passes agree on this one. |
| Post-solve audit (`validator_audit.py`) | 509 | NEVER-PORT | **Corrected on re-read**: `audit_domain_clearance_validator` re-invokes the domain-clearance checker (its geometry kernel is counted where that checker lives) and classifies/reports violations; this file is the audit *call site* and report builder, not the geometry itself. |
| `placer/` top-level (`__init__.py`) | 1 | NEVER-PORT | Trivial; the real non-cp_sat placer compute already migrated (has direct ref). |

Subtotal: **PORT 1,452 / NEVER-PORT 6,991 = 8,443.**

> **Note on the four "corrected on re-read" rows.** This document went through two independent full-surface passes in parallel (see §5.9), and a *third*, narrowly-scoped pass was run specifically against `placer/cp_sat/` with instructions to read every disputed function body rather than classify by filename. That narrow pass disagreed with the broader passes on exactly these four files. Re-reading the actual function bodies (`_compute_heuristic_position`'s hardcoded ±5mm return, `run_clearance_repair_solve`'s wrapper structure, `_loop_stability.py`'s history bookkeeping, `validator_audit.py`'s call-and-report shape) sides with the narrow pass: none of the four contains an independent numeric kernel, they orchestrate/report on kernels counted elsewhere. This is the single largest correction made to either full-surface draft — 1,911 LOC moved from PORT to NEVER-PORT within `cp_sat/` alone.

**`deterministic/` — 6,463 LOC, 33 files.** The deterministic (non-CP-SAT)
placement pipeline.

| Cluster | LOC | Verdict | What it is |
|---|---:|---|---|
| Pipeline factory/wiring (`__init__.py`, `flags.py`, `instrumentation.py`, `state.py`, `feedback/__init__.py`, `feedback/drc_runner.py`, `feedback/orchestrator.py`, `geometry/__init__.py`, `geometry/courtyard.py`) | 926 | NEVER-PORT | `create_drc_aware_pipeline`/`create_legacy_pipeline` factory, feature flags, debug instrumentation, `kicad-cli` subprocess wrapper. |
| Stage wiring (`stages/__init__.py`, `_phase_core.py`, `apply_placements.py`, `base.py`, `clearance_grid.py`, `config_attach.py`, `drc_validation.py`, `net_ordering.py`, `phased_component_assignment.py`, `setup.py`) | 1,424 | NEVER-PORT | Thin `Stage` entry points delegating to the real kernels listed below; `_phase_core.py` is explicitly "core orchestration" per its own docstring. |
| Small geometry stub (`geometry/guard_strip.py`) | 26 | PORT | `compute_guard_strip` — small but real. |
| Placement-phase geometry (`stages/_grid_stage.py`, `_phase_rotation.py`, `_phase_validation.py`, `_phase_zones.py`) | 1,185 | PORT | Clearance-grid construction, HV creepage/isolation-slot geometry, zone placement geometry. |
| DRC/connectivity/clearance validation stages (`connectivity_validation.py`, `courtyard_check.py`, `drc_sweep.py`, `phased_component_assignment_validator.py`, `placement_validation.py`, `via_validation.py`) | 1,725 | PORT | Real geometric checks: overlap resolution, creepage/slot-spacing radius search, HV clearance validation, via cleanup. |
| Routing/escape geometry (`fine_pitch_escape.py`, `hv_lv_partition.py`, `zone_aware_slot_generation.py`) | 1,087 | PORT | Fine-pitch escape routing, HV/LV guard-strip partitioning, point-in-polygon zone-aware slot generation. |

Subtotal: **PORT 4,113 / NEVER-PORT 2,350 = 6,463.**

**`core/` — 3,577 LOC, 23 files.** Shared data structures.

| Cluster | LOC | Verdict | What it is |
|---|---:|---|---|
| Type/registry/constant/spec glue (`__init__.py`, `_contract_dataclass_compat.py`, `bus_cohort.py`, `decision.py`, `differential_pair.py`, `interfaces.py`, `isolation_constants.py`, `net_graph.py`, `netclass_rules_gen.py`, `specification.py`, `stackup.py`) | 1,228 | NEVER-PORT | Protocol interfaces, a dataclass-protocol compat shim over the already-migrated contract pyclasses, static stackup table, name-pattern bus grouping, plain accessor methods. |
| Graph/geometry algorithms (`community.py`, `courtyard.py`, `geometry_types.py`, `graph.py`, `hypergraph.py`, `loop_extractor.py`, `loop_ownership.py`, `pin_geometry.py`, `power_topology.py`, `routing_validator.py`, `state.py`, `topology.py`) | 2,349 | PORT | Networkx community detection, hypergraph representation, automatic current-loop extraction, rotation-and-side-aware pad geometry, grid-based routing validation. |

Subtotal: **PORT 2,349 / NEVER-PORT 1,228 = 3,577.**

**`validation/` — 5,730 LOC, 19 files** (top-level 15/4,402, `prereg/` 1/30,
`results/` 2/1,022, `spice_templates/` 1/276; the other 17 top-level files /
8,700 LOC already import `temper_drc_rs` directly — this area is more than
half migrated already, including `drc_types.py`/`drc_result.py`, see §5.5).

| Cluster | LOC | Verdict | What it is |
|---|---:|---|---|
| Type/registry/gate glue (`__init__.py`, `base.py`, `gate_input_registry.py`, `mfem_gate.py`, `prereg/__init__.py`, `results/__init__.py`, `scorecard.py`, `validation_gates.py`) | 2,564 | NEVER-PORT | Threshold/decision-gate classes comparing already-computed metrics; a config registry; margin-scoring contract over pre-existing values, not a new numeric result. |
| External-tool subprocess wrappers (`_drc_api.py`, `mfem_mesh.py`, `mfem_runner.py`, `spice_pipeline.py`, `spice_templates/__init__.py`) | 1,076 | NEVER-PORT | `kicad-cli`/compiled-FEM-binary subprocess wrappers, SPICE netlist template strings, board→Gmsh-mesh format conversion. |
| Experiment-harness orchestrators (`helps_battery.py`, `results/battery_run.py`, `scheduler.py`) | 1,963 | NEVER-PORT | A/B experiment harnesses producing keep/kill verdicts and a training-loop scheduler — orchestration, not the physics kernel they wrap. Same harness-independence shape already recorded for `regression/`'s six carved-out modules (§2.2). |
| Real metrics/comparison compute (`metrics.py`, `mfem_compare.py`, `manufacturing.py`) | 579 | PORT | Placement quality metrics; full-field MFEM-vs-FDM numeric comparison. |

Subtotal: **PORT 626 / NEVER-PORT 5,104 = 5,730.**

### 2.2 Remaining areas

| Area | LOC | Verdict | Justification |
|---|---:|---|---|
| `(root)` (`__init__.py`, `__main__.py`, `_version.py`, `protocol.py`, `runner.py`, `strategy_registry.py`) | 521 | NEVER-PORT | Package entry points, `Protocol` definitions, a `PipelineRunner` orchestrator, a dict-of-callables strategy registry. |
| `_constraint_types/` | 1,033 | NEVER-PORT | **Corrected**: an earlier draft of this row deferred to the ledger's `MIGRATE phase 2` tag over the substance read. That tag is stale. PR **#719** ("docs(wave4): measured verdict — `_constraint_types` is not a pyclass candidate", merged 2026-08-05, same day as this baseline) is a dated, measured verdict, authored by the repo owner, that supersedes it: 1,027 LOC across 9 files is 34 `pydantic.BaseModel` subclasses and exactly 5 methods (~58 LOC of bodies); none of the program's numerical traps are reachable (no numpy, no sum/min/max, no accumulation); the Phase-2 precedent (`net_types`, #560, `@dataclass`/`Enum` → pyclass) doesn't transfer because these are pydantic models with load-bearing pydantic-specific behavior a pyclass can't reproduce. `docs/wave4-verdicts.yaml`'s own comment block (added the same day, 2026-08-06) records this exact conflict and says a product-authority decision is owed — it does not resolve it, and this triage does not resolve it either, but the dated, measured, merged PR is stronger evidence than an unflipped pattern-level tag. |
| `adapters/` | 398 | NEVER-PORT | `router_v6_stage_adapter.py`, `register_strategies.py`, `deterministic_adapter.py`, `placement_adapter.py` — each wraps another already-classified module as a `PipelineStage`; `placement_adapter.py`'s body is a single `raise NotImplementedError("... post-JAX retirement")` (dead code, not a port candidate — flag for RETIRE, see §5.3). |
| `analysis/` | 1 | NEVER-PORT | Sole remaining file is a near-empty `__init__.py`; the substance (2 files / 281 LOC) already has a direct `temper_*` import. |
| `cli/` | 1,501 | NEVER-PORT | `__init__.py` (click dispatcher + rich panels), `drc_cli.py`, `watch_commands.py`, `andon_commands.py`, `version.py`, `_io.py`, `_signal.py`, `_version.py`, `__main__.py` — uniformly click/rich CLI wiring dispatching into already-classified compute. (`timing.py`/`trace_commands.py`, 963 LOC, already migrated — out of this scope.) |
| `constraints/` | 133 | NEVER-PORT | `_payload.py` marshals `PlacementConstraints` into a plain dict at the boundary the Rust constraint builder/compiler consumes — a one-time attribute-read boundary, not compute; `__init__.py` re-exports. |
| `explainability/` | 76 | NEVER-PORT | Sole no-ref file is `__init__.py`, re-exporting `Decision`/`DecisionTrace` from `core/decision.py` (already counted, NEVER-PORT, above). |
| `extraction/` | 0 | — | Fully migrated (125 LOC has direct ref); nothing in the residual set. |
| `fields/` | 279 | NEVER-PORT | `interface.py` (Protocol) + `result.py` (composition/accessor properties over a kept-Python gate object) = 220 NEVER-PORT; `field.py` (numpy per-cell scalar grid ops: ravel/astype/ascontiguousarray) = 59, arguably PORT-able but recorded as `fields/**: JUSTIFIED-KEEP` in the ledger — "no algorithm to protect," every operation is a buffer op. Deferring to the recorded verdict; classified NEVER-PORT in full. |
| `fixtures/` | 393 | NEVER-PORT | `synthetic.py` — synthetic netlist generator for scale/stress testing, consumed only by pytest. |
| `geometry/` | 164 | ALREADY-DONE | **Corrected**: `kicad_transform.py` is the sanctioned KiCad footprint-rotation implementation (see §5.6 for why it matters disproportionately to its size) — but it is not unmigrated. `packages/temper-geometry/VERIFICATION.md` records it explicitly: *"JUSTIFIED-KEEP, unchanged: `kicad_transform.py`... the drift risk is already closed by `tests/geometry/test_kicad_transform_rust_differential.py`, which pins it against this crate's `rotate_local_to_world`."* An equivalent Rust kernel (`rotate_local_to_router::rotate_local_to_world`) already exists in `temper_geometry`; the 6-test differential (confirmed present and passing-shaped, `tests/geometry/test_kicad_transform_rust_differential.py`) is exactly Trap 1 — no direct import, but an oracle already pins it. The Python function stays as the call site deliberately (a 2-line scalar formula isn't worth a per-call FFI crossing), which is a real, already-made, already-tested engineering decision, not a residual. |
| `heuristics/` | 4,378 | PORT / NEVER-PORT split | `mcu_subsystem.py`, `power_stage.py`, `spectral.py` (networkx spectral layout), `structural.py`, `organizational.py`, `conflict.py`, `style.py`, `topological_init.py`, `graph_utils.py` (3,486 LOC) = PORT, nine real placement-heuristic algorithms. `__init__.py`, `base.py`, `pipeline.py` (892 LOC) = NEVER-PORT, package init/abstract base classes/orchestrator. **A sibling agent is porting this area now — not duplicated here.** |
| `io/` — parse-engine boundary markers | 91 | ALREADY-DONE | `_parse_modules.py`, `_parse_tracks.py`, `_parse_zones.py` — each docstring states verbatim that the extraction logic "now run[s] inside `parse_kicad_pcb` on the Rust side" and the file "exists as the migration boundary marker." Verified by reading all three files directly. |
| `io/` — write/export + real_board geometry | 3,531 | PORT | `_write_board/_modules/_tracks/_zones.py`, `kicad_exporter.py`, `placement_exporter.py`, `via_dedup.py`, `zone_manager.py`, `real_board.py` — s-expression construction geometry (Phase-3 plan candidate 4) plus `real_board.py`'s copper-reach and board-surface-geometry kernels (shoelace ring area, outline/cutout classification for creepage — verified by reading the function bodies, see §5.7). |
| `io/` — glue/dead code | 1,165 | NEVER-PORT | `net_class_manager.py` (524, **zero consumers**, already recorded RETIRE in the Phase-3 plan — see caveat below), `snapshot.py` (197, JSON/SVG debug dumper — explicit SVG rendering), `boundary_registry.py` (142, name→config lookup), `kicad_writer.py` (93, explicit "re-export hub"), `_write_types.py` (90, shared dataclasses), `__init__.py`. |
| `manufacturing/` | 23 | NEVER-PORT | `__init__.py` only, re-exporting already-migrated `tolerances.py` content. |
| `metrics/` | 645 | PORT / NEVER-PORT split | `aesthetic.py` + `physics.py` (408 LOC) = PORT, real numpy quality/physics metrics. `__init__.py` + `external_oracle.py` (237 LOC) = NEVER-PORT, re-export + thin adapter forwarding to other already-classified compute. |
| `pcl/` — delegating bridge | 245 | ALREADY-DONE | `rust_bridge.py` — directly imports `temper_constraints` (the 13th, glob-excluded module, see §5.1) for `tier_to_weight`/loss-function kernels backed by `temper-constraints/src/loss.rs`, with FFI differential tests. **Caveat:** production code (`tiers.py`) does not call this bridge yet — see §5.1. |
| `pcl/` — parser/compiler/glue | 1,962 | NEVER-PORT | `__init__.py`, `_constraint_parser.py` (dict-dispatch parser), `_schema.py` (JSON-schema wrapper), `_tag_parser.py` (boolean-expression parser), `linter.py` (structural lint over the constraint language, not geometry), `parser.py` ("re-export hub" per its own docstring), `resolver.py`, `schemas/__init__.py`, `sat_bridge.py` (522, PCL→SAT compilation — builds `ortools` model primitives, the exact "ortools-encoder entanglement" the ledger's own resolved conflict note describes; the *objects* migrate, the ortools calls stay Python per that ruling). |
| `pcl/` — constraint-object compute | 2,069 | PORT | `constraints.py` (872, PCL data structures — ledger MIGRATE phase 2, contract-object layer, `temper-pcl-ir` is the named Rust seed), `_tag_expanders.py` (tag→concrete-constraint expansion), `tagged_constraints.py`, `drc_bridge.py` (PCL→DRC-assertion compiler), `tiers.py` (tier/penalty-weight computation — the *unwired* Python twin of `rust_bridge.py`'s already-built-and-tested Rust kernel, see §5.1), `unsat_compiler.py` (UNSAT-core→PCL upward compiler). |
| `physics/` | 240 | PORT | `loop_area.py` — commutation-loop-area computation from routed traces (networkx+numpy+scipy); the rest of `physics/` (3,921 LOC, 12 files) already has a direct Rust ref. |
| `pipeline/` — compute | 1,396 | PORT | `convergence.py` (stagnation/success criteria), `derivation.py` (physics-based constraint derivation), `feedback.py` (validation root-cause analysis, numpy+scipy — likely the "numpy part" a sibling agent is already porting, not duplicated here), `preflight.py` (real feasibility-check methods: area/capacity/clearance/isolation/stackup checks, not just Protocol defs), `topology_phase.py` (`build_topological_graph`/`generate_initial_placement`). |
| `pipeline/` — orchestration/UI/dead code | 3,582 | NEVER-PORT | `dag_engine.py`/`dag_expr.py`/`dag_schema.py`/`dag_types.py`/`dag_observability.py` (declarative DAG executor + predicate parser + pydantic manifest schema), `andon_observer.py` (HTTP+SSE dashboard), `terminal_dashboard.py`/`visualization.py` (rich terminal UI), `metrics_observer.py` (JSONL event bridge), `bottleneck_report.py` (`to_dict`/`from_dict` data contract), `iterator.py`, `state.py`, `explainability.py`, `logging_context.py`, `__init__.py`; `pipeline/stages/*` (705 LOC, 8 files, all thin `Stage.__call__` wrappers over already-classified compute). `topological.py` (75 LOC) is inside this bucket but is **dead code**, not merely glue — see §5.3. |
| `profiling/` | 1,302 | NEVER-PORT | CI/dev instrumentation harness (`cli.py` explicit click CLI, `timing_gate.py` CI gate contract, `pipeline_metrics.py` metrics-emission, `validation/invariants.py` is literally Hypothesis PBT test code living under `src/`). No product hot path. |
| `regression/` | 1,181 | NEVER-PORT | `runner.py`, `reporter.py`, `corpus_runner.py`, `metrics_recorder.py`, `cli.py`, `manifest.py` — recorded `JUSTIFIED-KEEP` in the ledger (harness-independence, D6): "these six modules orchestrate the migrated regression kernels" (`drc_ratchet`/`closure_test`/`measure_closure`/etc., already Rust-backed). |
| `report/` | 0 | — | Fully migrated (231 LOC has direct ref). |
| `requirements/` | 185 | PORT / NEVER-PORT split | `validators/_geometry.py` (175, `_distance`/`_point_in_rect`/`_rects_overlap` real geometry kernels) = PORT; `__init__.py` ×2 (10 LOC) = NEVER-PORT. |
| `testing/` | 733 | NEVER-PORT | `golden_diff.py`, `quarantine.py`, `version_gate.py` — recorded `JUSTIFIED-KEEP`: "test helpers consumed by pytest... migrating them would require the test suite to cross the pyo3 boundary to construct fixtures." |
| `topological/` | 71 | ALREADY-DONE | Sole no-ref file is `__init__.py`, re-exporting `force_refinement.py`/`graph.py`/`initial_placement.py`/`propagation.py`/`zone_solver.py` — **all five** directly `import temper_placement_topology as _rust` today (verified). This is the task's Trap 1, confirmed on today's `origin/main`. |
| `visualization/` | 6,086 | NEVER-PORT | Recorded `JUSTIFIED-KEEP`: HTML/Plotly output "accepted by human visual judgment," no bit-identical bar applies, plotly/websockets are optional guarded imports not on the default install path. `board_renderer.py` (1,012, Plotly), `status.py` (656, Plotly), `loss_plots.py` (627, Plotly), `report.py` (562, HTML generation), `validation.py` (526, coordinate-vs-KiCad-source diffing *for rendering accuracy*), `live.py` (597), `server.py` (492, WebSocket server), `routing_health.py` (469, Plotly dashboard), `model.py` (589, viz data models), remainder small. |
| `temper_workflow/` | 393 | NEVER-PORT | `metrics/{aesthetic_turing_test,compare_refinement,measure_displacement}.py`, `routing/steiner_sweep.py` — each is a `def main()`-fronted research/experiment script (JAX-era study scripts), not shipped product compute; `utils/__init__.py` trivial. (`routing/route_and_measure.py`, 115 LOC, already migrated — out of scope.) |

## 3. Revised totals

| Class | LOC | % of 82,310 | Files (approx.) |
|---|---:|---:|---:|
| **PORT** (real compute, should migrate) | **36,269** | 44.1% | ~211 |
| **NEVER-PORT** (I/O / CLI / rendering / orchestration / third-party wrapper) | **45,470** | 55.2% | ~153 |
| **ALREADY-DONE** (miscounted — oracle/differential exists or docstring proves Rust already runs) | **571** | 0.7% | 6 |

*(These are the corrected totals after §2.1's cp_sat re-read and the
`_constraint_types`/`geometry` corrections documented inline above — three
changes moving 3,108 LOC out of PORT: 1,911 within `placer/cp_sat/`
(`clearance_repair.py`/`feedback.py`/`validator_audit.py`/`_loop_stability.py`,
all reclassified NEVER-PORT on re-read), 1,033 (`_constraint_types/`,
reclassified NEVER-PORT per PR #719), and 164 (`geometry/kicad_transform.py`,
reclassified ALREADY-DONE — an existing passing differential was found after
the first classification pass).*

The honest "Python remaining" debt is **36,269 LOC**, not 82,310 — **55.9%
lower** once NEVER-PORT and ALREADY-DONE are excluded. `router_v6/`
(16,424 PORT LOC) and `deterministic/`+`core/`+`heuristics/`+`placer/cp_sat/`
(1,452 PORT LOC in cp_sat now that the re-read landed) account for most of
the real remaining kernel work. NEVER-PORT is not evenly spread — it's
concentrated in areas that are each >90% NEVER-PORT by construction:
`visualization/` (6,086, 100%), `placer/cp_sat/` (6,991 of 8,443, 82.8%,
`JUSTIFIED-KEEP`'d in the ledger as the ortools boundary itself), `cli/`
(1,501, 100%), `profiling/` (1,302, 100%), `regression/` (1,181, 100%),
`testing/`+`fixtures/` (1,126, 100%) — over 18,000 LOC that should probably
be dropped from the tracked denominator entirely rather than re-verified
every sweep, since each already carries a recorded ledger `JUSTIFIED-KEEP`.

## 4. Proposed verdict-file entries (not written — the user's call)

For areas where `docs/wave4-verdicts.yaml` has no entry, or where this
triage's substance read disagrees with an existing one, here is what a Step-3
evidence entry (per `docs/wave4-discipline-contract.md` §3) would say. These
are recommendations only.

- `router_v6/**` (the 7,896 NEVER-PORT LOC identified in §2.1): product-runtime
  → mixed. Recommend splitting the pattern: the orchestration/reporting/type
  clusters (`_pipeline_*`, `_adapter_*`, `stage*_orchestrator.py`, `*_stage.py`
  wiring, `benchmark.py`, `diagnostics.py`, `manufacturing_report.py`, evidence
  validators) as `JUSTIFIED-KEEP` (wiring, no independent kernel); leave the
  8,911+2,433+... LOC of real compute clusters as `MIGRATE` (already implied
  by the program's Phase 4/5 rows, just not itemized this finely).
- `router_v6/routability_check.py`: extend the KTD8 recorded verdict's
  consumer list to include it (currently omits it — see §5.2). No new verdict
  needed, just a correction to an existing one.
- `placer/cp_sat/**` already carries a whole-subtree `JUSTIFIED-KEEP` in the
  ledger (`docs/wave4-verdicts.yaml`, dated 2026-08-04, "the ortools CP-SAT
  boundary, KEEP per the Phase 1 R4 gate"), with a nuanced blocker (not
  feature-coverage — Pumpkin 0.4.0 covers 12/13 constraint classes — but
  unassertable cross-engine acceptance criteria, re-decidable when a corpus
  benchmark + acceptance gate exist). This triage's file-level read is
  consistent with that whole-subtree keep for all of `cp_sat/` **except**
  `fixed_copper.py` (1,452 LOC): its pad-rotation/half-extent/edge-extraction/
  point-segment-distance geometry computes the constraint's *inputs*, not the
  CP-SAT model itself, and isn't blocked by the ortools boundary at all — it
  sits next to `audit.py`/`isolation_barrier.py`, two files that already
  extracted the identical class of geometry primitive to `temper_geometry`
  and are `has-ref` today. Recommend carving `fixed_copper.py` out of the
  subtree's blanket keep as `MIGRATE`; the remaining 6,991 LOC stays under the
  existing verdict as-is (no new entry needed, it already exists and this
  triage's read confirms it applies cleanly).
- `_constraint_types/**`: the ledger's `MIGRATE phase 2` entry is stale and
  contradicted by its own same-day comment citing PR #719's measured verdict.
  Recommend flipping to `JUSTIFIED-KEEP`, blocker = "declarative pydantic
  schema validation (34 `BaseModel` subclasses, 5 methods) — not a
  pyo3-pyclass candidate; pydantic-specific behavior (validators, aliasing)
  doesn't survive the `@dataclass`/`Enum`→pyclass precedent that worked for
  `net_types`" (this is PR #719's own finding, already measured — the ledger
  just hasn't caught up to it).
- `geometry/kicad_transform.py`: no verdict change needed — it's already
  correctly `JUSTIFIED-KEEP`'d in `packages/temper-geometry/VERIFICATION.md`
  with a passing differential. Flagging only because an early pass of this
  same triage misclassified it as PORT before finding that record — worth
  remembering as a live example of Trap 1 catching out the people looking for
  Trap 1.
- `validation/{helps_battery,results/battery_run,scheduler}.py` (1,963 LOC):
  product-runtime → `JUSTIFIED-KEEP` — harness independence, same D6 reasoning
  already recorded for `regression/`'s six carve-outs.
- `io/net_class_manager.py`: RETIRE (already recorded in the Phase-3 plan;
  zero consumers, confirm and action).
- `pipeline/topological.py`: RETIRE or fix — currently dead code (§5.3), not
  a keep-as-is NEVER-PORT.
- `adapters/placement_adapter.py`: RETIRE — body is
  `raise NotImplementedError(...)`, nothing to port.

> **Actioned 2026-08-07** (commit on `feat/rust-hardening-pyany-removal-wave3`):
> `pipeline/topological.py` and `adapters/placement_adapter.py` were retired
> (git rm) along with five further dead modules discovered by an AST import-graph
> scan (zero importers): `pipeline/stages/geometric_stage.py` (the only importer
> of `pipeline/topological.py`), `output_stage.py`, `preflight_stage.py`,
> `semantic_stage.py`, `topological_stage.py`. Verified: 0 importers each via
> importlib AST walk; no test, `.importlinter`, `import-linter-allowlist.yaml`,
> `deadcode-baseline.py`, `vulture_gate.py`, or `.loc-allowlist.txt` references;
> `import_linter_gate.py` PASSED; `import temper_placer` package import smoke
> PASSED. `pipeline/stages/routing_stage.py` and `input_stage.py` are LIVE
> (imported by `router_v6/congestion.py`/`register_strategies.py` and a test)
> and were retained. The never-port verdicts above remain correct as written;
> this addendum records that the RETIRE half of the "RETIRE or fix" verdicts
> was the branch taken.

## 5. Surprising findings

**5.1 — A third measurement trap, distinct from the task's two: the
authoritative 12-module list itself misses a real extension, and it hides
partial delegation inside otherwise-NEVER-PORT files.**
`temper_constraints` (`packages/temper-placer/temper-constraints/pyproject.toml`,
nested one directory below the single-level glob) is a working Rust extension
— `temper-constraints/src/loss.rs`/`encoder.rs` — excluded from the reference
list because including it breaks the reproduced baseline (§0). This has two
distinct consequences, found in two different places:

- `pcl/rust_bridge.py` (245 LOC) is **entirely** a delegation bridge to
  `temper_constraints` (`tier_to_weight_rust`, `compute_*_loss_rust`), backed
  by FFI differential tests — genuinely ALREADY-DONE, just invisible to the
  12-module scan. But production code doesn't call it yet: `pcl/tiers.py`
  computes `tier_to_weight` as a plain Python dict, independently, unaware the
  Rust twin exists and is tested. The bridge and its target kernel are
  finished; the wiring that would make it actually save the 280 PORT LOC in
  `tiers.py` is not.
- Three `placer/cp_sat/` files (`_encoder_solve.py`, `model.py`,
  `handlers/keepout.py`) call `temper_constraints` for specific
  bit-exact micro-kernels (`courtyard_clearance_mm_py`, `mm_to_units_py`/
  `units_to_mm_py`, `keepout_rect_units_py`, each pinned by
  `test_encoder_rust_differential.py`) while the rest of each file remains
  genuine `ortools`-wrapper glue. These files are correctly NEVER-PORT
  overall (§2.1), but the measurement's blind spot means the ledger cannot
  currently see that they're already partially delegated — worth a footnote
  wherever cp_sat's verdict is recorded.

**5.2 — KTD8's recorded consumer list is incomplete.** The ledger's KTD8 entry
(`docs/wave4-discipline-contract.md` §3) names exactly two consumers of the
scipy-EDT boundary: `channel_widths.py:208` and `_astar_heuristics.py:101`.
`router_v6/routability_check.py` also calls
`scipy.ndimage.distance_transform_edt` directly (`_edt_from_obstacle_mask`)
and isn't in that list. Same blocker, same verdict, just not recorded against
this file.

**5.3 — Two files are dead code, not NEVER-PORT keeps.**
`adapters/placement_adapter.py`'s entire body raises
`NotImplementedError("... post-JAX retirement")`. `pipeline/topological.py`
defines `legalize_zone_aware(*a, **kw): raise NotImplementedError(...)` and
calls it unconditionally from step 3 of `run_topological_phase` — every call
that reaches that step crashes today. Both are counted NEVER-PORT above
(porting a `raise` doesn't move correctness either), but the honest verdict
for both is RETIRE, not keep — see §4.

**5.4 — `astar_core.py`'s "legacy" 2D loop is retired, but its 3D fallback is
still live.** `astar_core_rust.py`'s docstring says the JIT/pure-Python 2D
inner loop was fully replaced by `temper-rust-router` on 2026-07-31. But
`astar_core.py::_route_segment_3d` is still called from `_astar_search.py` as
the documented third-tier ("last resort") fallback when the primary and
secondary search tiers fail — real, reachable code, not a dead fallback path,
which is why the whole `astar_core.py` cluster is classified PORT above
rather than folded into ALREADY-DONE.

**5.5 — The Phase-3 formats/IO plan's two open residuals are already
resolved on `origin/main`, just not recorded as closed.** The plan
(`docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md`) names
`validation/drc_types.py` (581 LOC) and `validation/drc_result.py` (779 LOC)
as residuals "decided at their own pull." Both now `import temper_drc_rs`
directly — already migrated. Neither shows up in this triage's 82,310-LOC
surface at all.

**5.6 — The single most safety-critical unported file in the whole sweep is
also one of the smallest.** `geometry/kicad_transform.py` (164 LOC) is,
per its own docstring, the one sanctioned implementation of KiCad's
footprint-child rotation convention, written specifically because the
convention was independently reimplemented *incorrectly* in other places in
this repo's history. Its LOC weight is negligible; a Python/Rust divergence
here would silently reintroduce the exact class of geometry bug the file
exists to prevent. Worth prioritizing out of proportion to its size.

**5.7 — `io/real_board.py` looks like a loader wrapper; it isn't.** Its
docstring calls it a "production loader," which is why an earlier read of
this file classified it NEVER-PORT — but its body contains
`_copper_reach_mm` (pad-geometry hypot/bounding-radius math) and
`_board_surface_geometry` (shoelace-formula ring-area computation classifying
KiCad `Edge.Cuts` graphic items into an outline plus interior cutouts, for a
creepage-path soundness argument). 710 LOC, genuine geometry, verified by
reading the function bodies rather than the docstring alone — the module-name
and docstring-only survey pass this triage started from would have gotten
this one wrong.

**5.8 — Ledger corroboration was strong where it existed.** Six areas this
triage classified NEVER-PORT from a cold, bottom-up substance read
(`fields/`, `fixtures/`, `profiling/`, `regression/`, `testing/`,
`visualization/`) already carry a recorded `JUSTIFIED-KEEP` in
`docs/wave4-verdicts.yaml` with matching reasoning, found only after the
independent read was already done. Cross-checking after the fact rather than
before avoided anchoring on the ledger's language, and the agreement is a
useful sanity signal on the rest of this triage's un-recorded calls.

**5.9 — This document is the product of several independent passes over the
same 82,310-LOC surface, and they disagreed in specific, checkable ways.**
Because the task is large enough to parallelize, multiple independent
sub-investigations were run concurrently: one per large area
(`router_v6/`, `deterministic/`+`core/`, `validation/`+`pcl/`), plus at least
two full-surface passes that (beyond their assigned scope) each produced an
independent draft of the whole document, and one narrowly-scoped re-read of
just `placer/cp_sat/`. Where two passes reached the same conclusion from
different angles (§5.8's ledger corroboration, the `370`/`82,310` baseline
reproducing exactly across every pass), that agreement is real signal. Where
they disagreed — `_constraint_types/` (PORT vs NEVER-PORT, resolved by
finding PR #719), `geometry/kicad_transform.py` (PORT vs ALREADY-DONE,
resolved by finding the existing differential), and four `cp_sat/` files
(resolved by reading the actual function bodies in dispute, see §2.1's
cp_sat note) — the disagreement itself was the signal that a claim needed a
harder look before being trusted, which is the same lesson as Traps 1 and 2:
a plausible-sounding classification from a docstring, filename, or an
unflipped ledger tag is not the same as one confirmed by reading the code.

**5.10 — `physics/loop_area.py`'s PORT verdict has a carve-out inside it.**
The shoelace-formula/graph-cycle-finding majority of the file is real,
portable compute. But its convex-hull fallback path
(`scipy.spatial.ConvexHull`, used when the trace graph doesn't produce a
closable cycle) is a recorded KTD9-style keep:
`packages/temper-drc-rs/VERIFICATION.md` — *"`scipy.spatial.ConvexHull`
(Qhull)... stays Python — Qhull is not bit-reproducible outside scipy."* The
ledger's `physics/**` note references this ("KTD9... recorded below") but no
such carve-out entry actually exists in `docs/wave4-verdicts.yaml` — a gap
independently flagged by `docs/evidence/2026-08-06-wave4-owned-surface-closeout.md`
§4. Recommend porting the shoelace/graph majority under the existing
`physics/**` `MIGRATE` verdict while adding a narrow, named `ConvexHull`
carve-out, the same split pattern already used for `drc_inflate.py`'s
GEOS-buffer functions.
