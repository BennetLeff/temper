<!-- provenance: commit=66a277d94411154d063ea2894d367600c7d33c3d dirty=UNKNOWN -->
     base=origin/main 2cd88c9b7a10eac7eaabe929a8da9cff16d6adfc
     date=2026-08-12
     method=AST pyclass/import reachability over packages/temper-placer/src +
       tests + shim re-exports + Rust value-reachability, verified by
       cargo build/test + focused pytest sweeps -->

# Pyclass-removal spike — full 214-item audit + deeper Python sweep

**Scope.** (A) Enumerate every `#[pyclass]` across the 10 pyo3 crates and
determine Python-name reachability for each; delete the safely-dead ones.
(B) A second, deeper sweep over `packages/temper-placer/src` for additional
deletable Python modules beyond the 8 the 2026-08-12 deprecation spike
(`docs/evidence/2026-08-12-python-deprecation-deletion-spike.md`) already
removed.

**Result.** Part A deleted **12 pyclasses / 654 LOC** (2 commits pushed on
`spike/pyclass-removal`); Part B found **no additional deletable modules**
(the earlier 8 were the complete safe set) and cleaned **4 dead `__init__`
re-export names** (~20 LOC). All Rust crates build and test green; the
import-linter gate passes; `make regen-check` shows only the two
pre-existing concurrent drifts (the `_measure_closure_py_oracle.py` pin from
#1037 and the manifest-less `generate_power_islands.py`).

## Part A — method

1. **Enumerated all `#[pyclass]`** with a multi-line scan that skips comment
   lines and resolves `#[pyclass(module=..., name=...)]` renames (enums like
   `ConstraintTier` have `#[derive]/#[allow]` lines between the attribute and
   the type declaration). **214 pyclasses** found across 10 crates (the
   hypothesis said ~239; the gap is doc-comment mentions).
2. **Python-name reachability**, resolved through a shim-aware AST graph:
   `import mod as alias` / `from mod import name` / attribute chains
   `alias.sub.Name`, **module-level re-export assignments**
   (`_rs = _tdb.board_contracts`, then `Pad = _rs.Pad`), package-`__init__`
   re-export chains, `getattr`, and tests (production `src/` vs `tests/`).
   This is the machinery that matters: a naive grep for the Rust struct name
   flags everything, and a naive "attribute chain on the import alias" misses
   `core/board.py`'s `_rs = _tdb.board_contracts` rebind (every board-contract
   pyclass would have been miscounted as unreferenced).
3. **Rust value-reachability** as a second axis: a pyclass returned by a
   function or embedded in another pyclass's getter is reachable from Python
   **as a value** even when its Python name is never imported. This killed
   several of the initial hypothesis's "unreferenced" candidates (below).

### The initial hypothesis, verified (all 12)

| Hypothesis candidate | Verdict | Evidence |
|---|---|---|
| `DrcOracleTrackPadPair/TrackPair/ViaPadPair/ViaPair` | **LIVE — KEEP** | `router_v6/constraints_drc_oracle.py` constructs all four via `_temper_drc_rs.DrcOracleTrackPair(...)` etc. (production). |
| `PyCompilationContext` (`CompilationContext`) | **LIVE — KEEP** | `pcl/sat_bridge.py` + `pcl/unsat_compiler.py` import it from `temper_placer.pcl.constraints`. |
| `PyDsnExporterCore` (`DSNExporterCore`) | **LIVE — KEEP** | `io/dsn_exporter.py` builds `DSNExporterCore(...)`. |
| `PyExportResult` (`ExportResult`) | **LIVE — KEEP** | `io/kicad_exporter.py` (via `io/export_types` shim). |
| `PyFootprintLibrary` / `PyFootprintSpec` | **LIVE — KEEP** | `fixtures/synthetic.py`, `io/footprint_library.py`. |
| `PyPlacementViolation` (`PlacementViolation`) | **LIVE — KEEP** | `core/placement_drc.py` re-exports it from `temper_io_types`. |
| `PyReferenceAliasManifest` | **LIVE — KEEP** | `io/reference_aliases.py`. |
| `PySkipExpr` (`SkipExpr`) | **VALUE-REACHABLE — KEEP** | No source imports the *name*, but `pipeline/dag_expr.py` calls `_rs.parse_skip_expr_rs(...)` and uses the returned object's `to_spec()`/`evaluate()`. Deleting the pyclass breaks the function signature and the object methods. The hypothesis's "unreferenced" was true for the name only, not the value. |
| `PyRect` (`Rect` on `temper_io_types`) | **UNREACHABLE — DELETED** | Zero name refs (prod/tests/stubs), zero Rust callers outside its own `#[pymethods]`; the *other* `Rect` (design-bundle `board_contracts`, used via `core/board.py`) is the live one. |

So the hypothesis was wrong on 11 of 12; only `PyRect` was a genuine delete.

### Additional value-reachable keeps (in the 21-name unreach set)

`ExtractedLoopWire` (`LoopExtractionOutput.loops`), `DrillDefinition` /
`Position` (`PadData.drill` / `DrillDefinition.offset` getters — returned to
Python), `DrcComponentSnapshot` / `DrcViaSnapshot` / `DrcTraceSnapshot` /
`DrcNetClassRuleSnapshot` (`DrcBoardSnapshot` fields). These have zero Python
*name* references but are returned as values; deleting them breaks the Rust
build of the enclosing pyclass.

### Deleted (Part A) — 12 pyclasses, 654 LOC

