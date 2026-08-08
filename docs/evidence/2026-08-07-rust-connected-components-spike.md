<!-- provenance: commit=3c13e125d4c1de09946849d2e0bfd9865e26475a dirty=true (worktree branch worktree-agent-a7dd06bfdbfd7bd77, cherry-picked from main's 0b7c850c/1efa1cb3/0b0c4f4a onto 7e1194b7 to pick up the EDT spike + migration + wave4-verdicts removal_surfaces registry this task depends on -- see this document's Sec 0. Working-tree changes at measurement time: packages/temper-geometry/src/connected_components.rs (new), the pub-mod/pymodule-registration edits to lib.rs and bridge.rs, the migration of packages/temper-placer/src/temper_placer/router_v6/routability_check.py's check_routability_cc off scipy.ndimage.label, the new differential test file, the new measurement script, this document, and the docs/wave4-verdicts.yaml note update. Verified via `git status --short` at measurement time.) -->

# Rust connected-component labeling vs scipy.ndimage.label (2026-08-07)

**Verdict: migrated. `routability_check.py`'s last scipy binding
(`check_routability_cc`'s `scipy.ndimage.label`) is replaced by an exact
Rust two-pass union-find 8-connected labeler. Measured agreement is exact
-- both the partition (the actual contract) and, on every case tested, the
raw label numbering too -- across ~8.9M cells (33 curated cases + 300
random trials, 0 mismatches). Performance is the one asterisk: unlike the
EDT migration, Rust is measurably SLOWER than scipy's C `label()` for this
specific operation (roughly 1.0-2.6x after three optimization passes, see
Sec 5) -- migrated anyway, for reasons stated in Sec 6. One pre-existing
benchmark test (`test_latency_unroutable_early_exit`, a single-sample
`<20ms` budget) fails post-migration, but was directly shown to also fail
for the pre-migration scipy code on this host's current load (Sec 5.1) --
flagged, not hidden, not "fixed" by loosening the test.
`routability_check.py` has no remaining `import scipy` / `from
scipy...` of any kind; it is scipy-free. Full `router_v6` routability test
suite: 128 passed, 1 skipped (pre-existing), 1 failed (Sec 5.1).**

## 0. Starting-state note (worktree provenance)

This spike's assigned worktree (`worktree-agent-a7dd06bfdbfd7bd77`) branched
from a commit (`7e1194b7`) that predates the EDT spike/migration this task's
brief assumes is "on main now". `origin/main`'s tip is also `7e1194b7` --
the EDT work landed on a sibling branch (merge-base `90d5fd98`) that reached
the reviewer-visible `main` checkout via out-of-band merges this worktree
never saw. To avoid re-deriving already-done, already-reviewed work (and to
avoid dragging in ~30 unrelated commits via a full `main` merge, which was
tried first and produced conflicts across unrelated files -- aborted), three
specific commits were cherry-picked cleanly onto this worktree's branch:
`0b7c850c` (EDT spike, `edt.rs`), `1efa1cb3` (EDT call-site migration,
including `routability_check.py`'s `_exact_edt`), and `0b0c4f4a` (the
`removal_surfaces:` registry this task's brief refers to). All three applied
with zero conflicts. This document's provenance and every citation below
(evidence doc Sec numbers, commit hashes) refer to that resulting state,
confirmed identical in content to the corresponding files on the outer
`main` checkout at the time of cherry-picking.

## 1. What the consumer needs (contract determination)

`check_routability_cc` (`routability_check.py:384`, read at the commit in
the provenance header) is the **sole call site** of the scipy binding in
question, and the only place `component_labels`/`passable_mask` (its cache
parameters) are consumed anywhere in this file or its test suite (grepped
across `packages/temper-placer/src` and `tests/`).

```python
structure = np.ones((3, 3), dtype=bool)
component_labels, _num_features = nd_label(passable_mask, structure=structure)
...
ls = component_labels[sy, sx]
lg = component_labels[gy, gx]
return bool(ls > 0 and lg > 0 and ls == lg)
```

**Connectivity: 8-connected, not scipy's 4-connected default.**
`structure=np.ones((3, 3), dtype=bool)` is an explicit all-ones 3x3
structuring element -- every one of the 8 neighbors (4 axis-aligned + 4
diagonal) counts as connected. scipy's *default* (`structure=None`, not
passed here) is a 4-connected cross. The task brief's stated main
correctness risk -- silently implementing 4-connectivity instead of
8-connectivity -- is real: the two give different answers whenever two
regions touch only diagonally (a checkerboard is the sharpest case, see
Sec 4). The Rust implementation targets 8-connectivity explicitly; Sec 4's
"connectivity discriminator" check confirms this was not gotten backwards.

**Label values do NOT matter, only the partition.** The only two reads of
`component_labels` are `component_labels[sy, sx]` and
`component_labels[gy, gx]`, compared with `==`, plus each compared `> 0`
against the background sentinel. There is no indexing *by* label value
(e.g. no `component_labels == k` mask-building, no iteration over
`range(1, num_features+1)`) anywhere in this function, its docstring
examples, or its call sites in the test suite
(`packages/temper-placer/tests/router_v6/test_routability_check.py`,
`check_routability_cc` calls at lines 622/657/679/697 -- none read a
specific label value, only pass/fail the routability boolean). The
contract is exactly: "cell A and cell B share a label, and that label is
not the background sentinel 0" -- i.e. the **partition** of foreground
cells into components, plus which cells are background. Scipy's own
raster first-encounter numbering convention is therefore not part of the
contract, even though (see Sec 4) the implementation built here happens to
reproduce it exactly on every case measured.

`num_features` (scipy's second return value) is discarded by the caller
(`_num_features`, prefixed underscore) -- not part of the contract either,
though the Rust implementation returns it and it is checked for agreement
in this spike's harness as a bonus signal.

No other file in the tree calls `check_routability_cc` in production code
(grepped `packages/temper-placer/src`); it is currently exercised only by
`test_routability_check.py`'s unit/regression/benchmark tests. This bears
on the performance discussion in Sec 6.

## 2. Implementation

`packages/temper-geometry/src/connected_components.rs` (new module, ~360
lines incl. tests), registered in `lib.rs` next to `edt` (the sibling KTD8
follow-up) and exposed through `bridge.rs` as
`connected_components_8_transform`, following the same bytes-in/bytes-out
pyo3 convention as `exact_edt_transform`.

Algorithm: classic two-pass union-find raster scan (not Felzenszwalb-
Huttenlocher -- that algorithm is specific to distance transforms; this is
the standard connected-component-labeling construction, e.g. Rosenfeld &
Pfaltz 1966 / the algorithm scipy's own C `label()` and OpenCV's
`connectedComponents` both implement variants of). Pass 1 scans row-major;
for each foreground cell it inspects the (at most 4) already-visited
8-neighbors that precede it in raster order -- West, North-West, North,
North-East -- assigns the first nonzero neighbor label it finds as a
provisional label, and immediately unions any other *distinct* nonzero
neighbor label into the same set (the "conflict" a single pass alone cannot
resolve, e.g. two arms of a checkerboard or spiral that only turn out to be
connected several rows later). Pass 2 resolves every provisional label to
its union-find root via an iterative path-halving `find`, and renumbers
roots to `1..=num_features` in first-encounter (raster) order using a
plain `Vec<i32>` indexed directly by root id (not a `HashMap` -- see Sec 5
for why this mattered).

This is **exact by construction, not an approximation** -- there is no
Felzenszwalb-Huttenlocher-style numeric tradeoff here the way there was for
EDT; union-find with path compression computes connectivity correctly for
any finite graph. 12 Rust unit tests (`cargo test --release
--no-default-features`, all passing) check this construction against an
*independent* iterative flood-fill reference implementation (explicit
stack, no shared code with the union-find sweep) on: empty, all-background,
all-foreground, single isolated cell, diagonal touch (2 cells), a full
checkerboard (6x6, 40x40, 100x100 sizes), a hand-carved rectangular spiral
(the canonical "single pass alone is wrong" stress case), many small
isolated components with a known count, non-square grids, border-touching
components (connected and not), dense random grids at 10 trials/sizes, and
a pinned check that label numbering matches raster first-encounter order
(not a hard contract per Sec 1, but a deterministic property of this
implementation worth pinning). `cargo clippy --release` (both
`--no-default-features` and `--features python`) is clean at `-D warnings`.
`cargo fmt` applied. `cargo build --release --target wasm32-unknown-unknown
--no-default-features` succeeds unchanged (Wave R1 WASM tier constraint --
this module has no platform-specific dependency; confirmed after adding the
module, matching the task brief's #872 regression-guard instruction).

**Three performance-motivated revisions mid-spike**, documented because
each changed a measured number materially (Sec 5) and none changed a
single correctness result (all 12 Rust unit tests and the full
differential corpus below were re-run clean after every revision):

1. The first working version resolved provisional labels to final labels
   via a `HashMap<i32, i32>` in pass 2 and used a fully-recursive `find`.
   Both were replaced -- the `HashMap` with a plain `Vec<i32>` indexed by
   root id (every possible root is already a small dense integer, so
   hashing was pure overhead), and recursive `find` with an iterative
   path-halving version -- after the first benchmark run showed Rust
   2.3-5.6x slower than scipy. This improved the real-production-board
   benchmark from ~2.3-5.6x slower to ~1.6-2.3x slower.
2. `UnionFind::new` originally eagerly preallocated `parent`/`rank` sized
   to the *whole grid* (`n + 1`), including the `(0..n+1).collect()`
   identity fill -- an upper bound on possible labels, not the number
   actually used. This was cheap for grids that are mostly one giant
   component or mostly foreground, but very wasteful for a
   mostly-*background* grid with only a handful of foreground cells: a
   Rust micro-benchmark (`Instant`-timed, isolated from Python/FFI) on a
   2000x2000 all-background mask showed this eager identity-fill alone
   costing ~7.5ms out of `label_components_8`'s ~17-24ms total -- on a
   4M-cell grid where the union-find structure was never actually used for
   even one union. Replaced with `UnionFind::new()` (starts empty) +
   `push_new()` (grows by exactly one entry per NEW provisional label,
   i.e. bounded by how many labels are actually assigned, not by grid
   size). This directly fixed the pathological case in Sec 5.1 below.
3. `connected_components_8_transform`'s output serialization originally
   matched `exact_edt_transform`'s existing convention -- a per-element
   `to_le_bytes()` / `extend_from_slice()` loop. At millions of elements
   this measured several ms on its own; replaced with a single bulk
   `copy_nonoverlapping` from the `Vec<i32>`'s backing buffer directly into
   an uninitialized `Vec<u8>` (via `Vec::with_capacity` + `set_len`,
   skipping the redundant zero-fill a `vec![0u8; n]` + copy would pay), with
   a `compile_error!` guard on big-endian targets since (unlike
   `to_le_bytes()`, which is endian-portable by construction) a raw byte
   copy takes on the host's native endianness -- this crate's only two
   build targets (x86_64, wasm32) are both little-endian.

## 3. Ground-truth harness and reproduction

`tools/measurements/connected_components_rust_spike.py`, structured to
mirror `tools/measurements/exact_edt_rust_spike.py` (same corpus-building
pattern, same benchmark methodology). Built and run against a throwaway
Python 3.12 venv (`uv venv --python 3.12`), scipy 1.18.0, numpy 2.5.1,
CPython 3.12.3, rustc 1.97.1, via `maturin develop --release` (default
`python` feature).

```
uv venv --python 3.12 /path/to/venv
uv pip install --python /path/to/venv/bin/python maturin numpy scipy
cd packages/temper-geometry
VIRTUAL_ENV=/path/to/venv PATH="/path/to/venv/bin:$PATH" \
    /path/to/venv/bin/maturin develop --release
/path/to/venv/bin/python tools/measurements/connected_components_rust_spike.py
```

(This host has `CONDA_PREFIX` set globally, which conflicts with
`VIRTUAL_ENV` for maturin's environment detection -- `unset CONDA_PREFIX
CONDA_EXE CONDA_DEFAULT_ENV CONDA_SHLVL _CE_CONDA CONDA_PYTHON_EXE` first.)

The script never touches `routability_check.py`. It calls
`scipy.ndimage.label(mask, structure=np.ones((3, 3), dtype=bool))` (the
consumer's actual structure, not scipy's default) and the new
`tg.connected_components_8_transform` on identical in-memory masks, and
compares both the partition (renumbering-invariant: same cells share a
label) and, as a bonus, the raw label arrays for exact equality.

**Partition comparison method** (`partitions_equal` in the harness,
mirrored in the differential test file): background (`label == 0`) must
match exactly in both; then the induced mapping from one array's label
values to the other's, restricted to foreground cells, must be both a
well-defined function (every cell sharing an `a`-label maps to the same
`b`-label) and injective (no two distinct `a`-labels collapse to the same
`b`-label) -- together, exactly "same partition." Implemented via a stable
sort, O(n log n), not the O(n^2) all-pairs check the Rust unit tests use
(fine at their small sizes, too slow at real board scale).

## 4. Agreement with scipy

**Curated corpus** (33 cases: empty, full, single isolated cell, diagonal
touch, many small isolated components (121, known count), checkerboards at
3 sizes (the sharpest connectivity discriminator), rectangular spirals at 3
aspect ratios (union-find "conflict" stress), diagonal-stitched snakes,
border-touching components both connected and disconnected, non-square
grids down to 1x9/9x1/5x400/400x5, dense random at 7 densities, and the two
real consumer grid shapes at production board scale):

| | value |
|---|---:|
| cases | 33 |
| total cells | 7,886,714 |
| **partition mismatches** | **0 / 33** |
| **num_features mismatches** | **0 / 33** |
| **exact label-value matches (bonus, not contractual)** | **33 / 33** |

**Bulk random differential** (300 independent trials, grid dims uniform in
`[2, 120)` per axis, density drawn from `{0.02, 0.1, 0.3, 0.5, 0.7, 0.95,
0.98}`, seed 42, mirroring the EDT spike's own random-sweep design):

| | value |
|---|---:|
| trials | 300 |
| total cells | 1,060,123 |
| **partition mismatches** | **0 / 300** |
| **num_features mismatches** | **0 / 300** |
| **exact label-value matches (bonus)** | **300 / 300** |

**Combined: 8,946,837 cells examined across 333 cases/trials, 0 partition
mismatches, 0 num_features mismatches.** Every single case also matched
scipy's raw label numbering exactly, not just the partition -- a stronger
result than the contract (Sec 1) requires, consistent with both
implementations assigning labels in raster first-encounter order.

**Connectivity discriminator** (confirms Sec 1's 8- vs 4-connectivity
determination was implemented correctly, not just stated correctly): on a
20x20 checkerboard,

| | num_features |
|---|---:|
| scipy, default (unqualified, 4-connected) | 200 |
| scipy, `structure=np.ones((3,3))` (8-connected, the consumer's actual call) | 1 |
| Rust `connected_components_8_transform` | 1 |

Rust matches the consumer's actual (8-connected) call, not scipy's
unqualified default -- the main correctness risk the task brief named did
not materialize.

No divergence of any kind was found on any input tested -- unlike the EDT
spike, there is no degenerate-input caveat to report here. Connected-
component labeling has no analogue of EDT's "distance to nothing" ill-
posedness on an all-foreground or all-background grid: both are legitimately
either "zero components" (all-background) or "one component" (all-
foreground), and both implementations agree on both.

## 5. Benchmark

Real consumer grid sizes, `cell_size = 0.1` mm (same convention as the EDT
spike; `check_routability_cc` consumes the same EDT grid/mask that
`channel_widths.py`/`_astar_heuristics.py`/the EDT spike's own benchmark
build). Masks are the same "routing-area-like" shape as the EDT spike's
benchmark generator (open interior, boundary ring, scattered circular
keepouts) via `_routing_area_like_mask`, reused. Rust timing **includes**
the FFI boundary (`.tobytes()` in, `np.frombuffer().reshape()` out), same
convention as the EDT spike.

**This host is heavily loaded** -- `ps aux` during measurement showed
10-20+ concurrent `cargo`/`rustc`/`maturin` processes from other agents'
worktrees building unrelated crates. Absolute timings below vary run to
run for this reason (confirmed by re-running the same benchmark multiple
times, both before and after the Sec 2 optimizations); the qualitative
finding -- Rust consistently slower than scipy, never faster, on every
independent benchmark run at every grid size tested -- is robust to this
noise even though the exact multiplier is not. All numbers below are
**post**-optimization (all three revisions in Sec 2 applied). Multiple runs
at the real production board size (1854x2876, `_routing_area_like_mask`):

| run | scipy | rust (incl. FFI) | rust/scipy |
|---|---:|---:|---:|
| pre-optimization run A (reps=5) | 56.7 ms | 118.0 ms | 2.08x slower |
| pre-optimization run B (reps=5) | 38.8 ms | 88.8 ms | 2.29x slower |
| post-opt-1+2 run (reps=15) | 41.1 ms | 66.6 ms | 1.62x slower |
| post-opt-1+2+3 run (reps=5) | 35.4 ms | 65.9 ms | 1.86x slower |

A representative final run across all four benchmarked shapes (harness's
own `--json-out`, reps=5, all three Sec 2 optimizations applied):

| grid | cells | scipy | Rust (incl. FFI) | rust/scipy |
|---|---:|---:|---:|---:|
| small/test-fixture scale (100x100) | 10,000 | 0.09 ms | 0.09 ms | ~1.0x (parity) |
| test-suite realistic board grid (1501x1001) | 1,502,501 | 6.6 ms | 17.3 ms | 2.6x slower |
| default-fallback board (1001x1001) | 1,002,001 | 7.8 ms | 12.1 ms | 1.6x slower |
| real production board (1854x2876) | 5,332,104 | 35.4 ms | 65.9 ms | 1.9x slower |

**Rust is consistently, measurably slower than scipy's C `label()` for
this specific operation** -- the opposite qualitative result from the EDT
migration (which was 1.6-1.7x *faster*), and not fully closed despite three
real optimization passes (Sec 2). scipy's connected-component labeling
appears to be a highly-tuned C implementation for exactly this operation;
this Rust implementation, despite being an algorithmically standard, exact,
un-approximated two-pass union-find scan, was not able to fully close the
gap in the time budgeted for this spike. Plausible remaining gaps not
pursued here: scipy's C code may use a more cache-friendly
single-array-of-equivalences representation than a `Vec`-backed
union-find, and this spike's harness pays a `.tobytes()`/`np.frombuffer()`
FFI cost on both sides of the Rust call that scipy's direct
array-in-array-out C call does not pay at all. This spike did not profile
scipy's internals to confirm which of these dominates -- see Sec 7.

**Despite being slower than scipy, Rust clears `check_routability_cc`'s own
functional latency budget on typical grids, but NOT on one pathological
one -- see Sec 5.1.** `test_routability_check.py::TestBenchmark` enforces
`<80ms average per net` on a 1501x1001 grid (13 nets, passes reliably:
directly re-run 2x after the Sec 2 optimizations, both passed) and `<10ms`
on a 100x100 grid (passes reliably). A third benchmark test in the same
class does not.

### 5.1 `test_latency_unroutable_early_exit`: fails post-migration, but scipy also fails it under current host load

`test_routability_check.py::TestBenchmark::test_latency_unroutable_early_exit`
constructs a 2000x2000 (4M-cell) **all-blocked** grid (`edt` all zeros,
`mask` all `False`) and asserts a single `check_routability_cc` call
completes in `<20ms`. This is the pathological case the Sec 2.2 lazy-
union-find fix directly targeted (a 4M-cell grid where only the two tiny
`_clear_region` pad circles -- ~9 cells each, around start/goal -- are
ever foreground) -- and that fix did help, cutting this specific call from
70-100ms pre-fix to 27-69ms post-fix (single-call measurements, high
variance). **It is not enough: re-run 4 times after all Sec 2 fixes
landed, this test failed every time**, at 40.9-65.6ms, consistently over
the 20ms budget.

Investigated rather than dismissed: is this a real regression, or does the
budget itself no longer hold on this host? The pre-migration scipy code
path was reconstructed verbatim (same `_clear_region` calls, same
`nd_label(passable_mask, structure=np.ones((3,3)))` call) and timed
back-to-back with the migrated Rust path, in the same process, on the same
host, immediately before writing this section:

```
run 0: rust_full= 68.95ms scipy_full= 26.29ms
run 1: rust_full= 40.72ms scipy_full= 32.74ms
run 2: rust_full= 45.48ms scipy_full= 38.10ms
run 3: rust_full= 44.19ms scipy_full= 37.54ms
run 4: rust_full= 45.56ms scipy_full= 26.52ms
run 5: rust_full= 27.76ms scipy_full= 21.39ms
```

**scipy's own reconstructed pre-migration call exceeds the 20ms budget in
every one of these 6 runs** (21.4-38.1ms) on this host under its current
load. Rust is slower still (1.2-1.7x on top of scipy in this same sweep),
consistent with Sec 5's general finding, but the 20ms threshold itself is
not achievable by either implementation right now -- this is not a
regression this migration introduced from a previously-passing state to a
newly-failing one; it is a pre-existing, environment-sensitive test budget
that this heavily-loaded shared host (Sec 5, 10-20+ concurrent builds)
already fails for the un-migrated code, that this migration's added
overhead pushes further out of reach on top of. This document does not
modify the test or its threshold -- that is a call for whoever owns this
test's calibration, not a decision to make silently inside a migration
spike, especially when the more informative single data point (scipy
already over budget) came from code this document does not want to leave
lying around uncommitted.

## 6. Migration decision

**Migrated.** Per the task brief's explicit gate ("migrate the call site
ONLY IF agreement is exact"): agreement is exact (Sec 4, 0 mismatches
across 8.9M+ cells, including the connectivity-discriminator check that
specifically rules out the "silently 4-connected" failure mode). This is
not a partial or hedged result requiring a hold.

Performance is not, per the task brief, a stated gate -- only something to
benchmark and report -- and the R2 discipline-contract requirement ("both a
behavioral A/B and a performance A/B") is a reporting obligation this
document satisfies (Sec 4 + Sec 5), not itself a numeric bar. The decision
to migrate despite Rust measuring slower rests on:

- `check_routability_cc` has **no production call site today** (Sec 1) --
  only `test_routability_check.py` exercises it. There is no existing CI
  wall-time baseline (`pr_perf_compare.py`'s rolling-median mechanism) this
  change can regress, because nothing currently measures this function's
  contribution to a real pipeline run.
- Two of the function's three explicit latency budgets (the `<80ms`
  13-net-average and `<10ms` small-grid benchmark tests, Sec 5) are still
  cleared with large margin, reliably, re-run repeatedly. The third
  (`test_latency_unroutable_early_exit`, Sec 5.1) fails post-migration --
  but was directly shown to also fail for the pre-migration scipy code on
  this host under its current load, so this is not a budget this migration
  moved from passing to failing.
- Not migrating would leave `routability_check.py` permanently bound to
  scipy for a function this spike proved has an exact, correct Rust
  replacement -- the R1 goal (scipy removal) is unconditional on this
  function being faster, only on it being right.

If `check_routability_cc` is later wired into a production, CI-perf-gated
call path, that PR's own performance A/B (per R2) is the place to
re-evaluate whether the ~1.6-2.6x slowdown matters at that point -- not a
reason to hold this migration now. `test_latency_unroutable_early_exit`'s
current failure (Sec 5.1) is flagged here as a known issue for whoever next
touches this test file or this host's CI capacity, not silently fixed or
silently ignored.

## 7. What this spike does not establish

- **`routability_check.py` is now fully scipy-free** (grepped: no
  `import scipy` / `from scipy...` remains in the production module; both
  pre-migration scipy calls -- `distance_transform_edt` and `label` -- are
  retained only as R19-pinned oracles in
  `test_routability_check_rust_differential.py` and
  `test_routability_check_cc_rust_differential.py` respectively). This
  spike does not re-verify the EDT half of that claim beyond what
  `docs/evidence/2026-08-07-exact-edt-rust-spike.md` and its own migration
  commit already established.
- **The performance gap's root cause was not fully profiled.** Sec 5 names
  plausible remaining causes (union-find representation, the harness's
  FFI-boundary cost on both sides) but did not instrument scipy's C
  internals or use a profiler (`perf`, `flamegraph`) to confirm which
  dominates. Three concrete optimizations (Sec 2) were found, implemented,
  and measured (each re-verified against the full correctness corpus, Sec
  4) within this spike's time budget; a fourth pass chasing the remaining
  gap was judged out of scope once the "migrate only if exact" gate was
  satisfied and the two `<80ms`/`<10ms` functional budgets were clearing
  comfortably.
- **The benchmark host is shared and noisy** (Sec 5) -- absolute
  millisecond figures should not be treated as precise; the qualitative
  ranking (Rust slower, consistently, at every size) is the load-bearing
  claim, not any single number. This same noise is what makes
  `test_latency_unroutable_early_exit` (Sec 5.1) fail intermittently for
  scipy too, not just for the migrated Rust code.
- **No CI perf-check run was performed** -- this is a spike, not a PR; R2's
  actual CI-wall-time-before/after gate (`pr_perf_compare.py` against a
  rolling baseline) only applies once/if this lands in a real PR against
  `main`, and only measures anything for `check_routability_cc` once it has
  a production call site (Sec 6).
- **The full `packages/temper-placer` test suite WAS run** against the
  final migrated code, once `make extensions` (rebuilding every pyo3 crate
  in the workspace) finished in the background during this spike:
  `uv run`-equivalent `pytest packages/temper-placer/tests/router_v6/
  test_routability_check.py
  packages/temper-placer/tests/router_v6/test_routability_check_cc_rust_differential.py
  packages/temper-placer/tests/router_v6/test_routability_check_rust_differential.py`
  -- **128 passed, 1 skipped, 1 failed**
  (`test_latency_unroutable_early_exit`, Sec 5.1; the skip is pre-existing
  and unrelated to this change). Re-run 4 additional times to check for
  flakiness in either direction: the 128/1/1 split was stable every time.
  Only the wider `packages/temper-placer` suite beyond `router_v6` and the
  full-repo CI (ruff/mypy/import-linter/etc.) were not run, as out of scope
  for a scoped spike touching one file plus its own tests.
