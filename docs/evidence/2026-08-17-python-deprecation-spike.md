<!-- provenance: commit=e00d0c7a9707b825631876386b7f2b37352417b3 dirty=false -->

# 2026-08-17 — Python deprecation / Rust migration spike

## Summary

A spike investigating further Python deprecation across `packages/temper-placer/src/temper_placer/`
(~116k LOC across ~310 non-test modules), following the session's already-landed cleanup
(#1239, #1252, #1253, `spike/pyclass-removal`, #1251 — ~1,593 LOC deleted; see
`docs/HANDOFF-2026-08-17.md` §2). This is a spike, not a mandate: it inventories, classifies,
ranks, and migrates **one** low-risk candidate end-to-end as proof of the plan.

**Prototype landed**: deleted `packages/temper-placer/src/temper_placer/io/reference_aliases.py`
(a 13-line pure-delegation shim), repointing its two production call sites and two tests to
import `temper_io_types` directly. Zero oracle re-pin required. Commits `1c577cd10` +
`e00d0c7a9` (pre-commit-hook ruff fixup). Full account in §5.

**Method and a correction about the method itself**: four independent read-only sweeps ran
over disjoint (mostly) directory sets: one by me directly (`io/`, `cli/`, `pipeline/`,
`constraints/`, `adapters/`, `_constraint_types/`, plus a follow-up pass on `core/`),
two dispatched sub-agents (`placer/`/`deterministic/`/`validation/`/`regression/`/`testing/`/
`profiling/`, and `router_v6/`), and a `fork` (inherits this session's context and git
access) assigned `core/`/`physics/`/`geometry/`/`manufacturing/`/etc. that instead spent
most of its budget re-covering `router_v6/` with an additional check the others didn't run
— grepping `.rs` sources for runtime `py.import(...)`/`PyModule::import(...)` calls, which a
Python-only AST/grep scan cannot see (this is the exact mechanism the codebase's own
`.unwired-kernel-inventory` documents for the *opposite* direction — Rust kernels invisible
to a Python-liveness scan because nothing Python names them; here it's Python modules
invisible to *Python* liveness scans because only Rust calls them).

That check caught a real, consequential false negative — `router_v6/placement_legalization.py`
was independently reported DEAD by the router_v6 sweep and is in fact live, called from
`packages/temper-orchestration/src/router_pipeline.rs:309` — **verified directly for this
document** (see §2). But the same fork's own "confirmed dead" list (its proposed cheapest
next win) also contained **two files that are not actually dead**, both caught here by
direct re-verification: `router_v6/vacuity_guards.py` (imported for its registration side
effect by `router_v6/stage2_orchestrator.py:23`, `# noqa: F401`) and
`deterministic/geometry/courtyard.py` (imported by `deterministic/stages/courtyard_check.py:6`,
which is the live stage-9 `CourtyardCheckStage` in the production 23-stage pipeline). Both
errors were plain-Python-import misses, not Rust-import misses — the fork's own new
methodology worked, but its execution wasn't exhaustive. **No claim in this document is
taken from a single source without at least one direct, independent verification command
run for this document** — the discrepancies above are exactly why. This is the same lesson
twice over: liveness is not naming, and it is also not any single scan.

Cross-checked against `docs/plans/2026-08-01-001-...wave4-full-migration-program-plan.md`
and `docs/plans/2026-08-02-001-...wave4-phase3-formats-io-plan.md`, which record prior
`MIGRATE`/`RETIRE`/`JUSTIFIED-KEEP` verdicts for large swaths of this surface (vocabulary
per `docs/wave4-discipline-contract.md` §3). Where a verdict already exists, this doc defers
to it rather than re-litigating — several "candidates" a naive scan would flag are already
adjudicated `JUSTIFIED-KEEP` (e.g. `core/board.py`, `core/netlist.py`, `pcl/constraints.py`,
`protocol.py`, `router_v6/routing_results.py`, `router_v6/_pipeline_types.py`,
`router_v6/_adapter_types.py`, `router_v6/routing_space.py`) and are excluded below.

`physics/thermal.py` was re-confirmed as **KEEP** (SSOT data module, not a shim — #1251/
tier2-shim doc), not re-litigated.

---

## 1-2. Inventory + liveness

