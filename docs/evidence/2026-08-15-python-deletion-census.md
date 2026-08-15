---
module: python-deletion-census
tags: [census, python-rust-migration, shims, dead-code, deletion]
problem_type: tooling-decision
date: 2026-08-15
branch: census/python-deletion-candidates-2026-08-15
base: origin/main @ 7f6a6bd5c
---

# Python Deletion Census — 2026-08-15

Read-only census of every Python file that is a candidate for deletion:
pure-delegation shims to Rust, dead code with no callers, duplicate
implementations where Rust is the SSOT, test-only support files, and
files made redundant by the SafetyValue SSOT migration. Produces a
prioritized deletion list. **No source files were modified.**

## Summary

| Metric | Value |
|---|---|
| Python files in repo (non-oracle) | 2,020 (2187 total − 167 oracles) |
| Total Python LOC (non-oracle) | ~616,981 |
| **Deletable LOC (Tier 1, safe)** | **539** (10 files) |
| **Deletable LOC (Tier 2, needs care)** | **884** (12 files) |
| **Total deletion headroom** | **1,423 LOC** |
| Truly dead production files found | **0** |
| Dead scripts found | **0** |
| Protected oracle LOC (excluded) | 54,703 (167 files) |

### Breakdown by classification

| Classification | Files | LOC |
|---|---|---|
| Fully redundant re-export shim (names all re-exported by package `__init__`) | 5 | 326 |
| Pure-delegation shim, test-only consumers | 4 | 213 |
| Pure-delegation shim, production callers (needs rewiring) | 12 | 884 |
| Partial shim (compute in Rust, real Python retained) — **keep** | 5 | 1,955 |
| Truly dead (no importers, no CI/manifest reference) | 0 | 0 |
| Protected (oracles / independent pins) — **excluded** | 169+ | 54,736+ |

---

## Method

1. AST import graph over all 2,187 Python files (full dotted-name
   resolution incl. the `packages/temper-placer/src` and `tests` roots,
   function-body imports, and relative imports) → zero-importer set.
2. Shim scan: every non-test `src` file importing a pyo3 Rust module;
   per-function body classification (pure delegation vs. retained
   Python logic).
3. For each pure shim: caller census (`grep` + graph), plus CI wiring
   check (`.github/workflows/*`, `scripts/manifest.yaml`, `Makefile`)
   to separate "entry point" from "dead".
4. Cross-reference with the handoff's §5 SSOT-migration branches and
   the protected-oracle list (`scripts/oracle_hashes.json`).

The repo's own tooling (`.coverage-allowlist`, `check_stale_extensions`,
`import_linter_gate.py`) was not run — this is a census, not a build.

---

## Tier 1 — SAFE deletions (fully redundant / test-only pure shims)

These files contain **zero Python logic**: every function body is a
one-line call into a pyo3 Rust kernel (or a module-level bind of a Rust
pyfunction). No production module imports any of them. Consumers are
tests that could import the Rust module (or the package `__init__`)
directly.

### 1.1 geometry/{polygon,smooth,projections,primitives,overlap}.py — 326 LOC

