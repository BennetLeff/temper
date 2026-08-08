<!-- provenance: commit=73ddab17 (merge base, worktree-agent-a0c9bd1a1df109a4d) dirty=true (working-tree changes at authoring time: this document plus the diff and measurement script it describes) -->

# `mfem_compare.py`'s `griddata(nearest)` — Rust `rstar` nearest-neighbor migration (2026-08-07)

**Verdict: migrated.** `validation/mfem_compare.py`'s `project_mfem_to_fdm`
no longer imports scipy. `scipy.interpolate.griddata(method="nearest")` is
replaced by `temper_geometry.nearest_neighbor_transform` — a new `rstar`
R*-tree single-nearest-neighbor kernel in `packages/temper-geometry/`,
reusing the crate's existing `IndexedPoint` wrapper
(`radius_pairs.rs`/`persistent_radius_index.rs`). Test coverage of the
actual nearest-neighbor code path went from **zero** to a 14-case
differential suite, added as part of this port per the task brief.

## 1. Premise verification

The re-triage (`docs/evidence/2026-08-07-scipy-keeps-re-triage.md` Sec 4)
flagged this "portable but untriaged." Verified independently:

- **The call site** (`project_mfem_to_fdm`, `mfem_compare.py:89-119`, before
  this change): `griddata(src_pts, t, grid_pts, method="nearest",
  rescale=False)` projects MFEM mesh-node temperatures onto the FDM grid.
  `method="nearest"` internally builds a `cKDTree(src_pts)` and calls
  `tree.query(grid_pts)` (`scipy.interpolate.NearestNDInterpolator`, which
  `griddata`'s `"nearest"` branch delegates to) — a batch single-nearest-
  neighbor query, exactly the primitive class `radius_pairs.rs` (radius
  query) and `persistent_radius_index.rs` (persistent radius query) already
  proved `rstar` handles correctly and deterministically in this crate;
  `rstar::RTree` additionally exposes `nearest_neighbor` directly, so no
  new spatial-index crate or algorithm was needed.
- **Tie sensitivity, verified by reading the sole consumer**:
  `compare_fields` (`mfem_compare.py:29-86`) computes `max(abs(mfem_field -
  fdm_field)) > tolerance_C` with `tolerance_C=5.0` (degrees) as the
  default — a coarse pass/fail gate over the WORST cell in the whole field,
  not a value read at machine precision anywhere. Confirmed no other
  consumer reads `project_mfem_to_fdm`'s output at finer granularity
  (grepped: `mfem_gate.py` is the only caller, and it only ever calls
  `compare_fields` on the result).
- **Usage volume, verified by grep, not assumed**: `mfem_gate.py` (a
  fail-closed `Gate`, `GateStage.ROUTING`, called once per board
  evaluation) and its own test file are the only callers.
  `tests/validation/test_mfem_compare.py`'s one `project_mfem_to_fdm` test
  (`test_project_mfem_to_fdm_reshape`) uses the flat-reshape fallback
  branch (`node_coords=None`) — **it never exercises the `griddata` branch
  at all**. This is confirmed, not merely repeated from the re-triage: read
  the test file directly, and it is the only test in the repo that calls
  `project_mfem_to_fdm`.

**Conclusion: the premise holds** — genuinely portable, no exactness
blocker, and the "essentially zero existing coverage" claim is accurate
(one test, and it takes the non-`griddata` code path). Per the task brief,
coverage of the actual code path was added as part of this port (Sec 3).

## 2. What was implemented

`packages/temper-geometry/src/nearest_neighbor.rs` (new module):

- `nearest_neighbor_indices(src: &[[f64;2]], query: &[[f64;2]]) -> Vec<u32>`
  — for each query point, the index of the nearest `src` point. Built on
  `RTree::bulk_load` + `nearest_neighbor` per query point (reuses
  `radius_pairs.rs`'s `IndexedPoint`). Empty `src` yields `u32::MAX` per
  query point rather than panicking (documented sentinel; the sole call
  site guards `len(src) > 0` before calling, mirroring
  `radius_pairs`/`query_ball_point`'s existing "define the degenerate case"
  convention in this crate).
- `nearest_neighbor_transform` — the `#[cfg(feature = "python")]` pyo3
  boundary, bytes-in/bytes-out (`(x,y)` f64 pairs in, `i64` indices out),
  matching `radius_pairs_transform`'s and `RadiusIndex`'s existing
  conventions in this crate (index dtype `i64` to match
  `cKDTree`'s own `np.intp`).
- Value interpolation (`temps[nearest_idx]`) stays Python-side — this
  module returns indices only, matching the crate's established "geometry
  kernel returns indices, caller owns domain values" pattern.
- 9 `#[cfg(test)]` unit tests: empty src/query, single-source-always-wins,
  query-coincident-with-source, brute-force cross-check on a regular grid,
  brute-force cross-check on 8 random dense/sparse trials, coincident-
  source-cluster optimality (distance-correctness, not index-identity, on
  genuine ties), an explicit equidistant-tie determinism test, and a
  general repeated-call determinism test.

Registered in `lib.rs`/`bridge.rs` following the exact pattern
`radius_pairs_transform` established (module declaration, `pub use`,
import in `bridge.rs`, `wrap_pyfunction!` registration).

`packages/temper-placer/src/temper_placer/validation/mfem_compare.py`:
`project_mfem_to_fdm` no longer imports `scipy.interpolate`. The value-gather
step is factored into `_nearest_neighbor_lookup(src_pts, values, query_pts)`,
which calls `temper_geometry.nearest_neighbor_transform` for the spatial
query and does `values[idx]` in Python for the gather — kept as a standalone
function specifically so the differential suite (Sec 3) can drive it
directly against curated point sets, including the tie case, without
constructing a full `MFEMResult`/`ThermalFDMConfig` pair each time.

**Build verification** (from `packages/temper-geometry/`, all four required
per the migration contract):

```
cargo check  --offline --no-default-features                          # OK
cargo test   --offline --no-default-features nearest_neighbor          # 9/9 OK
cargo test   --offline --no-default-features                           # 523/523 OK (full suite, no regressions)
cargo clippy --offline --no-default-features --lib -- -D warnings      # clean
cargo clippy --offline --features python --lib -- -D warnings          # clean
cargo build  --offline --target wasm32-unknown-unknown --no-default-features   # OK
```

## 3. Differential, including the tie case

New file:
`packages/temper-placer/tests/validation/test_mfem_compare_nearest_neighbor_rust_differential.py`
(14 tests), R19-pinned oracle: an inlined `_scipy_nearest_lookup`
(wraps `scipy.interpolate.griddata(..., method="nearest", rescale=False)`
directly) and `_scipy_project_mfem_to_fdm` (the full pre-migration
function, verbatim grid-construction logic + the scipy interpolation call).
`mfem_compare.py` itself no longer imports scipy; it stays available here,
unused in production, as the pinned oracle.

- **Value agreement on well-separated point sets** (single source point,
  8x8 regular grid of sources queried off-grid, 4 seeds of 50-source/
  200-query random clouds, coincident query/source point): `np.testing
  .assert_array_equal` / exact list equality against the scipy oracle on
  every case — no ties occur at these scales with continuous random
  coordinates, so index-level (not just value-level) agreement is the
  effective bar and it holds.
- **The equidistant-tie case, explicit, as required**: `src = [(0,0),
  (0,10)]`, `values = [50.0, 50.3]`, `query = [(0,5)]` — both points are
  EXACTLY distance 5.0 from the query point (float64-exact, no rounding
  involved). Measured directly (not just asserted): **both the Rust and
  scipy backends picked the same candidate (value 50.0) on this
  construction** — a coincidence of this particular geometry, not a
  guaranteed property (see module doc's tie-breaking discussion: both
  backends' picks are real but undocumented artifacts of internal tree
  traversal order). The test therefore does not assert index/value
  identity between backends as a hard requirement — it asserts the
  property that actually matters: each backend's pick is one of the two
  genuinely-tied candidates, and `abs(rust_val - scipy_val) <= 0.3`
  (the actual value spread between the tied candidates), i.e. **far below
  the 5.0 degC default `tolerance_C`** regardless of which one either side
  picks. A second, denser test (`test_multiple_simultaneous_ties`)
  constructs a 4-way tie (axis-aligned points at a common radius, exactly
  representable in float64) with the same property verified. A third test
  confirms the tie-break itself is deterministic (same input -> same pick,
  every repeated call) even though it need not match scipy's pick.
- **End-to-end `project_mfem_to_fdm` agreement**: 3 cases (small grid,
  offset origin, sparse-mesh-onto-fine-grid — the shape the real
  MFEM-vs-FDM comparison actually has: few source nodes, many query
  cells) against the full pre-migration oracle function (not just the
  value-gather helper), plus a determinism-across-repeated-calls test.

All 14 new tests pass, plus the 5 pre-existing `test_mfem_compare.py` tests
(the flat-reshape-fallback path, unaffected by this change) still pass:

```
tests/validation/test_mfem_compare.py .....
tests/validation/test_mfem_compare_nearest_neighbor_rust_differential.py ..............
23 passed, 1 skipped (test_mfem_gate.py, unrelated MFEM-binary-unavailable skip)
```

**Tolerance justification**: exact equality (not a numerical tolerance) for
every non-tie case — this is an index-selection primitive over float64
coordinates with no accumulated arithmetic, so there is no rounding budget
to argue for. For the tie case specifically, the "tolerance" that actually
governs is the production consumer's own `tolerance_C=5.0` degC gate — the
test asserts the measured cross-backend value discrepancy (<= 0.3 degC in
the constructed case, and in general bounded by the value spread across
whichever points are genuinely tied) is far under that bar, which is the
actual acceptance criterion the migration brief specified ("say how each
side resolves it and why that's acceptable given the 5 degC tolerance").

## 4. Performance — measured, not just predicted

**Prediction from call shape, before measuring**: `project_mfem_to_fdm`
builds an R*-tree once and queries it once per call (a board evaluation),
never reusing a standing index across many calls — the same one-shot
"build, query once, discard" shape as `radius_pairs_transform`
(1.8-2.0x slower than scipy) and `connected_components_8_transform`
(1.0-2.6x slower), NOT the persistent-structure shape that made
`RadiusIndex` 3.4-20x faster. Expected: parity-to-slower, not a speedup.

**Measured** (`tools/measurements/mfem_nearest_neighbor_rust_spike.py`,
best-of-5, synthetic corpora at production-representative scale —
`n_src` mesh-node counts and grid sizes drawn from this repo's own
defaults: `mfem_gate.py`'s `height_cells=min(50, board.height)` /
`width_cells=min(50, board.width)`, and `thermal_fdm.py`'s module-level
`ThermalFDMConfig` default `height_cells=100, width_cells=200`; no real
MFEM run is available in this environment to source a production mesh
size from, consistent with the re-triage's own "likely unavailable in most
CI/dev environments" framing):

| Case | n_src | n_query | scipy | rust | rust/scipy |
|---|---:|---:|---:|---:|---:|
| grid 50x50 (mfem_gate min-cap) | 500 | 2,500 | 1.1-1.7ms | 1.0-1.4ms | **0.84-0.98x** |
| grid 50x50 (mfem_gate min-cap) | 2,000 | 2,500 | 1.5-2.3ms | 1.5-1.6ms | **0.70-0.98x** |
| grid 100x200 (thermal_fdm default) | 2,000 | 20,000 | 9.5ms | 10.3-10.7ms | **1.08-1.13x** |
| grid 100x200 (thermal_fdm default) | 5,000 | 20,000 | 10.6-11.3ms | 12.6-13.4ms | **1.12-1.27x** |

(Two independent runs shown as ranges; `values_agree=True` on every case —
no accidental ties at these random-cloud scales, so this table is also a
second correctness confirmation independent of the pytest suite.)

**Result: much closer to parity than the other one-shot migrations, not a
regression band.** At the smaller, gate-representative grid size
(`mfem_gate.py`'s own 50x50 cap, the config the actual production call
site uses), Rust is at or slightly under scipy's wall time. At the larger
module-default grid (rarely what the actual gate call site configures —
`mfem_gate.py` always caps at 50x50, not the 100x200 default), Rust is
1.08-1.27x slower — mild, and still well inside the precedent band
(1.0-2.6x) this task's other migrations established as an acceptable R2
exception, not an outlier.

**Why no R2 exception is even really needed here, stated plainly:**
absolute wall time is single-digit milliseconds either way, this call
happens once per board evaluation (not a search loop), and the entire
gate this feeds is itself skipped (`UNMEASURED`) whenever the external MFEM
tool isn't installed — which is the common case per the re-triage's own
framing. A ~1-3ms difference, once per gate run, is not a performance
story either direction. Recorded as a formal R2 A/B pass (measured, not
assumed) rather than an exception request, since the regression (where one
exists at all) is materially smaller than the other precedents that needed
one.

## 5. Migrated, not held

Both halves of the migration contract are satisfied: exact index/value
parity on every non-tie case (Sec 3), a documented and measured-acceptable
resolution for the tie case (Sec 3), and a performance result that does not
need to lean on precedent to justify (Sec 4). `scipy.interpolate` no longer
appears in `mfem_compare.py`.

## 6. Test coverage added (per the migration brief's explicit ask)

Before this task: **zero** coverage of the `griddata`/nearest-neighbor code
path (one existing test, `test_project_mfem_to_fdm_reshape`, exercises only
the flat-reshape fallback). After: **14 new tests** covering value
agreement (5 tests), the tie case explicitly (3 tests), and end-to-end
`project_mfem_to_fdm` agreement including a sparse-mesh/fine-grid
production-representative shape (4 tests) — see Sec 3 for the full
breakdown.

## 7. Sources

- `docs/evidence/2026-08-07-scipy-keeps-re-triage.md` Sec 4 — the re-triage
  this migration executes.
- `packages/temper-geometry/src/nearest_neighbor.rs` — implementation,
  contract determination, tie-breaking discussion, unit tests.
- `packages/temper-placer/src/temper_placer/validation/mfem_compare.py` —
  `project_mfem_to_fdm`/`_nearest_neighbor_lookup`.
- `packages/temper-placer/tests/validation/test_mfem_compare_nearest_neighbor_rust_differential.py`
  — the 14-case differential suite.
- `tools/measurements/mfem_nearest_neighbor_rust_spike.py` /
  `mfem_nearest_neighbor_rust_spike_results.json` — the performance
  measurement this doc's numbers come from.
- `docs/evidence/2026-08-07-radius-pairs-rust-migration.md`,
  `docs/evidence/2026-08-07-persistent-radius-index-rust-migration.md` —
  the crate-choice and `IndexedPoint`-reuse precedents this migration
  follows.
