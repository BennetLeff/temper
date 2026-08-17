---
module: temper-placer (repo-wide Python inventory)
tags: [migration, python-deprecation, rust, shim, inventory, liveness, spike]
problem_type: migration-planning
---

<!-- provenance: commit=e00d0c7a9707b825631876386b7f2b37352417b3 dirty=false -->

# 2026-08-17 — Python deprecation / Rust migration spike

**Branch:** `worktree-agent-aca94229ce8f0aeb1` (base `origin/main` @ `e81196c87`).
**Board sha256:** `9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd` —
verified unchanged before and after this spike; `pcb/temper.kicad_pcb` was
never opened for write.
**Method:** three parallel read-only sweeps of
`packages/temper-placer/src/temper_placer/`, each scoped to a disjoint
directory set, followed by direct verification (grep against non-test
Python **and** Rust `.rs` source for `py.import`/`PyModule::import` runtime
calls, test runs, oracle-hash gate, unwired-kernel gate) of every claim
before it's repeated here. This is a **spike**: time-boxed, not exhaustive.
`core/`, `physics/`, `geometry/`, `manufacturing/`, `metrics/`, `pcl/`,
`requirements/`, `topological/`, `fields/`, `report/`, `explainability/`,
`heuristics/` were not covered by a completed sweep this pass (the fork
assigned that scope did not return an actionable report before this
document's time-box closed; only the two directories touched incidentally
during verification — `core/isolation_constants.py`-adjacent files and
`physics/thermal.py`, both already resolved in prior sessions — are
mentioned below). That is a known gap, not a claim of completeness.

