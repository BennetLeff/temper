---
title: Python deprecation inventory — how much can we delete today?
date: 2026-08-11
status: investigation, no code changes
---

# Python deprecation inventory

**Question asked:** how much Python in this repo is now dead weight after the
Rust migration, and how much is still load-bearing (either doing real work,
or deliberately kept as a differential oracle)?

**Headline answer:** almost none of it can be deleted today with zero
behaviour change, the amount that's *architecturally* blocked (OR-Tools, or
retained-by-design oracles) is small and well-named, and the overwhelming
majority of Python is either genuinely still doing the work, or is test
infrastructure the migration pipeline itself requires to exist. The single
biggest deletable chunk found is not "old code the Rust team forgot to
remove" — it's abandoned one-off investigation scripts under `tools/` that
were never covered by any manifest or CI gate in the first place.

| Bucket | Files | LOC | Confidence |
|---|---:|---:|---|
| 1. DEAD (verified today, zero callers) | 60 | **~12,165** | high for `tools/measurements/**`, medium for the rest |
| 2. THIN SHIM (delete once callers bind direct) | 6 named examples | ~1,700 | illustrative, not exhaustive |
| 3. PARTIALLY MIGRATED (front line) | 4 named clusters | ~2,500 | illustrative, not exhaustive |
| 4. LIVE, NOT MIGRATED | 302 files (R1-triaged slice) | 66,309 | from `docs/wave4-verdicts.yaml` |
| 5. RETAINED BY DESIGN (never delete) | 153 oracle files + named constants | **50,141+** | high — pipeline-mandated |
| Production Python (repo's own definition) | 734 | 189,643 | `scripts/check_migration_narrowing.py::production_py_files()` |
| Test Python under `packages/` | 1,258 | 399,655 | includes the 153 oracle files above |

The two numbers that matter most: **~11,700 LOC is deletable today with no
behaviour change** (bucket 1, verified against real import evidence, not
guessed), and **at least 50,141 LOC must never be deleted** (bucket 5) — it
is the pipeline's own regression harness, not legacy debt. Between those two
poles sits ~600K LOC of Python that is either still the only implementation
of something real, or has not been individually triaged at all.

---

## 1. Method — what evidence backs each classification

This inventory deliberately reuses machinery already in the repo rather than
inventing new heuristics, per the task brief:

- **`scripts/check_migration_narrowing.py`** — its `production_py_files()`
  (roots `packages/`, `scripts/`, `tools/`; excludes `/tests/`, `/test_*`,
  `*_test.py`, `.venv`, `target`, `_py_oracle`) is the repo's own definition
  of "production Python," reused verbatim here (`python3 -c "... from
  check_migration_narrowing import production_py_files ..."` → **734 files,
  189,643 LOC**). Its `is_live_config_surface()` is the discriminator this
  document borrows conceptually for bucket 5: a constant/oracle is retained
  precisely when *no* production module other than its own definer reads it.
- **`docs/wave4-verdicts.yaml`** + **`scripts/check_verdict_coverage.py`** —
  an existing, machine-checked ledger that already answers two related but
  different questions per file under `packages/temper-placer/src/temper_placer`,
  `packages/temper-workflow`, `scripts/`, `benchmarks/`, and
  `packages/temper-placer/tests`:
  - **R7** ("should this move to Rust?"): MIGRATE / RETIRE / JUSTIFIED-KEEP /
    UNDECIDED.
  - **R1** ("what has to happen before the Python interpreter can go away
    entirely?"): BLOCKER-ORTOOLS / BLOCKER-SCIPY / PORT / REPLACE / DELETE /
    OUT-OF-RUNTIME / UNDECIDED.
  Run 2026-08-11: `uv run python3 scripts/check_verdict_coverage.py --report
  --removal`.
- **`.unwired-kernel-inventory`** + **`scripts/check_unwired_kernels.py`** —
  the CI gate that catches a Rust kernel registered and proven, but never
  called from a non-test Python module. This is the primary source for the
  PARTIALLY MIGRATED bucket: it names, per symbol, *why* the Python call site
  still runs the old code.
- **`.migration-narrowing-allowlist`** + **`scripts/check_migration_narrowing.py`**
  docstring — the prior-art the task brief points at. Quoting it directly:
  *"Measured on the 2026-08-10 tree, all 8 raw Check A hits were retained
  oracles: the 7 pattern sets in `router_v6/net_classification.py` ... plus
  `CONTACT_TOLERANCE_MM` in `router_v6/connectivity.py`."* This is bucket 5's
  founding evidence.
- **`docs/migration-pipeline.md`** stage 3: *"differential test pinning the
  pre-migration implementation as oracle, written first (red), then the Rust
  pyfunction (green)"* — the rule that makes bucket 5 mandatory, not
  optional.
- **My own import-graph pass** (AST-based, `scripts` in this doc's own
  scratchpad, not committed) — used only as a *first-pass filter* to shrink
  the search space, then every candidate it flagged was independently
  verified with direct `grep`/AST checks before being classified DEAD. This
  mattered: the pass had real false positives (below), so nothing in bucket 1
  rests on the heuristic alone.

### The trap this task warned about, both directions, both hit

**Direction 1 (undercounting deletable code): not hit here** — no retained
oracle was misclassified as dead; see bucket 5.

**Direction 2 (overcounting deletable code): hit and corrected during this
investigation.** `docs/wave4-verdicts.yaml`'s R1 axis has a 13-file, 951 LOC
`DELETE` bucket that looks, at a glance, exactly like this document's DEAD
bucket. It is not the same question. R1's `DELETE` means "no compute worth
porting if Python leaves the runtime entirely" — it says nothing about
whether the file is *called today*. Direct verification of every `DELETE`
entry still present in the tree found:

- `router_v6/__init__.py` — **93 other files** reference
  `temper_placer.router_v6`. Executes on every one of those imports.
- `constraints/_payload.py` — imported by `constraints/builder.py`,
  `constraints/compiler.py`, and `constraints/reporter.py`
  (`from temper_placer.constraints._payload import _build_payload`), which
  are in turn re-exported by `constraints/__init__.py` and reached from
  `pcl/__init__.py`. Live chain, not dead.
- `explainability/__init__.py` — imported by
  `tools/demo_explainability_file.py` and exercised extensively by
  `packages/temper-placer/tests/core/test_coverage_paydown_misc.py`.
- `manufacturing/__init__.py`, `placer/__init__.py` — package `__init__.py`
  files execute on *any* submodule import; `placer/` alone has dozens of
  live submodules.

Two of the sixteen `DELETE` entries (`adapters/placement_adapter.py`,
`pipeline/topological.py`) *had* already been deleted from the tree by the
time of this audit — confirming the mechanism works, just on a lag from the
ledger's last edit, not that the ledger's remaining entries are still-dead.

**Conclusion carried into this document:** a ledger verdict of "no compute
worth keeping" is not evidence of "nothing calls it." Every DEAD claim below
is backed by a direct, current, file-specific caller search — not by copying
the R1 `DELETE` list.

---

## 2. Bucket 1 — DEAD (verified zero callers today)

Definition used: no `import`/`from ... import` reference anywhere in the
repo (production or test), no reference in `.github/workflows/*.yml`, no
`Makefile` target, no entry in `scripts/manifest.yaml` (for anything under
`scripts/`), and — for anything under `packages/` — no reference under any
import spelling (dotted path, relative import, or re-export chain), checked
by direct grep, not just the AST first pass.

| Path | LOC | Evidence |
|---|---:|---|
| `tools/measurements/**` (36 files) | **8,362** | Zero Python importers anywhere (`grep -rl "tools\.measurements\|tools/measurements"` matches nothing outside the directory itself, aside from spike files importing their own siblings). Zero references in `.github/workflows/*.yml` or `Makefile`. No `tools/` manifest exists to register them against (unlike `scripts/`, which has 100% `scripts/manifest.yaml` coverage). Every file is a one-off measurement/spike driver (`exact_edt_rust_spike.py`, `geos_polygon_algebra_spike.py`, `ckdtree_parity_spike.py`, `connected_components_rust_spike.py`, the `router_v6_survey/` and `*_reachability`/`*_permutation` clusters) whose *conclusions* are already committed as prose in `docs/evidence/*.md` and cross-referenced by name from `docs/wave4-verdicts.yaml` (e.g. the EDT spike's bit-exactness numbers are quoted directly in the `routability_check.py` PORT note). Git history confirms single-commit, single-purpose origin (e.g. `0b7c850cd feat(geometry): exact Rust EDT spike resolves KTD8 blocker`). |
| `tools/spice/**` (11 files) | 2,150 | Zero references outside the directory (`grep -rl "tools/spice\|tools\.spice\|spice\.sign_off\|spice\.challenger"` matches only files inside `tools/spice/`). No CI/Makefile wiring. No README (only a `report_template.md` data template, not usage docs). Medium confidence: SPICE sign-off tooling is plausibly hand-run by an EE outside any repo-visible trigger — flagged for owner confirmation before deletion, not asserted with the same confidence as `tools/measurements/`. |
| `tools/sil/**` (4 files) | 566 | Same shape as `tools/spice/`: zero external references, no CI/Makefile wiring, no README. Same medium-confidence caveat (firmware software-in-the-loop tooling may be run by hand). |
| `tools/demo_explainability_file.py` | 93 | Zero references anywhere (`grep -rl demo_explainability_file`). The package it demonstrates (`temper_placer.explainability`) is very much alive (imported by tests) — this file specifically, the demo entry point, has no caller. |
| `packages/temper-placer/src/temper_placer/io/_parse_tracks.py` + `_parse_zones.py` | 16 | Already-emptied migration boundary markers — the file's own docstring says it outright: *"Migrated to the Rust parse engine (`temper_design_bundle_python.parse_engine`) ... This module exists as the migration boundary marker; it imports no kiutils and exposes no names (the only historical consumer, `io.kicad_parser`, delegates to the engine directly)."* Confirmed zero production importers (`grep` for `_parse_tracks`/`_parse_zones` imports finds only a *separate*, fully mirrored oracle package at `tests/io/_parse_engine_py_oracle/`, which carries its own `_parse_tracks.py`/`_parse_zones.py` copies — the two files being classified here are the orphaned production originals, not the oracle). Rust replacement: `temper_design_bundle_python.parse_engine::parse_kicad_pcb`. |
| `.unwired-kernel-inventory`-documented, already-deleted shims (`router_v6/apply_suggestions.py`, `router_v6/congestion_heatmap.py`, `router_v6/placement_suggestions.py`, `adapters/placement_adapter.py`, `pipeline/topological.py`) | 0 (already gone) | Not counted in the LOC total — listed here only as evidence the "dead shim → delete" mechanism already works in this repo; these are historical, not current, candidates. |

**Total, high + medium confidence: 60 files, 12,165 LOC** — measurements
(8,362) + spice (2,150) + sil (566) + demo file (93) + parse markers (16) +
six more small, individually zero-referenced `tools/` one-offs not tabulated
above (`tools/scrape_github_pcbs.py` 284, `tools/clone_and_extract_pcbs.py`
231, `tools/block_dispersion_measure.py` 194, `tools/setup_kicad_env.py` 139,
`tools/fix_unused_args.py` 85, `tools/strip_zones.py` 45 — 978 LOC combined,
same "ungoverned one-off tool under `tools/`" shape as the measurements
cluster, each independently confirmed zero-referenced by the same grep
method).

**Notably absent from this bucket: anything under `packages/*/src/`
production code beyond the two 9/7-line stub markers above.** The AST
first-pass flagged ~40 more `packages/` files as zero-importer; every one
checked (`cli/andon_commands.py`, `cli/watch_commands.py`,
`_constraint_types/noise.py`, `deterministic/feedback/orchestrator.py`,
`deterministic/stages/apply_placements.py`, `deterministic/stages/_phase_rotation.py`,
`_phase_validation.py`, `_phase_zones.py`, `profiling/pipeline_metrics.py`,
and every package `__init__.py`) turned out to have real callers once
relative imports and re-export chains were checked directly — the AST
first-pass missed `from . import X` and `from .X import Y` shapes inside
package `__init__.py` files. **This is the headline finding stated in the
task brief, confirmed empirically: the obvious guess is wrong in both
directions — here, in the direction of "surely there's a pile of dead
`src/` code," and there mostly isn't.**

---

## 3. Bucket 2 — THIN SHIM (delete once callers bind directly)

| Path | LOC | What it forwards to | Caller change needed to delete it |
|---|---:|---|---|
| `packages/temper-placer/src/temper_placer/constraints/_payload.py` | 108 | `_build_payload()` marshals `PlacementConstraints` attribute-by-attribute into the plain dict that `temper-constraint-compiler` (Rust) parses — "a one-time marshalling boundary... all compute on the other side of this boundary is Rust" (module's own docstring). | `builder.py`, `compiler.py`, `reporter.py` (its three callers) would need to pass the pydantic model directly across the pyo3 boundary (a `FromPyObject` impl on the Rust side) instead of a pre-marshalled dict. |
| `packages/temper-placer/src/temper_placer/cli/timing.py` + `cli/trace_commands.py` | 963 | Both "already import a Rust extension directly" — explicitly excluded from the `cli/*.py` REPLACE cluster in `docs/wave4-verdicts.yaml` because they are R7-migrated already; what's left is the click command wrapper. | Once the CLI itself moves off `click`/`rich` (the re-triage's stated R1 target, `cli/ -> clap`), these two thin wrappers disappear with the rest of `cli/`, not independently. |
| `router_v6/net_classification.py` — `is_ground_net`/`is_power_net`/`is_hv_net`/`is_signal_net`/`classify_net_type` + the four `is_*_pin` helpers | ~30 (the delegating functions only, not the file) | One-line delegations into `temper_io_types` (`is_power_net_v6`/`is_signal_net_v6`/`classify_net_type_v6`, plus shared `is_ground_net`/`is_hv_net`/`is_*_pin` bindings `core/net_classification.py` also uses). | Nothing — callers already bind to these thin Python wrappers by name across the codebase; deleting the wrappers means every call site imports `temper_io_types` directly instead. Low priority: the wrapper cost is ~30 LOC total. |
| `packages/temper-placer/src/temper_placer/validation/drc_oracle.py`'s Rust/Python dual-backend branch | n/a (see bucket 3) | See PARTIALLY MIGRATED below — this file is a shim *plus* a dead fallback branch, not a pure shim. | — |

This bucket is illustrative rather than exhaustive: a full sweep would mean
checking every `packages/*/src/temper_placer/**/*.py` file for "does this
module's entire body reduce to marshalling a pyo3 call," which the task's
effort budget did not allow at whole-repo scale. The `.unwired-kernel-inventory`
entries tagged *"production now goes through the typed constructor"* (the
Phase-A U5 cluster: `build_board_dict_py`, `build_board_dict_from_parsed_pcb_py`,
`build_constraints_dict_py`, `constraint_value_to_plain_py`) name several
more legacy dict-marshalling Rust kernels retained *specifically* for
`test_drc_oracle_marshal_rust_differential.py` — those are RETAINED BY
DESIGN on the Rust side, and their Python callers
(`validation/drc_oracle.py`, `validation/drc_runner.py`, 834 LOC combined)
are candidates for a similar shim audit, not evaluated function-by-function
here.

---

## 4. Bucket 3 — PARTIALLY MIGRATED (the front line, by function)

This is the bucket the task says tells us where the migration front line
actually is. Four concrete, function-level examples, each independently
confirmed against Rust source:

### 4.1 `router_v6/net_classification.py` (188 LOC) — migrated and retained, in the same file

- **Migrated** (delegate to Rust): `is_ground_net`, `is_power_net`,
  `is_hv_net`, `is_signal_net`, `classify_net_type`, and the four
  `is_*_pin` helpers → `temper_io_types.is_power_net_v6` /
  `is_signal_net_v6` / `classify_net_type_v6`, plus shared
  `is_ground_net`/`is_hv_net`/`is_*_pin` bindings.
- **Retained, unused in production** (bucket 5, not a migration gap):
  `GROUND_NET_PATTERNS`, `POWER_NET_PATTERNS`, `HV_NET_PATTERNS` (lines
  71–76) plus four pin-pattern `frozenset`s and `_matches_any` — R19 pinned
  oracle for `tests/router_v6/test_net_classification_rust_differential.py`.
- **Not migrated, deliberately** (process-local state, not a kernel):
  `_SINGLE_LAYER_MODE` / `set_single_layer_mode` / `get_single_layer_mode`
  — `test_quality_metrics_oracle_pin.py` asserts on the module-global
  directly.

### 4.2 The DFM cluster — Rust proven, Python still runs (PR #749)

`router_v6/thermal_relief.py`, `acid_trap_detection.py`, `copper_balance.py`,
`annular_ring_check.py`, `teardrop_generation.py` — 1,551 LOC, the "Post-route
DFM" `PORT` cluster in `docs/wave4-verdicts.yaml`. Per
`.unwired-kernel-inventory`: `dfm_adjacent_layer_py`, `dfm_board_bounds_py`,
`dfm_power_pour_bounds_py`, `dfm_rect_polygon_py`,
`dfm_thermal_via_positions_py`, `dfm_via_segment_index_py` are all
**"Rust proven, shim not written."** The kernels pass their differential
suite bit-exact against the pinned oracle; production has never been
switched to call them. This is a distinct failure mode from "half the
functions are ported" — here, *all* of a cluster's Rust replacements exist
and are proven, and *none* of production's call sites have moved. Naming
these six symbols is the actionable next step, not a Python rewrite.

### 4.3 Euclidean Distance Transform — kernel proven, call sites unchanged

`router_v6/routability_check.py` (477 LOC) and `router_v6/_astar_heuristics.py`
(196 LOC) both call `scipy.ndimage.distance_transform_edt` directly today.
`temper-geometry/src/edt.rs` implements an exact Felzenszwalb-Huttenlocher
port, measured bit-exact against scipy: **0.0 max abs diff, 0 differing
cells across 7,435,980 cells** (23 curated + 300 random trials), 1.6–1.7x
faster including the FFI boundary (`docs/evidence/2026-08-07-exact-edt-rust-spike.md`).
`docs/wave4-verdicts.yaml`'s own note is explicit: *"Migration itself is
unstarted — this file still calls scipy today."* `routability_check.py`
additionally calls `scipy.ndimage.label` for connected-component labeling, a
different scipy function the spike explicitly left out of scope — not
resolved by the EDT work at all.

### 4.4 `validation/drc_oracle.py` (518 LOC) — a shim with a dead internal branch

`DRCOracle` is heavily live (imported by `deterministic/state.py`,
`drc_sweep.py`, `drc_validation.py`, `setup.py`, `validation/__init__.py`,
`router_v6/constraints_drc_oracle.py`, and 19+ test files). Its own
docstring describes a dual-backend design: *"Optionally uses the Rust DRC
engine (`temper_drc_rs`) ... Graceful degradation: If `temper-drc` is not
installed ... the Python backend still works."* The Python fallback package,
`temper_drc`, **no longer exists in this tree** — per `AGENTS.md`: *"the
Python `temper-drc` package was deleted in the shim-then-delete migration"*
(`docs/solutions/architecture-patterns/temper-drc-rust-migration-shim-then-delete-2026-08-03.md`).
The file as a whole is very much alive; the "graceful degradation to a pure
Python backend" branch inside it is not reachable — a dead code path inside
a live file, which a whole-file DEAD/LIVE classification would miss
entirely. Not re-verified line-by-line whether the `except ImportError`
guard still degrades gracefully to *something* or would now raise; flagged
for a closer look, not resolved here.

---

## 5. Bucket 4 — LIVE, NOT MIGRATED

`docs/wave4-verdicts.yaml`'s R1 axis is the best available accounting of
this bucket, because it is the only place in the repo that has already
separated "inherently Python" from "migratable, just not done" at the
663-file scale it covers (`packages/temper-placer/src/temper_placer` +
`packages/temper-workflow`, **302 of those files / 66,309 LOC actually
triaged** as of 2026-08-11):

| R1 verdict | Files | LOC | Migratable? |
|---|---:|---:|---|
| BLOCKER-ORTOOLS | 15 | 2,858 | **Inherently Python** — `placer/cp_sat/**`, direct `ortools.CpSolver()`/`CpModel` calls. No mature Rust CP-SAT solver exists; remediation is an FFI project to OR-Tools' C++ library, an out-of-process solver, or a different solver entirely. Not a translation task. |
| PORT | 211 | 45,804 | **Migratable** (69.1% of the triaged share) — real numeric/geometric compute or mechanical glue that has a clear Rust destination but hasn't moved. Includes the EDT and DFM examples above. |
| REPLACE | 28 | 8,838 | **Inherently Python-shaped, replaceable by different Rust, not translatable** — `visualization/**` (6,086 LOC, Plotly HTML for human visual judgment — "no bit-identical bar to port against"), `cli/*.py` (click→clap), and the reporting/diagnostics cluster (`benchmark.py`, `diagnostics.py`, `manufacturing_report.py`, etc., 2,177 LOC). |
| OUT-OF-RUNTIME | 22 | 5,520 | **Dev/CI tooling** — `profiling/**`, `regression/{runner,reporter,corpus_runner,metrics_recorder,cli,manifest}.py`, `testing/**`, `fixtures/**`. In scope only under a "no Python anywhere in the repo" goal, which is explicitly an open question, not current policy. |
| UNDECIDED (recorded) | 13 | 2,338 | Explicitly flagged unresolved (e.g. `router_v6/zone_emission.py` — the re-triage's own cross-check found a GEOS convex-hull boundary, not a clean PORT). |
| **Unmatched (never triaged on this axis)** | **1,666** | **530,453** | Not a verdict — `scripts/`, `benchmarks/`, and the **entire test suite** were never scored on "what does full Python removal require," only on R7 ("should this move to Rust," where JUSTIFIED-KEEP mostly means "yes, but no case for a pyo3 boundary yet"). |

The BLOCKER-ORTOOLS cluster (`placer/cp_sat/_encoder_solve.py`, the 8
`handlers/encode_*.py` files, `cp_sat/__init__.py`/`_encoder_core.py`/`encoder.py`,
`model.py`, `unsat.py`/`unsat_surface.py`, `clearance_repair.py`) is the
cleanest "must stay Python, and not because of an oracle rule" example in
the repo: every file's blocking dependency is named
(`ortools.CpSolver().Solve()`, `ortools.CpModel.AddConstraint`/`NewIntervalVar`),
and the blocker is a missing piece of Rust ecosystem, not a policy choice.

---

## 6. Bucket 5 — RETAINED BY DESIGN (never propose deleting these)

**50,141+ LOC, high confidence, pipeline-mandated.** Two distinct shapes:

### 6.1 The `_py_oracle.py` test-companion population

**153 files, 50,141 LOC**, all under `packages/temper-placer/tests/**`,
never counted in the "production" total above because they live in the test
tree by construction. Each pairs with a `test_*_rust_differential.py` suite
and is the pinned pre-migration reference implementation
`docs/migration-pipeline.md` stage 3 requires: *"differential test pinning
the pre-migration implementation as oracle, written first (red), then the
Rust pyfunction (green)."* Deleting any one of these breaks the differential
suite it backs — there is no Rust-side equivalent to compare against once
the Python oracle is gone. `check_migration_narrowing.py`'s own
`production_py_files()` explicitly excludes any path containing
`_py_oracle` from its production scan for exactly this reason.

### 6.2 In-production retained-oracle constants — the prior art the task cites

`scripts/check_migration_narrowing.py`'s Check A used to flag exactly this
shape as a possible defect (a Rust `pub const` alongside a same-named,
unthreaded Python module constant) until `is_live_config_surface()` was
added to distinguish "nobody reads this constant, it's the in-repo statement
of the rule the Rust reproduces" from "someone imports this constant and the
Rust port silently hardcoded it" (the real `H_CONV_BACKGROUND` defect the
gate exists to catch). Quoting the script's own docstring: **"Measured on
the 2026-08-10 tree, all 8 raw Check A hits were retained oracles: the 7
pattern sets in `router_v6/net_classification.py` ... plus
`CONTACT_TOLERANCE_MM` in `router_v6/connectivity.py`."** This is the exact
prior art named in the task brief. Confirmed still true today
(`.migration-narrowing-allowlist`'s CHECK_A section is empty, by design —
*"An empty section is the expected steady state"*):

- `router_v6/net_classification.py:71-76` — `GROUND_NET_PATTERNS`,
  `POWER_NET_PATTERNS`, `HV_NET_PATTERNS`, plus four pin-pattern sets —
  pinned oracle for `test_net_classification_rust_differential.py` (R19,
  the module's own docstring).
- `router_v6/connectivity.py:21` — `CONTACT_TOLERANCE_MM = 1e-4`.

### 6.3 `_constraint_types/**` (1,033 LOC, 34 pydantic `BaseModel` subclasses)

R7-resolved 2026-08-11 as **JUSTIFIED-KEEP**
(`docs/evidence/2026-08-11-r7-constraint-types-resolution.md`, referenced
directly from `docs/wave4-verdicts.yaml`): `config_loader.rs` (already Rust)
calls `PlacementConstraints.model_validate` back into Python as *"final
authority, never reimplemented in Rust"* — a pyclass migration would break
the exception type and validation semantics, and the `gen_config_reference`
CI gate reads `model_fields`. Not a numeric kernel (34 models / 5 methods /
one float expression) — a schema-authority boundary, structurally different
from an oracle but equally "do not delete."

### 6.4 Mutation-campaign drivers — adversarial harnesses, not dead code

`scripts/phase5_batch2_mutations.py`, `phase5_cli_adapters_workflow_mutations.py`,
`phase5_final_leaves_mutations.py`, `phase5_hubs_mutations.py` (943 LOC) each
apply one-line mutants to already-migrated Rust kernels, rebuild, and assert
the differential/PBT suites *fail* (anti-vacuity evidence), then revert.
`check_unwired_kernels.py`'s own `production_references()` explicitly
excludes these by name — *"Mutation-campaign drivers contain MUTATED copies
of the pre-migration kernels ... they are adversarial harnesses, not
production callers."* All four remain in `scripts/manifest.yaml` as
`category: keep`, `owner: wave4-migration`, with recent `last_run` dates —
not dead, and not migration debt; they exist to prove the differentials
aren't rubber stamps.

---

## 7. Top 15 ranked deletion candidates, biggest first

Every row below is DEAD (bucket 1) or THIN-SHIM-with-a-named-caller-change
(bucket 2), independently caller-verified as described in §1 — none of these
come from copying `docs/wave4-verdicts.yaml`'s `DELETE` list uncritically.

| # | Path | LOC | Bucket | Evidence line |
|---|---|---:|---|---|
| 1 | `tools/measurements/**` (36 files) | 8,362 | DEAD | Zero importers, zero CI/Makefile refs, no `tools/` manifest exists; findings already committed as prose in `docs/evidence/*.md` (e.g. the EDT spike is quoted verbatim in `wave4-verdicts.yaml`'s `routability_check.py` note). |
| 2 | `tools/spice/**` (11 files) | 2,150 | DEAD (medium confidence) | Zero references outside the directory; no CI/Makefile wiring; no usage README. Confirm with an EE owner before deleting — plausibly hand-run. |
| 3 | `router_v6/net_classification.py` + `core/net_classification.py` near-duplication | ~325 (both files) | Partial dedup opportunity, not pure delete | Module's own docstring: *"This module is a near-duplicate of `core/net_classification.py` (same patterns, same docstring claim of being 'the' single source of truth)"* — both are R19/R7-live, so not in bucket 1, but the duplication itself (2 nearly-identical 137–188 LOC files) is a consolidation candidate once one is confirmed strictly subsumed by the other's Rust delegation. Listed for visibility, not a clean delete. |
| 4 | `cli/timing.py` + `cli/trace_commands.py` | 963 | THIN SHIM | *"already import a Rust extension directly"* per `wave4-verdicts.yaml`'s REPLACE-cluster note; deletable once `cli/` itself moves off click to clap (not independently — see caller change in §3). |
| 5 | `tools/sil/**` (4 files) | 566 | DEAD (medium confidence) | Zero references outside the directory; no CI/Makefile wiring; no README. Confirm with a firmware owner first. |
| 6 | `scripts/phase5_*_mutations.py` cluster — **excluded, listed to explain why** | 943 | NOT a candidate (bucket 5) | See §6.4 — adversarial harness, explicitly excluded from the unwired-kernel gate's own production-reference scan for that reason. Included here only so this list doesn't look like it missed the biggest zero-Python-importer scripts hit. |
| 7 | `validation/drc_oracle.py` dead fallback branch | ~unmeasured (file is 518 LOC, branch not isolated) | PARTIALLY MIGRATED, not a file-level delete | `temper_drc` (the Python fallback package the `except ImportError` branch degrades to) no longer exists in this tree at all (AGENTS.md, confirmed by `find`). The *file* is heavily live; only the fallback branch is dead. Needs isolation before it can be deleted as a unit. |
| 8 | `tools/demo_explainability_file.py` | 93 | DEAD | Zero references anywhere; the package it demonstrates is alive, this entry point is not. |
| 9 | `tools/fix_unused_args.py` | 85 | DEAD | Zero references anywhere; not registered in any manifest. |
| 10 | `tools/block_dispersion_measure.py` | 194 | DEAD | Zero references anywhere; same shape as the `tools/measurements/` cluster but sits one directory up. |
| 11 | `tools/clone_and_extract_pcbs.py` | 231 | DEAD | Zero references anywhere. |
| 12 | `tools/scrape_github_pcbs.py` | 284 | DEAD | Zero references anywhere. |
| 13 | `tools/setup_kicad_env.py` | 139 | DEAD | Zero references anywhere. |
| 14 | `tools/strip_zones.py` | 45 | DEAD | Zero references anywhere. |
| 15 | `packages/temper-placer/src/temper_placer/io/_parse_tracks.py` + `_parse_zones.py` | 16 | DEAD | Already-emptied migration boundary markers; docstring names the Rust replacement (`temper_design_bundle_python.parse_engine::parse_kicad_pcb`) and its own historical consumer directly. Smallest win on this list, but the cleanest possible example of "the mechanism already worked, someone just left the marker file behind." |

Row 6 is deliberately included as a non-candidate: it was the largest
remaining item in the zero-Python-importer scan after `tools/measurements/`,
`tools/spice/`, and `tools/sil/`, and a reader working from the raw
zero-importer list alone would reasonably guess it belongs here. It doesn't
— it's bucket 5, and leaving it off the list silently would look like an
oversight rather than a checked negative.

---

## 8. What this document does not cover

- **No per-function audit of the ~600K LOC that is neither bucket 1 nor
  bucket 5.** The R1 axis in `docs/wave4-verdicts.yaml` covers 302 files /
  66,309 LOC with real triage; everything else in `packages/`, all of
  `scripts/`, all of `benchmarks/`, and the entire test suite (1,666 files /
  530,453 LOC) has never been scored on "what does removing Python require,"
  only on the different, easier R7 question ("should this move to Rust" —
  where the answer is very often JUSTIFIED-KEEP for "yes eventually, no case
  for a pyo3 boundary yet," which is not the same as "stays forever").
- **`firmware/`, `elec/`, `simulation/`, `components/`, `ci-corpus/`** were
  out of scope — these are hardware-adjacent codegen/tooling, not part of
  the temper-placer/temper-workflow Rust migration this inventory tracks.
- **`.github/workflows/*`, `tools/wasm/**`, `packages/temper-worker/**`,
  `tools/wasm/wasm_tier_topology.json`** were read-only referenced (to check
  whether a script is CI/Makefile-invoked) but not audited themselves, per
  the task's exclusion list — other sessions are writing there concurrently.
- **Confidence is explicitly graded, not uniform.** `tools/measurements/**`
  is asserted DEAD with high confidence (multi-signal: zero imports, zero
  CI/Makefile refs, no governance manifest, git-log-confirmed single-purpose
  origin, findings already transcribed elsewhere). `tools/spice/**` and
  `tools/sil/**` carry the same *evidence* but a lower confidence label,
  because hand-run EE/firmware tooling with no repo-visible trigger is a
  real, non-hypothetical failure mode this method cannot distinguish from
  actually-abandoned code without asking the owner.
