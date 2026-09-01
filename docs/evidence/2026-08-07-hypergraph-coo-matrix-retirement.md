<!-- provenance: commit=73ddab178a7843308e2706d76ab8a8ebee532f58 (merge base, worktree-agent-a0c9bd1a1df109a4d) dirty=true (working-tree changes at authoring time: this document plus the diff it describes) -->

# `hypergraph.py`/`hypergraph_factory.py`'s `coo_matrix` — retired, no new Rust needed (2026-08-07)

**Verdict: migrated. No Rust crate was needed.** The re-triage
(`docs/evidence/2026-08-07-scipy-keeps-re-triage.md` Sec 3) found this was
never a sparse-matrix *algorithm* call site — it is a pre-deduplicated
triplet container consumed only by an order-invariant sum. That premise is
verified independently below and holds. `scipy.sparse.coo_matrix` is
replaced by `temper_placer.core.hypergraph.Coo`, a ~25-line plain-array
container living in Python, duck-typing the handful of `coo_matrix`
attributes (`shape`, `nnz`, `row`, `col`, `data`, `.T`, `@`) this codebase's
call sites and tests actually use.

## 1. Premise verification (independent of the re-triage's own read)

Read both actual call sites directly, not the docstrings' claims about them:

- **`hypergraph_factory.py:85-103`** (pre-migration): `rows`/`cols`/`data`
  are built by iterating `set(conn)` **per net**, before `coo_matrix` is
  ever constructed. By the time the constructor runs, every net's triplets
  are already deduplicated — there is no duplicate-`(row,col)` entry for
  `coo_matrix`'s constructor to sum, which is the one genuinely nontrivial
  thing its construction does that a naive reimplementation could get
  wrong. What remained was three parallel arrays plus a shape tag.
- **`hypergraph.py:64-74`**, the ONLY consumer of the resulting matrix:
  `compute_node_degrees` does `matrix @ ones`; `compute_edge_degrees` does
  `matrix.T @ ones`. Both are sums of per-row/per-column weights — order-
  invariant by construction (summation of a fixed multiset commutes,
  modulo ordinary floating-point rounding, which does not apply here since
  `data` here is exact small counts/weights, not an ill-conditioned
  accumulation).