| pyclass | Rust name | Registration removed | Rust file |
|---|---|---|---|
| `Rect` | `PyRect` | `placer_core::pybridge::register` | `temper-io-types/.../pybridge.rs` |
| `Provenance` (+ dead `sha256_hex_py` fn) | `PyProvenance` | `provenance::PyProvenance` + `sha256_hex_py` in `lib.rs` | `temper-io-types/.../provenance.rs` |
| `ConstraintType` | `PyConstraintType` | `add_class` in `pymodule` | `temper-placer/temper-constraints/src/lib.rs` |
| `Variable`, `NetChannelVar`, `NetLayerVar`, `ViaVar`, `OrderVar`, `Constraint`, `CapacityConstraint`, `DiffPairConstraint`, `LayerConstraint` | same | 9× `add_class::<crate::types::...>` | `temper-rust-router/src/types.rs` (whole module deleted) |

`sha256_hex_py` was deleted because it is the *only* other member of
`provenance.rs`'s `py_bridge` module; production uses design-bundle's
`sha256_hex` instead (verified: zero importers of the io-types name).

### Kept, TEST-ONLY (16), with evidence

Every TEST-ONLY pyclass is pinned by a `*_rust_differential.py` / PBT /
oracle suite and is retained per the R1a/R1b differential discipline
(deleting needs the oracle-retirement bar): `DiffPairConfig`,
`HypergraphBuildResult`, the monte_carlo set
(`DistributionParams`/`ManufacturingVariables`/`MonteCarloConfig`/
`MonteCarloResult`/`MonteCarloSimulator`), the tolerances set
(`CopperWeight`/`LayerType`/`ToleranceTable`/`FeatureTolerance`/
`ToleranceAnalyzer`), `LayerConfig`/`Stackup`, `ConstraintValue`
(drc_marshal), `FootprintBounds`. No pyclass was repointed-and-removed:
every TEST-ONLY item is a wave4 differential participant, not a pure
test-harness duplicate.

### Full classification (214)

- **LIVE** (production Python name reference): 177
- **TEST-ONLY** (tests pin it; all differential/PBT/oracle): 16
- **UNREACH by name** (21): 9 value-reachable keeps + 12 deleted
  (the `$name` macro placeholder in `pcl_tags.rs` is a scan artifact, not a
  real pyclass — `TagAnd`/`TagOr` come from the same `macro_rules!` and are
  registered/used).

## Part B — deeper Python sweep

Re-built the import graph over `packages/temper-placer/src` with corrected
relative-import resolution and ran four complementary checks:

1. **Transitive closure from package/CLI entry points** — too strict (the
   package `__init__` exports a deliberately narrow surface; most production
   code is reached via the CLI). Rejected as the criterion.
2. **Zero *direct* production importers** — recomputed; the set matches the
   earlier spike's 56-module triage exactly (minus its 8 deletions). No
   module shifted buckets: everything remaining is either an R20
   oracle/differential participant, an entry point / package machinery, or
   real compute whose removal is a product decision (`mfem_*`,
   `capacity_check`, `congestion_analysis`, `unsat_compiler`, `version_gate`,
   `geometry/{polygon,primitives,projections,sdf,smooth}`, ...).
3. **Pure re-export shims** (`X = _rs.X` bodies): 17 found; **16 have
   production importers**. The one without — `io/isolation_slot_geometry` —
   is imported by `_zone_aware_slot_generation_run_py_oracle.py` (an R20 py
   oracle) and retained for that reason (same call the earlier spike made).
   Function-delegation shims (`grid_utils`, `tht_check`) are R20-retained
   because their differential tests import shim + extension + oracle.
4. **`__init__` re-export consumption check** (the `drc_runner` shape: a
   module imported only by an `__init__` re-export whose names have no
   callers): found **4 dead re-export names** — `DegreesArray`,
   `RadiansArray` (`core/__init__`), `PCBExporterFn` (`io/__init__`),
   `QualityInputs` (`metrics/__init__`) — all with zero consumers
   repo-wide (verified by grep across src/tests/scripts). `run_regression`
   was a false positive of the heuristic (it is a lazy CLI command used at
   `cli/__init__.py:899`). These were removed (~20 LOC); the dead
   definitions (`units.py` TypeAliases, `quality_score.py` `QualityInputs`
   dataclass) were removed with them. `PCBExporterFn`'s definition stays
   (used as an internal annotation in `placement_exporter.py`).

**Bottom line for Part B.** The 2026-08-12 deprecation spike's 8 deletions
were the complete safe set; a corrected, deeper sweep finds nothing further
at module granularity. The additional yield is the 4 dead `__init__`
re-export names above.

## Gates

- `cargo build` + `cargo test` (incl. `--features wasm-registry`) green for
  `temper-io-types` (6730 tests), `temper-rust-router`, `temper-constraints`.
- Focused pytest sweeps over the touched boundaries: 973 passed
  (encoder/dag-expr/net-batching/provenance/footprint-parser +
  board/parse-engine/footprint-library/reference-aliases/config-loader/
  constraint-model/drc-oracle/netlist differentials + pcl constraints +
  drc-marshal + net-classification + units/metrics/placement-exporter).
- `scripts/import_linter_gate.py`: PASSED (0 violations).
- `make regen-check`: only the two pre-existing concurrent drifts
  (`_measure_closure_py_oracle.py` pin from #1037, manifest-less
  `generate_power_islands.py`); nothing new from this spike.
- `.unwired-kernel-inventory`: unchanged by these deletions (no kernels were
  orphaned — the deleted pyclasses had no kernel registration).
