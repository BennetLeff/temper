<!-- provenance: commit=fbc5ce517fec9bbefcbaf632efa6b0ee4062d047 dirty=UNKNOWN -->
     base=origin/main d8062c6e6f60b693aa42f615e4042826de417d63
     date=2026-08-12
     method=AST import-gate over packages/temper-placer/src + tests + scripts +
       tools + benchmarks (relative imports + __init__ re-exports resolved),
       grep-verified, differential-mapped shim population, per-module importer
       typing (oracle/differential vs plain functional test) -->

# Python deprecation-and-delete spike — what was deletable on 2026-08-12

**Scope.** The brief asked for a systematic, AST-based sweep of the temper
Python surface for modules that can be **deprecated and deleted now** —
dead code, zero-consumer modules, or code superseded by the (now-complete)
Rust migration — plus a re-triage of a specific named set of "remaining
undelegated" modules. The scan covered every `.py` under
`packages/temper-placer/src/temper_placer/` and resolved the full import
graph (absolute, relative, `from . import X` / `from .X import Y` inside
package `__init__.py` files, `importlib.import_module`, `__import__`), then
classified every production module by its importer set. This is the same
"import gate" discipline the 2026-08-06 deprecation audit
(`docs/evidence/2026-08-06-deprecation-eligibility-audit.md`) used, run on
the current tree.

**Result: 8 modules / 403 LOC deleted, all verifiable; 3 commits pushed
(`d8e60a532`, `9b7267f8f`; plus one unrelated concurrent commit `270f7780b`
from another session on the same shared branch).**

## Headline findings

1. The **obvious guess is wrong again**: after the scanner correctly
   resolved `__init__.py` re-export chains, only **3 modules** in all of
   `src/temper_placer` have zero importers at all (`cli/__main__.py` — a
   documented `python -m` entry, `pcl/schemas` — load-bearing for
   `importlib.resources` on `pcl.schema.json`, and `pipeline/stages` — an
   empty leftover package). The prior inventory's claim of "~40 zero-importer
   src files" was the same relative-import false-positive it itself flagged;
   the correction holds.
2. The **deletable set is the pure-delegation shims whose only importers are
   functional tests**: 6 shims re-exporting `temper_design_bundle_python` /
   `temper_io_types` pyclasses, each imported by exactly one plain test that
   could be repointed to the extension with zero behaviour change (their
   differential/PBT/oracle suites already import the extension directly). This
   is the R21 shape from the 2026-08-06 audit, whose own three R21 deletions
   had already landed.
3. **`drc_runner.py` was the one genuine dead module in the brief's named
   list** — imported only by its own package `__init__` re-export, and the two
   re-exported names (`KiCadDRCRunner`, `run_drc_check`) have zero callers
   anywhere in the tree.
4. **`mfem_*` and `router_v6/capacity_check.py` are dead-in-production but
   deliberately NOT deleted** — they are real compute / a plan deliverable
   (U4 corroboration gate), test-only in import terms, whose removal is a
   product decision, not a dead-code removal. See the flagged section.

## Executed deletions (8 files, 403 LOC)

| File | LOC | Evidence |
|---:|---:|---|
| `pipeline/stages/__init__.py` | 0 | Empty package; every prior member file (`input_stage`, `geometric_stage`, `topological_stage`, `semantic_stage`, `thermal_anchoring_stage`) was already deleted. Zero importers, zero references in src/tests/scripts; only a historical `docs/` mention and a stale `wave4-verdicts.yaml` `pipeline/stages/**` PORT pattern (removed). |
| `deterministic/feedback/drc_runner.py` | 99 | `KiCadDRCRunner`/`run_drc_check` imported only by `feedback/__init__.py`'s re-export; repo-wide grep: zero callers of either name. `run_feedback_loop.py` (the only consumer of the feedback package) imports `ViolationComponentMapper`/`ZoneAdjuster`/`parse_kicad_drc` only. `feedback/__init__.py` edited to drop the dead re-export. |
| `manufacturing/monte_carlo.py` | 65 | Pure-delegation shim → `temper_design_bundle_python` (`manufacturing_monte_carlo.rs`). Zero production importers. Sole importer `test_monte_carlo.py` repointed to the extension; differential (`test_monte_carlo_rust_differential.py`) + PBT + oracle already import the extension/oracle directly. |
| `manufacturing/tolerances.py` | 49 | Same shape (→ `manufacturing_tolerances.rs`). `test_tolerances.py` repointed. |
| `io/golden_serializers.py` | 23 | Same shape (→ `temper_io_types`). `test_golden_serializers.py` repointed. |
| `io/footprint_parser.py` | 19 | Same shape (→ `temper_io_types`). `test_footprint_parser.py` repointed (two import sites, one lazy). |
| `io/config_board_binding.py` | 136 | Same shape (→ `temper_io_types`). `test_config_board_binding.py` repointed. |
| `core/stackup.py` | 12 | Same shape (→ `temper-design-bundle` `stackup_contracts.rs`). `test_stackup.py` + `test_ipc2152.py` (lazy `jlc04161h_7628`) repointed. |