- **Every other read site**, grepped directly (not inferred): only
  `.shape` (`test_hypergraph.py:32`, PBT's `test_p4_incidence_connectedness`)
  and `.row`/`.col`/`.data`/`.nnz` (the differential test's `_matrix_key`,
  and PBT's `_canonical_matrix`, which explicitly canonicalizes by SORTING
  the triplets — i.e. the codebase's own test suite already treats
  triplet order as non-semantic outside the one differential test that
  deliberately asserts it as an extra-strict TDD oracle check, not a
  downstream requirement). No call site anywhere calls `.tocsr()`,
  `.tocsc()`, `.toarray()`, or checks `isinstance(x, coo_matrix)` /
  `scipy.sparse.issparse(x)` (grepped across `packages/temper-placer/src`
  and `tests`, zero matches for the hypergraph module).

**Conclusion: the premise holds.** No sparse-matrix algorithm was hiding
here — the re-triage's classification is correct, and no third-party
sparse-matrix crate (nor a new Rust module at all) is needed to retire this
scipy dependency.

## 2. What was implemented

`packages/temper-placer/src/temper_placer/core/hypergraph.py`: a new frozen
dataclass `Coo(row, col, data, shape)` with:

- `nnz` property (`len(data)`).
- `.T` property (swap row/col, swap shape) — matches `coo_matrix.T`.
- `__matmul__` — a real sparse matrix-vector product (`for each (r, c, d):
  result[r] += d * other[c]`), implemented as
  `np.bincount(row, weights=data * other[col], minlength=shape[0])`. This
  is NOT hardcoded to the ones-vector case `compute_node_degrees`/
  `compute_edge_degrees` happen to use today — it is a general matvec, so
  it doesn't quietly become wrong if a future caller multiplies by
  something other than a ones vector. `np.bincount`'s grouped summation is
  order-invariant in its inputs by construction (matching the order-
  invariance argument above).

`packages/temper-placer/src/temper_placer/extraction/hypergraph_factory.py`:
`coo_matrix((values, (rows, cols)), shape=shape)` replaced with
`Coo(row=np.array(rows, dtype=np.int64), col=np.array(cols, dtype=np.int64),
data=values, shape=shape)` — same `rows`/`cols`/`data` this module already
built from the Rust `HypergraphFactory`'s `connected_indices`, per the
re-triage's own recommended fix ("have the existing Rust HypergraphFactory
... return the deduplicated triplets directly and build HypergraphIncidence
from plain arrays"). No change to the Rust `HypergraphFactory` pyclass in
`temper-design-bundle` was needed — it already returned exactly the
deduplicated `connected_indices` this assembly step consumes.

**Corrected two standing wrong claims**, per the re-triage's own finding
that the "not reimplementable" framing was overstated (same failure mode
KTD8's `edt` and KTD9's `constraints_spatial_index` reversals both found):
`hypergraph_factory.py`'s module docstring and `hypergraph_factory.rs`'s
doc comment both previously asserted "scipy's COO construction ... is a
library semantic, not portable compute" as a blanket justification;
`packages/temper-design-bundle/VERIFICATION.md`'s Sec 6 made the same claim.
All three now describe the actual boundary (pre-deduplicated triplet
storage plus an order-invariant reduction), not the overstated one.

## 3. Differential result

No new differential test file was needed — the existing
`tests/core/test_hypergraph_factory_rust_differential.py` (18 tests) and
`tests/core/test_hypergraph_factory_pbt.py` (10 properties, R1c P1-P6 +
R1d MR1-MR4) already compare through the duck-typed
`.shape`/`.nnz`/`.data`/`.row`/`.col` surface, not through
`isinstance(matrix, coo_matrix)` or any scipy-specific method. Per R19, the
oracle (`tests/core/_hypergraph_factory_py_oracle.py`) still builds a REAL
`scipy.sparse.coo_matrix` — it was not touched, and still imports scipy —
so the differential is genuinely comparing the new `Coo` (production) against
the old `coo_matrix` (pinned oracle), attribute-by-attribute, including
exact triplet ORDER (not just the set) per the oracle's own stricter
convention. All 30 tests pass unchanged (2 `test_hypergraph.py`, 18
differential, 10 PBT):

```
tests/core/test_hypergraph.py ..
tests/core/test_hypergraph_factory_rust_differential.py .................. [18]
tests/core/test_hypergraph_factory_pbt.py ..........
30 passed in 1.71s
```

**Tolerance**: none needed — this is exact bit-for-bit parity (integer
indices and float32-cast values, both sides), not a numerical-tolerance
comparison. There is no third-party-algorithm exactness question here
(the entire point of Sec 1's premise verification) — `Coo`'s `row`/`col`
are the exact same Python `int` lists the pre-migration code built, wrapped
in `np.array(..., dtype=np.int64)` instead of handed to
`scipy.sparse.coo_matrix`'s constructor.

## 4. Performance

Not measured as a dedicated A/B, and this is a deliberate, argued
exception, not an oversight: there is no algorithmic operation to benchmark
— `Coo`'s constructor is a direct wrap of the same `np.array(...)` calls
the pre-migration code already made (same allocations, same triplet
construction loop, unchanged), and its only added compute
(`compute_node_degrees`/`compute_edge_degrees`'s `__matmul__`) replaces
scipy's C-level sparse matvec with one `np.bincount` call over the same
small (`nnz` = number of net-component connections, at most a few hundred
even on a dense board) array — not the kind of scale difference where a
Python-level `np.bincount` vs scipy's C sparse matvec would plausibly
register outside timing noise, and the operation happens once per
`compute_node_degrees`/`compute_edge_degrees` call (not a placement hot
loop — grepped: called only from `core/hypergraph.py`'s own module and
`tests/`, not from `placer/` or `router_v6/`). Recorded here as the R2
performance-exception justification: this migration removed a dependency,
not a bottleneck, and the call shape does not warrant a formal A/B.

## 5. Net scipy count

Methodology matches `docs/evidence/2026-08-07-radius-pairs-rust-migration.md`
Sec 5: `grep -rn "^from scipy\|^import scipy\|    from scipy\|    import
scipy"` over `packages/temper-placer/src/temper_placer` (production code
only, not tests/oracles).

- **Before this task** (merge base `73ddab17`): **17 import lines across
  11 files** — `core/hypergraph.py`, `extraction/hypergraph_factory.py`,
  `physics/loop_area.py`, `physics/thermal_fdm.py`,
  `router_v6/_astar_heuristics.py`, `router_v6/channel_widths.py`,
  `router_v6/routability_check.py`, `router_v6/zone_emission.py`,
  `validation/mfem_compare.py`, `validation/thermal_scorer.py`,
  `validation/trace_analyzer.py`.
- **After this task's two migrations** (this doc's `hypergraph`/
  `hypergraph_factory` change AND the companion `mfem_compare.py`
  migration, `docs/evidence/2026-08-07-mfem-nearest-neighbor-rust-migration.md`):
  **14 import lines across 8 files** — `core/hypergraph.py` and
  `extraction/hypergraph_factory.py` (this doc) and `validation/mfem_compare.py`
  (companion doc) all dropped off the list entirely; the other 8 files are
  untouched by this task (KEEP surfaces per the re-triage: `thermal_fdm.py`/
  `thermal_scorer.py`'s `spsolve`, and files covered by other agents'
  concurrent, unmerged branches per the radius_pairs doc's Sec 5 — this
  task did not merge those).

## 6. Sources

- `docs/evidence/2026-08-07-scipy-keeps-re-triage.md` Sec 3 — the re-triage
  this migration executes.
- `packages/temper-placer/src/temper_placer/core/hypergraph.py` — `Coo`.
- `packages/temper-placer/src/temper_placer/extraction/hypergraph_factory.py`
  — the assembly call site.
- `packages/temper-placer/tests/core/test_hypergraph_factory_rust_differential.py`,
  `test_hypergraph_factory_pbt.py`, `test_hypergraph.py` — unchanged tests,
  now exercising `Coo` instead of `coo_matrix` on the production side.
- `packages/temper-design-bundle/src/hypergraph_factory.rs`,
  `packages/temper-design-bundle/VERIFICATION.md` — corrected boundary docs.