Legend: **cat** = (a) pure-delegation shim / (b) logic+Rust-equivalent-exists / (c) good
candidate, no owner / (d) not a candidate. **live** = HIGH (directly traced)/MED (traced,
residual uncertainty)/LOW (real code, no confirmed caller)/**DEAD** (confirmed no non-test,
non-`TYPE_CHECKING` caller under *both* the Python-import and Rust-`py.import` surfaces).

### 1a. `io/`, `cli/`, `pipeline/`, `constraints/`, `adapters/`, `_constraint_types/`, `core/` (surveyed directly)

| path | LOC | cat | live | evidence |
|---|---|---|---|---|
| `io/reference_aliases.py` | 13 | a | HIGH | **DELETED this spike** — see §5 |
| `core/differential_pair.py` | 15 | a | HIGH | pure re-export of `_tdb.differential_pair_contracts.DifferentialPairConstraint`; live via `io/config_loader.py`, `core/__init__.py`. **No hash-pinned oracle exists for this file at all** (checked `scripts/oracle_hashes.json` — zero hits for `differential_pair`) — cleanest possible deletion candidate, no re-pin risk whatsoever. |
| `core/net_graph.py` | 18 | a | HIGH | pure re-export of `_tdb.net_graph_contracts.{NetGraph,SubNetEdge}`; live via `io/config_loader.py`, `_constraint_types/config.py`, `core/__init__.py`. No hash-pinned oracle. |
| `core/decision.py` | 19 | a | HIGH | pure re-export of `_tdb.decision_contracts.{Alternative,Decision,DecisionTrace}`; live via `pipeline/explainability.py`, `cli/trace_commands.py`, `core/__init__.py`. No hash-pinned oracle (`tests/explainability/explain_oracle/decision_oracle.py` is a self-contained verbatim copy, not an importer of the shim). |
| `core/community.py` | 21 | d | — | plain `@dataclass`, not a shim; the module's compute functions were already deleted as dead code in Spike S6 (2026-08-11) per its own docstring. |
| `io/isolation_slot_geometry.py` | 8 | a | test/oracle-only | `_zone_aware_slot_generation_run_py_oracle.py:63` imports it **inside the pinned-hash body** (past `# --- BEGIN PINNED BODY ---` at line 28) — deletion needs a re-pin. **BLOCKER**, see §4. Also named in the Phase-3 plan R8 as an undecided residual. |
| `io/export_types.py` | 9 | a | HIGH | live via `kicad_exporter.py`/`via_dedup.py`; but `_kicad_exporter_py_oracle.py:29` imports it and that oracle is **whole-file hash-pinned** with no digest-marker carve-out — any import-line edit changes the file's hash. **BLOCKER**, see §4. |
| `io/_kicad_types.py` | 26 | a-shaped | HIGH | **NOT a candidate** — deliberately breaks the `router_v6 → io` import cycle (own docstring); same structural role as `router_v6/grid_types.py` from PR #1252. |
| `io/footprint_library.py` | 20 | a | **DEAD** (prod) / test-fixture-only | Only non-test importer is `fixtures/synthetic.py`, which itself has zero importers outside `fixtures/__init__.py` and its own tests. Oracle (`_footprint_library_py_oracle.py`) is a self-contained verbatim copy — no re-pin needed. |
| `io/netclass_loader.py` | 56 | a | HIGH | Live via `scripts/route_board.py` and ~15 other call sites. Oracle is self-contained — no re-pin needed. Higher-effort candidate: same shape as the prototype but ~20 call sites. |
| `io/config_loader.py`, `io/reference_loader.py`, `io/loop_loader.py` | 113/315/163 | b | HIGH | Partial delegation, real logic remains (pydantic wiring / numpy / `LoopType.members()` adaptation). Not shim candidates. |
| `io/dsn.py` | 87 | a+RETIRE mix | mixed | 5 names (`DSNCircle`, `DSNExpression`, `DSNPath`, `DSNRect`, `dsn_list`) pure re-exports, HIGH live. `DSNPoint`/`DSNShape`/`DSNPolygon` (lines 53-87) are **dead**: own docstring claims zero non-module imports; verified — every consumer is a test. Module's own docstring defers this as "an R8 residual-candidate decision" (Phase-3 plan D6). |
| `io/via_dedup.py`, `io/provenance.py`, `io/zone_manager.py` | 49/80/352 | c | HIGH/MED/MED | Real logic, no Rust owner, explicitly named undecided R8 residuals in the Phase-3 plan. `provenance.py` still imports `kiutils.board.Board` directly (the D3 kiutils-removal boundary). |
| `constraints/compiler.py`, `builder.py`, `reporter.py` | 241/346/170 | b | HIGH | Partial delegation to `temper_constraint_compiler`; real logic remains. |
| `pipeline/state.py` | 38 | a (mostly) | HIGH | `PipelinePhase`/`PipelineConfig`/`PipelineState` pure re-exports; `PipelineError` stays a real (tiny) exception class by design. Live via `deterministic/__init__.py` → `create_drc_aware_pipeline` (CLI warm-start path). |
| `pipeline/metrics_observer.py` | 31 | a | MED | Pure re-export; liveness traced to `pipeline/__init__.py`. |
| `adapters/*.py` (3 files) | 96/67/193 | d | HIGH | Protocol adapters wrapping *other Python modules* (deterministic stages, router_v6 pipeline) — zero Rust delegation. Structural glue, not migration surface. |
| `_constraint_types/*` (9 files) | ~1000 total | d | HIGH | Explicitly out of scope per the Phase-3 plan ("generated stubs, permanently excluded from the coverage gate"); breaks the `constraints → io` circular import, same role as `io/_kicad_types.py`. |

All of `io/isolation_slot_geometry.py`, `io/export_types.py`, `io/dsn.py`'s 5 re-exports,
`core/differential_pair.py`/`net_graph.py`/`decision.py`, `pipeline/state.py`,
`pipeline/metrics_observer.py` are self-documented in their own module docstrings as
"delegation shim" / "pure-delegation re-export" — the fastest signal for finding candidates
across this whole codebase.

### 1b. `placer/`, `deterministic/`, `validation/`, `regression/`, `testing/`, `profiling/` (150 files, ~38.5k LOC)

Entry points traced: `scripts/route_board.py` (touches only `validation/_drc_api.py` in this
slice) and the `temper-placer`/`temper` console scripts. Production stage list resolved from
`packages/temper-orchestration/src/deterministic_pipeline.rs::DRC_AWARE_STAGE_KINDS` — the
Rust factory now owns stage-list construction, not a Python list.

**`deterministic/stages/`** (production 23-stage pipeline) — 21 of ~26 files are (a) pure
shims, HIGH live, each wrapping a `temper-orchestration`/`temper_design_bundle_python` FFI
call. `_phase_core.py`, `_phase_zones.py`, `_phase_rotation.py`, `_phase_validation.py` are
(b) partial-delegation with FFI-thin residuals; `_grid_hv.py`/`_grid_fence.py` are (c) real
logic with no Rust owner found.

**`placer/cp_sat/`** — the ortools CP-SAT solver boundary. Per the Wave-4 program's Phase 1
spike (`docs/evidence/2026-08-01-ortools-cpsat-spike.md`, re-confirmed
`2026-08-04-wave4-residual-verdicts.md`): **KEEP the Python/ortools boundary** — settled, not
open. Nearly everything under `cp_sat/` is (c) by design (`model.py` 553 LOC, `_encoder_core.py`
544, `_encoder_solve.py` 958, `gates.py` 1,285, and more, 130-900 LOC each). A few
(`_loop_core.py`, `feedback.py`, `audit.py`, `domain_clearance.py`) are (b) — partially moved
already, ortools-bound residual stays Python by design.

**`validation/`** — `drc_types.py`, `drc_result.py` are (a) pure re-exports, HIGH live.
`_drc_api.py`, `drc_oracle.py`, `drc.py`, `geometric.py`, `metrics.py`, `validation_gates.py`,
`preflight.py` are (b), HIGH/MED live. A long tail (`spice.py`, `rtd_safety.py`,
`human_reference_extractor.py`, `mfem_*.py`, `helps_battery.py`, `scorecard.py`,
`results/battery_run.py`) is (c) — real, standalone research/audit instruments, LOW-confirmed
liveness (CI/audit tools, not the production placement path).

**`regression/`** — `reporter.py` (30 LOC) is a pure re-export, HIGH live (own docstring:
exists only "so the public API is unchanged" — second-cleanest deletion candidate after the
core/ shims above). `manifest.py`, `fingerprint.py`, `cp_sat_comparison.py` are (a)/(b).
`drc_ratchet.py` (1,236 LOC) is (b) — the CI DRC-ceiling gate engine (handoff §10).

Full per-file table (150 rows) preserved in the sub-agent's raw report; not reproduced in
full here for length.

**Mechanism-2 flags found in this slice** (distinct from §2's router_v6 finding):

- **`deterministic/stages/drc_sweep.py::DRCSweepStage`** — exported in `stages/__init__.py`'s
  `__all__`, referenced in Rust doc-comments, but **never instantiated** anywhere in the
  production 23-stage list. Its siblings in the same file (`TrackDeduplicationStage`,
  `ShortCircuitDetectionStage`) ARE live.
- **`deterministic/stages/zone_aware_slot_generation.py::RoutingChannelAwareSlotStage`** —
  same pattern: exported, subclasses the live `ZoneAwareSlotGenerationStage`, zero
  construction sites.
- **`placer/cp_sat/heatsink_colocation.py`** (546 LOC) — an opt-in `heatsink_colocation=`
  kwarg to `solve_placement()`, exactly like sibling kwargs (`tank_creepage=`,
  `body_collision_input=`, `isolation_barrier=`, `fixed_copper=`, `domain_clearance=`) that
  **are** passed by `cli/__init__.py`/`repair_commands.py`. Zero call sites pass
  `heatsink_colocation=` anywhere. Its docstring cites a real, previously-shipped defect
  (commit `de59c0458`, PR #602 — two TO-247 IGBTs sharing heatsink `HS1`) — a safety
  constraint written and proven, never wired to a caller.
- **`validation/scheduler.py::ValidationScheduler`** (457 LOC) — imported eagerly by
  `validation/__init__.py`, but only ever constructed inside its own module
  (`scheduler.py:295`, an example/`__main__`-style block). Plausibly a JAX-optimizer-era
  leftover (`cli/version.py`: "JAX retired; CP-SAT is the sole placer"). No production/CI
  caller found.
- **`profiling/timing_gate.py`** / **`profiling/validation/invariants.py`** both call
  `deterministic.create_legacy_pipeline()` (a pre-Rust-factory, 14-stage hardcoded list)
  rather than `create_drc_aware_pipeline()` (the real 23-stage production factory).
  Reachable (via `temper-placer timing`), so not dead — but the "timing" tool measures a
  **different, non-production stage list** than what actually ships.

### 1c. `router_v6/` (113 files, exhaustive AST-based BFS from `route_board.py`'s actual entry points)

**~30 files are (a) pure-delegation shims**, LIVE, self-documented ("delegation shim", "full
substitution", "the Rust kernel is now the sole backend") — `annular_ring_check.py`,
`astar_core_rust.py`, `channel_mapping.py`, `clearance_engine.py`, `constraint_model.py`,
`constraints_geometry.py`, `corridor.py`, `corridor_erosion.py`, `dense_package_detection.py`,
`diff_pair_inference.py`, `escape_via_generator.py`, `net_classification.py`,
`net_ordering.py`, `resource_bound.py`, `routing_demand.py`, `stage_ledger.py`,
`teardrop_generation.py`, `terminal_extraction.py`, `terminal_tree.py`,
`topology_extraction.py`, and more. **Smallest, cleanest next paydown**, same
collapse-the-wrapper shape as this spike's prototype: `corridor.py` (53 LOC, one call to
`_tg.extract_corridor_mask`), `corridor_erosion.py` (73, `_tg.corridor_mask_for_net_py`),
`diff_pair_inference.py` (69, `_tg.infer_differential_pairs_py`), `terminal_tree.py` (94,
`temper_rust_router.plan_terminal_tree_py`, oracle-pinned differential already exists),
`stage_ledger.py` (138, own docstring: "This module is a delegation shim").

**~25 files are (b)** — partial delegation with a real, deliberately-Python residual
(shapely/GEOS operations with no bit-exact Rust target, ortools/CP-SAT boundary glue,
multiprocessing-boundary state). `routing_space.py` and `net_batching.py`/
`net_batching_subprocess.py` carry **already-recorded JUSTIFIED-KEEP verdicts**
(GEOS bit-exactness / subprocess-state, respectively) — not re-litigated.

**~15 files are (c)** — real, substantial logic, live, no confirmed Rust owner:
`_ground_plane.py` (1,466 LOC — the largest file in `router_v6/`, MST/A*-backbone plane
generation), `_power_islands.py` (903), `_zone_pour_stitch.py` (1,176),
`_corridor_backbone.py` (682), `kicad_connectivity.py` (441), `channel_skeleton.py` (666),
`terminal_tree_execution.py` (239), and the primary completion metric
`pad_connectivity_audit.py` (642 — see ranking §3, tier 3).

**Confirmed-dead cluster (verified independently by two sources for each entry below, not
taken from a single scan)**: `constraints_drc_oracle.py` (852) + `constraints_design_rules.py`
(682) + `constraints_spatial_index.py` (450) — 1,984 LOC, mutually-referencing, only
"live-looking" reference anywhere is a `TYPE_CHECKING`-only import in `deterministic/state.py`
that never executes; `routability_check.py` (546, real BFS-reachability with a
soundness-proof docstring); `capacity_check.py` (212); `congestion_analysis.py` (144,
superseded by the live `congestion.py`/`congestion_tensor.py` pair); `benchmark.py` (552) +
`test_boards.py` (162, a board-catalog data module despite the `test_` name); `verifier.py`
(241) + `congestion.py`/`congestion_analysis.py`'s dead sibling cluster. Total ≈3,340 LOC
confirmed dead under *both* liveness surfaces (Python import + Rust `py.import`), each
independently re-checked for this document.

**Two claimed-dead files that are NOT dead** (caught by direct re-verification for this
document, see §2 for the mechanism): `vacuity_guards.py` (123 LOC — imported for its
registration side effect by `stage2_orchestrator.py:23`, `# noqa: F401`) and
`deterministic/geometry/courtyard.py` (1 LOC — imported by `deterministic/stages/
courtyard_check.py:6`, the live stage-9 `CourtyardCheckStage`).

**53 files reported "≥1 grep hit" by the router_v6 sweep were not individually re-verified
past that raw count.** Given that two of the sweep's *own* explicitly-checked "confirmed
dead" verdicts turned out wrong, and the fork's cross-check separately caught a third
(`placement_legalization.py`) that had been called dead with more confidence than a bare
grep-hit, **liveness for those 53 should be read as "not disproven," not "confirmed live"**
until each gets the same two-surface check. Out of scope to re-verify all 53 individually
within this spike's time-box.

### 1d. `core/`, `physics/`, `geometry/`, `manufacturing/`, `metrics/`, `pcl/`, `requirements/`, `topological/`, `fields/`, `report/`, `explainability/`, `heuristics/`

**Partially covered.** §1a above covers 3 small `core/` shims found and verified directly
(`differential_pair.py`, `net_graph.py`, `decision.py`) plus `core/community.py` (not a
candidate). The rest of this directory set — including `requirements/validators/clearance.py`,
which per the handoff carries the REQ-SAFE-01 SSOT matrix and should not be assumed either
a shim or safety-load-bearing without the same two-surface check — was **not** swept this
pass. This is a known, explicitly-flagged gap, not a claim of completeness.

---

## 2. The `placement_legalization.py` false negative — full detail

The router_v6 sweep flagged `router_v6/placement_legalization.py` (31 LOC) as "CONFIRMED
DEAD (0 non-test callers anywhere in src/ or scripts/)" — the single cheapest-looking
candidate in its report (thin wrapper calling `PlacementAuditor.check_collisions()`, no
dedicated test even). Verified directly for this document with the check the sweep's own
Python-only grep couldn't perform — a `.rs`-source grep for a runtime import of the module
path:

```
packages/temper-orchestration/src/router_pipeline.rs:309:
    let legalizer_mod = py.import("temper_placer.router_v6.placement_legalization")?;
```

This call sits inside `RouterStageLegalize::run`, gated by `ctx.flag(py, "enable_legalization")`
(`router_pipeline.rs:857`) — and `router_v6/_pipeline_core.py:134` sets
`enable_legalization: bool = True` as the default in `RouterV6Pipeline`'s own constructor
(the real production pipeline; only `profiling/timing_gate.py`'s non-production
`create_legacy_pipeline()` path disables it). So the stage is live-by-default, not merely
reachable.

`placement_legalization.py` is also referenced from `_pipeline_core_py_oracle.py:47`
(`from temper_placer.router_v6.placement_legalization import Legalizer`),
`test_router_pipeline_rust_differential.py` (×2), and `test_router_pipeline_pbt.py` — all of
which a Python-source-only scan of non-test files correctly skips (they're tests), which is
exactly why the Rust-side runtime import was the only signal that mattered and the only one
the router_v6 sweep's methodology didn't check. **This is the handoff's mechanism 2
recurring in the opposite direction**: instead of dead code hiding behind a `False` flag
(the handoff's `enable_nlayer_astar_spike` example, and see this same spike's own
`_astar_nlayer.py` finding below), a module that is genuinely called was invisible to a
liveness scan because the only caller is Rust, not Python.

**Separately, this spike also found the reverse-direction sibling of this exact bug in
`router_v6/_astar_nlayer.py`** (1,319 LOC): a module that correctly self-describes as an
unproven spike (docstring: "prototype, not production") is nonetheless live and
unconditionally reachable on the current 6-layer board, via an undocumented second
OR-branch in `_pipeline_route.py:936`:

```python
use_nlayer = self.enable_nlayer_astar_spike or len(available_grids) > 2
```

`enable_nlayer_astar_spike` does default to `False` everywhere it's constructed — but
`available_grids` is the board's declared signal-layer count, and the 6-layer stackup
declared in #1178 gives 4 usable signal grids (F.Cu, In3.Cu, In4.Cu, B.Cu). `len(available_grids)
> 2` is therefore true unconditionally on the current board. A module correctly labeled
"not production" went live when an *unrelated* change (the layer-count growth from the
6-layer stackup adoption) silently satisfied its second, undocumented gate condition. This
needs an owner decision on its own — "is this code allowed to be running in production" —
independent of and prior to any migration-value ranking for the file. See tier 0 in §3.

**Consequence for the 53 router_v6 "≥1 hit, not individually re-verified" files** (§1c):
the same blind spot could hide a false "live" as easily as it hid a false "dead" (a file
whose only Python-source hit is itself dead code, or is a comment). None of the 53 should be
treated as confirmed live or confirmed dead from the existing sweep alone.

---

## 3. Ranking (cheap-and-safe → expensive-and-risky)

**Tier 0 — owner decision needed before any migration ranking applies:**

0. **`router_v6/_astar_nlayer.py`** — determine whether this admittedly-unproven 1,319-LOC
   spike module is *supposed* to be running in production on every 6-layer board today
   (§2). This is a "should this be running at all" question, not a migration question, and
   it sits on the routing hot path of a mains-voltage board — arguably more urgent than
   everything below it.

**Tier 1 — cheap and safe (shim deletion / confirmed-dead retirement, same mechanical shape
as the landed prototype):**

1. **`core/differential_pair.py`, `core/net_graph.py`, `core/decision.py`** (15/18/19 LOC) —
   pure re-exports, **zero hash-pinned oracle exists for any of the three** (checked
   `scripts/oracle_hashes.json` directly), live via 3-5 production call sites each plus
   `core/__init__.py`'s re-export. The single lowest-risk category found this spike — no
   oracle to even consider re-pinning.
2. **`router_v6/corridor.py`, `corridor_erosion.py`, `diff_pair_inference.py`,
   `terminal_tree.py`, `stage_ledger.py`** (53-138 LOC each) — pure delegation shims, Rust
   side fully proven, self-documented.
3. **`io/footprint_library.py` deletion** — dead-to-production pure shim, self-contained
   oracle, one test-fixture caller to repoint plus 2 test files.
4. **`router_v6/constraints_drc_oracle.py` + `constraints_design_rules.py` +
   `constraints_spatial_index.py` RETIRE** (1,984 LOC combined) — confirmed fully dead under
   both liveness surfaces, independently re-verified. Largest single LOC removal on this
   list; main cost is deciding each oracle's FREEZE/REIMPLEMENT/KEEP disposition before
   deleting.
5. **`router_v6/routability_check.py` (546), `capacity_check.py` (212),
   `congestion_analysis.py` (144), `benchmark.py`+`test_boards.py` (714 combined),
   `verifier.py`+`congestion.py` cluster** — same shape, all confirmed dead under both
   surfaces, independently re-verified (**not** `vacuity_guards.py` or
   `deterministic/geometry/courtyard.py` — both proven live in §2/§1c, despite being
   flagged dead by one source).
6. **`io/dsn.py::DSNPoint/DSNShape/DSNPolygon` RETIRE** — confirmed zero production
   consumers, self-documented as dead, blocked only by deleting/repointing 3 test files that
   test the dead code itself (not an oracle).
7. **`regression/reporter.py`, `pipeline/bottleneck_report.py`** — pure re-export /
   `TYPE_CHECKING`-only-referenced shims respectively, both with self-contained oracles
   (verified directly: `_bottleneck_report_py_oracle.py` never imports the shim). Same
   pattern as #1.
8. **`pipeline/state.py` / `pipeline/metrics_observer.py`** — same shape, live via the
   CLI warm-start path; oracle self-containment not yet verified — check first.

**Tier 2 — same pattern, more surface area:**

9. **`io/netclass_loader.py` deletion** — same pattern as the prototype but ~20 call sites
   to repoint instead of 2.
10. **`deterministic/stages/*.py` shim collapse** (21 files) — same shape, individually
    small, but load-bearing in the live 23-stage pipeline; higher review cost from criticality
    of the placement path, not code risk.
11. **~20 more router_v6 (a)-category shims** (`net_classification.py`, `net_ordering.py`,
    `teardrop_generation.py`, `annular_ring_check.py`, `resource_bound.py`,
    `routing_demand.py`, and others in §1c) — same collapse-the-wrapper shape.

**Tier 3 — real migration work (new Rust + oracle + differential, not a deletion):**

12. **`io/via_dedup.py`, `io/provenance.py`, `io/zone_manager.py`** — real logic, no Rust
    owner, explicitly named undecided R8 residuals in the Phase-3 plan.
13. **`router_v6/pad_connectivity_audit.py`** (642 LOC) — real, substantial, no Rust owner,
    directly imported by `route_board.py`. Explicitly the handoff's own cited PRIMARY
    completion metric (the module PR #1008 restored after a bulk-deletion incident) — its
    criticality argues for a careful REIMPLEMENT-class port with a from-spec Rust oracle if
    ever pulled, not a routine translation.
14. **`router_v6/_ground_plane.py` (1,466 LOC), `_power_islands.py` (903),
    `_zone_pour_stitch.py` (1,176), `_corridor_backbone.py` (682)** — real, large, live
    orchestration with partial Rust composition but no single owner for the algorithm
    itself. Biggest LOC-value if migrated, also the biggest behavioral-parity risk.
15. **`deterministic/stages/_grid_hv.py`, `_grid_fence.py`, `validation/*` long tail
    (spice.py, rtd_safety.py, mfem_*.py, etc.)** — real, substantial, standalone logic, no
    Rust owner, LOW-confirmed liveness. Bottom of the list until liveness is nailed down.
16. **`core/`, `physics/`, `geometry/`, `manufacturing/`, ... beyond the 3 shims found in
    §1a/§1d** — genuinely unranked; not swept this pass. Do not assume either direction;
    `requirements/validators/clearance.py` alone reportedly carries the REQ-SAFE-01 SSOT
    matrix per the handoff, so this set likely mixes easy shims with load-bearing safety
    logic.

**Explicitly not ranked — already settled by standing decisions:**

- **`placer/cp_sat/*` compute** — Wave-4 Phase-1 spike already settled KEEP for the
  ortools/Python solver boundary. Re-opening is a program-level re-decision.
- **`router_v6/routing_space.py`, `net_batching.py`/`net_batching_subprocess.py`** — already
  carry recorded JUSTIFIED-KEEP verdicts.

---

## 4. Blockers found

- **`io/isolation_slot_geometry.py`** — its only non-test importer,
  `_zone_aware_slot_generation_run_py_oracle.py`, imports it (line 63) **inside** the
  oracle's pinned/hashed body (marker at line 28). Deletion needs a re-pin. **Per this
  task's hard rules: STOP, reported, not executed.**
- **`io/export_types.py`** — `_kicad_exporter_py_oracle.py` imports `TraceSegment` from this
  shim at module level (line 29), and that oracle is **whole-file hash-pinned** with no
  digest-region carve-out. Any import-line edit changes the hash. Same STOP-and-report call.
- **`_constraint_types/`, `io/_kicad_types.py`** — not blocked, structurally excluded: both
  exist specifically to break circular imports. "Deleting the shim" would reintroduce the
  cycle it prevents — a different, larger piece of work than a delegation-shim removal.
- **`placer/cp_sat/*` (the whole ortools boundary)** — blocked by a standing program-level
  KEEP decision, not a technical blocker.
- **General pattern found twice this spike** (`export_types.py`, `isolation_slot_geometry.py`):
  a pure-delegation shim can be blocked from deletion purely because a *pinned oracle*
  imports it, even though the shim's own production callers are trivially repointable — the
  oracles that are self-contained verbatim copies (`_footprint_library_py_oracle.py`,
  `_reference_aliases_py_oracle.py`, `_bottleneck_report_py_oracle.py`,
  `explain_oracle/decision_oracle.py`) never have this problem. **Before picking a
  shim-deletion candidate, check whether its oracle imports it, and if so, whether that
  import sits inside a hash-pinned region** — this single check is what selected both the
  prototype and most of the tier-1 candidates above.

---

## 5. Prototype — `io/reference_aliases.py` deletion

**What**: deleted the 13-line pure-delegation shim
`packages/temper-placer/src/temper_placer/io/reference_aliases.py`
(`from temper_io_types import ReferenceAliasManifest, load_reference_alias_manifest`).
Repointed:
- `packages/temper-placer/src/temper_placer/cli/__init__.py` — 2 production call sites
  (the `place`/`optimize` and `optimize --no-loop` commands, both load a
  `.references.yaml` manifest when present) now `from temper_io_types import
  load_reference_alias_manifest` directly.
- `packages/temper-placer/tests/io/test_reference_aliases.py`,
  `test_reference_aliases_pbt.py` — repointed the same way (the differential test,
  `test_reference_aliases_rust_differential.py`, already imported `temper_io_types`
  directly and needed no change).

**Why this one**: it is exactly a Wave-4 Phase-3 plan R8/R5 residual (candidate 5,
already-migrated-but-not-yet-collapsed) — the plan explicitly lists `io/reference_aliases.py`
alongside `io/footprint_library.py` as loader-parity candidates whose Rust side already
shipped. It had zero oracle-import blocker (its oracle, `_reference_aliases_py_oracle.py`,
is a self-contained verbatim pre-migration copy — grep confirmed no import of the shim
anywhere in the oracle), exactly two production call sites (both in `cli/__init__.py`), and
no test asserting the shim's *existence* (both touched tests just use the re-exported name
functionally).

**Verification**:
- `pytest` on the 3 touched suites: 29/29 passed.
- `pytest packages/temper-placer/tests/io/`: 987 passed / 9 skipped / 1 xfailed / 6 failed —
  all 6 pre-existing and unrelated (net classification SSOT gap, footprint directory checks,
  board-dimension pin, fab-body baseline — none touch `reference_aliases` or
  `cli/__init__.py`'s manifest-loading branch; confirmed via `git status` showing only the 4
  intended files touched).
- `pytest packages/temper-placer/tests/cli/`: 106 passed / 6 skipped, 4 pre-existing
  failures in `test_optimize_no_loop.py` (a placement round-trip coordinate-offset bug,
  confirmed unrelated: the test fixture has no `.references.yaml`, so the touched code
  branch never executes).
- `scripts/import_linter_gate.py`: PASSED, 0 new violations.
- `scripts/check_oracle_hashes.py`: 166/167 OK — the one drift
  (`topological/_graph_py_oracle.py`) is pre-existing on `origin/main` (from #1280's
  networkx→graph_fixtures port), confirmed via `git status` showing it untouched.
- `scripts/check_unwired_kernels.py`: initially FAILED with a new `ReferenceAliasManifest`
  NEW_UNWIRED finding — deleting the shim removed the only place the class name was spelled
  out in non-test Python (now consumed anonymously via `.component_aliases`/`.loop_aliases`
  on the object `load_reference_alias_manifest` returns). Same "gate blind spot" shape
  already ledgered for `PySafetyValue`/`SkipExpr`/`HypergraphBuildResult` in
  `.unwired-kernel-inventory` — added a `[NEVER-WIRE-BY-DESIGN]` entry following the same
  documented pattern (not a check-weakening: the ledger mechanism exists precisely for this
  case, per `docs/migration-pipeline.md` stage 7). Gate now shows only the 9 pre-existing,
  unrelated `NEW_UNWIRED` findings (`layer_identity.rs`, `temper-thermal`,
  `temper-quality-oracle` slop-lint bindings) already failing before this change.
- Board `pcb/temper.kicad_pcb` sha256 verified unchanged before and after:
  `9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd`.

**Commits**: `1c577cd10` (the deletion + repoints + ledger entry), `e00d0c7a9` (pre-commit
hook's ruff import-sort auto-fixup, no behavior change).

---

## 6. Open items for the next pull

- **Tier 0 (§3) is the actual top priority of this whole document**: get an owner decision
  on whether `router_v6/_astar_nlayer.py` is supposed to be live in production. This isn't
  migration-shaped work, and it's more urgent than the Rust-migration ranking below it.
- §3 tier 1 items are the natural next prototypes — same shape as this spike's landed one,
  already fully scoped above, starting with the `core/` shims (§1a) which have literally no
  oracle to worry about.
- `core/`/`physics/`/`geometry/`/`manufacturing/`/`metrics/`/`pcl/`/`requirements/`/
  `topological/`/`fields/`/`report/`/`explainability/`/`heuristics/` need a real sweep — only
  3 files in `core/` were checked this pass. `requirements/validators/clearance.py`
  specifically should not be assumed either direction without the two-surface liveness check
  used throughout this document.
- The 53 router_v6 files with unverified "≥1 grep hit" liveness (§1c/§2) need the same
  two-surface check individually before anyone acts on their apparent liveness either way.
- The `export_types.py`/`isolation_slot_geometry.py` oracle-blocked pair (§4) should go to
  the owner as a named re-pin decision, following the PR #1198 discipline — not attempted
  here.