Accompanying edits in the same PR: `.coverage-allowlist` (2 `drc_runner`
entries), `.typecheck-allowlist` (1 `stackup` entry),
`docs/wave4-verdicts.yaml` (removed `pipeline/stages/**` pattern + the
`core/stackup.py` and `deterministic/feedback/drc_runner.py` path entries),
and `.unwired-kernel-inventory` — the deletions exposed **22 Rust kernels**
whose only production callers were the shims; each is now ledgered
`[ORPHANED-DELETE]` following the `DiffPairConfig` precedent from the
2026-08-06 R21 deletions (commit `9b7267f8f`).

**Verification.** The 7 repointed tests + `test_orchestrator.py` (feedback
package) pass: **100/100**. The retained differential/PBT suites for the
deleted shims still pass: **115/115**. Post-deletion AST re-scan: zero
remaining imports of any deleted module path. `import_linter_gate.py`
PASSED. `check_migration_narrowing.py` PASSED. `check_unwired_kernels.py`
PASSED (125 unwired, all ledgered). `make regen-check` leaves only the two
pre-existing concurrent drifts (a `_measure_closure_py_oracle.py` pin
touched by #1037, and a manifest-less `generate_power_islands.py` from
another session) — both unrelated to this change.

## Re-triage of the brief's named "remaining undelegated" modules

| Module | Prod consumers (2026-08-12) | Verdict | Evidence |
|---|---:|---|---|
| `protocol.py` | 6 (`adapters/*`, `runner.py`, `strategy_registry.py`, `scripts/full_pipeline_profile.py`, `regression/closure_test.py`) | **KEEP** | `StageInput`/`StageMeta` are the stage-protocol types the strategy registry + runner dispatch on; `@runtime_checkable` typing with no pyclass equivalent. |
| `placer/cp_sat/handlers/_model_protocol.py` | 6 (all six non-ortools handlers) | **KEEP** | The `Protocol` boundary the `adjacent/aligned/anchored/enclosing/loop_area/onside` handlers build against (named in the 2026-08-11 endgame assessment §1.1). Runtime-used. |
| `router_v6/_adapter_types.py` | 3 (`adapter`, `_adapter_core`, `_adapter_convert`) | **KEEP** | Live adapter typing. |
| `io/_write_types.py` | 5 (`_write_board`, `_write_modules`, `_write_tracks`, `_write_zones`, `kicad_writer`) | **KEEP** | `WriteResult` etc. consumed by all four writer modules + `kicad_writer`. |
| `constraints/_payload.py` | 3 (`builder`, `compiler`, `reporter`) | **KEEP** | `_build_payload` marshals `PlacementConstraints` for `temper-constraint-compiler`; all three callers live. The inventory's own §3 check confirms the chain. |
| `core/netclass_rules_gen.py` | 1 prod (`design_rules.py`) + 7 tests | **KEEP** | Generated pydantic `NetClassRules` SSOT (from `scripts/gen_domain_models.py` + `configs/netclass_rules_manifest.yaml`); `design_rules.py` builds every `TEMPER_NET_CLASSES` instance from it. |
| `core/_contract_dataclass_compat.py` | 6 prod, **dozens** of `_install_dataclass_fields(...)` calls at import time | **KEEP** | Still load-bearing: `dataclasses.replace()` (e.g. `deterministic/stages/apply_placements.py`) requires the installed `__dataclass_fields__`; the differential tests pin the resulting surface. |
| `router_v6/test_boards.py` | 2 (`debug_plot.py` dev script, `router_v6/benchmark.py` ← `profiling/pipeline_metrics.py` ← `profiling/__init__` ← `cli/__init__`) | **KEEP** | Reachable from the CLI through the profiling chain; deleting would require a cascade into `profiling/` (excluded). |
| `router_v6/stage_validators.py` | 18 | **KEEP** | Heavily live (`run_validators` across router_v6 stages + deterministic phases). |
| `validation/mfem_runner.py` | 1 (`mfem_gate.py`, itself 0 prod / 1 test) | **FLAGGED — decision, not deleted** | Whole `mfem_gate`/`mfem_runner`/`mfem_compare`/`mfem_mesh` cluster is test-only (5 tests), unwired from production since #145. Real corroboration-gate compute + a differential (`test_mfem_compare_nearest_neighbor_rust_differential.py`); removal is a plan-deliverable decision (see flagged section). |
| `deterministic/feedback/drc_runner.py` | 1 (`feedback/__init__` re-export, names unused) | **DELETED** (99 LOC) | See executed table. |
| `pipeline/terminal_dashboard.py` | 1 (`cli/watch_commands.py` ← `cli/__init__` ← console script) | **KEEP** | The `watch` CLI command is registered in `cli/__init__.py` and reachable from the `temper-placer` console entry; the dashboard is its UI. |