**Do not redo:** #1239 (9 shims, 539 LOC), #1252 (4 blocked shims, 231 LOC),
#1253 (4 Tier-2 shims, 169 LOC), `spike/pyclass-removal` (12 unreachable
`#[pyclass]`, 654 LOC), #1251 (thermal SSOT to Rust). `physics/thermal.py`
was re-confirmed in this pass as **KEEP** (SSOT data module, not a shim —
see #1251/tier2 doc), not re-litigated.

---

## 1. Inventory

Vocabulary, per the task brief:

- **(a) pure-delegation shim** — every function/class body calls straight
  into a compiled Rust extension; no independent logic.
- **(b) logic with a Rust equivalent already available** — real Python
  logic remains, but a Rust crate already implements the same computation
  (kernel exists, wiring is the gap).
- **(c) good migration candidate, no Rust owner yet** — real logic, no
  Rust equivalent found.
- **(d) not a candidate** — SSOT, test-only, CLI/orchestration glue, or
  already thin for a non-shim reason.

Liveness is traced by call sites, not naming (handoff §3 mechanism 2). Two
liveness surfaces exist and **grepping Python source alone misses one of
them**: a plain `from X import Y` in `.py`, and a runtime
`py.import("temper_placer.…")` / `PyModule::import(...)` issued from `.rs`
(invisible to any Python-only AST/grep scan — this is the exact shape
`.unwired-kernel-inventory`'s `NEVER-WIRE-BY-DESIGN` entries document for
Rust→Python kernel calls, and it bit this spike directly, see §2).

### 1a. `io/`, `cli/`, `validation/`, `deterministic/`, `pipeline/`, `placer/`, `regression/`, `constraints/`, `testing/`, `adapters/`, `extraction/`, `profiling/`, `_constraint_types/`

~230 non-test files. Full per-file classification was not budgeted; every
file **<30 LOC was read in full and its callers traced**, plus every file
carrying the codebase's own self-documenting `"delegation shim"` docstring
marker (39 hits) was located.

| path | LOC | category | liveness | evidence |
|---|---|---|---|---|
| `io/isolation_slot_geometry.py` | 8 | (a) → `temper_io_types.isolation_slot_aabb` | **dead in prod**, live in 1 test | zero non-test/non-oracle importer; sole importers are `tests/deterministic/test_isolation_slots_in_slot_generation.py:105` and the oracle `_zone_aware_slot_generation_run_py_oracle.py:63` (verified: `grep -rn isolation_slot_geometry packages/temper-placer/src` returns only a docstring mention, zero imports) |
| `io/export_types.py` | 9 | (a) → `temper_io_types.{ExportResult,TraceSegment,TraceVia}` | live | 2 prod callers: `io/kicad_exporter.py`, `io/via_dedup.py`; also imported by oracle `_kicad_exporter_py_oracle.py:29` |
| `io/reference_aliases.py` | 13 | (a) → `temper_io_types.{ReferenceAliasManifest,load_reference_alias_manifest}` | live, 2 call sites | **migrated in this spike — see §5** |
| `io/_kicad_types.py` | 26 | (a) → `temper_design_bundle_python.parse_engine` | live, load-bearing | breaks an import cycle deliberately; do not delete, only a re-export-path change is even possible |
| `io/footprint_library.py` | 20 | (a) | live-ish | only importer is `fixtures/synthetic.py` (test-fixture generator, not CI-invoked production — borderline) |
| `pipeline/bottleneck_report.py` | 30 | (a) → `temper_orchestration` | **dead at runtime** | sole non-test reference is `deterministic/stages/base.py:37`, and that import is inside `if TYPE_CHECKING:` (verified directly) — never executes; oracle `_bottleneck_report_py_oracle.py` is self-contained (does not import the shim) |
| `deterministic/geometry/courtyard.py` | 1 | (a), Python-to-Python (not even Rust) | **confirmed dead** | zero importers anywhere (`grep -rn deterministic.geometry.courtyard` / relative-import forms all empty); no oracle references it (oracle_hashes.json's only "courtyard" hit is the unrelated `_courtyard_check_run_py_oracle.py`, which pins a different file, `router_v6/annular_ring_check.py`'s courtyard helper) |
| `deterministic/stages/zone_assignment.py` | 27 | (a), thin | live, wired | registered in `deterministic/__init__.py`'s stage list |
| `placer/cp_sat/handlers/_shared.py` | 26 | (d) | live | small dict/list resolution helper, no Rust equivalent |
| `_constraint_types/noise.py` | 29 | (d) | — | pydantic SSOT types, R7 JUSTIFIED-KEEP precedent applies |

**39 files carry the codebase's own `"delegation shim"` docstring marker**
but are 95–1285 LOC each — mixed real-logic-plus-a-delegating-method
(category **b**, not clean **a**): `pipeline/convergence.py`,
`io/config_loader.py`, `io/_parse_board.py`, `testing/golden_diff.py`,
`validation/drc_result.py`, `validation/validation_gates.py`,
`validation/_drc_api.py`, `validation/drc_types.py`,
`pipeline/metrics_observer.py`, `pipeline/dag_types.py`, `pipeline/state.py`,
`validation/scheduler.py`, `pipeline/dag_observability.py`,
`placer/cp_sat/feedback.py`, `placer/cp_sat/_loop_core.py`,
`regression/cp_sat_comparison.py`, `regression/manifest.py`,
`placer/cp_sat/validator_audit.py`, `io/_write_zones.py`,
`placer/cp_sat/fixed_copper.py`, `io/_write_modules.py`,
`io/kicad_parser.py`, `placer/cp_sat/gates.py`, `io/dsn.py`,
`regression/reporter.py`, `io/reference_loader.py`, `io/loop_loader.py`,
`io/dsn_exporter.py`, `cli/trace_commands.py`, `io/_write_tracks.py`,
`io/netclass_loader.py`, `constraints/compiler.py`, `testing/quarantine.py`,
`cli/timing.py`. Each would need per-function triage to find a residual
pure-delegation sub-piece — a separate, larger pass than this spike.

### 1b. `router_v6/` (105 non-test files, 38,366 LOC)

router_v6 is the actively-developed production router this whole session
(handoff PRs #1222/#1249/#1256/#1260/#1261/#1264/#1267/#1278/#1279 all
touch it) and is deeply interconnected via both top-level and function-local
imports. ~48 files were confirmed live by a direct BFS from the two real
production entrypoints (`scripts/route_board.py` → `router_v6.adapter` →
`_pipeline_core.py`). A second pass grepped the remaining 58 names for any
non-test reference; 53 had ≥1 hit (live via some router-internal or
`scripts/*.py` path — not independently re-verified past "≥1 hit", flagged
as a caveat below), **5 had zero**.

**Verification correction (see §2): 1 of those 5 is not actually dead.**
Cross-checking against `.rs` sources for `py.import(...)`/
`PyModule::import(...)` (invisible to a Python-only grep) found that
`placement_legalization.py` **is** wired — `temper-orchestration/src/router_pipeline.rs:309`
calls `py.import("temper_placer.router_v6.placement_legalization")` at
runtime. The other 4 were independently re-checked the same way and found
genuinely dead (see §2 for full detail and §3 for the corrected list).

### 1c. `_*_py_oracle.py` files

Out of scope for deletion/consolidation per the hard rules (never touched).
Where a candidate's oracle imports the shim directly, that's recorded as a
**blocker** (§4), not executed.

---

## 2. Liveness correction caught live — the mechanism-2 trap, this time on `placement_legalization.py`

The router_v6 sweep flagged `router_v6/placement_legalization.py` (31 LOC)
as "CONFIRMED DEAD (0 non-test callers anywhere in src/ or scripts/)" —
the single cheapest-looking candidate in its report (no dedicated test
even). Independent verification for this document ran one more grep the
sweep didn't: Rust source for a runtime `py.import` of the module path.

```
packages/temper-orchestration/src/router_pipeline.rs:309:
    let legalizer_mod = py.import("temper_placer.router_v6.placement_legalization")?;
```

It is also referenced from `_pipeline_core_py_oracle.py:47`
(`from temper_placer.router_v6.placement_legalization import Legalizer`),
`test_router_pipeline_rust_differential.py` (×2), and
`test_router_pipeline_pbt.py` — all of which a Python-source-only scan
of non-test files would correctly skip (they're tests), which is exactly
why the Rust-side call was the only signal that mattered and the only one
the first pass didn't check. This is the handoff's mechanism 2
(`get_clearance_impl` believed live when `router_clearance.rs` was;
`ipc2152_min_width` believed to have a production caller when it had none)
recurring in the opposite direction — a module believed **dead** that
is in fact the thing a Rust stage calls back into. **Corrected:
`placement_legalization.py` is LIVE, not a deletion candidate.**

The other four modules flagged dead by the same sweep were independently
re-checked against `.rs` sources for `py.import`/`PyModule::import` and
found to have **zero** such calls (only comment/coincidental-name hits —
e.g. `congestion_analysis.rs` is the Rust crate's *own* module, unrelated
to the dead `congestion_analysis.py`; `zone_capacity_check` in
`preflight_stage.rs` is a Rust function name, not an import of
`capacity_check.py`). Those four stand as confirmed dead (§3).

**Consequence for the 53 "≥1 hit" router_v6 files the sweep did not
individually re-verify past a raw grep count**: liveness for those is
**uncertain, not confirmed** — the same Rust-runtime-import blind spot
could hide a false "live" as easily as it hid this false "dead" (a file
whose only Python-source hit is itself dead code, or whose only hit is a
comment). None of the 53 are asserted live with confidence in this
document; they're reported as "not disproven," which is a materially
weaker claim than the fork's original report implied.

---

## 3. Confirmed-dead cheap wins (deletion, not migration — no parity proof needed)

These have **zero** callers under both liveness surfaces (Python-source
grep + Rust `py.import`/`PyModule::import` grep) and **zero** oracle
references, verified directly for this document:

| path | LOC | oracle? |
|---|---|---|
| `router_v6/routability_check.py` | 546 | none (own dedicated tests only: `test_routability_check.py` + 2 differential/PBT files, 1,114 LOC of tests exercising dead code) |
| `router_v6/capacity_check.py` | 212 | none (`test_capacity_check.py`, 507 LOC) |
| `router_v6/congestion_analysis.py` | 144 | none (`test_congestion_analysis.py`, 103 LOC; superseded by the live `congestion.py`/`congestion_tensor.py` pair) |
| `router_v6/vacuity_guards.py` | 123 | none (`test_anti_vacuity_preconditions.py`, 506 LOC) |
| `deterministic/geometry/courtyard.py` | 1 | none |

**Total: 1,026 LOC of confirmed-dead source**, backed by roughly
2,230 LOC of tests that exercise it only in isolation, never through the
real pipeline. Each of the four router_v6 files has a
`*_rust_differential.py`/`*_pbt.py` suite, suggesting a Rust replacement
already landed elsewhere and the old Python was simply never unhooked —
this is a **wire/retire gap** per `docs/migration-pipeline.md`, not a
migration that needs doing.

**Not executed in this spike** (scope discipline: the prototype in §5 was
chosen instead, see rationale there) — but this is the single cheapest
category in the whole inventory and should be first in line for a
follow-up: delete the 5 files, delete or repoint their isolation tests,
and run `check_unwired_kernels.py --write-inventory` to ledger whatever
Rust kernels they were the last caller of.

---

## 4. Ranking (value/risk, cheap-and-safe → expensive-and-risky)

1. **Confirmed-dead deletions** (§3) — 1,026 LOC, zero callers under either
   liveness surface, zero oracle touch. Lowest risk in the inventory:
   nothing to prove equivalent because nothing calls it.
2. **Pure-delegation shims, live, oracle-clean** — `io/reference_aliases.py`
   (migrated this spike, §5), `pipeline/bottleneck_report.py` (dead at
   runtime per §1a but its oracle is self-contained, so it's actually
   deletable at zero risk — closer to category 1 than its "live" tag
   suggests once the TYPE_CHECKING-only import is accounted for),
   `deterministic/stages/zone_assignment.py`. Low risk: repoint 1-3 call
   sites to the Rust extension directly, delete the shim, no oracle edit.
3. **Pure-delegation shims, live, oracle-touching** — `io/isolation_slot_geometry.py`,
   `io/export_types.py` (§4 blockers). Same shape as #2 but the oracle
   imports the shim, so deletion requires an oracle-file byte change →
   re-pin. **Per the hard rules, this spike reports these as blocked
   rather than executing the re-pin.**
4. **The 39 mixed shim+logic files** (§1a) — real work, but each needs
   per-function triage before any deletion is possible; not a single
   atomic move like categories 1-3.
5. **router_v6's 53 "not disproven dead" files** (§2) — before touching
   any of these, each needs the same two-surface liveness check
   `placement_legalization.py` failed on a first pass. Not safe to act on
   the existing sweep's "≥1 hit" verdict alone.
6. **The 138/1059 unwired-kernel backlog** (`.unwired-kernel-inventory`,
   §6) — Rust already exists and is proven-equivalent by differential for
   most of these; the gap is wiring (stage 7), not implementation (stage
   3). Cheaper than a fresh migration but still requires finding and
   repointing every real caller, one kernel at a time — the exact
   "4,096 LOC unwired" incident `check_unwired_kernels.py`'s own docstring
   documents happened before when this was skipped.
7. **`core/`, `physics/`, `geometry/`, `manufacturing/`, `metrics/`, `pcl/`,
   `requirements/`, `topological/`, `fields/`** — not covered this pass
   (§0). Unknown ranking; likely contains both easy shims and load-bearing
   safety logic (per the handoff, `requirements/validators/clearance.py`
   alone carries the REQ-SAFE-01 SSOT matrix) — do not assume either
   direction without the same two-surface liveness check used above.

---

## 5. Prototype: `io/reference_aliases.py` deletion

**Chosen because**: pure 13-line re-export (category a), 2 known
production call sites (real liveness, not a no-op deletion), and —
verified before starting, not after — its pinned oracle
(`tests/io/_reference_aliases_py_oracle.py`) is a **self-contained
verbatim reimplementation that never imports the shim module**, so no
oracle byte changes and no re-pin. This is the one shape in the whole
inventory that clears the hard rule ("if your prototype needs a re-pin,
STOP and report it as a blocker") with zero exceptions taken.

**Baseline**: `29 passed` (`tests/io/test_reference_aliases.py` +
`test_reference_aliases_rust_differential.py` +
`test_reference_aliases_pbt.py`) before any change.

**Change** (commit `1c577cd1045f35a2e218c2b5de8479c281255bbf`, follow-up
lint fixup `e00d0c7a9707b825631876386b7f2b37352417b3`):

- `cli/__init__.py` — both call sites (`optimize`'s two code paths, lines
  629 and 811) repointed from `from temper_placer.io.reference_aliases
  import load_reference_alias_manifest` to `from temper_io_types import
  load_reference_alias_manifest`.
- `tests/io/test_reference_aliases.py` — same import repoint (still tests
  the real function, just via the direct path).
- `tests/io/test_reference_aliases_pbt.py` — docstring updated to state
  the shim is gone and why (it already imported `temper_io_types`
  directly, so no code change was needed there, only the stale
  cross-reference).
- `packages/temper-placer/src/temper_placer/io/reference_aliases.py` —
  deleted (13 LOC).
- `.unwired-kernel-inventory` — one `NEVER-WIRE-BY-DESIGN` entry added for
  `ReferenceAliasManifest`: deleting the shim removed the only textual
  mention of the class name from non-test Python, so the AST-based
  unwired-kernel scan can no longer see it being consumed (anonymously,
  via `.component_aliases`/`.loop_aliases`) — same gate-blind-spot shape
  already ledgered for `PySafetyValue`/`SkipExpr`/`HypergraphBuildResult`.
  **This entry was added by hand, matching the existing ledger's prose
  convention** — not by a blind `--write-inventory` regen, which also
  picks up ~9 unrelated pre-existing `NEW_UNWIRED` entries already on
  `origin/main` (§6) that don't belong in this commit.

**Verification**:

- `29 passed` after the change (same suites, same count).
- `tests/cli/` + `tests/io/` (1,069 passed / 40 skipped / 1 xfailed / **9
  failed**) — all 9 failures independently confirmed pre-existing and
  unrelated: none of the 9 failing files reference `reference_aliases`
  anywhere (`grep` came back empty for all 5 distinct failing test
  modules), and the one traced in full
  (`test_optimize_no_loop.py::test_no_loop_success_writes_output`) fails
  on a placement round-trip coordinate mismatch
  (`R1: footprint_anchor expected=(10.0, 20.0) actual=(100.0, 90.0)`) —
  unrelated to an import path change. A full origin/main A/B re-run
  (temporary revert of the 4 touched files, single failing test rerun,
  same failure, then the 4 files restored) confirmed this for the CLI
  case specifically; the other 4 (`test_fab_body_extraction`,
  `test_finepitch_production_board` ×2, `test_kicad_metadata_board_dimensions`,
  `test_netclass_loader`) are inferred pre-existing from the same
  zero-reference-to-reference_aliases evidence, not independently A/B'd.
- `scripts/import_linter_gate.py` — PASSED, 0 new violations.
- `scripts/check_oracle_hashes.py` — 166/167 OK, unchanged from before this
  change; the 1 drift (`tests/topological/_graph_py_oracle.py`) predates
  this spike (traced to `e81196c87`/#1280's networkx→graph_fixtures port,
  confirmed via `git log` on the oracle file — not touched or caused here).
- `ruff check` — 2 import-sort nits (I001) fixed in the follow-up commit,
  zero remaining.
- `pcb/temper.kicad_pcb` sha256 unchanged (`9c1f4a37b0…6dd`, verified
  before and after).
- `make extensions-check` — 10/10 fresh (this worktree's own isolated
  `.venv`, built via `make venv-isolate`; no shared-venv rebuild).

**Not done**: this prototype does not run `scripts/check_unwired_kernels.py
--write-inventory` wholesale — that regenerates ~9 unrelated pre-existing
entries (§6) that would conflate unrelated drift into this commit. The one
relevant ledger line was added by hand instead, matching the existing
file's own prose convention, and the resulting file diff is exactly one
line.

---

## 6. Pre-existing state observed, not caused by this spike

`scripts/check_unwired_kernels.py` (no `--write-inventory`) currently
exits 1 on this base commit with **9 unrelated `NEW_UNWIRED` findings**
(`engine_supported_signal_layer_names`, `estimate_gate_inductance_py`,
`parse_stackup`, `parse_stackup_from_path`, `slop_lint_hairpin_turns_py`,
`slop_lint_isolated_vias_py`, `slop_lint_single_net_detours_py`,
`slop_lint_zigzag_patterns_py`, `test_only_stackup` — all
`packages/temper-geometry/src/layer_identity.rs`,
`packages/temper-thermal/src/lib.rs`, or
`packages/temper-quality-oracle/src/cluster_f/bindings.rs`). None
reference `reference_aliases`; all predate this spike (confirmed: they
appear identically whether or not this spike's 2 commits are present).
Flagged here so a future pass doesn't attribute them to this work — same
"pre-existing failures are A/B verified before being dismissed" discipline
the migration pipeline's stage 5 requires.

`scripts/check_oracle_hashes.py` reports 1 pre-existing drift
(`tests/topological/_graph_py_oracle.py`), traced to #1280
(`e81196c87`), not touched here.

---

## 7. Blockers (per candidate)

| candidate | blocker |
|---|---|
| `io/isolation_slot_geometry.py` | oracle `_zone_aware_slot_generation_run_py_oracle.py:63` imports it directly — deletion needs an oracle byte change → re-pin. **STOP per hard rule; not executed.** |
| `io/export_types.py` | oracle `_kicad_exporter_py_oracle.py:29` imports it directly — same blocker shape. **Not executed.** |
| the 39 mixed shim+logic files (§1a) | no single blocker — each needs per-function triage to separate the delegating piece from real logic before any move is safe; this is a scoping problem, not a technical one |
| router_v6's 53 "not disproven dead" files | the mechanism-2 liveness trap (§2) — a Rust-side `py.import` can make a file live with zero Python-source signal, and a comment/coincidental-name match can make a dead file look referenced. Neither direction is safe to act on from a single grep pass. |
| the 138/1059 unwired-kernel backlog | not a missing-binding problem — the Rust exists and is proven equivalent by differential; the blocker is finding and repointing every kernel's real (or legitimately absent) Python caller one at a time, which is the exact granularity `docs/migration-pipeline.md` stage 7 and `check_unwired_kernels.py`'s docstring both insist on (never bulk import-scan) |
| `core/`, `physics/`, `geometry/`, `manufacturing/`, `metrics/`, `pcl/`, `requirements/`, `topological/`, `fields/` | not inventoried this pass (§0) — the blocker is simply that this spike's time-box closed before that sweep returned an actionable report |

---

## 8. Summary

- **Inventoried**: ~335 non-test Python files across `io/`, `cli/`,
  `validation/`, `deterministic/`, `pipeline/`, `placer/`, `regression/`,
  `constraints/`, `testing/`, `adapters/`, `extraction/`, `profiling/`,
  `_constraint_types/`, and all of `router_v6/` (105 files).
- **Confirmed-dead, zero-risk deletions available**: 1,026 LOC across 5
  files (§3), not executed this pass — recommended as the very next spike.
- **Migrated end-to-end, as proof of the plan**: `io/reference_aliases.py`
  (13 LOC), commits `1c577cd1045f35a2e218c2b5de8479c281255bbf` +
  `e00d0c7a9707b825631876386b7f2b37352417b3`.
- **Blocked, reported rather than forced**: 2 oracle-touching shims (§7).
- **One liveness false-positive caught and corrected before it could ship**:
  `placement_legalization.py` (§2) — a reminder that this spike's own
  first-pass sweep reproduced the exact class of error the handoff's §3
  mechanism 2 already warned about, and that the fix is a second grep
  against `.rs` sources, not more confidence in the first one.
- **Not covered**: `core/`, `physics/` (except the already-settled
  `thermal.py`), `geometry/`, `manufacturing/`, `metrics/`, `pcl/`,
  `requirements/`, `topological/`, `fields/`, `report/`, `explainability/`,
  `heuristics/` — flagged as the largest open gap in this inventory, not
  silently dropped.