**Classification: fully redundant re-export shim.** Commit `d8a797c66`
(2026-08-09, "collapse geometry/ pure-delegation shims to one-line Rust
binds") already collapsed every wrapper body in these five modules to
module-level binds of `temper_geometry` pyfunctions. `geometry/__init__.py`
(202 LOC) **re-exports every single name from all five** directly from
`temper_geometry` — verified name-by-name:

- `polygon.py` (108): `polygon_area`, `polygon_signed_area`,
  `triangle_area`, `polygon_centroid`, `point_in_polygon_winding`,
  `point_in_rect`, `point_in_polygon_soft`, `point_in_rect_soft`,
  `polygon_perimeter`, `compute_loop_area`, `compute_loop_perimeter`,
  `loop_area_penalty`, `polygon_bounding_box`, `polygon_bounding_circle`,
  `is_convex`, `polygon_orientation`, `nearest_point_on_segment`,
  `nearest_point_on_polygon`, `translate_polygon`, `scale_polygon`,
  `rotate_polygon` — all in `__init__`.
- `smooth.py` (70): all 16 names in `__init__` (incl. `smooth_leaky_relu`
  with its default-value shim).
- `projections.py` (41): all 7 names in `__init__` (incl.
  `project_outside_keepout`).
- `primitives.py` (60): all 23 names in `__init__`.
- `overlap.py` (47): all 11 names in `__init__`.

Importers (all tests, no production):
`tests/geometry/test_geometry.py`, `test_geometry_coverage.py`,
`test_drc_inflate.py`, `tests/core/test_coverage_paydown_v8.py`,
`tests/unit/test_projections.py`.

**Deletion**: change those ~5 test files to import from
`temper_placer.geometry` (or `temper_geometry`) instead of the submodule
paths. **Rust equivalent**: `temper_geometry` pyo3 surface (same pyfunctions
the binds point at). **Deletion safety: SAFE.** LOC: 326.

### 1.2 core/placement_drc.py — 55 LOC

**Classification: pure-delegation shim, test-only consumers.** Single
function `validate_placement_drc` delegates to
`temper_io_types.validate_placement_drc` (Wave-4 Phase-2 port; `PinInfo`/
`PlacementViolation` are now Rust `#[pyclass]` types). Zero production
importers — the only consumers are the four Wave-4 contract tests
(`test_core_contracts_{pbt,metamorphic,differential,perf}.py`) which
already import `temper_io_types` elsewhere and `_core_py_oracle` (protected)
for the differential. **Deletion safety: SAFE** — tests re-point
`prod_drc.validate_placement_drc` → `temper_io_types.validate_placement_drc`.
Rust equivalent: `temper_io_types`. LOC: 55.

### 1.3 physics/emi.py — 60 LOC

**Classification: pure-delegation shim, test-only consumers.**
`predict_radiated_emissions` / `check_emi_compliance` delegate to
`temper_thermal` (Wave 4 Phase 4). No production importers; only
`tests/physics/test_emi_rust_differential.py` and
`test_extra_physics.py`. **Deletion safety: SAFE.** Rust equivalent:
`temper_thermal.predict_radiated_emissions_py` /
`check_emi_compliance_py`. LOC: 60.

### 1.4 physics/safety.py — 61 LOC

**Classification: pure-delegation shim, test-only consumers.** All three
functions delegate to `temper_thermal`. Only
`tests/physics/test_extra_physics.py` and
`test_safety_rust_differential.py` import it. **Deletion safety: SAFE.**
LOC: 61.

### 1.5 report/summary.py — 37 LOC

**Classification: pure-delegation shim, test-only consumers.**
`generate_summary` / `_extract_key_metrics` delegate to
`temper_io_types.report_generate_summary` /
`report_extract_key_metrics` (Wave 4 Phase 5). Only
`tests/report/test_report_pbt.py` and `test_summary_rust_differential.py`
import it (the differential compares the shim against
`tests/report/_summary_py_oracle.py`, which is protected — the test
would compare `temper_io_types` against the oracle directly instead).
**Deletion safety: SAFE.** LOC: 37.

**Tier 1 total: 539 LOC across 10 files.**

---

## Tier 2 — NEEDS-CARE deletions (pure shims with production callers)

These files are also pure delegation (100% pure per the shim scan), but
production modules import from them. Deleting requires re-pointing those
callers at the Rust module — a mechanical but multi-site change. Ordered
by (caller count, LOC).

### 2.1 router_v6/metrics/slop_linter.py — 66 LOC — 1 production caller

5/5 functions pure; delegates to `temper_quality_oracle`. Sole importer:
`placer/cp_sat/gates.py` (production). Re-point gates.py at
`temper_quality_oracle` and delete. **Deletion safety: safe w/ 1 caller.**
LOC: 66.

### 2.2 core/ipc2221.py — 32 LOC — 2 production callers + tests

Both functions pure delegation to `temper_drc_rs`
(`estimate_trace_current`, `estimate_current_from_net_class`). Production
importers: `core/__init__.py:40` (re-export) and
`tools/wasm/r2_serialize_board.py:255`. `TRACE_CURRENT_TABLE_1OZ` dict is
test-only data (used only by `tests/core/test_ipc2221.py`; no Rust
equivalent — moves into the test or dies). Re-point the two production
sites at `temper_drc_rs` and delete. **Deletion safety: safe w/ 2 callers.**
LOC: 32.

### 2.3 io/dsn_normalizer.py — 17 LOC — 1 production importer

3/3 functions pure delegation to `temper_io_types`; re-exported verbatim
by `io/__init__.py:28` (same redundancy pattern as geometry §1.1).
Re-point `io/__init__.py` and the 2 test files at `temper_io_types`.
**Deletion safety: safe w/ 1 caller.** LOC: 17.

### 2.4 physics/thermal.py — 57 LOC — 1 production caller

`estimate_junction_temp` pure delegation to `temper_thermal`
(`estimate_junction_temp_py`), keeping only default thermal-resistance
parameters (Rjc/Rch/Rha_base — **defaults, not logic**; the Rust kernel
mirrors the operation order bit-for-bit per the differential). Production
importer: `physics/thermal_potential.py`. Re-point and delete.
**Deletion safety: safe w/ 1 caller** (verify the defaults ride through
the pyo3 signature). LOC: 57.

### 2.5 physics/inductance.py — 69 LOC — 1 production caller

2/2 functions pure delegation to `temper_thermal`. Production importer:
`metrics/physics.py`. **Deletion safety: safe w/ 1 caller.** LOC: 69.

### 2.6 router_v6/_strip_copper.py — 83 LOC — 2 production callers

2/2 pure delegation to `temper_io_types` (strip-copper geometry). Production
importers: `router_v6/_adapter_convert.py`, `scripts/route_board.py`.
**Deletion safety: safe w/ 2 callers.** LOC: 83.

### 2.7 deterministic/stages/{zone_assignment,apply_placements,fine_pitch_escape,_phase_zones}.py — 273 LOC — pipeline interface

Each keeps a `Stage` subclass whose `run()` delegates to
`temper_orchestration` across the FFI (Phase D batches D2/D7 of plan
2026-08-09-001). The Stage subclass is the deterministic pipeline's plugin
interface (`deterministic/__init__.py` iterates `Stage` objects) — deleting
means the pipeline re-points at `temper_orchestration` directly, which is a
design change to stage registration, not a mechanical import swap. These
are the **lowest-priority Tier-2 items**: the shell is arguably retained
API, and the differential oracles (`_zone_assignment_py_oracle.py`,
`_apply_placements_run_py_oracle.py`, etc. — protected) pin the current
behavior. LOC: 27 + 30 + 114 + 102 = 273.

### 2.8 router_v6/grid_converter.py — 116 LOC — 2 production callers

4/4 pure delegation to `temper_geometry`. Production importers:
`io/kicad_exporter.py`, `router_v6/path_simplify.py`. **Deletion safety:
safe w/ 2 callers.** LOC: 116.

### 2.9 geometry/kicad_transform.py — 171 LOC — ~10 production callers + 2 scripts

6/6 pure delegation to `temper_geometry` (kernels landed 2026-08-10,
`963503eb7`). This is the **sanctioned R(-theta) rotation surface**
(`geometry/__init__.py` re-imports from it) with 28 importers total:
production `io/_write_board.py`, `io/_write_modules.py`,
`io/kicad_exporter.py`, `router_v6/_adapter_convert.py`,
`router_v6/connectivity.py`, `validation/placement_roundtrip.py`, plus
`scripts/check_board_containment.py`, `scripts/check_isolation_keepout.py`,
`scripts/check_pad_orientation.py` and ~19 test files. All pure binds —
mechanical rewire, but the widest blast radius of any candidate.
**Deletion safety: safe but wide — do last, or keep as the sanctioned
import surface.** LOC: 171.

**Tier 2 total: 884 LOC across 12 files.**

---

## Tier 3 — Partial shims (NOT deletion candidates)

Compute has moved to Rust, but the files retain real Python: enums,
dataclasses, matrices, duck-typed marshalling, or orchestration. Deleting
these is a port, not a deletion. Listed for completeness and to prevent a
future census from flagging them.

| File | LOC | Retained Python (why it can't go yet) |
|---|---|---|
| `requirements/validators/clearance.py` | 523 | `IEC60335_REQUIREMENTS` matrix (consumed by CP-SAT encoder; mirrored in Rust `MATRIX_ROWS`, pinned together by `test_requirement_matrix_values_pinned`), `VoltageDomain`/`InsulationType` enums, `ClearanceViolation`/`ClearanceResult` dataclasses, `_result_from_payload`/`_violation_from_dict` materialization. Check/report/matrix functions delegate to `req_safe_01_*`. |
| `router_v6/clearance_check.py` | 837 | `_verify_clearance_python` fallback path, `_calculate_minimum_clearance_by_layer` with via-segment checks, `_load_manifest_hv_net_names`, `_get_required_clearance` voltage tables, `_classify_net_class`. Imports Rust lazily (drc-rs, orchestration). Live in manufacturing report + pipeline verify. |
| `router_v6/creepage_check.py` | 490 | `verify_creepage` orchestration, `_extract_segments` duck-typed route marshalling (deliberately Python), `_find_clearance_violations` aggregation, dataclasses. Geometry delegates to `temper_geometry`; pair loop to `temper_orchestration.run_creepage_check`. |
| `core/ipc2152.py` | 88 | `ipc2152_min_width` stackup/layer resolution (real logic); module is also the re-export surface for `gates.py:395` (`get_net_current`) and `validation/dead_parameter_probe.py` (`ipc2152_external_width`). Handoff: `ipc2152_min_width` itself has no production caller. |
| `tests/requirements/validators/clearance.py` | 17 | Test-tree import-compat shim (`from temper_placer.requirements.validators.clearance import *`). Deletable only after ~10 test files re-point to the production module — same mechanical class as Tier 2, but test-tree-only. |
| `router_v6/net_classification.py` | 188 | Documented near-duplicate of `core/net_classification.py` with a distinct router_v6 power-net kernel (4 extra patterns, `+`-prefix heuristic). Both live; Rust holds one copy of the shared patterns. Deletion would merge two distinct kernels — needs design, not deletion. |

**Notable non-candidates worth recording:**
- `core/design_rules.py` (689) — zero *direct* importers in the graph but
  live via `deterministic/state.py`, `deterministic/__init__.py`,
  `validation/drc_oracle.py`, `tests/conftest.py`; holds `TEMPER_NET_CLASSES`
  (the N4 SSOT feeding `generate_kicad_dru.py`).
- `regression/measure_closure.py` (208) — zero importers but live: the U5b
  promotion gate `tests/closure/test_router_completion.py` shells out to
  `python -m temper_placer.regression.measure_closure`.
- `router_v6/clearance_engine.py` (205), `router_v6/clearance_floor.py`
  (174) — live (imported by `clearance_check.py`, `_astar_reconstruct.py`).

---

## Truly dead code — verified NONE

- **`src/`**: exactly two zero-importer modules
  (`regression/measure_closure.py`, `core/placement_drc.py`) — both have
  live test/CLI consumers (above). Every other zero-importer `src` file
  resolves to a dynamic/function-body/`__init__`-package import that the
  graph now resolves.
- **`scripts/`**: all 159 scripts are referenced in
  `.github/workflows/*`, `scripts/manifest.yaml`, or `Makefile` — zero
  orphans. (Note: `scripts/manifest.yaml`'s `_meta` header is stale —
  says 119 total/0 ticket, file now has 160 entries all `category: keep`;
  not a deletion signal, a hygiene nit.)
- **`core/ipc.rs` (Python)**: does not exist — the task's §3 candidate.
  Only `core/ipc2152.py` and `core/ipc2221.py` exist; both are shims over
  `temper_drc_rs` (the authoritative kernel is `temper-drc-rs/src/ipc.rs`,
  IPC-2221B k=0.048/0.024).
- `tools/` and `simulation/` — standalone developer tools (wasm helpers,
  ngspice harnesses, measurement scripts); invoked manually, not dead.

## Protected — excluded from every deletion recommendation

- **167 `_*_py_oracle.py` files (54,703 LOC)** — content-hash pinned in
  `scripts/oracle_hashes.json`; the Rust migration's differential safety
  net (handoff §1). **Never suggest deleting.**
- `tests/requirements/clearance_oracle/{clearance.py,_copper.py}` — the
  verbatim pre-migration oracle for the `req_safe_01` Rust port
  ("pinned verbatim" per the shim's docstring; not in `oracle_hashes.json`
  but the same safety-net role).
- `tests/router_v6/_ipc2221_brackets.py` (33) — the single shared
  independent copy of the IPC-2221 bracket table (UNSOURCED label,
  handoff §3); the boundary tests deliberately derive from it so the Rust
  `required_creepage_bracket` is verified against independent data. A
  Rust-only source would make the tests self-referential — the exact
  "byte-identical to implementation" pattern the handoff condemns.

## SSOT-migration status (§5 branches) — already landed, nothing left to reap

| Old value | Python homes after migration | Verdict |
|---|---|---|
| 14.0 mm creepage base | gone from `src`; only comments remain (`design_rules.py:65,472`). The value was never in Python src post-correction. | nothing to delete |
| 0.065 k-value | only a comment in `placer/cp_sat/gates.py:607` citing the rejected `temper-constraints/src/ipc.rs` | nothing to delete (the Rust file is a separate, pre-existing decision) |
| 1.0 FUNCTIONAL creepage pin | corrected to 1.8 in `requirements/validators/clearance.py` matrix (2026-08-15) and mirrored in Rust `MATRIX_ROWS`; the value lives in the **pinned test** pins (SNAPSHOT by design) | keep — regression pins |
| 6.0 legacy family / UNSOURCED labels | documented in `clearance.py` module comments; the 3.0/6.0 clearance cells are flagged UNSOURCED and deliberately **not** removed (non-binding under the 6.3/12.6 creepage floor) | keep |
| SafetyValue/Provenance | `scripts/generate_kicad_dru.py` already pulls via `temper_design_bundle_python` (`creepage_table_lookup`/`clearance_table_lookup`); no Python copy of the tables remains | keep (it's the consumer, not a duplicate) |

The four SSOT branches did their work in Rust + `generate_kicad_dru.py`;
the Python-side constant tables they superseded are already gone. **No
`ssot-redundant` deletions remain to make.**

---

## Prioritized deletion list (top 20)

Rank = safety of deletion, then LOC, then caller count.

| # | File | LOC | Classification | Rust equivalent | Callers to update | Safety | Cum. LOC |
|---|---|---|---|---|---|---|---|
| 1 | `geometry/polygon.py` | 108 | redundant re-export shim | `temper_geometry` (via `geometry/__init__`) | 3 tests | safe | 108 |
| 2 | `geometry/smooth.py` | 70 | redundant re-export shim | `temper_geometry` | 4 tests | safe | 178 |
| 3 | `geometry/primitives.py` | 60 | redundant re-export shim | `temper_geometry` | 3 tests | safe | 238 |
| 4 | `core/placement_drc.py` | 55 | pure shim, test-only | `temper_io_types` | 4 tests | safe | 293 |
| 5 | `geometry/overlap.py` | 47 | redundant re-export shim | `temper_geometry` | 2 tests | safe | 340 |
| 6 | `geometry/projections.py` | 41 | redundant re-export shim | `temper_geometry` | 3 tests | safe | 381 |
| 7 | `report/summary.py` | 37 | pure shim, test-only | `temper_io_types` | 2 tests | safe | 418 |
| 8 | `physics/safety.py` | 61 | pure shim, test-only | `temper_thermal` | 2 tests | safe | 479 |
| 9 | `physics/emi.py` | 60 | pure shim, test-only | `temper_thermal` | 2 tests | safe | 539 |
| 10 | `router_v6/metrics/slop_linter.py` | 66 | pure shim | `temper_quality_oracle` | 1 (gates.py) | safe w/ 1 caller | 605 |
| 11 | `io/dsn_normalizer.py` | 17 | pure shim | `temper_io_types` | 1 (io/__init__) | safe w/ 1 caller | 622 |
| 12 | `core/ipc2221.py` | 32 | pure shim | `temper_drc_rs` | 2 + 1 test data | safe w/ 2 callers | 654 |
| 13 | `physics/thermal.py` | 57 | pure shim | `temper_thermal` | 1 (thermal_potential.py) | safe w/ 1 caller | 711 |
| 14 | `physics/inductance.py` | 69 | pure shim | `temper_thermal` | 1 (metrics/physics.py) | safe w/ 1 caller | 780 |
| 15 | `router_v6/_strip_copper.py` | 83 | pure shim | `temper_io_types` | 2 | safe w/ 2 callers | 863 |
| 16 | `tests/requirements/validators/clearance.py` | 17 | test-import compat shim | production module (not Rust) | ~10 tests | safe w/ re-point | 880 |
| 17 | `router_v6/grid_converter.py` | 116 | pure shim | `temper_geometry` | 2 | safe w/ 2 callers | 996 |
| 18 | `deterministic/stages/zone_assignment.py` | 27 | pure shim (Stage shell) | `temper_orchestration` | 1 (stages/__init__) | needs care (pipeline API) | 1023 |
| 19 | `deterministic/stages/apply_placements.py` | 30 | pure shim (Stage shell) | `temper_orchestration` | 1 (stages/__init__) | needs care (pipeline API) | 1053 |
| 20 | `geometry/kicad_transform.py` | 171 | pure shim, sanctioned surface | `temper_geometry` | ~10 prod + 2 scripts + 19 tests | needs care (widest blast radius) | 1224 |

Remaining Tier-2 items beyond #20: `deterministic/stages/fine_pitch_escape.py`
(114), `deterministic/stages/_phase_zones.py` (102) — same Stage-shell
class as #18/#19; delete together with them.

## Recommendations

1. **Land Tier 1 (539 LOC) as one mechanical PR**: delete the 10 files,
   re-point the ~25 test import sites at the Rust modules /
   package `__init__`s. No behavior change (the binds point at the same
   pyfunctions). `make regen-check` + the differential suites verify.
2. **Land Tier 2 (884 LOC) as a follow-up, smallest-blast-radius first**
   (slop_linter → dsn_normalizer → ipc2221 → thermal → inductance →
   _strip_copper → grid_converter), each with its production caller
   re-pointed in the same commit.
3. **Defer the Stage-shell files (#18/19 + fine_pitch_escape +
   _phase_zones)** and `kicad_transform.py`: the Stage subclass is the
   pipeline's plugin interface and kicad_transform is the sanctioned
   R(-theta) surface — deleting is a design change, not a shim removal.
4. **Do not touch** the 167 oracles, `clearance_oracle/`,
   `_ipc2221_brackets.py`, or any Tier-3 partial shim.
5. `scripts/manifest.yaml` `_meta` header (119 total / 0 ticket vs 160
   actual entries) should be refreshed by whoever next touches the file —
   a hygiene nit, not a deletion signal.