## Full zero-production-consumer sweep (src/temper_placer, 2026-08-12)

The AST gate found **56** modules under `src/temper_placer` with zero
*direct production* importers. (The count is higher than the 3 "zero
importers at all" because the rest have test-only importers.) Classification:

- **DELETED (8)** — the shims/empty-package/dead-re-export above.
- **RETAINED ORACLE / differential participant (~27)** — imported by a
  `*_rust_differential.py` or `_py_oracle` test; bucket-5 (R20) retained,
  never delete without a campaign re-run. Includes: `core/graph`,
  `core/power_topology`, `core/placement_drc` (prod module in the wave4
  phase-2 contract differential), `deterministic/geometry/grid_utils`,
  `deterministic/geometry/guard_strip`, all five `explainability/*`,
  `heuristics/mcu_subsystem`, `heuristics/power_stage`,
  `io/isolation_slot_geometry`, `metrics/physics`,
  `placer/adjustment`, `regression/cp_sat_comparison`,
  `regression/measure_closure` (also `python -m`-invoked by the promotion
  gate), `regression/schema_validator`,
  `requirements/validators/_geometry`, `router_v6/routability_check`,
  `testing/golden_diff`, `validation/rtd_safety`, `validation/tht_check`,
  `validation/trace_analyzer`, `adapters/*` (via `_closure_test_py_oracle`
  + `regression/closure_test.py`).
- **DECISION-DEFERRED — dead-in-production, real compute (flagged below)**:
  `validation/mfem_*` (4 modules), `router_v6/capacity_check.py`,
  `router_v6/congestion_analysis.py`, `geometry/{polygon,primitives,
  projections,sdf,smooth}.py`, `pcl/unsat_compiler.py`,
  `pipeline/dag_expr.py`, `deterministic/instrumentation.py`,
  `deterministic/seed_filter.py`, `testing/version_gate.py`,
  `placer/cp_sat/domain_clearance.py` (imported only by
  `docs/evidence/*` measurement scripts), `cli/_signal.py`,
  `cli/_version.py`.
- **KEEP — entry points / CLI internals / package machinery**: `__main__`,
  `cli/__main__`, `cli/_version`, `cli/_signal`, `pcl/schemas` (resources
  package for `pcl.schema.json`).

## Flagged: deliberately kept despite looking dead

1. **`validation/mfem_*` (4 modules, ~570 LOC)** — zero production importers;
   the chain reaches `placer/cp_sat/gates.py`'s `Gate` base and the U4
   plan's corroboration design. Deleting it removes a plan deliverable that
   CI explicitly deselects only one test of; the other four mfem tests still
   run. **Not deleted** — the decision belongs to the plan owner, and the
   differential (`test_mfem_compare_nearest_neighbor_rust_differential.py`)
   makes it R20/U4/U5 territory.
2. **`router_v6/capacity_check.py` (real compute, test-only)** — a deliberate
   `feat(router-v6): capacity-demand pre-routing check` (fb5b23fd0) that was
   never wired into the pipeline. Not a shim, not an oracle. Deleting it
   means deleting the feature + 4 test files, two of which are generic
   coverage-paydown files. **Not deleted** — product question, not dead-code
   question.
3. **`geometry/{polygon,primitives,projections,sdf,smooth}.py`** — real
   geometric compute, zero production importers, plain test coverage. These
   predate the Rust geometry kernels and are candidates, but each deletion
   cascades into several coverage-paydown tests; out of the "safe" envelope
   for this spike.
4. **`adapters/deterministic_adapter.py` + `router_v6_stage_adapter.py`** —
   test-only adapter code whose tests also exercise the shared
   `tests/protocol/test_adapters.py` protocol surface.
5. **The `grid_utils`/`tht_check` shims were NOT deleted** even though they
   are pure delegation: their `*_rust_differential.py` tests import the shim
   module *and* the extension+oracle, so deleting them means editing R20
   evidence files — the audit's own "never the oracle alone" caution.

**Bottom line.** 403 LOC of verifiably-dead Python deleted with zero
behaviour change; the remainder of the "zero production consumer" surface is
either R20-retained oracle/differential machinery or real compute whose
removal is a product decision — recorded above so the next pass can execute
them without re-deriving the evidence.
