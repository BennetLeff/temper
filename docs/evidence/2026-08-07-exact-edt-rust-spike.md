<!-- provenance: commit=90d5fd983f825d1895f416b8535dee6a169b8979 dirty=true (worktree branched from main at 90d5fd98; the only working-tree changes at measurement time are exactly this spike's own additions -- packages/temper-geometry/src/edt.rs (new), the two-line pub-mod/pymodule-registration edits to lib.rs and bridge.rs, this document, and tools/measurements/exact_edt_rust_spike.py. The three consumer files -- channel_widths.py, _astar_heuristics.py, routability_check.py -- and every other tracked file are untouched, verified via `git status --short` at measurement time.) -->

# KTD8 spike: exact Rust EDT (Felzenszwalb–Huttenlocher) vs scipy (2026-08-07)

**Verdict: KTD8 does NOT hold as a hard blocker. An exact, scipy-matching
Euclidean distance transform in pure Rust is straightforward, bit-exact
on every reachable input, and 1.6–1.7x faster than scipy including the
Python↔Rust FFI boundary crossing, at the actual production grid sizes.**
The scipy dependency for `distance_transform_edt` is resolvable by a normal
port — it belongs in the PORT stream, not held open as a blocker requiring
a design decision.

This spike answers only "is the algorithm the obstacle?" — per the task
brief the three consumer call sites (`channel_widths.py`,
`_astar_heuristics.py`, `routability_check.py`) are **untouched**. No
migration happened here.

## 0. Recap: what KTD8 previously rejected

`docs/evidence/2026-07-31-edt-crate-ktd8-spike-rejected.md` rejected the
third-party `edt` crate (v0.2.2): max diff 2.0–2.236 vs scipy, traced to the
crate hardcoding a grid-edge clamp that treats array boundaries as
distance-zero sources regardless of the actual mask. That document's own
"Consequence" section named the fallback explicitly: *"A Rust-native exact
EDT (Felzenszwalb–Huttenlocher or Saito) remains the recorded fallback for a
follow-up."* This spike is that follow-up. The rejection was of one
approximate crate, not of the algorithm class.

## 1. Implementation

`packages/temper-geometry/src/edt.rs` (new module, ~360 lines incl. tests),
registered in `lib.rs` alongside `channel_widths` (the crate's existing EDT
*consumer* — bilinear lookup over a grid computed elsewhere) and exposed
through `bridge.rs` as `exact_edt_transform`, following the same bytes-in/
bytes-out pyo3 convention as `channel_widths::edt_width_lookup_batch`.

Algorithm: Felzenszwalb & Huttenlocher, "Distance Transforms of Sampled
Functions" — the separable, O(n) per axis, lower-envelope-of-parabolas
construction. For a 2-D grid this is two 1-D passes (columns, then rows)
over squared distances, with a final `sqrt`. This is the algorithm scipy's
own C implementation computes; it is exact by construction, not an
approximation.

Semantics match `scipy.ndimage.distance_transform_edt(mask)` with no
`sampling` argument: `mask[i] == 0` (background) is a distance-zero source;
nonzero cells get the Euclidean distance, in grid-cell units, to the
nearest source. An anisotropic `sampling` variant
(`exact_edt_sampled(mask, h, w, row_sampling, col_sampling)`) is included
because the separable algorithm supports it for free — see §3 for why none
of the three call sites currently need it.

11 Rust unit tests (`cargo test --release --no-default-features`, all
passing) check the sweep against an independent O(h·w·sources) brute-force
reference: empty, full (all-foreground, the degenerate case — see §4),
single seed (center and corner), sparse seeds, dense random (xorshift,
no external RNG dependency), thin diagonal feature, all-background row and
column, non-square aspect ratios (4×60), single row/column, a
row-major/transposed symmetry check, and the anisotropic-sampling scaling
identity. `cargo clippy --release` (both `--no-default-features` and
`--features python`) is clean at `-D warnings`; the crate's
`unwrap_used`/`expect_used` deny lints are respected (no panics in the
production path — the one `debug_assert_eq!` is a length-contract check,
not a Python-facing exception, matching `channel_widths.rs`'s stated
convention of no pyo3 exceptions in this crate). `cargo build --release
--target wasm32-unknown-unknown --no-default-features` also succeeds
unchanged (Wave R1 WASM tier constraint — `edt.rs` has no platform-specific
dependency).

## 2. Ground-truth harness and reproduction

`tools/measurements/exact_edt_rust_spike.py`. Built and run against a
throwaway Python 3.12 venv (`uv venv --python 3.12`; the repo's checked-in
tooling has no Python ≥3.12 workspace venv in this worktree) with
`maturin develop --release` building `temper_geometry` with the `python`
feature enabled — scipy 1.18.0, numpy 2.5.1, CPython 3.12.3, rustc 1.97.1
(the repo's default rustup toolchain resolved to 1.73.0 before an explicit
`rustup install stable`; `Cargo.toml`'s `edition = "2024"` requires ≥1.85).

```
uv venv --python 3.12 /path/to/venv
uv pip install --python /path/to/venv/bin/python maturin numpy scipy
cd packages/temper-geometry
VIRTUAL_ENV=/path/to/venv PATH="/path/to/venv/bin:$PATH" \
    /path/to/venv/bin/maturin develop --release
/path/to/venv/bin/python tools/measurements/exact_edt_rust_spike.py
```

The script never touches the three consumer files. It calls
`scipy.ndimage.distance_transform_edt` and the new `tg.exact_edt_transform`
on identical in-memory masks and diffs the results.

## 3. What each consumer actually needs

Read at `90d5fd98`. All three call sites use the single-positional-argument
form — no `sampling`, no `return_indices`, no `return_distances=False`:

| File | Call | Needs |
|---|---|---|
| `channel_widths.py:171` | `distance_transform_edt(mask.astype(np.uint8))` | scalar distance grid only |
| `_astar_heuristics.py:103` | `distance_transform_edt(mask)` (`mask` already `uint8`) | scalar distance grid only |
| `routability_check.py:397` | `distance_transform_edt(interior.astype(np.uint8))` | scalar distance grid only |

None call with `return_indices=True` (the feature/nearest-seed-index
transform) or pass `sampling=` (anisotropic spacing) — every call site uses
the same `cell_size = 0.1` mm for both axes and lets the multiplication by
`cell_size` happen downstream, in Python/Rust code that already exists
(`edt_width_lookup_batch`, `check_routability`'s `min_edt` threshold). All
three consume the return value as a plain `float64` numpy array (scipy's
default output dtype). **Implementing only the scalar distance transform —
which is what this spike did — is therefore sufficient for all three named
consumers as they exist today.** Grepping the router_v6 tree turns up one
more internal caller of the shared `_build_edt` helper
(`capacity_check.py:125`, `from temper_placer.router_v6.channel_widths
import _build_edt`) — same requirements, same helper, not a fourth
independent `scipy.ndimage` call site.

`routability_check.py` also imports `scipy.ndimage.label`
(`check_routability_cc`, line 341) for connected-component labeling — a
different scipy function, not `distance_transform_edt`, and out of scope
for this spike (not part of the 673-LOC EDT figure by the retriage doc's
own accounting; it would need its own port evaluation).

## 4. Agreement with scipy

Two independent measurements, both from `exact_edt_rust_spike.py`, both
comparing bit patterns (`np.abs(scipy_out - rust_out)`), not a loosened
tolerance:

**Curated corpus** (23 cases spanning every category the task brief named
— empty, full, single seed, sparse seeds, dense random at 3 densities,
thin diagonal feature as both foreground and background, all-background
row/column embedded in noise and in isolation, non-square aspect ratios
down to 5×400 and 400×5, an annulus, a checkerboard, and the two real
consumer grid shapes below):

| | value |
|---|---:|
| cases | 23 |
| total cells | 6,375,857 |
| **max abs diff (both finite)** | **0.0** |
| **differing cells (both finite)** | **0** |
| finiteness mismatches | 626 |

**Bulk random differential** (300 independent trials, grid dims uniform in
`[2, 120)` per axis, density drawn from `{0.02, 0.1, 0.3, 0.5, 0.7, 0.95,
0.98}`, seed 42):

| | value |
|---|---:|
| trials | 300 |
| total cells | 1,060,123 |
| **max abs diff (both finite)** | **0.0** |
| **differing cells (both finite)** | **0** |
| finiteness mismatches | 64 |

**Combined: 7,435,980 cells examined, 0 differing cells, max abs diff
exactly 0.0** — genuine bit-exact agreement, not "close to" agreement.
This is the real number the task asked for, and it is categorically
different from the rejected `edt` crate's 2.0–2.236 max diff: that was a
different, incorrect algorithm; this is the same algorithm scipy runs,
implemented independently.

**The one documented divergence (690 finiteness mismatches, all from cases
with zero background cells).** When a mask has *no* background cell
anywhere — the "full" / all-foreground case the task brief explicitly asks
for — there is no principled nearest-background distance to report. This
Rust implementation returns `+inf` for every cell, which is the honest
answer to an underspecified query. scipy instead returns a **finite**
value, and it is not arbitrary: for every all-foreground grid tested (1×1
up to 20×30, plus incidental hits in the 300-trial sweep at density 0.95
and 0.98), scipy's output matches `sqrt((row+1)^2 + col^2)` exactly —
i.e., scipy's C implementation behaves as though there is an undocumented
virtual background source at `(row=-1, col=0)`. This was reverse-engineered
empirically (see `edt.rs`'s test comments and the reproduction below); it
is not documented scipy behavior and reads as a boundary-handling artifact
of scipy's C code on a degenerate input, not a real "exact EDT" semantics
worth replicating. It does not affect the three consumers: their masks are
constructed from rasterized routing polygons / occupancy grids where the
grid always extends past the polygon/board interior (`_rasterize_boundary_mask`
samples from the polygon's own bounding box, whose corners lie on or outside
the boundary; `OccupancyGrid`'s free/blocked split likewise cannot be
all-one-value for any board with actual copper), so an all-foreground mask
is not a reachable input in production. Flagged here as a real, measured
discrepancy rather than silently excluded — per the task brief's explicit
instruction not to loosen tolerance until a check passes.

```python
>>> from scipy.ndimage import distance_transform_edt as dt
>>> import numpy as np
>>> dt(np.ones((3,3), dtype=np.uint8))
array([[1.        , 1.41421356, 2.23606798],
       [2.        , 2.23606798, 2.82842712],
       [3.        , 3.16227766, 3.60555128]])
>>> # matches sqrt((r+1)**2 + c**2) exactly for every (r, c)
```

## 5. Benchmark

Real consumer grid sizes, `cell_size = 0.1` mm (the value every EDT-building
call site in `router_v6` uses — `channel_widths.py`'s `compute_channel_widths`,
`capacity_check.py`'s `_EDT_CELL_SIZE`, `_astar_heuristics.py`'s default).
Board extents: `RoutingSpace` falls back to 100×100 mm when board
dimensions are unset (`_adapter_core.py:273-274`); the real board
(`pcb/temper.kicad_pcb`'s `Edge.Cuts` bounding box) is ~185.3×287.5 mm.
5 reps each, mean wall time. The Rust timing **includes** the FFI boundary
— `.tobytes()` in, `np.frombuffer().reshape()` out — the same shape of
crossing a real migrated call site would pay, not a zero-copy shortcut:

| grid | cells | scipy | Rust (incl. FFI) | speedup |
|---|---:|---:|---:|---:|
| small/test-fixture scale (100×100) | 10,000 | 0.45 ms | 0.27 ms | 1.62x |
| default-fallback board (1001×1001) | 1,002,001 | 58.7 ms | 35.1 ms | 1.67x |
| **real production board (2876×1854)** | **5,332,104** | **485.1 ms** | **288.8 ms** | **1.68x** |

Rust is faster at every size tested, including the boundary crossing, and
the margin is stable (~1.6–1.7x) from 10K cells up to the real 5.3M-cell
board. This is a single-threaded, un-tuned first implementation (no SIMD,
no parallelism); the FH algorithm is trivially parallelizable across rows
in the second pass if more headroom is ever needed.

## 6. Verdict

**KTD8 is resolved, not a genuine blocker.** The re-triage's own text
already said this ("EDT is a known algorithm with a clear Rust
implementation path... belongs in the PORT stream with a differential
rather than in a spike") — this spike is the differential that confirms it:

- **Correctness**: bit-exact (0.0 max abs diff) against scipy across
  7,435,980 cells spanning every requested category, including the real
  consumer grid shapes at production scale. The only divergence is a
  scipy C-implementation artifact on an unreachable degenerate input
  (all-foreground mask, no background cell anywhere), documented above.
- **Requirements match**: all three call sites need only the scalar
  distance transform with isotropic unit sampling and float64 output —
  exactly what was implemented. No feature/index transform, no
  anisotropic sampling, needed.
- **Performance**: 1.6–1.7x faster than scipy at every tested scale,
  including the real board size, even paying the FFI boundary-crossing
  cost a migrated call site would actually incur.

**Recommendation**: move the scipy-EDT blocker from BLOCKER to the PORT
queue. `packages/temper-geometry/src/edt.rs`'s `exact_edt`/`exact_edt_sampled`
is ready to be wired into the three call sites by a follow-up migration PR
(not this one, per the spike brief) — that PR's job is replacing
`from scipy.ndimage import distance_transform_edt; distance_transform_edt(mask)`
with the equivalent `tg.exact_edt_transform` call and adding the
differential test suite pinning bit-exact agreement, mirroring how
`edt_width_lookup_batch` was pinned bit-exact against its own Python
reference.

## 7. What this spike does not establish

- **No production call site was touched.** Per the brief, `channel_widths.py`,
  `_astar_heuristics.py`, and `routability_check.py` are unchanged; the
  migration itself (including updating the disk cache format in
  `_build_edt`, which currently caches scipy's exact output) is future work.
- **Correctness was not checked against `scipy.ndimage.label`**
  (`check_routability_cc`'s connected-component labeling) — a different
  function, out of scope here (see §3).
- **The benchmark is single-process, single-run-shape.** It measures one
  FFI call per array (the shape a migrated call site would use); it does
  not measure e.g. batching multiple boards' EDTs in one call, nor does it
  profile where the 300+ ms scipy time or 289 ms Rust time is spent
  internally (cache effects, allocation, etc.) — only end-to-end wall time
  at the Python boundary, which is what a real caller pays.
- **The scipy fallback behavior on all-foreground input (§4) was
  reverse-engineered from output patterns, not read from scipy's C source.**
  The `sqrt((r+1)^2+c^2)` fit is exact on every all-foreground case tested
  (square and non-square, up to 30×6) but is an empirical hypothesis about
  an implementation detail of an unreachable input, not a verified reading
  of scipy's internals.
