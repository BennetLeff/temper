# CongestionTensor — Verification by Mathematical Induction

Updated 2026-07-31: Rust implementation extended for the wire-up —
`increment_cells` (batch increments over pre-mapped (row, col) pairs),
`to_flat_bytes` (raw float32 storage for the Python wrapper's numpy
view), and `cost` now computes in f64 before returning f32 (bit-identical
to the Python oracle's f64 arithmetic cast to f32; a pure f32 chain
would differ by 1 ulp at the `max_cost` clamp). The Python side
(`temper_placer/router_v6/congestion_tensor.py`) is now a wrapper over
this pyclass with the unchanged public API.

## Base Case: 1×1 Grid, Zero Usage

For a 1×1 grid with zero usage:

- `CongestionTensor::new(1, 1)` allocates `vec![0.0_f32]`
- `cost(0, 0)` computes: `raw = 0.0`, `raw <= 0.0`, returns `1.0`
- Result: `cost = 1.0`

This matches the Python reference:
```python
ct = CongestionTensor.zeros(1, 1)
assert ct.cost(0, 0) == 1.0  # zero usage → cost = 1.0
```

The base case holds because the cost formula is a pure function of
the per-cell usage value and the global `max_cost` parameter,
neither of which depends on grid dimensions.

## Induction Hypothesis: Correctness for n×m Grid

**Hypothesis:** If the Rust `CongestionTensor` is correct for an
n×m grid (i.e., produces bit-identical `cost()` outputs to the
Python reference for all cells), then it is correct for an (n+1)×m
grid and an n×(m+1) grid.

**Proof of inductive step:**

1. **Per-cell independence.** The `cost()`, `increment()`, `decay()`,
   and `reset()` methods operate on cells independently. There is
   no cross-cell interaction — each cell's value affects only its
   own cost.

2. **Flat storage is dimension-agnostic.** The internal storage is a
   flat `Vec<f32>` with row-major indexing: `index = row * cols + col`.
   This is mathematically equivalent to a 2D array. Adding a row
   allocates more elements but does not change the indexing logic
   for existing cells.

3. **Extending dimensions preserves correctness.** When we extend
   from n×m to (n+1)×m:
   - Existing cells at indices `[0, n*m)` are unaffected.
   - New cells at indices `[n*m, (n+1)*m)` are initialized to 0.0.
   - `cost()` on new cells returns 1.0 (base case).
   - After `increment()` on new cells, `cost()` follows the same
     formula as existing cells.

4. **The cost formula is uniform.** `cost(row, col)` computes
   `min(max_cost, 1.0 + ln(1.0 + data[row*cols + col]))` regardless
   of grid size. There is no dimension-dependent branch.

Therefore, by induction on grid dimensions, the Rust implementation
is correct for all n×m grids.

## Empirical Verification

The differential test suite
(`packages/temper-placer/tests/router_v6/test_congestion_tensor_rust_differential.py`)
pins the wrapper and the Rust storage against the pre-migration numpy
implementation, including the f32/f64 `max_cost` clamp band and the
relationship to the retired JIT kernel's production formula (f32
`1.0 + log(1 + raw)`, which differs from the f64 log1p oracle in the
last ulp and collapses to 1.0 for raw below ~6e-8 — the three-way
relationship is pinned by `test_kernel_formula_relation`).

The closure test suite (`ci_closure_test.py`) runs the full router
pipeline with the Rust-backed CongestionTensor. The default
`congestion_weight = 0.0` makes the tensor inert, so the plain closure
run cannot exercise it: the wire-up gate is a non-zero-weight A/B
routing comparison (Rust-backed vs Python-backed) plus the differential
suite above.

Current closure state (measured 2026-07-31): the closure test is red at
HEAD for a pre-existing, unrelated reason — the placement stage exhausts
its strategies ("All strategies exhausted for phase='placement':
['template', 'template']"), giving 0.4% router completion before any
routing-dependent assertion can run. Verified by A/B: identical failure
signature and DRC counts with the pre-migration pure-numpy tensor
restored. The routing stage that does run imports the Rust-backed
wrapper. U1's executable gates (cargo tests, differential suite, PBT,
router unit tests) are all green; the closure gate re-runs when the
placement stage is healthy.

## Corridor Mask Builder — Verification by Induction (added 2026-07-31)

**Base case:** a 1-cell coarse path `[(0, 0)]` with `buffer_cells = 0`
on a `(1, 1)` fine grid yields a single `True` cell — `r0 = c0 = 0`,
`r1 = c1 = min(1, factor) = 1`. Both the Rust `corridor_mask` and the
pinned numpy oracle produce `[[True]]`.

**Induction step:** the mask is the OR of per-coarse-cell fine-grid
rectangles. Each rectangle's bounds are a pure function of its cell
`(cx, cy)`, `coarse_factor`, and `buffer_cells` — no cross-cell
interaction. Appending a coarse cell adds one independently-computed
rectangle to the OR, so if the mask is correct for a path of length
n it is correct for length n+1. OR is commutative, so the mask is
symmetric under path reversal (PBT property 3).

**Empirical verification:** the differential suite
(`packages/temper-placer/tests/router_v6/test_corridor_rust_differential.py`)
pins the Rust mask against the pre-migration numpy implementation on
randomized corpus-style boards (6 grid geometries × 40 random paths),
negative buffers, huge buffers, and edge-touching paths. The existing
`test_corridor.py` now exercises the Rust path through the wrapper.
PBT properties (`test_corridor_pbt.py`): 8-connectivity of connected
paths, boundedness within the grid, symmetry under reversal.

## Copper Coverage Rasteriser — Verification by Induction (added 2026-07-31)

**Base case:** a 3-vertex polygon on a 1×1 grid — the even-odd ray cast
evaluates one crossing test per edge and yields either a single `True`
or `False` cell. The Rust `polygon_mask` and the pinned numpy oracle
agree bit-for-bit (asserted in the differential suite).

**Induction step:** the mask is the bitwise result of the per-cell
even-odd test; each cell's test is a pure function of its centre
`(ox + (col+0.5)·cs, oy + (row+0.5)·cs)` and the polygon edges, with no
cross-cell interaction. If the mask is correct for an h×w grid it is
correct for (h+1)×w and h×(w+1) — adding a row/column evaluates the
same formula on new centres, so correctness extends by induction on
grid dimensions. Arithmetic order is preserved exactly (f64,
left-to-right, strict `>`/`<` comparisons), which is what makes the
masks bit-identical rather than merely close.

**Empirical verification:** the differential suite
(`packages/temper-placer/tests/physics/test_copper_coverage_rust_differential.py`)
pins the Rust rasteriser against the pre-migration pure-Python loop on
randomized star-shaped polygons (30 cases), degenerate polygons
(empty/single-vertex/segment/self-touching/duplicate-vertex), and
axis-aligned grids where cell centres fall exactly on edges and
vertices. `copper_coverage_grid` itself is verified end-to-end against
an oracle grid rebuilt with the numpy rasteriser (8 random outlines),
and the pre-existing `test_copper_coverage.py` suite now exercises the
Rust path through the wrapper. PBT properties (`test_copper_coverage_pbt.py`):
grid bounded in [0,1], zero-weight stackup → zero, monotonic in plane
weight, keepout reduction, all-plane weighted-mean value.

## Channel Widths EDT Lookup — Verification by Induction (added 2026-07-31)

**Base case:** a 1×1 EDT grid with a single sample point at its centre —
the bilinear interpolation reads the four (identical) neighbours and
returns `2 * d * cell_size`; the Rust batch and the per-point Python
reference agree bit-for-bit.

**Induction step:** each sample's width is a pure function of its world
coordinates, the grid values, and the mask — no cross-sample
interaction — so a batch of n+1 samples equals n samples plus one
independently-computed value. The Rust implementation preserves the
reference's exact f64 arithmetic order (floor indexing, strict
bounds check, masked cells → 0.0, left-to-right bilinear
interpolation), which is what makes the outputs bit-identical rather
than merely close.

**Empirical verification:** the differential suite
(`packages/temper-placer/tests/router_v6/test_channel_widths_rust_differential.py`)
pins the batch against the module's own per-point reference on
randomized grids (bit-exact), with offset bounds, out-of-bounds
samples, and all-masked grids; `compute_channel_widths` is verified
end-to-end (batched vs per-point rebuild) on corridor and multipolygon
skeletons, bit-exact over node/edge widths and statistics. The
existing `test_channel_widths.py` and `test_stage2_monolith_parity.py`
(which exercises the batched path through both pipeline arms) pass.
PBT properties (`test_channel_widths_pbt.py`): non-negative, bounded by
the grid diagonal, scale-invariant, symmetric under coordinate swap,
monotonic in the interior mask.

**KTD8 history:** the third-party `edt` crate (2026-07-31 spike) was
evaluated as a `scipy.ndimage.distance_transform_edt` replacement and
rejected — its distance field diverges from scipy's Euclidean transform
even with a False-border padding workaround (measured max diff 2.0–2.236 on
random masks). That rejection was of the third-party crate specifically,
not of a Rust-native EDT in general; the U4 perf win described above (the
per-sample lookup hot loop) is delivered by the batch, and at that time
scipy's transform itself was never the hot loop.

A 2026-08-07 follow-up spike (`docs/evidence/2026-08-07-exact-edt-rust-spike.md`)
implemented an exact Felzenszwalb–Huttenlocher sweep in-house
(`packages/temper-geometry/src/edt.rs`, `exact_edt`/`exact_edt_transform`)
and measured bit-exact agreement with scipy (0.0 max abs diff over
7,435,980 cells across 23 curated cases + 300 random trials), 1.6–1.9x
faster including the Python↔Rust FFI boundary at realistic grid sizes.
KTD8 is resolved: `channel_widths.py:_build_edt`, `_astar_heuristics.py:
_build_edt_from_grid`, and `routability_check.py:_edt_from_obstacle_mask`
now delegate to it (R19 migration; the pre-migration
`scipy.ndimage.distance_transform_edt` calls are retained as pinned
oracles in `test_channel_widths_rust_differential.py`,
`test_astar_heuristics_rust_differential.py`, and
`test_routability_check_rust_differential.py`). The one documented
divergence — an all-foreground mask (no background cell anywhere) yields
Rust `+inf` vs scipy's finite C-implementation boundary artifact — is
reachable at two of the three call sites (an all-free `OccupancyGrid` and
an obstacle-free `obstacle_mask`, both exercised by existing tests); it
does not change any downstream boolean/budget outcome because each
consumer already treats an unbounded/very-large EDT specially (an
`inf`-fallback branch or a `>=`-threshold comparison). `routability_check.py`
is not scipy-free: it still calls `scipy.ndimage.label` in
`check_routability_cc`, a different function this migration does not
address.

### Consumer: `_compute_bottleneck_widths` (last per-point EDT width loop, cleanup C3 — 2026-07-31)

`temper_placer.router_v6._astar_heuristics._compute_bottleneck_widths`
was the last remaining per-point EDT width-lookup hot loop in the repo
(it sampled every waypoint-segment point and called the per-point
lookup inside a Python loop, ~1 FFI-adjacent Python call per sample).
The C3 cleanup rewrote it to collect every sample point per call and
resolve all widths with ONE `_edt_width_lookup_batch` crossing, then
reassemble the per-net minima.

**Base case:** a single sample point — the batch is bit-identical to
the per-point reference for that point (proven above; same f64
arithmetic order, floor indexing, strict bounds check, masked cells →
0.0, left-to-right bilinear interpolation).

**Induction step:** the batch is per-point independent (proven above),
so resolving n+1 samples in one crossing equals resolving n samples
plus one independently-computed value. The C3 change only relocates the
sampling loop — the sample-point arithmetic (`t = s / num_samples`,
`sx = x1 + t * dx`, degenerate-segment → endpoint) is unchanged Python
executed in the same order, and the per-net minimum is an
order-independent `min` over the same multiset of widths. Each net's
bottleneck width is therefore bit-identical to the pre-change
implementation by construction.

**Empirical verification:** the differential suite
(`packages/temper-placer/tests/router_v6/test_astar_heuristics_rust_differential.py`)
pins the batched function against a verbatim copy of the pre-change
per-point loop (the oracle) on ~200 randomized channel mappings —
empty paths, single waypoints, degenerate zero-length segments,
out-of-bounds samples, varied cell sizes (0.1/0.5/1.0) and sample
distances — asserting bit-exact per-net widths; a second test
monkeypatches `_edt_width_lookup_batch` and asserts exactly ONE batch
call per invocation (this failed against the pre-change code, proving
the per-point loop is actually gone). The pre-existing
`test_bottleneck_ordering_pbt.py` and `test_net_ordering*.py` suites
(which drive ordering from these widths) pass unchanged. Measured on a
120-net/0.5 mm-sample fixture: 5.6x faster (22.9 ms → 4.1 ms per call).

## Pad Geometry + Isolation-Barrier Sweep — Verification by Induction (Wave 2, 2026-07-31)

**Base case:** a 1×1 circle pad at the origin — `corner_radius = 0.5`,
`support_radius = 0.5` in every direction; the barrier sweep over one
HV and one SELV pad returns `|Δ| − r_a − r_b`. The Rust core and the
pinned Python oracles agree bit-for-bit.

**Induction step:** support_radius is the sum of per-axis closed-form
terms, each a pure function of the pad's shape parameters and the
rotated query direction — no cross-pad interaction. The barrier sweep
is the min over independent pair gaps and the max over 4 independent
rotations; appending a pad adds independent terms. Extending to any
grid/pad count preserves every existing value. The rotation table is
integer-exact (KiCad R(−θ) convention), and the arithmetic order is
preserved exactly — including two hard-won details: `math.hypot` is
CPython's Dekker double-double `vector_norm` (not libm hypot — 1 ulp
apart), and `cos`/`sin` are resolved via `dlsym` so the crate matches
the host Python runtime's own libm (the uv standalone build's `sin`
differs from the statically-bound `f64::sin` by 1 ulp — measured on a
real input). `axis_radius` uses `PI / 2.0` (the division), not
`FRAC_PI_2` — also 1 ulp apart.

**Empirical verification:** the differential suite
(`packages/temper-placer/tests/placer/cp_sat/test_isolation_barrier_rust_differential.py`)
pins all five pad-geometry functions bit-exactly against the
pre-migration implementations (500–1000 random samples each, all
shapes incl. unknown-shape fallback, arbitrary rotations), the barrier
axis-gap and best-rotation sweep on 200 random pad groups per axis
(rot, gap, convention flag — exact), the Y-axis-separation rotation
bug-regression case, and the mean-equality convention case. The
pre-existing `test_pad_geometry.py` (61 tests) and
`test_isolation_barrier.py` (37 tests) now exercise the Rust core
through the wrappers. PBT properties
(`tests/core/test_pad_geometry_pbt.py`): support_radius never
under-reports the corner disk; bounding_radius is an upper bound for
every direction (the load-bearing safety property); 2π periodicity
(closeness — 2π is not representable); mirror symmetry (bit-exact);
axis radii within the bounding radius.

**Shared-model note:** `temper_placer.core.pad_geometry` remains the
single interface every consumer imports (the isolation-barrier
encoder, `check_isolation_keepout.py`, the router's pad-inflation
paths); the computation is now one Rust implementation, so the
consumers cannot drift apart by construction.

## PBT Properties Verified

| # | Property | Test |
|---|----------|------|
| P1 | Cost monotonically increasing with usage | `test_cost_monotonic_in_usage` |
| P2 | Cost ≥ 1.0 for all cells | `test_cost_never_below_one` |
| P3 | increment then decay(1.0) ≈ identity | `test_increment_then_decay_factor_one_is_identity` |
| P4 | increment linear in weight | `test_increment_linear_in_weight` |
| P5 | reset produces all zeros | `test_reset_zeroes_every_cell` |

## SPICE Estimators — Verification by Induction (Wave 2, 2026-07-31)

**Base case:** a 3-vertex loop — the shoelace sum evaluates exactly
three cross terms; the Rust core and the pinned Python oracle agree
bit-for-bit (the `<3 components` and missing-ref early returns stay in
the Python wrapper, unchanged).

**Inductive step:** the shoelace area is the sum of independent
per-edge cross terms `x1·y2 − x2·y1`, accumulated in vertex order —
appending a vertex adds one term without perturbing existing ones, so
correctness extends over arbitrary loop sizes. The inductance is a
three-operation chain (`mu_0 * area_m2 / h_m`, left-to-right, with
`mu_0 = 4 * 3.14159265359e-7`) — exact order preserved. Unit
inference is a pure substring/range classifier; the same substring
sets, thresholds, and evaluation order as the reference.

**Empirical verification:** the differential suite
(`packages/temper-placer/tests/validation/test_spice_rust_differential.py`)
pins `estimate_loop_inductance` bit-exactly (500 random loops,
reversal symmetry) and `_infer_unit` (1000 name/value samples across
all unit classes and case variants) against the pre-migration
implementations. The pre-existing `test_spice.py` +
`test_spice_templates.py` suites (63 tests) now exercise the Rust
estimators through the wrappers.

## ClearanceGrid Rasterisation + Fence + HV Compute — Verification by Induction (Wave 3, 2026-07-31)

Wave 3 candidate #1: the rasterisation kernels of
`deterministic/stages/_grid_core.py` (`block_circle` / `_block_segment` /
`block_rect` / `unblock_circle` inner loops and `occupancy_bitmap`), the
U3 fence's sample geometry in `_grid_fence.py`, and the creepage-factor /
closest-component compute in `_grid_hv.py` moved to
`packages/temper-geometry/src/grid_raster.rs`. The deterministic-stage
orchestration (bbox computation, net-id resolution, expansion-log
bookkeeping, violation assembly, ConfigError raising, layer-set
membership) stays Python; the modules keep their public API and
delegate.

**Base case:** a 1×1 grid with a disc of radius 0.5 centred on the cell
centre — the kernel evaluates one cell centre against
`pow(pow(dx, 2) + pow(dy, 2), 0.5) <= r` and either writes `net_id` or
leaves 0; the Rust kernel and the pinned pure-Python oracle agree
bit-for-bit on the resulting cell (asserted in the differential suite).
The same holds for the segment kernel's one-cell projection, the
rect kernel's single integer merge, the bitmap kernel's single word,
the fence's first circle sample, and `effective_creepage`'s two arms.

**Inductive step:** each kernel is a loop over *independent* cells in a
closed bbox `[min_row, max_row) × [min_col, max_col)`; every cell's
decision is a pure function of its own centre, the shape parameters,
and the *current value of that one cell* (the merge rule reads only
`grid[row, col]` — no cross-cell interaction). Appending a row or
column, or enlarging the bbox, evaluates the same formula on new
centres and never perturbs already-evaluated cells, so correctness on
an h×w bbox extends by induction to any bbox. The merge operation is
idempotent and order-independent per cell (0 → net_id, net_id → keep,
anything else → −1), which is what the PBT round-trip and
commutativity metamorphic relations pin.

Three bit-exactness details carried across, each a measured pitfall
class from earlier waves:

1. `x ** 2` and `x ** 0.5` in the Python reference are libm
   `pow(x, 2.0)` / `pow(x, 0.5)` (CPython `float_pow`), not `x * x` /
   `sqrt`; the kernels resolve `pow` via `dlsym` so they call the exact
   libm of the host Python runtime (the uv standalone build's libm can
   differ from the crate's statically-bound f64 intrinsics in the last
   ulp — see `pad_geometry.rs`).
2. `math.cos` / `math.sin` are likewise dlsym-resolved for the fence's
   circle samples; `theta = 2.0 * math.pi * i / n` is a three-op
   left-to-right chain (and `math.pi` == `std::f64::consts::PI`
   bit-for-bit).
3. The segment kernel's `t = max(0.0, min(1.0, t))` is evaluated as
   `(1.0_f64.min(t_raw)).max(0.0)` — NOT `t_raw.max(0.0).min(1.0)`: for
   `t_raw = NaN` (zero-length segment, unreachable from the Python
   method's early return but reachable at the kernel level) CPython's
   `min` keeps its first argument, so `t` clamps to 1.0 and the
   degenerate segment blocks a circle around its endpoint; only the
   min-then-max nesting reproduces that.

**Empirical verification:** the differential suite
(`packages/temper-placer/tests/deterministic/test_grid_core_rust_differential.py`,
`test_grid_fence_rust_differential.py`, `test_grid_hv_rust_differential.py`)
pins all eight kernels bit-exactly against the pre-migration
implementations copied verbatim: 500 randomized inputs per kernel
(pre-populated grids with nets/conflicts/obstacles, out-of-bbox
centres, boundary radii), plus end-to-end parity through the public
`ClearanceGrid` methods (bbox + kernel + net-id resolution together,
25–15 seeds each). PBT (`test_grid_core_pbt.py` / `test_grid_fence_pbt.py`
/ `test_grid_hv_pbt.py`): 15 invariants, ~100–150 examples each, all
with vacuity guards — merge-domain, bbox-boundedness, radius
monotonicity, transpose symmetry, block-then-unblock round trip; ring
and expanded-rect boundary membership, sample-count linearity, eff
monotonicity, shape fallthrough; creepage identity/scaling/bounds and
nearest-wins first-min selection. Metamorphic relations (3 per kernel):
integer-cell translation (exact for power-of-two cells + dyadic
centres), net-merge commutativity (conflict/blocked masks), circle ≡
degenerate-segment, segment reversal on lattice segments, rect size
subset + idempotence, unblock round-trip/idempotence/identity, bitmap
zero/union/trace-pad symmetry, fence count-doubling (bit-exact: 2π·2i/2n
== 2π·i/n), rect outward monotonicity, unknown-shape fallthrough,
closest-component append/duplicate/removal stability, creepage
doubling (2·fl(b·0.3) == fl(2b·0.3)) and inner ≤ outer. The
pre-existing suites (`test_clearance_grid.py`, `test_4layer_grid.py`,
`test_router_v6_fence_integration.py`, `test_stage_invariants.py`,
bottleneck-geometry consumers) pass unchanged against the Rust-backed
wrappers; `_grid_core.py` no longer imports the retired JIT runtime
(the module's documented cold-start cost — the migration's perf win). The Rust module
carries 11 unit tests covering merge semantics, degenerate inputs, and
word/boundary layout.

## Bottleneck Geometry (Min-Cut Kernels) — Verification by Induction (Wave 3 #2, 2026-07-31)

**Scope.** The per-cell capacity kernel (with the R4 "category-HIGH on
category-LOW" creepage discount), the hard-blocked check, and the
capacitated-graph build (BFS node set + min-cap edge construction, with
the 256-iteration deadline-stride abort) moved to
`temper_placer/router_v6/bottleneck_geometry.rs`. The Python module keeps
its public API: `_build_capacitated_graph` is now a thin wrapper that
flattens the grid occupancy, calls the Rust kernel, and replays the
returned (nodes, edges) into a `networkx.DiGraph` in the exact order the
pre-migration code added them — so `nx.minimum_cut` (which stays in
Python) sees a bit-identical graph including adjacency insertion order.
All kernels are integer-only (i32 occupancy ids, i64 capacities); there
is no floating-point arithmetic to drift.

**Base case (smallest meaningful input, bit-exact with the oracle).**
A 1×1 free grid: `cell_capacity(0, 0, 0)` = 4 (no traces, no pads), the
cell is not hard-blocked, and the graph build over `source = sink =
(0,0,0)` returns the single node `[0]` with no edges (no in-bounds
4-neighbours). The differential suite pins this exact case:
`test_capacity_batch_empty_grid_and_single_cell_grid` (capacity 4) and
`test_graph_kernel_empty_and_single_cell_grids` (single node, no edges)
compare the Rust kernel against the verbatim pre-migration oracle and
assert bit-exact equality. The deadline kernel's base behaviour is also
pinned: below 256 iterations the deadline never fires
(`test_graph_deadline_never_fires_before_first_stride`), matching the
reference's stride-gated checks.

**Induction step (per-cell independence, order preservation, no
cross-cell interaction).**

1. *Per-cell independence of the capacity function.*
   `cell_capacity(l, r, c)` reads only the cell itself, its 4 cardinal
   neighbours' trace ids, and its 4 cardinal neighbours' pad ids + class
   ranks. Every discount is a pure function of those 5+4 values and the
   two scalars (`current_category`, the bounds). No value of any other
   cell participates, and no cell's result feeds another cell's
   computation (capacities are cached but each is computed from the raw
   arrays, so caching is a pure memoisation of an idempotent function —
   bit-identical to the reference's recompute-per-edge). Adding a row or
   column to the grid evaluates the same formula on new cells without
   perturbing existing ones, so correctness extends by induction on grid
   dimensions. The R4 discount decision is likewise a pure function of
   the neighbour's class rank (or the unresolvable-class sentinel,
   which maps to the reference's "any non-zero pad discounts" fallback).
   Pinned by `test_capacity_batch_matches_reference_on_randomized_inputs`
   (400+ cells) and the full R4 decision matrix test.

2. *The hard-blocked check is per-cell.* `hard_blocked` is a pure
   function of the cell's two occupancy ids (with out-of-bounds →
   blocked). No interaction between cells. Pinned by
   `test_hard_blocked_batch_matches_reference_on_randomized_inputs`
   (300+ cells).

3. *Order preservation of the graph build.* The node set is the
   (order-independent) reachability closure over 4-neighbours of
   capacity>0, non-hard-blocked cells seeded from source ∪ sink — a pure
   graph-theoretic closure, so the Rust frontier's (caller-order) seeding
   yields exactly the reference's set, which the kernel then sorts.
   Edge construction iterates nodes in sorted order with the fixed
   neighbour order (-1,0),(1,0),(0,-1),(0,1) and emits each undirected
   pair's two directed edges exactly once, at the smaller endpoint's
   turn — the same first-insertion sequence the reference's
   `g.add_edge` calls produce (its second call per pair is a dict
   update). Because the wrapper replays the list in order, the networkx
   adjacency insertion order — which `minimum_cut`'s BFS iterates — is
   bit-identical. Pinned by
   `test_graph_kernel_matches_reference_on_randomized_inputs` (50 random
   graphs, comparing node lists, edge sets, capacities, AND per-node
   adjacency order).

4. *No cross-cell interaction in the deadline kernel.* The deadline
   (stride-checked every 256 iterations in both loops, counting every
   BFS pop and every in-nodes neighbour visit from both endpoints, as
   the reference does) only ever short-circuits a build; it never
   changes a node/edge value. An expired deadline on a grid with ≥ 256
   pops raises TimeoutError; below the first stride it never fires
   (both pinned).

**Empirical verification.** The differential suite
(`packages/temper-placer/tests/router_v6/test_bottleneck_geometry_rust_differential.py`)
pins the Rust kernels bit-exactly against the verbatim pre-migration
implementations (17 tests): randomized capacity batches (400+ cells),
hard-blocked batches (300+ cells), 50 randomized full graph builds with
node/edge/order equality, degenerate grids (empty, single-cell,
fully-saturated), obstacle walls, the R4 decision matrix, out-of-bounds
behaviour (row/col → 0; layer → IndexError, mirroring the reference),
and the deadline stride semantics. The pre-existing suites
(`test_bottleneck_geometry.py` incl. the end-to-end 3×3 min-cut,
`test_diagnostics.py`, `test_adapter.py` — 116 tests) pass unchanged,
exercising the Rust kernels through the wrappers, including
`nx.minimum_cut` on the Rust-built graph. The PBT suite
(`test_bottleneck_geometry_pbt.py`) verifies five non-vacuous properties
(boundedness [0,4], monotonicity with a strict-decrease witness,
edge-label round-trip = induced min-cap subgraph, 90°-rotation symmetry
of the capacity field + min-cut value, min-cut non-negativity and cut
bound), each with a mutation test proving a degenerate kernel violates
it. Metamorphic relations (`test_bottleneck_geometry_metamorphic.py`):
translation invariance, source/sink swap invariance of the min-cut
value, obstacle-doubling monotonicity (see the note there on why
per-area s² scaling does not apply to a per-cell trace-count model),
and higher-safety reclassification monotonicity.

**Recorded remainder (not faked):** `nx.minimum_cut` itself (networkx's
Edmonds–Karp) still runs in Python on the bit-identical graph. Porting
it would require replicating networkx's residual-network construction
and bidirectional-BFS augmentation order to reproduce the exact
`reachable`/`non_reachable` partition (the cut VALUE alone is an
algorithm-invariant and would be easy; the partition is not). This is a
separate, lower-risk follow-up; the graph build and capacity loops — the
documented pure-Python hotspot — are the kernels migrated here.
## PBT Properties Verified
## Clearance Validator Geometry (REQ-SAFE-01) — Verification by Induction (Wave 3, 2026-07-31)

**What moved.** The pure geometry compute of the clearance/creepage
validator (`packages/temper-placer/src/temper_placer/requirements/
validators/_copper.py` and `core/pad_geometry.py::pad_pair_distance`)
now runs in `packages/temper-geometry/src/clearance_geometry.rs`: the
pad-offset rotation (KiCad R(−θ)), the component reach, the origin
distance, the copper pair scan (hypot centre-gap pruning + exact
pad-pair distance), and the pad-pair distance itself (core polygon
construction + the core-vs-core gap). The domain-classification and
pairing logic (`clearance.py`'s `_nets_domain_map` /
`_components_in_domain` / `_domain_boundary_pairs` and `_copper.py`'s
`pads_in_domain` / `domain_restricted`) stays Python; the shared
classifier contract is verified by the unchanged import
`placer/cp_sat/domain_clearance.py` → `requirements/validators/
clearance.py`.

**Base case:** a 1×1 rect pad at the origin against a second 1×1 rect
pad 5 mm away — the cores are axis-aligned boxes, the core distance is
a single segment-to-segment candidate `(gap − ra − rb) = 3.0`, and the
Rust core and the pinned Shapely/GEOS oracle agree bit-for-bit
(`clearance_geometry.rs::test_pad_pair_distance_rect_gap`, plus the
differential suite's crafted axis-aligned cases).

**Inductive step:** the pad-pair distance is a pure function of the two
pad specs: core construction rotates/translates a fixed corner set
(per-corner affine, no cross-corner interaction), and the core gap is
the min over an independent candidate set — segment-to-segment /
point-to-segment distances, each a closed-form chain over the pair's
coordinates, plus a containment test per vertex. Appending a pad to the
scan adds independent pairs without perturbing existing ones, and the
`d < best` update preserves every incumbent value; extending to any
pad count / any pair therefore preserves every existing result. The
arithmetic order is preserved exactly, which is what makes the outputs
bit-identical rather than merely close — four hard-won details:

1. **GEOS's point distance is `sqrt(dx·dx + dy·dy)`, NOT hypot** —
   replicating it with CPython `math.hypot` (Dekker vector_norm) or
   libm `hypot` fails by 1 ulp on ~12% of random pairs (measured).
   This crate's `py_hypot` is used only where CPython `math.hypot` is
   the oracle (reach, centre-gap pruning).
2. **Shapely's rotate is not the naive trig rotation**: `pad_core_polygon`
   passes `math.degrees(rotation_rad)` into `shapely.affinity.rotate`,
   which converts *back* with `angle * pi / 180.0` — the effective
   angle is the round-tripped value, and `abs(cos/sin) < 2.5e-16` is
   snapped to exactly 0.0.
3. **cos/sin resolve via dlsym** to the host Python's own libm (the uv
   standalone build differs from the statically-bound `f64::sin` by
   1 ulp on real inputs).
4. **`dist(A,B) != dist(B,A)` in general** — `max(gap − ra − rb, 0.0)`
   subtracts the corner radii in pad order. The pre-migration oracle
   has the same asymmetry; it is preserved, not fixed.

**Empirical verification:** the differential suite
(`packages/temper-placer/tests/requirements/
test_clearance_rust_differential.py`) pins all five migrated surfaces
(`_rotate`, `_component_pads`, `_CopperModel.reach/lower_bound/
copper_distance`, `pad_pair_distance`) bit-exactly against the
pre-migration implementations — 500 random pad pairs per seed across
all shapes including unknown-shape fallback and arbitrary rotations,
300 random components, 100 random placements, plus crafted edge cases
(containment, boundary-touching, zero-size pads, exact-rotation
configs). PBT properties (`tests/requirements/test_clearance_pbt.py`):
non-negativity, symmetry (1-ulp — oracle behaviour), 2π periodicity,
boundedness by centre-distance + reaches, monotonicity in pad
width/height. Metamorphic relations: translation/rotation/mirror
invariance (tight tolerance) and exact scale-doubling
(`d(2·A, 2·B) == 2·d(A, B)` — powers of two scale every f64 exactly).

**Pre-existing failures, unrelated:** `tests/geometry/test_geometry.py`
(42) and `tests/geometry/test_drc_inflate.py` (2) fail at base HEAD
(da4af81eb) and in this worktree identically — a numpy-2.3.5/pyo3
scalar-extraction TypeError in `polygon.py::rotate_polygon` /
`drc_inflate`, files this migration does not touch (verified in a
scratch worktree at the base commit).
## PBT Properties Verified

## Placement-Audit Geometry (Chebyshev gap + bbox) — Verification by Induction (Wave 3 #5, 2026-07-31)

The R24 post-solve audit's pure compute: `bbox_from_center` (audit.py
`_bbox`) and `chebyshev_gap` (audit.py `_chebyshev_gap`).  Every
per-constraint check the auditor runs (separated, enclosing,
adjacent edge-to-edge, on_side, anchored-region, keepout, loop-area)
is built from these two functions; the per-constraint orchestration
stays in Python.

**Base case:** two zero-size boxes (a single point each) at (0,0) and
(d, 0) — `bbox_from_center` collapses to the center point and the gap
evaluates to `max(d − 0, −0) = d`, exactly the Chebyshev (L-inf)
distance between the two points; the Rust core and the pinned Python
oracle agree bit-for-bit for d = 0, 3, and arbitrary reals.

**Induction step:** the gap decomposes into independent per-axis
components — `gap(A, B) = max(gap_x, gap_y)` where
`gap_x = max(ax1 − bx2, bx1 − ax2)` is a pure function of the two
boxes' x-extents alone and `gap_y` of the y-extents alone; there is
no cross-axis interaction, so correctness for 1D boxes (the base) lifts
to 2D by the axis independence of the outer `max`.  Per-box
`bbox_from_center` is four arithmetic ops on one component's
center/size with no cross-component interaction, so by induction on the
number of components a placement's bbox map is correct for any size.
Extending to any number of boxes: each pair's gap is computed
independently and the auditor's SEPARATED check is an any/min over
pairs, so appending a component adds independent pair terms. The
arithmetic order is preserved exactly (left-to-right, two-op chains
stay two ops), and the reference's Python-builtin `max` NaN semantics
are replicated (`py_max`: `max(NaN, x) == NaN` but `max(x, NaN) == x`,
unlike `f64::max` which discards NaN) — that is what makes the gaps
bit-identical rather than merely close.

**R24 soundness property (PBT):** for separated boxes the Chebyshev
gap is a conservative under-approximation of the Euclidean gap
(`0 ≤ cheb ≤ euclid`), so the auditor's SEPARATED check never claims
more isolation than the true clearance.

**Empirical verification:** the differential suite
(`packages/temper-placer/tests/placer/cp_sat/test_audit_rust_differential.py`)
pins `bbox` (500 random components + zero-size + missing-ref defaults)
and `chebyshev_gap` (500 random box pairs, direct Rust pins of 300
each) bit-exactly against the pre-migration implementations, plus
edge cases (zero-size, touching, nested, identical, diagonal
separation, NaN/inf builtin-max semantics).  The pre-existing
`test_audit.py` (23 tests) now exercises the Rust core through the
wrappers.  PBT (`tests/placer/cp_sat/test_audit_pbt.py`): the five
properties above + three metamorphic relations (translation invariance
incl. the auditor-level SEPARATED verdict, ref-swap verdict symmetry,
uniform scaling of both boxes scales the gap linearly and preserves the
verdict when the threshold scales too).

## Euclidean Point Distance (`dist_py`) — Verification by Induction (Wave 3 #4, 2026-07-31)

The R24 domain-clearance audit's distance recompute:
`domain_clearance.py::audit_domain_clearance`'s `math.dist(pos_a,
pos_b)` — the post-solve recomputation of the real Euclidean
center-to-center distance of every generated `domain_clearance_*`
constraint from the *solved* placement coordinates (R24 item 3: "does
not trust the solver's own bookkeeping").  The per-constraint
orchestration (constraint filtering, position lookups, violation
reporting) stays in Python; only the distance moves to Rust.

`math.dist(p, q)` is CPython's Dekker double-double compensated
`vector_norm` over the per-coordinate differences
(`vec[i] = p[i] − q[i]`) — the same algorithm `py_hypot` (pad_geometry.rs)
replicates exactly, so `dist_py` computes the differences first and
delegates: `dist(ax, ay, bx, by) = py_hypot(ax − bx, ay − by)`.

**Base case:** coincident points — `dist(p, p)` computes diffs of
exactly 0.0, `py_hypot(0, 0)` short-circuits to 0.0, and the Rust core
and the pinned `math.dist` oracle agree bit-for-bit (verified for
identical points and for the 3-4-5 triangle `dist((0,0),(3,4)) == 5.0`).

**Induction step:** the norm accumulates over the two differences
independently — the compensated sum adds `(dx·scale)²` then `(dy·scale)²`
with the fma-based `dl_mul`/`dl_fast_sum` correction terms, and the
differential correction (`h += x / (2h)`) is a pure function of that
sum.  Adding a coordinate would add one more independent squared term
(CPython's `vector_norm` is dimension-agnostic); within the fixed 2D
case, correctness for the base point pair lifts to any pair because
each difference is a pure function of its own coordinate axis with no
cross-axis interaction, and the scaling `2^-max_e` normalizes any
magnitude to the same [0.5, 1) binade before the accumulation runs.
The reference's up-front guards are replicated exactly: any NaN
difference → NaN, any infinite difference → +inf, and `inf − inf = NaN`
so a coincident-inf pair is NaN, not inf (all pinned in the differential
suite).

**Non-bit-exact metamorphosis (recorded honestly):** a 90° rotation
(axis swap) reorders the two squared terms inside the compensated sum,
so `dist((ay,ax),(by,bx))` can differ from `dist((ax,ay),(bx,by))` in
the last ulp — the PBT asserts that relation only within 1e-12 relative
tolerance, and documents why it cannot be bit-exact.

**Empirical verification:** the differential suite
(`packages/temper-placer/tests/placer/cp_sat/test_domain_clearance_dist_rust_differential.py`)
pins `dist_py` bit-exactly against `math.dist` over 500 random point
pairs + 300 mixed-magnitude pairs (1e6 vs 1e-3 scales), known points,
Sterbenz-scale/axis-aligned edges, subnormal components, and the
NaN/±inf parity cases.  The pre-existing `test_domain_clearance.py`
(25 tests) and the R24 audit path keep exercising the wrappers.  PBT
(`tests/placer/cp_sat/test_domain_clearance_dist_rust_pbt.py`): five
non-vacuous invariants (variation, zero-iff-identical, bit-exact
symmetry, Sterbenz-exact translation invariance on the 2^-52 grid,
L∞/L1 sandwich) + five metamorphic relations (reflection, axis swap
with tolerance, bit-exact power-of-2 scaling, the Chebyshev-gap
conservative relation, dual-call translation identity).

## Creepage/Clearance Geometry — Verification by Induction (Wave 3 #7, 2026-07-31)

The HV-isolation safety validator's pure geometry:
`point_to_segment_distance`, `closest_point_on_segment`,
`segments_intersect`, `segment_to_segment_info`, the same-layer
min-clearance aggregation, the IPC-2221 voltage table, and the
HV-net word-boundary classifier (creepage_check.py).  Route-object
extraction (`_extract_segments`) and the per-net report orchestration
(`verify_creepage`) stay in Python.

**Base case:** two zero-length segments (points) — the
`denom == 0` arm returns the point-to-point distance
(`math.hypot`, CPython's Dekker double-double `vector_norm`, shared
with `pad_geometry.rs`); a point against a non-degenerate segment
reduces to the clamped projection, whose distance is the true minimum
by the standard argument (the minimum over a closed segment is attained
at the projection if it lies within, else at the nearer endpoint — the
`max(0, min(1, t))` clamp covers exactly these cases).  The Rust core
and the pinned Python oracle agree bit-for-bit.

**Induction step:** for two non-intersecting segments the minimum
distance is attained at an endpoint of one of them (if the closest
point on each segment were interior, the two segments' supporting lines
would cross inside both segments — a proper intersection, which the
orientation test has already excluded).  The algorithm evaluates
exactly those four endpoint-to-opposite-segment distances, in the
reference's order (seg1 endpoints first, then seg2's), taking a strict
`<` min so NaN distances (from NaN coordinates) never displace a finite
best — the same fallback the reference relies on.  The aggregation
`min_clearance_distance` is a min over independent per-pair
computations (with a same-layer filter that is a pure skip, not a
transform), and the min is associative/commutative — by induction on
the n×m pair grid, correctness for n×m pairs implies correctness for
(n+1)×m and n×(m+1), with the strict-`<` tie-break and midpoint
`(p1 + p2) / 2.0` update preserved.  The voltage table and the
word-boundary classifier are pure functions of their inputs (bracket
comparisons; keyword scan with `_`/start boundaries and a trailing
end/digit/`_` check where Python re's `\d` matches the Unicode Nd
property via `char::to_digit`), with the reference's keyword order
preserved.

**Latent reference bug, pinned not fixed:** the pre-migration
`_segments_intersect` intersection-point formula is
`t = cross(P1 − P3, d1) / cross(d1, d2)` — the negative of the true
parameter on segment 2 — so the reported intersection point for a
proper crossing mirrors through P3 (e.g. for (0,0)-(10,10) ×
(0,10)-(10,0) it reports (−5, 15) instead of (5, 5)).  The distance is
0 either way, so the pass/fail verdict is unaffected; the bit-exact
migration replicates the mirrored values (pinned by the differential
suite), and the sign fix is recorded as a follow-up rather than a
silent behavior change.

**Empirical verification:** the differential suite
(`packages/temper-placer/tests/router_v6/test_creepage_check_rust_differential.py`)
pins all six geometry functions bit-exactly against the pre-migration
implementations (500 random point/segment and segment/segment samples
each, 300 random intersection and aggregation samples, 300 random
route pairs, 500 random voltages, 1000 random net names, plus the 14
known false positives, the known true positives, non-ASCII names, and
the NaN/inf contract the boundary suite documents).  The pre-existing
suites — `test_creepage_check.py` (10), `test_creepage_properties.py`
(11), `test_creepage_boundary.py` (79), `test_creepage_induction.py`,
`test_clearance_boundary.py`, `test_geometric_degeneracy.py`,
`test_scale_resolution.py`, `test_manufacturing_report_induction.py`,
`test_induction_strategy.py` — now exercise the Rust core through the
wrappers (287 + 112 tests green, 14 xfail).  PBT
(`tests/router_v6/test_creepage_geometry_pbt.py`): distance
non-negativity, bit-exact symmetry, monotonicity under perpendicular
translation, rotation invariance, boundedness by the midpoint
distance, plus voltage-table monotonicity and HV-detection
case-insensitivity, and four metamorphic relations (translate-both,
swap-segments, rotate-both, HV/LV role swap in `verify_creepage`).

## FFI Audit (spike C7, 2026-08-01) — tagged-type simplification

The pyo3 surface was audited per-function (see the C7 spike report for
the full table). B-class parameters (Python-object-tagged types) that
were converted to int enums / flat arrays, with the public Python API
unchanged (the wrapper converts once):

| pyfunction | Old | New |
|---|---|---|
| `pad_corner_radius_py` / `pad_core_half_extents_py` / `pad_support_radius_py` / `pad_axis_radius_py` / `pad_bounding_radius_py` | `shape: String` | `shape: i64` code (`SHAPE_*`; 0=circle, 1=oval, 2=rect, 3=roundrect, 4=thru_hole, 99=unknown→r=0) |
| `fence_samples_py` | `shape: String` | `shape: i64` code (oval/rect/roundrect = rect branch, else circle) |
| `barrier_axis_gap_py` / `best_rotation_for_barrier_py` | `Vec<(f64,f64,f64,f64,String,f64)>` | same tuple with `i64` shape code |
| `pad_pair_distance_py` / `component_reach_py` / `copper_scan_py` | `(f64,f64,String,f64,f64,f64,f64)` PadSpec | `i64` shape code in the tuple |
| `extract_corridor_mask` | `Vec<(i64,i64)>` | flat `Vec<i64>` (pairs re-grouped at the boundary) |
| `rasterise_polygon_mask` | `Vec<(f64,f64)>` | flat `Vec<f64>` |
| `spice_loop_inductance_py` | `Vec<(f64,f64)>` | flat `Vec<f64>` |
| `CongestionTensor.increment_cells` | `Vec<(i64,i64)>` | flat `Vec<i64>` |
| `cell_capacity_batch_py` / `hard_blocked_batch_py` / `build_capacitated_graph_py` | `Vec<(i64,i64,i64)>` cells | flat `Vec<i64>` |

Bit-exactness is preserved by construction: element order is unchanged
(the Rust side re-groups flat pairs/triples in order) and the shape/edge
match arms are the same decisions the old string matches made (unknown →
safe r=0 / circle-branch / all-Neumann). Pinned by the existing
differential suites (isolation-barrier, grid-fence, clearance, corridor,
copper-coverage, spice, congestion-tensor, bottleneck-geometry) plus the
new wrapper-conversion pins in
`tests/rust_integration/test_ffi_tagged_type_conversion.py`.

**Deliberately kept (B-class, not converted):** `min_clearance_distance_py`
(layer name is open-ended KiCad data, not a small enum),
`closest_component_for_zone_py` (component refs are arbitrary strings and
the result must return the ref), `spice_infer_unit_py` (name content is
the input, not a tag), `is_high_voltage_net_py` (net-name content is the
input), and `precompute_from_pad_polygons` / `compute_drc_proxy_score`
(variable-length nested polygons — a flat conversion would need offsets;
cold paths). Return-value tuples (`Vec<(usize,usize,f64)>` from
`check_clearance_violation`, etc.) were left as-is: the spike targets
parameters, and pyo3's return-tuple extraction is already efficient.

---

## Wave 4 — router_v6 DRC constraint geometry (`drc_constraints_geometry.rs`)

Migrates `temper_placer/router_v6/constraints_geometry.py` — the geometric
distance kernel behind the router's DRC oracle
(`router_v6/constraints_drc_oracle.py`, 9 call sites), the connectivity
checks (`router_v6/connectivity.py`, 3 call sites) and the deterministic
pipeline's pad-attachment test
(`deterministic/stages/connectivity_validation.py`, 4 call sites).

**Crate choice.** `temper-geometry`, not a new crate and not
`temper-rust-router-core`. Three reasons, in order of weight:

1. This crate is already the home of the router's geometry kernels
   (`bottleneck_geometry.rs`, `channel_widths.rs`, `clearance_geometry.rs`,
   `creepage_check.rs`, `corridor.rs` are all router_v6 ports), so the slice
   lands where its siblings already are.
2. It already carries the two CPython primitives this port needs and could
   not otherwise share: `pad_geometry::py_hypot` (CPython's compensated
   `vector_norm`) and `pad_geometry::math_cos_sin` (the host interpreter's
   own libm, resolved via `dlsym`). Re-deriving either in a new crate would
   create a second copy of a numeric contract that must not drift — the
   exact failure mode `geometry/kicad_transform.py`'s module docstring
   exists to describe.
3. Its dependency set is `pyo3` + `rand` only. `temper-rust-router-core`'s
   default features pull `rustsat` + CaDiCaL, a large C++ build, for a
   kernel that needs no solver at all.

### What was migrated, and what was not

| Function | Status |
| --- | --- |
| `point_to_segment_distance` | migrated |
| `segment_to_segment_distance` | migrated |
| `closest_points_segment_segment` | migrated |
| `_segments_intersect` (+ nested `_orientation`, `_on_segment`) | migrated |
| `point_to_circle_distance` | migrated |
| `RotatedRect.corners` | migrated |
| `RotatedRect.bounding_radius` | migrated |
| `point_to_rotated_rect_distance` | migrated |
| `segment_to_rotated_rect_distance` | migrated |
| `LineSegment.length` / `.direction` / `.midpoint` | migrated |

Deliberately **kept in Python**, argued rather than overlooked:

* **The dataclasses themselves** (`LineSegment`, `RotatedRect`, and the
  re-exported `Point`). They stay plain frozen dataclasses instead of
  becoming pyclasses. These objects are stored on `Pad`/`Track`/
  `PCBGeometry` and travel through `pickle` and `copy.deepcopy` in the
  router; a pyo3 pyclass is **unpicklable by default**. PR #724's
  differential was green across 941 assertions while `pickle` and
  `copy.deepcopy` were completely broken, because nothing in that suite
  pickled anything. Keeping the types in Python makes that failure mode
  structurally impossible here, and
  `test_types_are_still_plain_frozen_dataclasses` asserts `repr`, `==`,
  `hash`, `pickle`, `copy` and `deepcopy` anyway rather than relying on the
  argument.
* **`np.array([dx, dy])` in `LineSegment.direction`** — a container
  construction, not arithmetic. The two floats are computed in Rust; only
  the array build stays.
* **`w, h = self.size` in `corners`/`bounding_radius`** — the reference
  unpacks there (raising `ValueError` on a malformed size) and *indexes*
  in `point_to_rotated_rect_distance` (raising `IndexError`). Both
  exception types are preserved: the unpack stays in Python, and the
  indexing crosses the boundary as a sequence so `size_wh` can raise the
  `IndexError` **after** the rotation trig, matching the reference's
  statement order.

### R1e — soundness argument

There is no induction to perform: every function in this kernel is a
straight-line arithmetic expression or a bounded, fixed-trip loop (`for` over
exactly 4 rect corners / 4 rect edges). Termination is therefore immediate
and unconditional, and there is no recursion, no unbounded iteration, and no
solver.

The soundness claim is **observational equivalence to the pinned Python
reference**, and it is established compositionally:

1. **Leaf operations.** Each Python operation is mapped to a Rust operation
   proven to be bit-identical on this platform:
   `math.hypot -> py_hypot` (CPython `vector_norm`, replicated),
   `math.radians -> x * (PI/180.0)` (CPython `degToRad`, same association),
   `math.cos`/`math.sin -> dlsym'd host libm`, builtin `min`/`max ->`
   `py_min`/`py_max` (first-argument-on-ties, NaN-from-the-left),
   `abs -> f64::abs`, and every `+ - * /` in the same left-to-right order
   and the same association as the source. No `powi`/`powf` is introduced:
   the reference squares with `x * x`.
2. **Control flow.** Every branch predicate is transcribed verbatim,
   including the comparisons that are false for NaN in both languages
   (`<`, `<=`, `>`) and the one that is true for NaN in both (`!=`). No
   branch was merged, reordered, or specialised.
3. **Composition.** Because each leaf is bit-identical and each branch
   selects the same arm on the same inputs, the composite functions are
   bit-identical by structural induction over the (finite, acyclic) call
   graph `point_to_segment_distance -> segment_to_segment_distance ->
   segment_to_rotated_rect_distance`.

Step 3 is an argument, not a proof of the implementation, which is why it is
backed by the differential (255 assertions, no tolerance) and by the
mutation campaign below: a defect in any single leaf or branch shows up as a
surviving mutant.

**One deliberate deviation.** `segment_to_rotated_rect_distance` opens with
a call to `point_to_segment_distance(rect.center, segment)` whose result is
discarded — a half-finished broad-phase, left in the reference with an
explanatory comment. It is not reproduced. Justification: it is a pure
function of its arguments with no observable effect and it cannot raise —
`math.hypot` returns `inf` on overflow rather than raising (verified:
`math.hypot(1.7e308, 1.7e308) -> inf`, no exception), and every other
operation in it is plain f64 arithmetic. The differential corpus carries the
overflow-scale inputs that would expose the reasoning if it were wrong.

### R24 — physical quantities

Every scalar crossing this FFI boundary is a **length in millimetres** in
the board coordinate frame, except `rotation`, which is **degrees**
counter-clockwise in KiCad's footprint-child convention (R(-theta); see
`temper_placer/geometry/kicad_transform`'s module docstring for the
ground-truth `kicad-cli` experiment that established the sign).

The kernel performs exactly one unit conversion, `degrees -> radians`, at
the two sites the reference performs it (`RotatedRect.corners` and
`point_to_rotated_rect_distance`). There is no mixed-unit arithmetic
anywhere: distances are only ever compared against, added to, or subtracted
from other distances, and the only dimensionless quantities (the projection
parameters `s`, `t`) are formed as ratios of like-dimensioned products and
are clamped to `[0, 1]` before use.

The boundary carries plain `f64` rather than a newtype because the Python
reference does, and this module is a bit-parity migration: introducing a
unit-carrying type at the boundary would change the public Python signatures
this slice is required to preserve. The three thresholds in the kernel
(`1e-10` on a squared length, `1e-10` on a cross product, `1e-9` on a
distance) are **absolute constants in mm and mm² inherited verbatim from the
reference**; they are not scale-invariant, which is recorded as a limitation
below rather than silently corrected.

This module is not a CP-SAT constraint encoder, so the R24 integer-scaling
rules for the solver boundary do not apply.

### Numerical contract and the traps it encodes

| Trap | Measured | Handling |
| --- | --- | --- |
| `math.hypot` is not `sqrt(x*x+y*y)` | 34 178 / 200 000 random 2-vectors disagree (17.1%) | `py_hypot`, CPython's `vector_norm`, replicated |
| `math.radians` association | `x*(pi/180)`: 0/200 000 mismatches; `(x*pi)/180`: 55 817/200 000 (27.9%) | `x * (PI/180.0)` |
| CPython `min`/`max` NaN + tie behaviour | `min(nan,1)=nan`, `min(1,nan)=1`, `max(0.0,-0.0)=+0.0`, `max(-0.0,0.0)=-0.0` | `py_min`/`py_max`; `f64::max`/`min`/`clamp` all wrong here |
| `math.cos(±inf)` raises `ValueError('math domain error')`; libm returns NaN | — | `check_finite_rotation` at the pyo3 boundary |
| `x ** 2` is libm `pow`, not `x*x` | — | no `powi`/`powf` in the kernel; also bit the *test* code (see M1 below) |
| `np.linalg.norm` / BLAS `ddot` FMA dispatch (PR #714) | — | **not applicable**: this module has no BLAS reduction. The only numpy use is `np.array([dx, dy])`, a container build. |

**Conditional parity claim.** `py_hypot` replicates CPython's `vector_norm`
in its default, fma-using configuration (`dl_mul(x,y) = fma(x, y, -x*y)`).
A CPython built with `UNRELIABLE_FMA` (some 32-bit x86 targets) takes a
Dekker-split path whose last bit can differ. Rather than assert
platform-independent parity,
`test_trap_hypot_matches_the_fma_vector_norm_the_port_replicates`
**asserts the condition holds on the running platform** by comparing
`math.hypot` against an exact-arithmetic transcription of the fma algorithm
(`Fraction`-based, since `math.fma` only exists from CPython 3.13). The
parity claim is therefore provably scoped, not assumed.

### Two pre-existing bugs found in the shared `py_hypot`

Both were found by this slice's differential corpus, not by inspection, and
both are fixed in `pad_geometry.rs` — which means every existing consumer
(`creepage_check.rs`, `pad_geometry.rs` itself) is also corrected.

1. **Top-binade NaN.** `vector_norm_2` computed its scale as
   `2f64.powi(-max_e)`. LLVM lowers a negative `powi` to `1.0 / powi(|e|)`,
   so `2f64.powi(-1024)` overflows `2^1024` to `inf` and returns `0.0`,
   where `2^-1024` is a representable subnormal. Consequence:
   `py_hypot(x, y)` returned **NaN for every input with `max(|x|,|y|) >=
   2^1023`**. `hypot(1e308, 1e308)` was NaN instead of
   `0x1.92c80954c51f5p+1023`. Fixed by an exact `pow2` (bit-pattern
   construction, with a subnormal branch); pinned by
   `pow2_is_exact_where_powi_is_not` and
   `py_hypot_matches_cpython_on_the_top_binade`.
2. **NaN checked before infinity.** CPython returns `+inf` from
   `math.hypot` as soon as any coordinate is infinite — infinity wins over
   NaN (`hypot(inf, nan) == inf`, `hypot(nan, 1.0) == nan`). The guards were
   in the opposite order. This is reachable for real, not only in the
   corpus: in `point_to_segment_distance` an infinite segment endpoint makes
   the clamped projection produce a NaN coordinate, and the final
   `hypot(-inf, nan)` must be `inf`. Pinned by
   `py_hypot_lets_infinity_win_over_nan` and, from the Python side, by
   `test_regression_infinity_beats_nan_in_hypot`.

### Gate summary

* **R1a** — `test_constraints_geometry_rust_differential.py`, 255 assertions,
  oracle = `tests/router_v6/_constraints_geometry_py_oracle.py` (verbatim at
  `c5875adad`). Compared by type-carrying signature
  (`tests/router_v6/_signature.py`): `float.hex()` per float, `dtype` +
  `shape` per array, concrete type name per leaf, **no tolerance**.
  Comparator discrimination proven by `test_signature_self_test.py`
  (13 tests: f32/f64 arrays and scalars, `np.float64` vs `float`, int vs
  float, `True` vs `1`, `0.0` vs `-0.0`, 1 ulp, tuple vs list, shape, dict
  order). Exceptions are compared as values, so error parity (type *and*
  message) is inside the differential.
* **R1b** — 4 benchmarks in `benchmarks/perf_ab.py`
  (`drc-geometry` / `point_segment`, `segment_segment`, `point_rect`,
  `segment_rect`), each asserting parity in-harness before timing. They draw
  their inputs from `tests/router_v6/_constraints_geometry_cases.py`, the
  **same module the differential iterates**;
  `test_benchmark_corpus_is_covered_by_differential` asserts the containment
  from the test side, so the #714 gap (differential at
  `[0,1,2,8,17,100]`, benchmark at 120) cannot recur here.
  No baseline rows are added: per this file's own capture rules, baselines
  are captured on CI, and these register as `NEW_BENCHMARK` until then.
* **R1c** — 7 properties, each vacuity-guarded by an explicit reached-count
  assertion.
* **R1d** — 5 metamorphic relations, 2 of them **exact** (power-of-two scale
  equivariance; argument symmetry of `segment_to_segment_distance`).
* **R1f** — TDD: the comparator self-test and the differential were written
  and run RED (`temper_geometry is missing [12 symbols]`) before the kernel
  existed.
* **R1g** — `cargo clippy --all-features --all-targets -D warnings` clean.

### Relations that do NOT hold, with witnesses

Each is recorded as a constructed counterexample rather than absorbed into a
looser claim:

| Relation | Status | Witness |
| --- | --- | --- |
| Segment reversal preserves the point distance | holds to 1e-12 relative, **not** bit-exact | `test_witness_segment_reversal_is_not_bit_exact` |
| ...and on the **degenerate** branch it fails by the whole segment length | genuinely false | `test_witness_reversal_is_not_even_approximate_when_degenerate` (found by Hypothesis) |
| 180° rotation + reflection through the centre | holds to 1e-9 relative, not bit-exact (`sin(pi) = 1.22e-16`) | `test_witness_180_degree_rotation_is_not_bit_exact` |
| General (non-power-of-2) scale equivariance | holds to 1e-12 relative, not bit-exact | `test_witness_general_scaling_is_not_bit_exact` |
| Translation invariance | not claimed at all | `test_witness_translation_invariance_is_not_bit_exact` |
| `d(p, seg) <= min(|p-start|, |p-end|)` | false on the degenerate branch | `test_witness_degenerate_arm_breaks_the_endpoint_bound` |

The last one is a real (minor) infidelity **in the reference algorithm**,
reproduced faithfully: for a segment shorter than 1e-5 mm the reference
measures from `segment.start`, so it can report a nonzero distance for a
point sitting exactly on the other endpoint. It is documented here rather
than "fixed", because fixing it would be a behaviour change this migration
is not authorised to make.

### Limitations

* The three epsilons (`1e-10` on squared length, `1e-10` on the orientation
  cross product, `1e-9` on the intersect test) are absolute constants in mm
  and mm², inherited verbatim. They make the kernel **not scale-invariant**:
  the exact power-of-two metamorphic relation has to exclude inputs that
  straddle the degenerate threshold under scaling. Inherited, not
  introduced.
* Callers may pass Python `int` coordinates (`Point(0, 0)` appears in the
  test suite). The differential covers integer inputs, but only at small
  magnitudes: above 2^53 the oracle's arbitrary-precision integer arithmetic
  would diverge from f64 before `math.hypot` is reached. Board coordinates
  are mm and bounded by ~10^3, so the gap is unreachable in practice — but
  it is a gap, not a proof.
* The perf figures below were measured on darwin/arm64 in this worktree, not
  on CI. Per this file's capture rules they are informational only; the
  gated baseline must be captured by `pr-perf-check.yml`.

### Measured perf A/B (darwin/arm64, this worktree — informational)

`rust_over_oracle_ratio`, lower is better; both arms in one process, median
of 9 after 3 warmups, over the shared differential corpus.

| stage | release build | debug build |
| --- | --- | --- |
| `point_segment` | **0.851** (1.17x faster) | 1.298 (**1.30x SLOWER**) |
| `point_rect` | **0.749** (1.34x faster) | 1.403 (**1.40x SLOWER**) |
| `segment_segment` | **0.524** (1.9x faster) | 0.817 (1.22x faster) |
| `segment_rect` | **0.173** (5.8x faster) | 0.413 (2.4x faster) |

Reported in both directions, deliberately. The shape is the expected one for
a scalar migration: the **leaf** entry points (`point_segment`,
`point_rect`) do a handful of flops behind a pyo3 boundary, so in a debug
build the FFI cost dominates and they are a genuine 30–40% regression; the
**composite** entry points replace 5 (`segment_segment`) to 25
(`segment_rect`) Python-level calls with one boundary crossing and win in
every configuration. The composites are also where the DRC oracle spends its
time (`segment_to_rotated_rect_distance` and `segment_to_segment_distance`
are the pad- and track-clearance inner loops), so the weighted effect on the
router is a speedup — but the leaf regression is real and is not hidden
behind that average.

The migration is fidelity-driven regardless: its purpose is one
implementation of the KiCad rotation convention and CPython's float
semantics, not throughput.

---

## Deterministic leaf geometry — grid_utils + via_placement (Wave 4, Phase 5, first slice, 2026-08-04)

The compute of `temper_placer/deterministic/geometry/grid_utils.py`
(`snap_to_grid`, `add_endpoint_nudge`) and
`temper_placer/deterministic/geometry/via_placement.py` (`distance`,
`is_via_position_valid`, `place_via_with_clearance`) moved here
(`src/grid_utils.rs`, `src/via_placement.rs`, with the dlsym "host math"
helpers extracted to the shared `src/host_math.rs`). The Python modules
are now delegation shims; the pre-migration implementations are pinned
VERBATIM as the differential oracles
(`tests/deterministic/_grid_utils_py_oracle.py`,
`tests/deterministic/_via_placement_py_oracle.py`).

### Candidate scorecard

| Kernel | Python origin | Verdict |
|---|---|---|
| `snap_to_grid` | `grid_utils.snap_to_grid` | migrated |
| `add_endpoint_nudge` | `grid_utils.add_endpoint_nudge` | migrated |
| `via_distance` | `via_placement.distance` | migrated |
| `is_via_position_valid` | `via_placement.is_via_position_valid` | migrated |
| `place_via_with_clearance` | `via_placement.place_via_with_clearance` | migrated |
| `PadInfo` dataclass | `via_placement.PadInfo` | **stays Python** — pure container; the boundary crosses flattened fields |

### Induction applicability

Mathematical induction is not applicable to these kernels: none is
recursive, and none iterates over a dimension whose correctness depends on
a size parameter. `snap_to_grid` / `via_distance` / `is_via_position_valid`
are closed-form scalar expressions; `add_endpoint_nudge` and
`place_via_with_clearance` iterate over caller-provided collections whose
per-element operations are size-independent (`add_endpoint_nudge` over a
fixed 2-3-element sequence of nudges, `place_via_with_clearance` over a
FIXED 8×8 spiral — the radius list and angle range are compile-time
constants). Per R1e, a **structural proof** is recorded instead.

### Structural proof (bit-identical parity)

Each kernel is a direct transcription of the oracle body with the following
load-bearing equivalences, each pinned by the differential suites and the
mutation campaign:

1. **round-half-to-even + int-semantics (`snap_to_grid`).** CPython's
   `round(x)` without ndigits runs `_Py_double_round` (round-half-to-even),
   then converts the double to an `int` before multiplying by `grid_size`.
   `host_math::py_round` uses `f64::round_ties_even` (the same IEEE
   roundTiesToEven `_Py_double_round` implements — both correctly rounded,
   hence identical on every finite input) and normalises `-0.0 → +0.0`
   because `int(-0.0) == 0` makes the CPython product `+0.0 * grid_size`.
   Rust's `f64::round` (half-away-from-zero) is deliberately NOT used —
   verified by mutant M1 (killed). A non-finite division result raises the
   exact CPython errors (M2-adjacent, pinned by `SnapError`):
   `OverflowError`/`ValueError` with CPython's message text, checked
   left-to-right like CPython's tuple evaluation order.
2. **`** 2` / `** 0.5` are libm `pow`.** CPython's `x ** y` on floats is
   libm `pow` (float_pow), NOT `x * x` and NOT `sqrt` — measured
   mismatch rates on this platform ~1.3e-3 (pow vs x*x) and ~1.4e-3 (pow
   vs sqrt). Every squared/half-power site routes through
   `host_math::pow`, resolved via `dlsym(RTLD_DEFAULT, ...)` to the exact
   libm the host CPython process loaded (the `_Py_double_round` C helper
   `round()`/`round_ties_even` are hardware IEEE ops and match without
   dlsym). Mutant M6 (`x * x` in `via_distance`) is killed by the FIXED
   sqrt-composed discriminator `test_distance_sqrt_composed_discriminates_pow`
   — the single-axis pow-not-square case round-trips the inner difference
   away (see the campaign notes below).
3. **`math.sqrt` is correctly-rounded IEEE sqrt.** `via_distance` uses
   `f64::sqrt` (matches `math.sqrt` bit-for-bit; NOT routed through dlsym).
4. **`math.radians(d)` is `d * (pi / 180.0)`; `math.cos`/`math.sin` are the
   host libm's.** The Rust side computes `angle * (std::f64::consts::PI /
   180.0)` (the same IEEE division of the same double constant CPython
   folds) and resolves cos/sin via `host_math` dlsym. The spiral angle
   sweep is `range(0, 360, 45)` → `0..360 step 45`.
5. **Strict comparison semantics.** `is_via_position_valid` uses
   `< required_distance` (STRICT — an exactly-equal distance is VALID,
   pinned by a fixed case; mutant M7 `<=` killed). `add_endpoint_nudge`
   uses `> 1e-4` (STRICT — an exactly-`1e-4` offset is NOT nudged, pinned
   by `test_nudge_threshold_boundary_exact`; mutant M4 `>=` killed).
6. **Search-order determinism.** `place_via_with_clearance` checks the
   target once up front (mutant M8, removing the short-circuit, killed by
   `test_place_empty_pads_returns_target`), then walks the FIXED radius
   list in order with `break` on `r > max_search_radius` (mutant M9 `>=`
   killed by the msr=1.25 case) and angles `0..360 step 45`; the first
   valid candidate wins. There is no set/dict iteration anywhere in these
   kernels, so no iteration-order trap applies.
7. **Empty-input semantics.** `add_endpoint_nudge([])` returns `[]` and
   `is_via_position_valid` over zero pads returns `True` — both asserted
   explicitly in the differential (vacuity guards).

### Mutation campaign (Phase 5, Batch 1 — 9 mutants, 9 killed, 0 survivors)

Driver: `scripts/phase5_batch1_mutations.py` (reproducible; apply →
rebuild → run the four suites → expect failure → revert). After the last
mutant the driver rebuilds from pristine source and re-runs the suites, so
the campaign ends bit-exact (the per-mutant revert alone would leave the
installed .so carrying the final mutant — the revert does not recompile).
Only a suite failure counts as a kill; rebuild/pytest infra failures are
counted as ERROR (driver exit non-zero), so the 9/9 claim cannot be
inflated by a spurious infra failure.

| Mutant | Site | What caught it |
|---|---|---|
| M1 `f64::round` (half-away) for round-half-even | `host_math::py_round` | fixed half-even cases (0.125/0.375/… grid 0.25) + exact-halves randomized |
| M2 dropped `-0.0 → +0.0` normalisation | `host_math::py_round` | `snap_to_grid(-0.125, …)` tie → `+0.0` (hex differs) |
| M3 no rounding at all (`rx * gs`) | `grid_utils::snap_to_grid` | randomized + on-grid identity cases |
| M4 nudge threshold `>= 1e-4` | `grid_utils::add_endpoint_nudge` | `test_nudge_threshold_boundary_exact` (dist EXACTLY 1e-4 → no nudge) |
| M5 always append the end nudge | `grid_utils::add_endpoint_nudge` | `test_nudge_single_point_path` (end-coincides case) |
| M6 `x * x` for `pow(x, 2.0)` | `via_placement::distance` | `test_distance_sqrt_composed_discriminates_pow` (fixed 2-coordinate pair whose composed `** 0.5` flips) |
| M7 `<=` for `<` | `via_placement::is_via_position_valid` | `test_is_valid_boundary_equality_not_less_than` (equal distance → valid) |
| M8 drop target-valid short-circuit | `via_placement::place_via_with_clearance` | `test_place_empty_pads_returns_target` |
| M9 `>=` for `>` (max_search_radius) | `via_placement::place_via_with_clearance` | `test_place_max_search_radius_respected` (msr=1.25 reaches r=1.25) |

**Equivalent-mutation notes (not kill targets, argued in-source):**
- Commutative reorder of `pow(dx,2.0) + pow(dy,2.0)` — IEEE addition is
  commutative, bit-identical by construction.
- `x * x` inside `add_endpoint_nudge`'s distance — the nudge's only
  observable use of the distance is the `> 1e-4` threshold decision, and
  no input straddling the threshold under the two readings was found in a
  10M-ulp-neighbourhood search around `1e-4` (the pow-vs-x*x delta is
  ~5e-21 at that magnitude, far below the 1-ulp resolution of the
  boundary). The same pow semantics ARE discriminated in `via_distance`
  (M6).

**Pass-2 campaign re-measurement (2026-08-05).** The pass-1 campaign log
recorded "9 killed" with a driver that counted ANY non-zero outcome as a
kill — including rebuild/pytest infra failures (P1-3). Re-measured with
the fixed driver (kill = suite exit 1 only; infra failures are ERROR and
fail the driver), two verdicts did not reproduce and were closed rather
than left as inflations:

- **M4** survived the pass-1 suites: the named pin
  `test_nudge_threshold_boundary` constructed `(1.0 + 1e-4) - 1.0`, which
  in binary is `9.999999999998899e-05` — just BELOW the threshold, so both
  the strict `>` oracle and the `>=` mutant behave identically on it.
  Closed by `test_nudge_threshold_boundary_exact`, which pins a distance
  that lands on `1e-4` bit-exactly (`1e-4 - 0.0` is exactly `1e-4` and
  `(1e-4 ** 2 + 0.0) ** 0.5 == 1e-4` in IEEE-754, asserted inline). Under
  the `>=` mutant the kernel prepends the start point; the oracle does
  not — the differential fails deterministically.
- **M6** survived the pass-1 suites: `test_distance_pow_not_square`
  documents that the COMPOSED `sqrt(pow(dx,2)+pow(dy,2))` round-trips the
  1-ulp inner difference away for its single-axis input, and the seed-3
  randomized arm draws 0/1200 discriminating values (its
  uniform(-100, 100) magnitude range never reaches the pow-mismatch
  regime, which starts around |x| ~ 1e3 — the pass-1 "killed by the
  randomized arm" claim did not reproduce and is attributed to the
  infra-failure-as-kill counting bug). Closed by
  `test_distance_sqrt_composed_discriminates_pow`: three fixed
  2-coordinate pairs found by scanning pow-mismatch magnitudes (e.g.
  `x=-122980.49419472546, y=1459.765068127158`) whose inner sums differ
  by 1 ulp AND whose composed `** 0.5` output flips (oracle
  `0x1.e06d2852f3b27p+16` vs `x*x` kernel `0x1.e06d2852f3b28p+16`).

Re-verified end-to-end with the fixed driver (9/9 KILLED, pristine ending
rebuild, exit 0) and the campaign claim below stands on the deterministic
fixed cases, not on a lucky random draw.

### R1 gate status (Phase 5, Batch 1)

- **R1a** — differential suites assert bit-identical output
  (`float.hex()`, type-carrying `canon`, empty-input semantics, error
  type+message parity). 39 assertions/examples green.
- **R1b** — pure-delegation compute with no measurable workload at this
  slice's call sites (dormant leaf kernels, imp=0); no perf arm registered
  (recorded as not-applicable — the kernels' callers are the stages under
  migration, which are not yet wired into a measurable hot path).
- **R1c** — 5 non-vacuous properties per module (grid_utils: idempotence,
  half-cell bound, pow-2 scale invariance, on-grid identity, zero fixed
  point + empty path; via_placement: self-distance zero, clearance
  monotonic, mask-radius monotonic, extra-pad never helps, place-returns-
  valid-or-target).
- **R1d** — 3 metamorphic relations per module (grid_utils: axis
  independence, reflection, nudge order preservation; via_placement: pad
  order invariance, reflection, spiral-lattice candidates).
- **R1e** — this entry (structural proof; induction N/A, stated why).
- **R1f** — TDD: oracles + differentials + PBT committed first as RED
  (fails to collect; RED commit 2128f6225, reachable from this branch),
  then the Rust landed GREEN (migration commit b3e269d94).
- **R1g** — borrow over clone, no `unwrap` outside tests, `catch_unwind`
  at every pyo3 boundary (`temper_py_bridge::catch_unwind` +
  `panic_to_err`), `PyResult` everywhere.
- **R1h** — not physics-gated (no thermal/creepage physics quantity is
  computed here; state explicitly: not applicable).

## Area-Sufficiency Aggregation (`area_sufficiency.rs`) — Verification (Wave 4 Phase 4, 2026-08-04)

The Wave 4 Phase 4 analysis-surface migration moved the compute of
`temper_placer/analysis/_area_sufficiency.py` (95 LOC) into this crate.
The Python module is now a delegation shim; its pre-migration
implementation is pinned verbatim as the differential oracle
(`packages/temper-placer/tests/analysis/_area_sufficiency_py_oracle.py`,
commit `c5875adad`).

**Home-crate decision (why temper-geometry).** The ledger
(`docs/wave4-verdicts.yaml`) assigns `analysis/**` to Phase 4 and the
mandate names temper-geometry or temper-design-bundle "per the dependency
direction" for area sufficiency.  The dependency direction is
`analysis → io/kicad_metadata → core/courtyard → geometry`, so the
aggregation's natural home is the geometry crate: usable-board-area
arithmetic and courtyard-area summation are 2D geometry math
(`(w-2m)·(h-2m)` and a compensated sum of polygon areas), and
temper-geometry is the crate that already owns board/courtyard-area
kernels (`polygon_area`, `rect_area`, `compute_loop_area`).
temper-design-bundle was rejected: it owns Phase-2 *contracts*, and the
`AreaSufficiencyResult` dataclass is a compute result, not a contract —
it stays Python-side in the shim (the pure-data-holder precedent from
`core/priority.py`'s `POWER_STAGE_TEMPLATES`).

**Boundary — what stays Python and why.** The per-courtyard areas
(`c._polygon.area`) stay Python-side: they are shapely/GEOS polygon
areas, and GEOS is not bit-reproducible outside shapely (the guide's
"library semantics are not reimplementable" precedent, GEOS-buffer case).
The board dimensions pass across as opaque objects and come back
unchanged, so an `int` board width (integer s-expr coords) stays `int`
in the result — the int-vs-float leaf type cannot drift.  The metadata
extraction (`io/kicad_metadata`) is another session's surface, called
but not modified.

**Induction applicability.** Mathematical induction is not applicable:
`py_sum_neumaier` iterates a caller-provided slice but each per-element
step is a fixed two-instruction compensation independent of the slice's
size, and `top_courtyards` is a fixed sort + slice.  Per the plan's R1e a
**structural proof** is recorded instead.

**Structural proof (bit-identical parity).** Claim: for every input in
the differential/PBT domains, the three pyfunctions reproduce the pinned
oracle bit-identically, with the documented deviations below.
*Proof by structural cases.*
- `py_sum` is a line-for-line port of CPython 3.12's
  `builtin_sum_impl` float fast path (`Python/bltinmodule.c`, gh-100425):
  the first item enters via `0 (int) + x0` (round-to-nearest normalises
  `-0.0` to `+0.0`), each later item runs Neumaier's compensation
  (`t = f + x`; `c += (f-t)+x` when `|f| ≥ |x|`, else `c += (x-t)+f`;
  `f = t`), and the final `if (c && isfinite(c)) f += c` mirrors C's
  truthiness exactly (`-0.0` is falsy, `NaN`/`±inf` fail the finite
  check).  The `fabs`/`>=` branch structure is copied so NaN takes the
  same path as CPython.  Empty input returns `int 0` (`sum([]) == 0`),
  not `float 0.0`.  Verified against the builtin on a 125-case adversarial
  corpus plus 80 hypothesis-generated cases (P1/P5), all bit-exact via
  `float.hex()` with the concrete leaf type carried.
- `area_sufficiency_compute` computes `used_w = w - 2m`,
  `used_h = h - 2m`, `usable = used_w · used_h`, the oracle's
  non-positive check (`used_w ≤ 0 or used_h ≤ 0 or usable ≤ 0`), the
  oracle's `(total / usable) * 100.0` ratio (operand order is load-bearing
  at the 1e308 overflow band — mutant M5), and the byte-identical
  `ValueError` message: `py_float_fixed` reproduces CPython's `:.1f`
  fixed formatting (correctly rounded; only `nan`/`inf` spellings
  diverge and are special-cased), `py_float_str` reproduces `repr(float)`
  (shortest round-trip; exponent sign/padding and `nan`/`inf` handled),
  and the int-or-float dimension objects are rendered through their own
  `str()` (so `100` renders "100", `100.0` renders "100.0").
- `top_courtyards` replicates `sorted(pairs, key=area, reverse=True)` —
  a *stable* descending sort (ties keep input order; `slice::sort_by` is
  stable, matching `list.sort`) — followed by Python's `list[:n]` slice
  semantics for every `n`: oversized, zero, and negative (`len + n`,
  floored at 0).  The comparator treats non-comparable keys (NaN) as
  Equal, which is deterministic and stable; Python's TimSort is not a
  strict weak order on NaN keys (measured: all 6 orders over 3 elements),
  but courtyard areas are shapely polygon areas or `0.0` — never NaN —
  so the domains agree on every reachable input (deviation D1).

**Documented deviations (per R1, recorded here).**
- D1 (NaN sort keys): Python `list.sort` with NaN keys is order-sensitive
  (TimSort's merge against a non-strict-weak-order comparator); the Rust
  sort is deterministic-stable for NaN.  Unreachable in production (see
  above) and asserted only on the non-NaN domain in the differential.
- D2 (render error surface): none — the module has no other documented
  divergences; `py_sum` covers only all-float inputs (the oracle's
  courtyard areas are all floats).

**Evidence.**
- Differential (R1a/R1f, TDD red→green): `test_area_sufficiency_rust_differential.py`
  — kernel arm (`py_sum` vs builtin `sum()` on a 125-case adversarial
  corpus: empty, single, `-0.0`, NaN, ±inf, subnormals, the
  1e16/1/-1e16 Neumaier discriminator, max-double overflow pairs),
  full-path arm (oracle `compute_area_sufficiency`/`compute_top_courtyards`
  vs the shim on 5 synthetic boards × 8 `n` values, floats via
  `float.hex()` with concrete leaf types, int-board-dim case,
  stability-tie case), and the error arm (ValueError messages
  byte-identical, float and int dimension boards).  RED before the Rust
  landed (fails to collect).
- PBT (R1c): `test_area_sufficiency_pbt.py` — 6 hypothesis properties
  (P1 kernel linkage, P2 usable arithmetic, P3 error path, P4 empty
  semantics, P5 special-value sum parity, P6 top-N contract),
  non-vacuously guarded.
- Metamorphic (R1d): `test_area_sufficiency_pbt.py` — MR1 power-of-two
  scaling (bounded to the courtyard-area band and exponents that keep
  every intermediate normal — IEEE scale-invariance fails at
  subnormal/overflow boundaries), MR2 margin monotonicity (bounded to
  non-negative areas; a negative total would invert the ratio ordering),
  MR3 top-N prefix, MR4 zero-padding (bounded to non-zero finite areas).
- Anti-vacuity mutation campaign: **5 mutants, all caught by the
  differential/PBT** — M1 naive accumulation (Neumaier discriminator),
  M2 dropped final compensation, M3 dropped `-0.0` normalisation,
  M4 dropped finite-check (max-double overflow pair: `inf + -inf → NaN`),
  M5 ratio operand order (overflow-band test).  No survivors.
- Performance A/B (R1b): **no perf arm registered — recorded why.**
  The migrated compute is a compensated sum over ≤ ~170 areas plus a
  stable sort, on a path whose wall time is dominated by the Python-side
  kiutils/shapely metadata extraction (I/O-shaped surface).  A
  pr_perf_compare arm would measure marshalling noise, not compute; the
  pure-delegation no-regression-beyond-noise statement applies (the
  differential's existence is the behavioural guarantee).  This mirrors
  the thermal slice's NO_BASELINE-by-decision record.
- Rust practice (R1g): borrow over clone (the sort takes the pairs by
  value; `0.0 + items[0]` avoids a clone); no `unwrap` outside tests;
  every `#[pyfunction]` boundary relies on pyo3's default `catch_unwind`
  (panics surface as `PanicException`, never as UB — the validation.rs
  precedent; an explicit `temper_py_bridge::catch_unwind` is impossible
  on a `Py<PyAny>` return, which is not `UnwindSafe`).
- Physics gating (R1h): **not applicable** — area sufficiency is not a
  physics-gated surface (no CP-SAT constraint gates on a physics
  quantity; the computation is courtyard-area vs usable-board-area
  arithmetic), so the R24 discipline does not apply.  Stated explicitly
  because the ledger requires the determination.

> **Superseded in part (Wave 4 Phase 4, 2026-08-04):** the two `drc_inflate`
> entries in the "deliberately kept" list above no longer exist.
> `precompute_from_pad_polygons` was retired from Rust (it was dead and did not
> match the Python semantics) and `compute_drc_proxy_score` was replaced by
> `drc_proxy_score`, which takes flat positions and half-dimensions rather than
> nested polygons — so the variable-length-nesting objection no longer applies
> to it. See the next section.

## DRC Inflation Kernels — Wave 4 Phase 4 (the `geometry/` remainder, 2026-08-04)

### What Phase 4 actually found

Phase 4's brief was "the 2,630 LOC of `temper_placer/geometry/` that Waves 1-3
left behind". Surveying the tree first — before migrating anything — showed
that most of it was **already migrated**. Per file, at base `ebf9326ff`:

| File | LOC | State at base |
|---|---:|---|
| `primitives.py` | 329 | already a pure delegation shim (`_tg.*`) |
| `polygon.py` | 329 | already a pure delegation shim |
| `sdf.py` | 302 | already a shim except `sdf_gradient` |
| `transform.py` | 271 | already a pure delegation shim |
| `smooth.py` | 267 | already a pure delegation shim |
| `constraints.py` | 235 | already delegating; NamedTuple wrappers only |
| `overlap.py` | 176 | already a pure delegation shim |
| `projections.py` | 127 | already a pure delegation shim |
| `__init__.py` | 202 | re-export table + 2 static constant tuples + `sdf_gradient` |
| `kicad_transform.py` | 164 | **Python**, deliberately and already documented |
| `drc_inflate.py` | 228 | **Python** — the only genuinely unmigrated compute |

So the residual compute surface was one module, and the work was to decide,
per function, what could be moved with a *proof* rather than a hope.

### Verdicts

**MIGRATED** (Rust: `src/drc_inflate.rs`, bound in `src/bridge.rs`):
`_smooth_relu_array`, `compute_inflated_half_dims_from_bounds`,
`compute_drc_proxy_score`.

**JUSTIFIED-KEEP, named blocker — GEOS buffer**: `inflate_pad_polygon`,
`precompute_inflated_dims`, `precompute_from_pad_polygons`.

Shapely's `buffer(r, resolution=16)` is GEOS's *polygonal approximation* of the
round Minkowski offset. It is tempting to assume the inflated bounds are just
`bounds ± r` — the extreme of a disk offset is axis-aligned — and to "port" the
function as four additions. Measured at `ebf9326ff` over random polygons:

| corpus | bit-mismatches vs `bounds ± r` | worst deviation |
|---|---:|---:|
| general polygons (3-8 vertices) | 169 / 169 | 2.4e-3 mm |
| axis-aligned rectangles | 12 / 400 | 8.9e-16 mm |

2.4e-3 mm is three orders of magnitude above a rounding artefact and about 1%
of a 0.2 mm clearance — the approximation is visible at the scale this module
works at. Reproducing it means vendoring GEOS's buffer algorithm; approximating
it is a behaviour change that a differential over shipped fixtures would not
catch, which is the judgment PR #688 made about keeping `yaml.safe_load` on the
Python side. The measurement is pinned by
`tests/geometry/test_drc_inflate_rust_differential.py::TestGeosBlockedSurfacesStayPython`,
which fails if GEOS ever *does* match the closed form — so the verdict is
re-decidable rather than folklore.

**JUSTIFIED-KEEP, named blocker — Python callable argument**:
`sdf.py::sdf_gradient` and `__init__.py::sdf_gradient` take an arbitrary Python
`sdf_fn` and evaluate it at four probe points. Moving the finite-difference
stencil to Rust would put a Python call inside the inner loop, so the boundary
crossing grows rather than shrinks. Already documented in `sdf.py`'s own
docstring at base; recorded here so it carries a verdict.

**JUSTIFIED-KEEP, unchanged**: `kicad_transform.py`. Its module docstring
already argues the case (a two-line scalar formula is not worth a per-call FFI
crossing) and the drift risk is already closed by
`tests/geometry/test_kicad_transform_rust_differential.py`, which pins it
against this crate's `rotate_local_to_world`. Phase 4 re-examined and upheld
it; nothing changed.

**RETIRED**: the previous `drc_inflate.rs` carried functions named
`inflate_pad_polygon`, `precompute_inflated_dims` and
`precompute_from_pad_polygons`, exported through pyo3 under those names. They
had no caller anywhere in the repo, in Rust or Python, and they were *not* the
Python semantics: `inflate_pad_polygon` pushed vertices away from the centroid
instead of taking a Minkowski sum and returned vertices rather than an AABB;
`precompute_inflated_dims` took a `(width, height)` pair where the Python
function takes a list of polygons. A caller reaching for
`temper_geometry.precompute_inflated_dims` expecting the documented Python
behaviour would have got silently different arithmetic. Dead and misleading is
worse than absent, so they went with this port. `bridge.rs`'s `vec_to_aabbs`
helper existed only to feed them and went too.

### Verification by induction — `pairwise_sum`

`compute_drc_proxy_score` ends in `np.sum`, and `np.sum` is **not** a
left-to-right accumulation: it is numpy's blocked pairwise reduction. Float
addition is not associative, so the reduction order is part of the result.
Measured on this repo's corpora, `np.sum` and naive accumulation disagree at
n = 8, 16, 129, 300 and 4950. The Rust port therefore transcribes numpy's
algorithm rather than approximating it.

*Base case.* For `n < 8` the algorithm is defined to be naive left-to-right
accumulation, and the port is literally that loop. Verified exhaustively for
n = 0..7 (`pairwise_sum_small_inputs_are_naive`).

*Induction step.* Two cases.

1. `8 <= n <= 128`. The reduction is a fixed, finite expression over the input:
   eight accumulators seeded from `a[0..8]`, an 8-strided loop over
   `a[8 .. n - n%8]`, the fixed tree `((r0+r1)+(r2+r3))+((r4+r5)+(r6+r7))`, then
   a naive tail over the final `n % 8` elements. There is no recursion, so
   correctness here is by construction from the transcription and needs no
   hypothesis.
2. `n > 128`. The result is `pairwise_sum(a[..n2]) + pairwise_sum(a[n2..])`
   where `n2 = (n/2) - (n/2) % 8`. Both halves are strictly shorter than `n`
   (for `n > 128`, `n2 >= 56` and `n - n2 <= n - 56 < n`), so the induction
   hypothesis applies to each, and the outer `+` is a single f64 addition
   fixed by the split point. The split point depends only on `n`, so the
   partition — and hence the association tree — is identical to numpy's.

Since every input length falls into exactly one of these three cases and each
either terminates or reduces to strictly shorter inputs, the reproduction is
exact for all n. Empirically confirmed against `np.sum` for every n in
0..300 plus 500, 1000, 4950 and 10000: zero bit-mismatches.

### Verification by induction — dtype width

The pre-migration pipeline is **dtype-polymorphic**: the pairwise gap
arithmetic runs in the caller's numpy dtype (float32 at every shipped call
site — see `tests/geometry/test_drc_inflate.py`) and only widens to float64 at
the softplus. Computing the gaps in f64 would be numerically close and
bit-wrong.

The port does not carry a separate f32 code path. It computes in f64 and
rounds through `f32` after each operation whose numpy result dtype is float32
(`round_to`). That is exact, not an approximation:

*Base case.* Every geometry-side operation in this module is `+`, `-`, `abs`,
`min` or `max` on values already exactly representable in f32. For those,
the f64 result of a single operation on f32 operands is itself exact (no
rounding occurs at f64 width), so rounding that exact value to f32 gives
precisely what f32 arithmetic would have produced.

*Induction step.* Each intermediate is the output of one such operation on
values that the previous step already narrowed to f32, so the base case
applies again at every step and the invariant "every f32-typed intermediate
holds exactly its f32 value" is maintained through the whole chain.

The one place this needs care is the weak scalar: numpy's NEP-50 promotion
casts a Python float to the *array's* dtype before the operation. Adding the
f64 literal and then narrowing is not the same as narrowing first — for
`bound = 0.14703835546970367` and `trace_width = 0.1` the two orders differ.
`inflated_half_dims_from_bounds` narrows the trace width first, and both the
Rust unit test and the differential pin the discriminating case.

The promotion is tracked per operand rather than per call, because numpy
promotes per operation: a gap is f32 only when both of its operands are, and
`distances` (through `np.where`) is f32 only when both gaps are.

### `np.minimum` / `np.maximum` are not `f64::min` / `f64::max`

numpy's form is `(a < b || isnan(a)) ? a : b`, which propagates a NaN in
*either* operand. Rust's `f64::min`/`f64::max` discard NaN and return the other
operand. The port uses numpy's form. Only the `np_maximum` NaN path is
reachable from `drc_proxy_score` — the `np_minimum` call is guarded by
`gap_x < 0 && gap_y < 0`, which is False whenever a gap is NaN — and the
differential pins that reachable path with NaN and +/-inf positions.

### Empirical verification

`tests/geometry/test_drc_inflate_rust_differential.py` — 91 bit-exact
assertions against `_drc_inflate_py_oracle.py`, a verbatim copy of the module
at `ebf9326ff`. Floats are compared via `float.hex()`, never a tolerance, and
every leaf carries its concrete `type` in the comparison key so an int/float
swap or an f32/f64 width change cannot hide behind numeric equality. Coverage:
the full float32 x float64 dtype matrix, four mixed-dtype combinations,
n = 0,1,2,3,4,5,9,13,20,40 (straddling numpy's 128-element blocksize and its
8-way unroll), a clearance x beta grid, dense all-overlapping placements,
coincident and zero-size components, subnormal/infinite/NaN softplus inputs,
and the `n < 2` return-type asymmetry (a 0-d `ndarray`, where `n >= 2` returns
`np.float64` — oracle behaviour, preserved rather than fixed).

`tests/geometry/test_drc_inflate_pbt.py` — 7 properties and 6 metamorphic
relations, each carrying an explicit anti-vacuity witness, plus a
`TestPropertiesAreFalsifiable` class that feeds each assertion a deliberately
wrong value and requires it to fail.

Metamorphic relations: translation (bit-exact, integer coordinates),
translation with general reals (approximate — see below), reflection in x/y/
both (bit-exact), 90-degree rotation as a coordinate *and* dimension swap
(bit-exact), permutation (tight tolerance — see below), and power-of-two scale
on the half-dims (bit-exact).

Two of those tolerances are statements about the implementation, not hedges:

* **Permutation is not bit-exact.** Relabelling components permutes the
  summands, and the blocked pairwise reduction is order-dependent. Claiming
  exactness here would be claiming something false.
* **Translation is exact only for exactly-representable shifts.** Translating
  `[0,0], [1e-6, 0]` by 1024 rounds the second coordinate, changes the computed
  gap, and moves the score in its last three hex digits. This is inherited
  arithmetic — the pre-migration numpy implementation does exactly the same
  thing, verified — not a porting defect. M1 therefore generates integer
  coordinates so it can assert on the bits, and M1b states the general-real
  case separately so M1's exactness claim cannot quietly be weakened into it.

### Anti-vacuity (mutation campaign)

Eight mutations of the Rust kernel, each rebuilt and run against the full
differential + PBT suite (baseline 109 passed / 0 failed):

| # | Mutation | Result |
|---|---|---|
| M1 | naive accumulation instead of the pairwise split | 3 failed |
| M2 | drop f32 narrowing in `round_to` | 26 failed |
| M3 | `np_maximum` instead of `np_minimum` in the overlap branch | 17 failed |
| M4 | `f64::max` instead of `np_maximum` | 2 failed |
| M5 | widen the trace width before adding instead of narrowing first | 1 failed |
| M6 | drop the `n % 8` guard on the unrolled loop bound | 38 failed |
| M7 | hard-code alpha = 10.0 instead of using `beta` | 10 failed |
| M8 | halve before inflating instead of after | 16 failed |

M4 and M5 **survived the first pass** — the differential had no NaN/inf input
and no trace-width/bound pair that discriminated the two rounding orders. Both
gaps were closed with targeted cases before the campaign was re-run; the table
above is the re-run. This is the whole point of mutating: two of eight gates
were not measuring what they claimed until they were shown a mutant they let
through.

### Performance A/B (R1b)

Measured darwin/arm64, release build, median of 9 after 3 warmups
(`benchmarks/perf_ab.py`):

| stage | rust / oracle | reading |
|---|---:|---|
| `drc_proxy_score` (40 components, 780 pairs, float32) | **0.195** | 5.1x faster |
| `smooth_relu_array` (4096 samples) | **1.890** | 1.9x *slower* |

The second number is reported rather than buried. The kernel is not the cost —
the Python-list marshalling across the pyo3 boundary is. Measured crossover:

| n | rust total | numpy | `.tolist()` alone | ratio |
|---:|---:|---:|---:|---:|
| 16 | 1.46us | 6.33us | 0.29us | 0.230 |
| 256 | 11.96us | 11.12us | 2.63us | 1.075 |
| 4096 | 203.25us | 110.12us | 42.92us | 1.846 |
| 65536 | 3760.29us | 2066.25us | 704.33us | 1.820 |

Rust wins below n ~= 256 and loses above it, with `.tolist()` alone accounting
for ~40% of the Rust arm at 4096. This does not affect the migration's value:
`_smooth_relu_array` is a private helper whose only production caller was
`compute_drc_proxy_score`, and the migrated `compute_drc_proxy_score` does not
call it — it runs the whole O(n^2) pipeline in Rust, crossing the boundary with
3n floats instead of n^2. It is kept Rust-backed anyway because the numpy
formulation was a hand-transcribed copy of `smooth.rs`'s branch split (its own
docstring said so), which is the duplicated-formula hazard that
`kicad_transform.py` exists to prevent.

Removing the marshalling cost means moving this crate's FFI convention from
flat `Vec<f64>` to the buffer protocol. That is a crate-wide change affecting
30+ bindings and contradicts the C7 FFI audit's settled convention, so it is
recorded as a measured, deferred optimisation rather than done here.

**Baseline capture is outstanding.** Both new `_BENCHMARKS` entries have no row
in `power_pcb_dataset/metrics/perf_ab_baseline.jsonl`, so `pr_perf_compare.py`
fails closed with NO_BASELINE. That is deliberate: `perf_ab.py`'s own guidance
is that a darwin-captured baseline is *worse* than none (a consistent -11%
platform bias would make the gate miss every regression between +20% and +35%
while reporting spurious improvements). The rows must be taken from this PR's
own CI "Run the performance A/B (PR branch)" step and committed before merge.

### R1h — physics gating

N/A. Nothing in this module is physics-gated. `compute_drc_proxy_score` is a
differentiable *proxy* loss for optimisation, not a manufacturing or safety
rule: it has no threshold, produces no verdict, and gates nothing. The R24
discipline applies to CP-SAT physics constraints; there are none here.

## Zone Pour Emission Geometry (`zone_pour.rs`) — Wave 4, 2026-08-06

Ports three kernels from `router_v6/zone_emission.py` and
`router_v6/_zone_pour_stitch.py`: `emit_zone_s_expr` (string formatting),
`_chamfer_path_points` (90-degree-turn chamfering), and the point-in-polygon
+ nearest-boundary-vertex geometric core of `_stitch_isolated_pads`
(`stitch_targets_py`, replacing `shapely.Polygon.contains`/`.touches` and
`scipy.spatial.cKDTree`).

### Verification by Induction

**`emit_zone_s_expr_py`.** Base case: a 3-point triangle with all-zero
numeric fields (`net_number=0`, `clearance=0.0`, `priority=0`,
`min_thickness=0.0`) — the output is a single format! expansion with no
branch taken, checked byte-for-byte against the oracle
(`test_emit_zone_s_expr_matches_oracle_edge_cases`). Induction step: each
additional polygon point contributes one more `(xy {x:.4} {y:.4})` segment,
joined by a single space, independent of every other point's value or the
scalar fields — string concatenation of independently-formatted pieces has
no cross-element interaction, so N-point correctness follows from 1-point
correctness by structural induction on `points`. `{:.4}` (Rust) and `.4f`
(Python) are both correctly-rounded decimal-digit-selection algorithms
applied to the same f64 bit pattern; they were not assumed to agree --
`test_emit_zone_s_expr_matches_oracle_random_corpus` checks 200 random
zones (including negative/near-boundary clearances and priorities up to
90) bit-exact against the oracle.

**`chamfer_path_points_py`.** Base case: paths of length 0, 1, or 2 return
unchanged (`if path_points.len() <= 2`), checked directly
(`test_chamfer_matches_oracle_edge_cases`). Induction step: each interior
point `i` is classified using only `path_points[i-1..=i+1]` (a fixed
3-point window) and emits 1 or 2 output points independent of every other
index's classification -- the chamfer decision has no accumulated state
across iterations (unlike, say, a running centroid), so per-window
correctness at every `i` implies whole-path correctness. The four boolean
guards (`prev[2] != curr[2]`, orthogonality, degenerate-length) are each
independently exercised by a crafted case in
`test_chamfer_matches_oracle_edge_cases`, and the random corpus
(`test_chamfer_matches_oracle_random_corpus`, 200 paths of 0-15 points,
random chamfer_offset in [0.01, 0.5], layer switches injected at ~15%
probability) exercises every guard in combination.

**`stitch_targets_py`.** Base case: a single pad, a single valid (>=3
point) polygon containing it -- empty output, checked directly
(`test_stitch_matches_oracle_pad_inside_zone_not_stitched`). Induction
step (containment): each pad's inside/outside classification depends only
on that pad and the polygon set, not on any other pad -- per-pad
correctness composes to whole-batch correctness by construction (the loop
carries no state between pads). Induction step (nearest-vertex): each
outside pad's nearest vertex is a linear scan over the flattened,
polygon-order-independent vertex list; extending that list with one more
polygon's vertices cannot change the answer unless one of the new vertices
is strictly closer, which is exactly what the `d < best_d` update tests --
so correctness for `k` polygons implies correctness for `k+1`. The
`len(pts) >= 3` polygon filter (dead-vertex-list rejection) is checked
directly (`test_stitch_matches_oracle_polygon_with_too_few_points_skipped`,
`test_stitch_matches_oracle_empty_zone_points_skipped`).

Containment reuses the already-shipped, already-verified
`polygon::point_in_polygon_winding` rather than a second predicate --
its own on-edge/on-vertex behaviour is covered by that function's existing
unit tests (`polygon.rs`, `test_point_in_polygon_on_edge`/`_on_vertex`).

### Empirical Verification

`packages/temper-placer/tests/router_v6/test_zone_pour_geometry_rust_differential.py`,
16 tests, all green against the pinned oracle
(`_zone_pour_geometry_py_oracle.py`, verbatim at
`a920657f2d4fa2f56b24d71f3ae558dd244dc0fc`): 200-case random corpora for
`emit_zone_s_expr` and `_chamfer_path_points`, a 60-trial multi-cluster
random corpus for `_stitch_isolated_pads` (including shared-tstamp-counter
state), plus crafted edge cases (empty/degenerate polygons, quoted net
names, negative-zero coordinates, non-eligible nets). Comparison is by
`tests/router_v6/_signature.sig` -- bit-exact, type-carrying, no tolerance.

**Mutation testing (anti-vacuity).** Each kernel was mutated, rebuilt, and
confirmed to fail a *named* test; reverted and confirmed `git diff` clean
before continuing:

| kernel | mutation | named test that failed |
|---|---|---|
| `emit_zone_s_expr` | `min_thickness` format precision `.4` -> `.3` | `test_emit_zone_s_expr_matches_oracle_random_corpus`, `test_emit_zone_s_expr_matches_oracle_edge_cases` |
| `chamfer_path_points` | short-segment skip guard `2.0 * chamfer_offset` -> `1.0 * chamfer_offset` | `test_chamfer_matches_oracle_random_corpus` |
| `stitch_targets` | inverted containment branch `if inside_any` -> `if !inside_any` | `test_stitch_matches_oracle_pad_outside_zone_gets_trace` (+3 others) |

**Wiring proof.** A `panic!("WIRING_PROOF_SENTINEL: ...")` was temporarily
inserted into each of the three `catch_unwind` closures, the extension
rebuilt, and each SHIPPED entry point invoked directly (not through a
test): `zone_emission.emit_zone_s_expr`, `_zone_pour_stitch.
_chamfer_path_points`, `_zone_pour_stitch._stitch_isolated_pads`, and the
top-level `_zone_pour_stitch._emit_zone_pours` orchestrator that
production's `route_pcb()` calls. All four raised `RuntimeError:
WIRING_PROOF_SENTINEL: <symbol>`, proving the panic propagates from the
Rust kernel through the shipped Python call chain, not just through the
differential's direct `temper_geometry.<symbol>` calls. Reverted; `git
diff` against the committed Rust source was empty.

### Known, recorded divergence: nearest-vertex tie-break

`stitch_targets_py` resolves exact nearest-vertex distance ties by
"first-strictly-smaller-wins" over the flattened, polygon-order vertex
list. Measured against `scipy.spatial.cKDTree.query`: of 2000 randomized
tie-forced queries (coordinates rounded to 1 decimal specifically to
manufacture ties), cKDTree picked a different tied vertex in 2 cases,
because its answer depends on its internal space-partitioning traversal
order, not input order. Reproducing that traversal bit-for-bit would mean
re-deriving scipy's `cKDTree` splitting rule -- out of scope for this
migration. Unreachable in practice: it requires an EXACT float64 distance
tie between two distinct pour-boundary vertices, a measure-zero event for
placement/routing-derived board coordinates. Demonstrated directly (not
routed through the full `_stitch_isolated_pads` composition, where
constructing a real-geometry tie proved incidental to the point) in
`test_tie_break_class_exists_direct_cKDTree_comparison`.

### `_cluster_positions`: MIGRATED (2026-08-07) -- was JUSTIFIED-KEEP, premise did not survive re-triage

Previously JUSTIFIED-KEEP as a scipy library boundary in the same class as
KTD8/KTD9 -- "the Ward-linkage NN-chain / Lance-Williams recurrence is a
specific numerical algorithm to reimplement and independently validate
bit-exact against scipy's own `_hierarchy.pyx`, not a closed-form
transcription." `docs/evidence/2026-08-07-scipy-keeps-re-triage.md` re-ran
that premise against the actual call sites (not the docstring) and found it
did not survive scrutiny: `compute_zones_for_net` reduces every returned
group to its own independent convex hull immediately -- nothing downstream
reads a cluster label or scipy-internal cluster id, and
`test_zone_emission.py`'s `TestDataInformedClustering` asserts only cluster
*count*. The exactness bar this JUSTIFIED-KEEP was written against
(bit-exact scipy internal tie-break reproduction) was never the actual
contract.

`docs/evidence/2026-08-07-zone-emission-clustering-kodama-port.md` ported
`_cluster_positions` to `hierarchical_clustering.rs` (`kodama` crate, Ward
linkage) after a differential spike, not by assumption:

- `kodama`'s raw Ward dissimilarity values are bit-exact to scipy's own
  `Z[:, 2]` column on every case checked (verified to full `f64` precision
  printed, not just "close").
- `kodama` has no `fcluster` equivalent; this port's own flat-cut
  reconstruction (union-find over `kodama`'s `Dendrogram` steps) initially
  used a `<` boundary comparison and mismatched scipy's partition on 4 of 12
  real HighVoltage-class production-board nets -- traced to scipy's
  `fcluster(criterion="distance")` treating a merge exactly AT the cut
  threshold as INCLUDED (verified empirically:
  `fcluster(Z, t=t, ...) == fcluster(Z, t=t+1e-9, ...) !=
  fcluster(Z, t=t-1e-9, ...)` for a merge whose height is bit-exactly `t`).
  Switching to `<=` reproduced scipy's partition exactly on all 12 real
  nets, 300 synthetic clustered-data trials, and 6 symmetric/degenerate
  stress configurations (perfect square, grid, duplicate points, collinear,
  hexagon, two well-separated squares) -- 0 mismatches after the fix.
- Emitted zone geometry (convex hull, clipped to the board outline) is area-
  identical between the two arms on every real board net tested (0.00 mm^2
  difference), not merely "within tolerance."
- `kodama` builds for `wasm32-unknown-unknown` with zero extra dependencies
  or feature wiring, verified directly.

See the evidence doc for the full differential, real-board numbers, and the
port decision. `_convex_hull_from_positions`'s `buffer()` step below is a
separate, unrelated GEOS boundary and is unaffected by this port.

### JUSTIFIED-KEEP: hull-buffer geometry (not migrated)

`_convex_hull_from_positions`'s `shapely.buffer(margin, join_style=2)` step
(GEOS mitre-join polygon offsetting) was evaluated and NOT migrated:

- **`_convex_hull_from_positions`'s `buffer()` step**: measured directly
  (offline, not committed as a test) against an analytic mitre-offset
  reimplementation (outward-normal edge offset + adjacent-offset-line
  intersection per vertex, matching GEOS's winding convention once its
  hull output was observed to be clockwise, not the textbook CCW):
  agreement to ~1e-13 (float noise, NOT bit-exact) on 181/200 random
  convex hulls, with the remaining ~10% diverging in VERTEX COUNT
  (mitre-limit beveling, GEOS's exact rule unconfirmed against the
  analytic model). Same divergence class as this file's own
  `drc_inflate.rs`-documented `buffer(r, resolution=16)` JUSTIFIED-KEEP
  (round join instead of mitre join, same GEOS boundary, same conclusion).

Stays on `_convex_hull_from_positions` in `zone_emission.py`, unchanged,
calling live `shapely`. Re-decidable per the discipline contract's residual
procedure: a future spike with a validated from-scratch GEOS-mitre-buffer
implementation can reopen this boundary.

### PBT / Metamorphic Coverage

Not added as a separate suite in this slice -- the differential's 200-case
random corpora (per kernel) plus the crafted edge-case sets serve the same
falsification role for these three kernels, which have no free parameters
beyond their direct inputs (no thresholds, no iteration counts, no solver
state) for a property suite to usefully vary independently of the
input-shape coverage the differential already has. Recorded here rather
than silently omitted, per the discipline contract's "reported and
recorded, not faked" rule.

### R1h — physics gating

N/A. Zone/pour emission is KiCad output geometry, not a manufacturing or
safety rule; it has no threshold and produces no pass/fail verdict.

## Channel Skeleton Medial-Axis (`channel_skeleton.rs`) — Wave 4, 2026-08-07

Ports `_extract_medial_axis` / `_extract_medial_axis_single`
(`router_v6/channel_skeleton.py:181-349`) -- boundary sampling, a Voronoi
diagram, the interior-edge filter, and both fallback branches.

### Why this was previously BLOCKED, and what changed

Three prior documents (most recently
`docs/evidence/2026-08-07-channel-skeleton-triage-no-port.md`, PR #870)
recorded this file as BLOCKED. The block was never the shapely/GEOS
Voronoi itself -- the 2026-08-04 spike
(`docs/evidence/2026-08-04-shapely-voronoi-channel-skeleton-spike.md`)
measured an independent (Qhull) Voronoi reproducing the GEOS skeleton to
<1e-9mm on 12/12 synthetic boards. The actual blocker was
`constraint_model.py`: SAT channel-edge identity came from
`enumerate(skeleton.graph.edges)` (networkx INSERTION ORDER) plus the raw
float `repr()` of both endpoints -- unsatisfiable by any reimplementation,
bit-exact geometry or not.

`fix/constraint-model-edge-identity` (not yet on `main` as of this port;
branched from directly) fixes the consumer: `canonical_channel_edges()`
now derives identity from endpoints quantised to 1e-6mm, ordered by that
quantised key, with the positional index retained only as a tie-break.

### Independent verification of the unblock, before porting

Re-ran (not inherited) the spike's central claim, first with the spike's
own Qhull-substitution harness extended to the NEW 1e-6mm quantum and to
`canonical_channel_edges()`-style ids computed independently over a
GEOS-built graph and a Qhull-built graph:

| Check | Result |
|---|---|
| Node-set match at 1e-6mm (6dp) | 12/12 boards |
| `canonical_channel_edges()` ids identical, GEOS-graph vs Qhull-graph | 12/12 boards |

Then again against the ACTUAL Rust (`spade`) build, in
`tests/router_v6/test_channel_skeleton_rust_differential.py`
(`test_rust_reproduces_geos_node_set_at_1e6mm_quantum`,
`test_canonical_channel_edges_identical_rust_vs_python`): same result,
12/12 boards plus a holes-bearing board and a simple box, all against the
shipped Rust path, not a Python stand-in.

### Implementation: `spade` instead of GEOS

Uses `spade` (Delaunay triangulation via `undirected_voronoi_edges()`,
`robust`-crate exact circumcenter predicates) -- an independent, non-GEOS
implementation, the class of crate the spike's §7 named as the parity
target (`voronator`/`spade`/`geo`). The interior-edge filter reuses
`polygon::point_in_polygon_winding` (already shipped) rather than
reimplementing GEOS's `polygon.buffer(1e-3)` + `prepared.contains()` --
measured to agree with the buffered-GEOS reference on all 12 boards tested
(see the differential); a true polygon-offset reimplementation was judged
unnecessary given that agreement, not attempted.

`sample_boundary_points` replicates CPython's `(dx**2+dy**2)**0.5` via
`host_math::pow` (NOT `f64::sqrt`, and NOT `math.hypot` -- this file never
calls `hypot`) and the `int(dist)` truncation-toward-zero (matches Rust's
`as i64` cast for the non-negative domain here, written explicitly per
this crate's documented `int()`-truncation trap). The fallback cross
pattern reuses `creepage_check::py_min` for CPython `min()` NaN semantics.

### Scope: what stays in Python (JUSTIFIED-KEEP for this pull)

- `_ensure_skeleton_connectivity` -- `nx.Graph` bookkeeping, an O(n^2)
  nearest-pair search over networkx node/component objects. The one
  arithmetic expression inside it (Euclidean distance) is a one-line
  expression embedded in graph traversal; marshalling the whole
  component/node structure across FFI per call is the "per-call boundary
  can be net-negative" trap this repo's Wave 4 notes measured elsewhere.
- `ChannelSkeletonStage` / `validate_channel_skeleton` -- pipeline `Stage`
  / `@register_validator` orchestration wiring.
- `extract_channel_skeleton`'s pad-anchoring block -- dict/list
  bookkeeping over `ParsedPCB.components`/`pins`.

`simplify_tolerance` is threaded through the Rust signature for parity but
is a documented no-op: GEOS's Voronoi edges on this path are always
exactly 2 coordinates (2026-08-04 spike §8), and spade's undirected
Voronoi edges are likewise always two circumcenters -- Douglas-Peucker
simplification of a 2-point line is the identity either way.

### Anti-vacuity (mutation campaign, 2 mutants, 2 killed, 0 survivors)

| Mutation | Rebuilt? | Named tests killed | Reverted + rebuilt clean? |
|---|---|---|---|
| Interior-edge filter forced to `true \|\| ...` (accept every Voronoi edge, not just interior ones) | Yes | `test_rust_reproduces_geos_node_set_at_1e6mm_quantum`, `test_rust_and_geos_edge_counts_agree`, `test_canonical_channel_edges_identical_rust_vs_python`, `test_canonical_channel_edges_identical_with_holes` (4) | Yes |
| Boundary-sampling density off-by-one (`dist as i64 + 1`) | Yes | all 4 above plus `test_canonical_channel_edges_identical_on_simple_box` (5) | Yes |

Each mutation was verified with `python -c "import temper_geometry"`
after every `maturin develop --release` (the stale-dylib build hazard:
`maturin develop` exits 0 on a stale cache with only a warning) before
running the differential, and reverted-then-REBUILT (not just reverted)
before declaring green, per this crate's anti-vacuity convention.

### Not attempted / unverified

- Cross-platform / cross-`spade`-version stability: measured on
  darwin/arm64 only, mirroring the spike's own stated scope limit for
  GEOS.
- Real (non-synthetic) `.kicad_pcb` routing areas: the differential corpus
  is the spike's synthetic degenerate-geometry generator (axis-aligned
  board minus axis-aligned pad rectangles), not boards pulled from the
  `power_pcb_dataset` fixtures. Chosen deliberately to match the spike's
  own measurement basis for the 1e-9mm/1e-6mm claims being re-verified;
  not extended to real boards in this pull.
- `_ensure_skeleton_connectivity`'s bridging path is exercised (several
  differential boards produce disconnected islands and bridge, visible in
  the `DEBUG: Added bridge` output) but not independently stressed beyond
  what the 12-board sweep produces.

### R1h — physics gating

N/A. Medial-axis skeleton extraction is routing-channel geometry, not a
manufacturing or safety rule; it has no threshold and produces no
pass/fail verdict.

---

## Validator Geometry Helpers (`geometry_kernels.rs`) — Verification by Induction (Wave 4)

Migrates all 12 kernels of `temper_placer/requirements/validators/_geometry.py`
— the shared PCB-layout-validation geometry helpers. The module is now a
delegation shim; every kernel computes in `temper-geometry`.

### Base Case: 3-4-5 triangle and a single cell

- `_distance((0,0),(3,4))` = `py_hypot` of (3,4) = `5.0` — the Rust kernel
  and the pinned `math.dist` oracle agree bit-for-bit.
- `_point_in_rect((5,5), (0,0,10,10))` wires `Rect::contains_point`, whose
  comparisons and `x + w` arithmetic are identical to the reference's
  chained comparison.
- `_segments_intersect` on the crossing pair `(0,0)-(10,10)` ×
  `(0,10)-(10,0)` returns True; `_segment_to_segment_distance` returns
  `0.0`; `_polyline_length` of one segment equals the segment's `math.dist`.

### Induction Step

Every kernel is a fold or a closed form over **independent per-element
computations** with no cross-element interaction:

1. **Per-segment folds.** `_point_to_polyline_distance`,
   `_segment_to_segment_distance`'s candidate min, `_polyline_min_distance`
   and `_polylines_intersect` iterate independent segment/segment-pair
   results (min/any/sum over closed-form per-pair values). Appending a
   segment evaluates the same formula on the new pair without perturbing
   prior results, so correctness on n elements lifts to n+1 by the
   associativity/commutativity of the fold. `_polyline_length` is a
   Neumaier-compensated `sum()` (CPython 3.12 `builtin_sum_impl`, shared
   with `area_sufficiency.rs`) over per-segment `math.dist` values — the
   compensation accumulator is element-independent; the two degenerates
   (`len < 2` → `0.0`) are guarded.
2. **Per-point/segment closed forms.** `_distance` (`py_hypot`),
   `_point_to_segment_distance`, `_orientation`, `_on_segment`,
   `_segments_intersect`, `_point_in_rect`, `_rects_overlap` are
   straight-line arithmetic/comparison expressions over their arguments —
   no iteration, so base-case exactness is exactness for every input. The
   reference's arithmetic order is preserved verbatim (`len2 < 1e-12`
   degenerate threshold, min-then-max `py_min(1.0, t)`/`py_max(0.0, …)`
   NaN clamp, sign-based `(o > 0) != (o > 0)` orientation test with `1e-9`
   epsilon, negation-form `_rects_overlap` whose NaN `<` comparisons make
   it True where `AABB::intersects` would return False).

**Not de-duplicated:** the point/segment kernels here differ from
`drc_constraints_geometry.rs`'s (degenerate threshold `1e-12` vs `1e-10`;
sign-based vs 0/1/2 orientation code; `1e-9` vs `1e-10` epsilon;
epsilon-padded vs plain `_on_segment` box). Reusing the DRC kernels would be
a silent behaviour change; each reference is preserved as written.

### Empirical verification

- Differential suite
  (`packages/temper-placer/tests/requirements/validators/test_geometry_rust_differential.py`):
  all 12 kernels pinned bit-exactly against the verbatim `_oracle_*` copy
  of the pre-migration module — randomized point/rect/segment/polyline
  corpora, adversarial magnitudes, subnormal-band (B8), NaN/inf parity,
  structured edge cases (collinear, touching, T-junctions, degenerate
  `1e-12` threshold boundary), and the Neumaier discriminator. Direct Rust
  pins + shim-level assertions both green (384 tests).
- PBT (`test_geometry_pbt.py`): 6 properties (distance non-negativity +
  exact symmetry; point-to-segment endpoint bound; segment-to-segment = the
  4-candidate min with 0-iff-intersect; point-to-polyline = per-segment
  min; polyline-min = per-pair min with 0-iff-crossing; far-point absorption
  monotonicity) + 5 metamorphic relations (M1 exact power-of-two translation
  invariance, M2 overlap commutativity, M3 segment reversal within 1e-9
  relative on the projection arm only — the degenerate arm is deliberately
  excluded because the reference's `return distance to a` breaks reversal,
  M4/M5 exact integer-coordinate translation), each property with a vacuity
  guard proving a degenerate mutant violates it (17 tests).
- The pre-existing validator suites
  (`packages/temper-placer/tests/requirements/validators/*`) pass unchanged
  through the Rust-backed shim (422 tests incl. clearance, layout_review,
  switching_nodes, bypass_caps, pick_and_place, ground_plane, emi_filter,
  isolation).

### R24 physics discipline

N/A — pure Euclidean geometry with no physics-gated threshold and no
pass/fail safety verdict.

---

## Channel-Mapping Geometry (`channel_mapping.rs`) — Verification by Induction (Wave 4)

Migrates the four pure-geometry kernels of
`temper_placer/router_v6/channel_mapping.py` (Stage 4.1, map topology to
channels): `_calculate_path_length`, `_nearest_skeleton_node`,
`_is_near_skeleton`, `_nearest_terminal_order`. The orchestration
(`map_topology_to_channels`, `_extract_waypoints`,
`expand_channel_path_terminals`, layer assignment, networkx traversal)
stays in Python; the module delegates the four kernels to `temper-geometry`.

### Base Case

- `path_length` of a single segment `(0,0)-(3,4)` = `(dx**2 + dy**2) ** 0.5`
  = `5.0` (host-libm `pow` chain, not `hypot`, not `sqrt`).
- `nearest_skeleton_node` over a one-node set returns that node; over an
  empty set returns `None`.
- `is_near_skeleton` with one node exactly `tolerance` away is True
  (`dx*dx + dy*dy == tol*tol`).
- `nearest_terminal_order` of a single pad is that pad; of an empty pad
  list is `[]`.

### Induction Step

Each kernel is a fold over **independent per-element computations**:

1. **`path_length`** is a naive `+=` fold (NOT builtin `sum()` — B12's two
   summation classes are deliberately kept distinct) of per-segment
   `pow(pow(dx, 2.0) + pow(dy, 2.0), 0.5)` values; appending a waypoint
   adds one independent segment term. The per-segment `**` goes through a
   CPython-exact overflow guard (`pow_checked`, mirroring
   `escape_via.rs::pow_operator`): a finite base whose power overflows to
   infinity raises `OverflowError`, an already-infinite/NaN base does not —
   evaluated left-to-right exactly as the reference expression is.
2. **`nearest_skeleton_node`** is an argmin over independent per-node keys
   `(pow(nx-cx, 2.0) + pow(ny-cy, 2.0), (nx, ny))` under Python tuple
   comparison; the argmin key is unique for distinct nodes, so the result
   is independent of node-set iteration order (pinned by the
   insertion-order and NaN-seed tests — a NaN key never displaces a finite
   one, and a NaN seed persists exactly as Python's `min` does).
3. **`is_near_skeleton`** is an existential per-node
   `dx*dx + dy*dy <= tolerance*tolerance` scan (multiplication, not pow) —
   order-independent boolean.
4. **`nearest_terminal_order`** is a greedy loop where each step is an
   independent argmin over the remaining (de-duplicated, `set(pads)`
   semantics) pads by the key `(manhattan, pad)` — unique per remaining
   pad, so the whole sequence is iteration-order-independent.

### Empirical verification

- Differential suite
  (`packages/temper-placer/tests/router_v6/test_channel_mapping_rust_differential.py`):
  all four kernels pinned bit-exactly (and exception-for-exception) against
  the verbatim `_oracle_*` copy — randomized waypoints/nodes/pads,
  adversarial magnitudes, degenerate/NaN/inf, the `1e-12`-class
  discriminators, the pow-vs-hypot discriminator, the `OverflowError` parity
  cases (`(1e308)**2` raises in oracle, shim and Rust alike; a finite-base
  `inf ** 0.5` does not), order-independence, and the tie-break-by-
  coordinate cases. Direct Rust pins + shim-level assertions green (159
  tests).
- PBT (`test_channel_mapping_pbt.py`): 6 properties (path length
  non-negative / exact single segment / zero-iff-coincide; nearest-node
  argmin; near-skeleton ≡ existential scan; terminal order is a permutation
  of the de-duplicated pads; greedy-step nearest-of-remaining; path-length
  monotone under append) + 4 metamorphic relations (M1 exact power-of-two
  translation invariance incl. frame-translated nearest-node result, M2
  input-order permutation invariance, M3 additive-append, M4 tolerance
  monotonicity), each property with a vacuity guard (16 tests).
- The pre-existing suites (`test_channel_mapping.py`,
  `test_channel_mapping_terminal_validation.py`) pass unchanged through the
  Rust-backed shim.

### R24 physics discipline

N/A — routing-channel geometry with no physics-gated threshold.

## Spatial-DRC Cluster (`resource_bound.rs`, `power_plane.rs`, `diff_pair_inference.rs`, `trace_width_assignment.rs`, `dense_package_detection.rs`) — Wave 4

Migrates the tractable kernels of the router_v6 spatial DRC/connectivity/
capacity cluster (5 modules): the resource-exhaustion bound
(`resource_bound.py`), the power-plane geometry (`power_plane.py`), the
differential-pair suffix matcher (`diff_pair_inference.py`), the trace-width
classifier (`trace_width_assignment.py`), and the dense-package classifiers
(`dense_package_detection.py`). Each Python module keeps its public API and
delegates the migrated kernels; the object-graph orchestration
(`ParsedPCB`/`Board`/`Component`/`PathfindingResult`/`OccupancyGrid` access,
the `Stage`/validator framework, the dataclasses) stays in Python.

### Verification by Induction — `resource_bound.rs`

The bound is a composition of four per-net / per-cluster folds over
independent elements:

1. **`conflict_clusters`** — pairwise overlap decisions over the net set.
   Each pair `(i, j)` contributes an independent edge decision
   `min(area_a, area_b) > 0 && overlap / min_area > threshold`; no pair's
   decision depends on any other pair, so adding a net only adds its O(n)
   pair terms. Cluster *membership* is then the connected components of that
   graph — order-independent — and the outer cluster discovery order is the
   input order of first occurrence, exactly the reference's.  Bit-exactness
   requires Python-builtin `min`/`max` semantics (class B5): `area =
   py_max(product, 0.0)` (product first), `overlap_x = py_max(0.0,
   py_min(ax2,bx2) - py_max(ax1,bx1))`.
2. **`capacity_in_bbox`** — per-cell counting over the grid region with a
   per-dimension clamp. Each row's cells are independent; `world_to_grid`
   truncates toward zero (`as i64`) matching `int()`, and the clamp is
   builtin `max(0, min(g, W-1))` on ints.
3. **`fill_factor`** — `sum(bbox_areas.values())` is CPython builtin `sum()`
   (Neumaier-compensated, class B12) over dict insertion order, then
   `np.sqrt` (correctly-rounded IEEE sqrt) and `np.clip(x, 0.01, 1.0)`
   = `np.minimum(np.maximum(x, lo), hi)` (class B12 NaN semantics).
4. **`demand_budget` / `max_routable`** — per-cluster greedy bin-packing.
   Each cluster's `k` depends only on its own union-bbox capacity and
   sorted demands; the per-cluster `total_capacity += capacity` fold is over
   clusters in the deterministic outer discovery order (matching the
   reference's dict-order iteration), and `total_demand` is builtin `sum()`
   (Neumaier) over input order.

The differential suite pins all four levels bit-exactly (see below),
including the cluster *partition* and the reference's set-iteration
nondeterminism: the reference's intra-cluster ordering is hash-seed
dependent, so the kernel returns each cluster sorted and the differential
compares the normalized form, while every downstream aggregate
(`total_capacity`, `max_routable`, `utilization`) is pinned exactly.

### Verification by Induction — `power_plane.rs`

1. **`rect_polygon`** — no arithmetic; a fixed 4-corner vertex list.
2. **`power_pour_strips`** — a per-strip arithmetic fold:
   `strip_width = (total_width - total_gap) / n` with
   `strip_x_min = x_min + i * (strip_width + gap)`,
   `strip_x_max = strip_x_min + strip_width`, ops copied left-to-right
   (class B7, no reassociation). Each strip depends only on its index and
   the shared strip width; the two ValueError branches are CPython-exact
   (float rendering via `py_float_str`, class B10).
3. **`thermal_via_positions`** — `side = int(round(count**0.5))`:
   `count**0.5` is CPython float `**` = host libm `pow` (class B1, via
   `host_math::pow` through `dlsym`), `round()` is round-half-even (class
   B3, via `host_math::py_round`), then `int` truncation. Positions are an
   independent per-(row,col) double loop matching the reference's
   `for row ... for col ...`.

### Verification by Induction — string kernels

`diff_pair_inference.rs`, `trace_width_assignment.rs`,
`dense_package_detection.rs` are pure string classifications with no
floating-point arithmetic except `dense_package`'s pin-distance fallback and
`trace_width`'s `power_width * 0.6`:

- **`infer_differential_pairs`** — three ordered passes over the input list;
  each net is independent (matched-set membership is a monotone predicate
  per net). `net_map = {name.upper(): name}` is last-wins (HashMap
  insert-overwrite). Base names are the UPPERCASED slices (the reference's
  `upper[:-k]`), p/n nets are the original-case names. ASCII contract
  (Python `str.upper()` replicated with `to_ascii_uppercase()`); the
  module docstring's `'USB_D'` example is stale relative to the code — the
  actual reference yields `'USB'` for `USB_DP[:-3]`, which the differential
  pins.
- **`kw_boundary_match` / `determine_trace_width`** — the regex
  `(?:^|_)kw(?:$|[\d_])` with `re.escape(kw)` and trailing `_` stripped is a
  byte-scan with boundary checks (keywords are alphanumeric/underscore, so
  `re.escape` is identity); precedence HV → power/leading `+` → gate/drive
  → default. `power_width * 0.6` uses the f64 literal `0.6`.
- **`estimate_pitch`** — the two pitch regexes are replicated by manual
  scans whose greedy `\d+\.?\d*` capture matches Python's regex engine
  bit-for-bit on the pinned footprint vocabulary (no backtracking case
  reaches a boundary where the maximal capture does not). The pin fallback
  is `pow(pow(dx,2.0) + pow(dy,2.0), 0.5)` (host libm `pow`, class B1,
  NOT `hypot`/`sqrt`) with a CPython-exact `OverflowError` guard for a
  finite base whose square overflows. Captures are plain decimals, so
  `str::parse::<f64>()` agrees with CPython `float()`.
- **`infer_package_type`** — first-hit substring scan over the fixed list,
  mapped to base families.

### Empirical Verification

- **Differential**
  (`packages/temper-placer/tests/router_v6/test_spatial_drc_cluster_rust_differential.py`):
  20 tests, all bit-exact `==` (plus `float.hex()` on the computed trace
  widths) against the verbatim `_oracle_*` copies: randomized bbox/grid
  conflict-cluster partitions and `max_routable_nets`/`demand_budget_summary`
  aggregates (Neumaier `total_demand`, per-cluster `total_capacity` fold
  order, `max(capacity, 1e-6)` utilization), randomized capacity/fill-factor
  probes incl. negative-origin grids and out-of-bounds bboxes, pour-strip
  bounds and polygons, the exact 3x3 via lattice, the CPython-exact
  ValueError messages (`py_float_str`), the diff-pair triple lists over a
  randomized net-name pool, the trace-width classification matrix, and the
  dense-package pitch/package-type cases incl. the mil conversion and the
  `OverflowError` parity.
- **PBT + metamorphic**
  (`packages/temper-placer/tests/router_v6/test_spatial_drc_cluster_pbt.py`):
  7 properties (G4 cluster-unit, every migrated module reached by at least
  one) + 5 metamorphic relations (M1 integer-translation invariance of the
  conflict partition, M2 neutral-net-addition invariance of diff pairs, M3
  power-of-two scale of the via grid, M4 pin-set independence of a parsed
  pitch, M5 power-of-two scale of trace widths) — each property with a
  vacuity guard killing a degenerate kernel (20 tests).
- The pre-existing suites for all five modules pass unchanged through the
  Rust-backed shims (74 tests: `test_resource_bound.py`,
  `test_power_plane_geometry.py`, `test_diff_pair_inference.py`,
  `test_diff_pair_constraints.py`, `test_trace_width_assignment.py`,
  `test_dense_package_detection.py`), plus `test_routing_results.py` and a
  consumer smoke of `identify_dense_packages`, `infer_differential_pairs`,
  `assign_trace_widths`, and `generate_power_planes`.
- Rust `cargo test --lib`: 628 tests green incl. the new per-module unit
  tests; `cargo clippy --all-targets` clean on the new modules.

### Known, recorded scope boundaries (JUSTIFIED-KEEP)

The remaining six modules of the cluster stay Python with evidence:

- `bundle_analyzer.py` — shapely `STRtree` spatial index,
  `MultiPoint.convex_hull`, polygon `union`; no bit-exact Rust equivalent.
- `connectivity.py` — shapely zone/pour containment predicates
  (`Polygon.contains/touches/intersects`), plus `constraints_geometry` and
  `kicad_transform` couplings.
- `obstacle_map.py` — shapely `unary_union`/`buffer`/polygon validity.
- `clearance_engine.py` — `core.net_types.VoltageClass` enum boundary and
  the `creepage_check._calculate_required_creepage` dependency.
- `layer_capacity.py` — `OccupancyGrid`/`ChannelWidths` object coupling;
  the arithmetic is trivial and object-bound.
- `via_placement.py` — duck-typed `RoutePath`/`RoutePath3D`/tree geometry
  object graph.

### R24 physics discipline

N/A — routing capacity/geometry and net-classification logic with no
physics-gated threshold.
## Core Graph/Geometry Cluster (`core_graph_geometry.rs`) — Verification by Induction (Wave 4, 2026-08-08)

Unit `core_graph_cluster`: the tractable kernels behind seven of the nine
`temper_placer/core/{graph, hypergraph, pin_geometry, power_topology,
topology, courtyard, geometry_types}.py` modules, all in one home-crate
module. `community.py` and `loop_ownership.py` are JUSTIFIED-KEEP (recorded
at the bottom of this section). Every f64 expression is a verbatim copy of
its oracle's expression shape (op count, grouping, left-to-right order —
B7); cos/sin/pow go through `host_math` (dlsym to the host CPython runtime's
libm — B1/B13); `math.hypot` is replicated as `pad_geometry::py_hypot`
(CPython 3.12 `vector_norm`, the Dekker two-step — B4); `_normalize_rotation`'s
int path writes `(i * PI) / 2.0`, the division, not `FRAC_PI_2` (B2).

### graph.py kernels — `graph_clique_expand`, `graph_batch_concat`

**Base case:** an empty netlist (`graph_clique_expand(&[], &[])`) emits no
edges — `([], [], [])`, bit-identical to the oracle's `not edge_sources`
branch. A single net with two component indices emits exactly one pair
`(i, j)` with the net's weight copied verbatim.

**Induction hypothesis:** for any netlist of k nets, the kernel emits the
oracle's edge sequence (pairs in per-net `i < j` order, weights copied).

**Induction step:** each net contributes an independent block of
`C(k, 2)` pairs computed from its own index list; no cross-net interaction.
Appending a net appends one independently-computed block, so if the kernel
matches for k nets it matches for k+1. The pair *order* matches because the
shim builds each net's index list with the oracle's exact CPython `set`
comprehension, so set-iteration order (and hence pair order) is identical on
both sides. `graph_batch_concat` shifts each edge pair by the cumulative
node count — exact int64 addition — and concatenates; the empty-`edge_flats`
dtype (int32) is reproduced in the shim to match numpy's concatenation
promotion.

### hypergraph.py kernel — `hypergraph_coo_matvec`

**Base case:** `nnz == 0` returns `vec![0.0; n_rows]`, exactly
`np.zeros(n_rows, dtype=np.float64)`. A single triplet `(r, c, d)` times a
vector yields `d * other[c]` in `result[r]` and zeros elsewhere — one
correctly-rounded f64 multiply.

**Induction hypothesis:** for any set of n triplets, the kernel reproduces
`np.bincount(row, weights=data.astype(f64) * other[col], minlength=n_rows)`
bit-for-bit (same output length — `max(n_rows, max(row)+1)` — same
extension, same negative-column wrap).

**Induction step:** each triplet contributes an independent
`data[i] * other[col[i]]` term; the scatter-add accumulates in triplet
order exactly as bincount does, so appending a triplet appends one
order-preserving contribution. The oracle's two-array structure (compute all
contributions, then accumulate) is preserved rather than fused, keeping the
accumulation order identical.

### pin_geometry.py kernels — `normalize_rotation_index`, `pin_world_position_kernel`

**Base case:** rotation index 0 → `(0 * PI) / 2.0 = 0.0`; `pin_world_position_kernel`
at theta 0 with side 0 reduces to the pure translation `(cx + px, cy + py)`
(cos(0) = 1, sin(0) = 0 exactly).

**Induction hypothesis:** for any pin offset, side and rotation, the kernel
matches `pin_world_position_at`'s mirror → R(-theta) → translate chain.

**Induction step:** the mirror (`side == 1` negates x) and the rotation
(`rx = mx*c + py*s; ry = -mx*s + py*c`, the sanctioned
`rotate_local_to_world` R(-theta) expression) are per-pin pure functions with
no cross-input interaction; cos/sin resolve through `host_math` so they equal
the reference's `math.cos`/`math.sin` bit-for-bit at every rotation, and the
final `(cx + rx, cy + ry)` additions match the oracle's own last two adds.

### power_topology.py kernels — trace widths + delivery strategy

**Base case:** 1.0 A → `required_trace_width = 1.0*0.15 + 0.1 = 0.25`; the
IPC-2221 `copper_weight_oz == 1.0` shortcut returns the same base expression.

**Induction hypothesis:** for arbitrary current and copper weight the two
width kernels and the strategy threshold reproduce their oracle expressions.

**Induction step:** all three are scalar pure functions of the rail's
`max_current_a` (plus `copper_weight_oz`); the `oz ** 0.625` term is
`host_math::pow` (libm, never `powf` lowered to `sqrt` — B13) and the
`base / pow(...)` division preserves the oracle's grouping. The strategy
thresholds are exact integer comparisons (`>= 3.0` PLANE, `>= 1.0` WIDE,
else STANDARD), including NaN/negative semantics (a NaN current falls to
STANDARD_TRACE, as in the oracle's `if` chain). The dataclass-tree traversal
(`flatten`/`find_rail`) stays Python: pure structural recursion with no
numeric kernel (structural non-applicability note per G6).

### topology.py kernel — `topology_connected_components`

**Base case:** zero or one node → a single empty / singleton partition,
matching `get_clusters`; two nodes with one edge → one two-node cluster.

**Induction hypothesis:** for any node set and adjacency edge list the kernel
yields the same partition AND group order as `get_clusters`.

**Induction step:** the partition is the mathematical equivalence closure of
the edges, independent of union order or root choice (union-find with the
same recursive path-compressed `find` as the oracle); the group ORDER is
determined by first-appearance in `self.nodes`, not by root naming, so it is
reproduced by walking nodes in input order and emitting each new component in
first-seen order. The `UnionFind` class stays Python (stateful incremental
API over arbitrary hashable keys — structural non-applicability note).

### courtyard.py kernel — `courtyard_global_points`

**Base case:** rotation 0 at position (0, 0) → the identity map
(cosp = cos(0) = 1, sinp = sin(0) = 0).

**Induction hypothesis:** for any vertex set, rotation index and position,
the kernel reproduces shapely `affinity.rotate` + `affinity.translate`
bit-for-bit per vertex.

**Induction step:** shapely 2.1.x's `rotate` (read from source) converts
degrees via `angle * pi / 180.0`, takes `cosp = cos(rad)`/`sinp = sin(rad)`
from `math`, and HARD-ZEROES either below `2.5e-16`; the kernel replicates
that exact chain, then applies the two affine passes' per-coordinate numpy
expressions (`x' = (a*x + b*y) + xoff`, including the `+ 0.0` / `1.0*` /
`0.0*` terms that preserve -0.0). Each vertex is an independent affine map,
so vertex-set cardinality is preserved and the per-vertex transforms compose
(exact quadrant rotation ladder, pinned by PBT MR16/MR17). The polygon
BOOLEAN (`intersects`/`touches`) stays with GEOS in the Python shim — a
geometry-engine library boundary, not a kernel (library-boundary note).

### geometry_types.py kernels — `point_distance`, `track_midpoint`, `pad_radius`

**Base case:** `point_distance(a, a) == 0.0` (py_hypot of (0, 0));
`track_midpoint` of a zero-length track is the point itself;
`pad_radius(0, 0) == 0.0`.

**Induction hypothesis:** for any two points / track / pad dimensions the
three kernels match `math.hypot`, `(x1+x2)/2`, and `(w**2 + h**2) ** 0.5 / 2`
bit-for-bit.

**Induction step:** each is a pure scalar function of its two inputs. `** 2`
and `** 0.5` are libm `pow` (B7/B13) resolved through `host_math`; `math.hypot`
is the Dekker `vector_norm` via `py_hypot`. String equality and numpy
construction stay Python (structural non-applicability note).

### Empirical verification

- Differential suite
  (`packages/temper-placer/tests/core/test_core_graph_cluster_rust_differential.py`,
  29 tests): every kernel pinned bit-exactly against the verbatim
  pre-migration `_oracle_*` blocks (numpy arrays as dtype/shape/tobytes;
  floats via `float.hex()`; shapely vertex sequences via hex) over a
  randomized corpus plus crafted edge cases — the empty netlist branches,
  the `batch_graphs([])` ValueError, the `Coo` length-extension and
  negative-column wrap, NaN matvec propagation, the `_normalize_rotation`
  None/int/float paths, all four courtyard quadrants and the <3-point box
  fallback, and `check_overlap`'s GEOS boolean driven through identical
  vertex transforms.
- PBT (`test_core_graph_cluster_pbt.py`, 41 tests): 8 properties P1–P8 (one
  per migrated module; every property reaches its kernel through the public
  shim) each with a mutation-test vacuity guard, plus 21 metamorphic
  relations MR1–MR21 (>= 3 per module) with per-relation exactness claims:
  exact where the transform preserves every bit (net/component/edge order
  invariance, batch associativity, single-triplet basis, zero-rotation
  translation, courtyard rotation composition/negation and vertex-shoelace
  area preservation, topology partition invariants, distance/radius
  symmetry, 1oz width consistency) and a stated tight tolerance where FP
  order genuinely matters (triplet-order summation, quadrant cos(pi/2) and
  rotation-composition bands, distance scaling).
- The pre-existing suites for all nine modules (test_graph, test_hypergraph,
  test_community, test_courtyard, test_loop_ownership, test_pin_geometry,
  test_power_topology, test_topology, test_hypergraph_factory_rust_differential)
  and the transitively-dependent consumers (tests/topological, router_v6
  net-ordering/congestion, deterministic courtyard-check/connectivity,
  physics loop-area) pass unchanged through the Rust-backed shims (1271 core
  tests + 1107 consumer tests green).

### Kept modules — R3 JUSTIFIED-KEEP (recorded)

- `core/community.py` (LOC 153; consumers: `core/__init__.py` re-exports
  `Community`/`detect_communities`; deps: networkx + python-louvain) —
  `detect_communities` runs networkx Louvain (`best_partition`) and
  `partition_netlist_min_cut` runs `nx.community.kernighan_lin_bisection`.
  Both are eigenvector/LAPACK-bound (scipy) and their partition output and
  bisection order are algorithm-order-dependent; no independent Rust
  implementation reproduces them bit-for-bit (mirrors the recorded
  `netlist.compute_eigenvector_centrality` keep). The only separable kernel,
  `get_community_component_indices`, is a one-line list comprehension with no
  compute to migrate.
- `core/loop_ownership.py` (LOC 327; consumers: `core/__init__.py` re-exports;
  deps: `loop_extractor.classify_component`, itself out-of-unit) — contains no
  numeric compute at all: it is dict/set structural plumbing over Python
  object graphs (`LoopCollection`, `Netlist`, `Loop`), priority weighting is a
  dict lookup + `max` over small lists, and `classify_role` is one string
  dispatch away from `loop_extractor.classify_component`. There is no
  separable numeric kernel to migrate.

### R24 physics discipline

N/A — graph/geometry kernels with no physics-gated threshold.

## Via/Clearance/Grid Cluster (`via_clearance.rs`) — Verification by Induction (Wave 4, tier-2, 2026-08-09)

Unit `via_clearance_cluster`: the pure kernels behind
`temper_placer/router_v6/{via_placement, clearance_engine, grid_converter,
path_simplify}.py`, in one home-crate module. The verbatim pre-migration
oracles are pinned in
`packages/temper-placer/tests/router_v6/test_via_clearance_tier2_rust_differential.py`
(`git show f1ffc013`). `path_simplify`'s three kernels were first migrated to
`temper-rust-router` (#856); this tier re-homes them here (the Wave-4 home
crate for router_v6 geometry), and the same pinned oracle
(`_path_simplify_py_oracle.py`) pins both copies.

**Bit-exactness classes:** the unit contains no libm transcendental — every
f64 is an exact table literal, an int-promoted product, or an addition with
the oracle's exact left-to-right expression shape — so the B1/B2/B4/B6/B7
classes do not apply here. The one precision-sensitive detail is *operation
order* (B7): `grid_to_world` is `(origin + cell*size) + size/2`, never
reassociated; `compute_path_length` accumulates with a naive `+=` fold in
segment order; the IEC tables short-circuit `voltage <= vl` exactly like the
Python loop (a NaN voltage fails every comparison, including the `inf`
sentinel, and keeps the initial 0.2/0.4). Int deltas are computed in i128
(Python ints are unbounded; i64 extremes cannot overflow). The word-boundary
matcher's `\d` is the Unicode Nd property (`char::is_digit(10)`), mirroring
`creepage_check.rs`'s `word_bounded` — a plain ASCII-digit check would miss
non-ASCII decimal digits Python `re` accepts.

### via_placement kernels — `adjacent_layer`, `via_segment_index`, `via_layer_pair`

**Base case:** a via whose position matches segment index 0 (first segment,
`abs` diff `< 1e-4` on both axes) derives `(segs[0][2], segs[1][2])`; a via
at the LAST segment's position (no successor) or matching nothing falls back
to the hardcoded `("F.Cu", "B.Cu")`, exactly like the oracle's
`vi + 1 < len(segs)` guard. `adjacent_layer("F.Cu") == Some("In1.Cu")` and
`adjacent_layer("In3.Cu") == None`.

**Induction hypothesis:** for any segment list and via position, the kernel
returns the oracle's from/to pair.

**Induction step:** `via_segment_index` is a left-to-right first-match scan
over an independent per-index predicate — appending a segment can only add
later match candidates, and the scan breaks on the first; the oracle's
`enumerate`+`break` and the kernel's `.find()` agree index-for-index. The
from/to pair is then a per-via pure function of the matched index and the
layer list (element access, no cross-via interaction), so the via list
derives per-element in position order. The `abs(...) < 1e-4` epsilon is the
identical f64 comparison on both sides, including its rounding quirk (e.g.
`5.0001 - 5.0` rounds BELOW `1e-4`, so `5.0001` is a *match* in both
languages — pinned, not "fixed"). `adjacent_layer` is the shipped `dict.get`
— a total function over the four-layer map, `None` elsewhere — including
`B.Cu -> In2.Cu` (the map is not a cycle).

### clearance_engine kernels — `safety_distances`, `kw_boundary_match`, `net_class_to_voltage_class`

**Base case:** `safety_distances(50.0, 2, 2)` → `(0.2, 0.4, 50.0)` (first
bracket on both tables); `(1200.0, 2, 2)` → `(5.0, 8.0, 1200.0)` (the `inf`
sentinel). `kw_boundary_match("AC_L", ["AC"])` is true ("AC" at start,
followed by `_`); `kw_boundary_match("ACH", ["AC"])` is false ("AC" followed
by "H"). `net_class_to_voltage_class("GND")` → SELV (1).

**Induction hypothesis:** for any voltage/pollution/overvoltage inputs, any
uppercased label string, the kernels reproduce the oracle bit-for-bit.

**Induction step:** `safety_distances` is a bracket lookup over fixed tables
then two scalar multipliers (`ovcat >= 3` ×1.25 both, `pollution >= 3`
creepage ×2.0) — per-voltage pure functions with no cross-term interaction;
the loop order (first `voltage <= vl`) is preserved, so appending a voltage
cannot change a previously matched bracket. `kw_boundary_match` reduces to
per-keyword `word_bounded` scans (start-or-after-`_` leading, end-`_`-or-
Unicode-digit trailing) combined by `any()` — each keyword is an independent
predicate, order does not affect the outcome (Python `any` is existential).
`net_class_to_voltage_class` is the oracle's if-chain transposed: the same
keyword branch, then the widened `120`/`240` trailing boundary
`(?:V|$|[\d_])`. Note the reference's asymmetry is preserved faithfully:
there IS a standalone 120 check but NO standalone 240 check, so
`"240V"` alone classifies as SELV (only `"MAINS..."`/HV-prefixed labels reach
the 240 branch). The composite `get_clearance` stays Python (the IEC 60335-1
tables and IPC-2221 bracket are shared pyo3/Rust deps, not re-copied); its
behavior is A/B'd end-to-end against the verbatim `_oracle_get_clearance`
over a randomized parameter space.

### grid_converter kernels — `grid_to_world`, `extract_vias`, `compute_path_length`, `count_vias_in_path`

**Base case:** `grid_to_world(0, 0, 0.0, 0.0, 0.5)` → `(0.25, 0.25)`
(`0 + 0 + 0.25`); `compute_path_length` on 0 or 1 cells → `0.0`; `extract_vias`
on a constant-layer path → `[]`.

**Induction hypothesis:** for any cell list / cell_size / origin, the kernels
reproduce the oracle.

**Induction step:** `grid_to_world` is `(origin + cell*size) + size/2`
per-axis — two independent scalar expressions; the int→f64 promotion
(correctly rounded) and both additions match the Python expression's order
exactly. `compute_path_length` sums per-step `(dx+dy)*size` terms with a
naive left-to-right `+=` fold in path order (the oracle's own loop — NOT the
builtin `sum()` Neumaier fold); each step is independent, so prepending or
appending a step only extends the fold. `extract_vias` / `count_vias_in_path`
are index/count scans over consecutive-layer comparisons (exact int
equality) — no cross-cell arithmetic.

### path_simplify kernels — `is_collinear`, `simplify_path`, `estimate_segment_count`

**Base case:** `simplify_path` of 0, 1 or 2 cells returns the input unchanged;
`is_collinear` of three same-layer same-y cells is true.

**Induction hypothesis:** for any cell path, the kernels match the oracle
(and the bit-identical `temper-rust-router` twins).

**Induction step:** `simplify_path` is a single ordered pass over
consecutive triples: keep on layer-change or non-collinearity, always keep
first/last. Each triple decision is independent of all others and the output
is built by appending in iteration order — so the pass is correct for n cells
if it is for n-1 (the new cell adds one triple decision at the tail). All
comparisons are exact int equality. `estimate_segment_count` is the same-layer
consecutive-pair count over the already-simplified list.

### Empirical verification

- **Differential** (`test_via_clearance_tier2_rust_differential.py`, 33
  tests): every kernel pinned bit-exactly (`float.hex()` via `sig()`, no
  tolerance) against the verbatim `_oracle_*` blocks over a seeded randomized
  corpus (300 path3D via-layer derivations, 300 clearance-engine parameter
  draws, 300 grid/path draws) plus crafted edge cases — NaN/inf voltages
  (fall-through to the initial 0.2/0.4 and the sentinel brackets), the
  `5.0001` f64-epsilon quirk, first-match-wins coincident segments, the
  `"F.Cu"/"B.Cu"` fallback, the `"MAINS240V"`/`"240V"` classification
  asymmetries, and the full existing `test_via_placement.py` /
  `test_path_simplify_rust_differential.py` / `test_clearance_rust_differential.py`
  consumer suites (117 tests green through the shims, plus 43 in the
  kicad-exporter / clearance-induction / DRC-invariant consumers).
- **PBT** (`test_via_clearance_tier2_pbt.py`, 23 tests): 9 properties
  P1–P7 (module-to-property map in the file docstring; every property calls
  its kernel directly on generated inputs — reachability measured, not
  assumed), each with a mutation-test vacuity guard
  (`test_pN_fails_for_<mutant>` monkeypatching the `temper_geometry` kernel
  and re-running via `hypothesis.inner_test`), plus 3 metamorphic relations
  M1–M3 (path-length translation invariance, simplify reflection invariance,
  simplify reversal symmetry — all EXACT: integer transforms preserve every
  f64 bit). The same properties run natively as 2000-case proptests in
  `via_clearance.rs` (P1–P5 + M1–M3), exercised by
  `cargo test --no-default-features` (661 lib tests green) even when the pyo3
  extension is not importable in the shared venv.
- **G1 red→green**: the differential file (with its verbatim oracle blocks
  and `test_oracle_is_verbatim_copy` re-extraction from `f1ffc013`) is the
  TDD oracle; its `test_rust_symbols_exist` is RED until the 12 kernels in
  this module exist.

### Kept Python (structural, per G6 non-applicability)

- `via_placement.place_vias` / `_place_vias_for_path` orchestration (per-net
  sizing resolution, `Via`/`ViaPlacement` dataclass construction, the legacy
  `RoutePath` midpoint fallback): pure structural iteration over Python
  objects — no numeric kernel to migrate (the segment-match derivation it
  uses IS migrated).
- `clearance_engine.get_clearance` composite and the `SafetyDistances`
  dataclass; the `VoltageClass` pyo3 tables and `_calculate_required_creepage`
  are already-Rust shared deps, deliberately not re-copied (no third copy).
- `grid_converter.GridCell` dataclass; `path_simplify._cell_wire` tuple
  conversion.

### R24 physics discipline

N/A — clearance/creepage-table lookups and grid/path geometry with no
physics-gated CP-SAT constraint surface.
---

## Spatial-Tier-2 Cluster (`bottleneck_kernels.rs`, `layer_capacity_kernels.rs`, `connectivity_kernels.rs`, `obstacle_map_kernels.rs`) — Verification by Induction (Wave 4, 2026-08-09)

Migration unit: `router_v6/{bottleneck_analysis,layer_capacity,connectivity,obstacle_map}.py`
compute kernels.  `routing_space.py` is JUSTIFIED-KEEP (see the keeps record
below).  Pinned by
`packages/temper-placer/tests/router_v6/test_spatial_tier2_rust_differential.py`
(G1/G2, verbatim oracles) and `test_spatial_tier2_pbt.py` (G4/G5, 6
non-vacuous properties + 13 metamorphic relations).

### `bottleneck_kernels` — Verification by Induction

**Base case:** one layer, `traces = [0]`, `total_demand = 0`.
`identify_bottlenecks_kernel` returns `total_capacity = 0`,
`demand_per_layer = 0`, utilization `inf`, severity `"none"` — the same as
`_oracle_identify_bottlenecks({"A": cap0}, zero_demand)` (a zero-capacity
layer with zero demand classifies NONE, matching `_classify_severity`).

**Induction hypothesis:** the kernel matches the reference for a k-layer
`traces` prefix.

**Induction step:** the (k+1)-th layer contributes
`(total_capacity += traces[k], utilization = demand_per_layer / cap,
 severity = classify_severity(cap, demand_per_layer))`, all per-layer
scalars independent of every other layer's values — `total_capacity` is a
left-to-right integer sum (no reassociation), `demand_per_layer` is
`total_demand.div_euclid(k+1)` (Python `//` floor division, equal for the
non-negative operand pairs the validator admits, and `div_euclid` for the
rest), and `utilization` is IEEE f64 division of two exactly-representable
non-negative integers (bit-exact against CPython `int / int`).
`classify_severity` is a pure decision tree on one f64 ratio, whose only
division operands are also exact; the `demand == 0` arm yields
`f64::INFINITY` exactly as Python's `float("inf")`.  No cross-layer
interaction, so the step holds.

**Empirical verification:** `test_classify_severity_kernel_*` (2000
randomized capacity/demand pairs + a 13-case edge matrix) and
`test_identify_bottlenecks_matches_reference_on_randomized_inputs` (200
random designs, bit-exact utilization via `.hex()`), plus the ``None``
short-circuit and empty-dict cases.  PBT P1/P2 (utilization arithmetic,
severity monotonicity in capacity) each carry a mutation-test vacuity guard;
metamorphic M1 (power-of-two severity scale invariance, exact), M2
(permutation of the layer dict, exact), M3 (zero-demand edge, exact).

### `layer_capacity_kernels` — Verification by Induction

**Base case:** `free_cells = 0`, `avg_channel_width = 0.0` → the
`avg_channel_width > 0 && trace_pitch > 0` guard fails and
`estimate_traces` returns `0`, matching `_oracle_calculate_layer_capacity`
(which also takes the `else` → `estimated_traces = 0`).

**Induction hypothesis:** the kernel's `estimate_traces` matches the
reference formula for all scalar inputs with the formula's branch taken.

**Induction step:** the estimate is a single closed expression
`max(1, int(free_cells * 0.01 * int(avg/trace_pitch)))`, computed with no
loop, so "correct for n" and "correct for n+1" are the same statement;
the proof is that each operator is reproduced: `trace_pitch =
min_trace_width + 2 * min_clearance` (same two-op chain, class B7),
`avg / trace_pitch` is IEEE division, Python `int()` truncates toward zero
like `f64 as i64`, `free_cells * 0.01` is `(free_cells as f64) * 0.01` (the
same `0.01` literal), and `max(1, int(...))` maps to `1_i64.max(...)`.
`int(inf)` raises `OverflowError` in Python; the kernel returns
`KernelError::Overflow`, mapped at the pyo3 boundary to CPython's exact
message `"cannot convert float infinity to integer"`.  The `int(nan)`
ValueError arm is unreachable because the reference's `>` guard is false
for a NaN operand (verified: the kernel returns `0`, like Python).
**Recorded unreachable divergence:** a finite `avg/trace_pitch >= 2^63`
would be an exact bigint in Python while `as i64` saturates — needs an
average channel width on the order of 1e18 mm (physics-unreachable;
documented here rather than silently absorbed).

**Empirical verification:** 400 randomized `(grid, widths, mtw, mc)`
differentials with full `LayerCapacity ==` equality, plus zero-edge cases
(avg 0, zero pitch).  PBT P3 (monotone non-decreasing in free cells and
channel width) with a decreasing-return mutant guard; metamorphic M1
(common power-of-two scaling of the three width params leaves the estimate
unchanged — exact, because scaling by 2 is exact and commutes with IEEE
rounding), M2 (zero pitch → 0, exact), M3 (monotone in free cells, exact).

### `connectivity_kernels` — Verification by Induction

**Base case:** zero pads.  `connectivity_components` returns no components;
the shim builds `NetConnectivity(net="", disposition=INCOMPLETE, ...)`,
identical to the reference on empty inputs.

**Induction hypothesis:** the kernel's pad-component partition matches the
reference union-find for any item set of size n.

**Induction step:** the reference's `union` sets
`parent[max(left_root, right_root)] = min(left_root, right_root)`, so every
set's canonical root is its minimum item index and the final partition is a
pure function of the set of touch pairs — independent of union order and of
path-halving intermediate state.  The kernel emits exactly the reference's
touch pairs for the ten portable predicates (identical f64 expressions,
reusing `drc_constraints_geometry::point_to_segment_distance` /
`segment_to_segment_distance` and `primitives::point_distance` — the very
kernels the pre-migration Python called through `constraints_geometry` /
`Point.distance_to`), and the shim supplies the four shapely zone-predicate
pairs, so the pair set is identical and the partition is identical.  Adding
one more item only adds its touch pairs — no existing pair changes, so the
step holds.  The pad-rotation unwinding (`_to_pad_coordinates`) is
R(+theta) with host-libm cos/sin (class B1 via `host_math`) on
`rotation * (PI / 180.0)` (Python `math.radians`); the Liang-Barsky box test
uses `py_max`/`py_min` for the CPython builtins.

**Empirical verification:** 300 randomized nets (pads 0-4, tracks 0-4,
vias 0-3, zones 0-2) with full `NetConnectivity` equality against the
verbatim pre-migration oracle (including crafted predicate cases: shared
track endpoints, boundary-touching circle pads, coincident vias, rotated
rect pads crossed by tracks, zone-pad containment).  PBT P4 (partition ==
from-first-principles circle-pad contact closure) and P5 (monotonicity
under copper addition, plus a strict bridge-merge test) with mutation
guards; metamorphic M1 (permutation invariance, exact), M2 (layer-index
shift, exact), M3 (duplicate-copper idempotence, exact).

### `obstacle_map_kernels` — Verification by Induction

**Base case:** `radius <= 0` → empty ring, matching
`Point.buffer(r <= 0)` == `POLYGON EMPTY` (GEOS `isLineOffsetEmpty`).

**Induction hypothesis:** `circle_buffer_ring` reproduces GEOS's circle for
any partial ring length < n.

**Induction step:** the ring is built left-to-right from GEOS's own
transcribed construction (`OffsetSegmentGenerator::createCircle` →
`addDirectedFillet`): `totalAngle = |0 - 2·MATH_PI|`,
`nSegs = (int)(totalAngle/fillet + 0.5)`, `angleInc = totalAngle/nSegs`,
vertex i at angle `-i·angleInc` with host-libm sin/cos snapped by GEOS's
`Angle::sinCosSnap` rule (`|x| < 5e-16 → 0.0`), coordinate
`(cx + r·cos, cy + r·sin)`, consecutive-duplicate skip, closure.  Every
step is a pure expression over the previous index — no cross-vertex
interaction, so vertex i's correctness is independent of vertex i+1.
The cardinal snap is what the S1 spike's naive closed form missed; the
kernel reproduces it (a unit test pins that the naive `cos(-π/2)` residual
~7.7e-18 would NOT equal GEOS's exact 0.0).

**Empirical verification:** 0/400 random circles differ from
`Point.buffer(r, quad_segs=8)`'s exterior ring (verified both in Rust unit
tests and in the differential suite over `(cx, cy) ∈ [-100, 100]²`,
`r ∈ [1e-3, 20]`), plus a cardinal-point snap pin, the empty-radius cases,
and the quad_segs clamp.  PBT P6 (ring vertices on the circle, count,
closure) with a square-ring mutant guard; metamorphic M1 (empty-ring
translation invariance, exact), M2 (vertex count = 4q+1 and closure,
exact), M3 (cardinal-axis placement, exact), M4 (start point, exact).

### Kept modules — R3 JUSTIFIED-KEEP (recorded)

- `router_v6/routing_space.py` (LOC 301; consumers: occupancy_grid,
  layer_capacity, stage2_orchestrator, tests; deps: shapely) — the module's
  compute surface is GEOS polygon algebra (`board_polygon.difference`
  and `.area`).  The S1 spike
  (`docs/evidence/2026-08-04-geos-polygon-algebra-spike.md`) measured that
  bit-exact `==` on a GEOS boolean result is not well-posed: ring-start
  order is a traversal artifact (§3.1), the output carries the input's
  redundant vertices (§3.2), and non-input vertices follow GEOS's
  conditioned intersection kernel up to 701 ulps from the closed form
  (§3.3).  The spike's §5 narrowing (drop the difference, carry
  `(bounds, area, obstacle_polygons)`) is a *design change* gated on the
  unresolved `channel_skeleton` Voronoi gate (§8), out of scope for a
  kernel-migration unit.  The two `RouterSpace` ratio properties are
  trivial arithmetic with no boundary-crossing value.  (LOC: 301;
  consumers: 3 production + test suites; deps: shapely; churn: low)
- `router_v6/obstacle_map.py` (partial) — `LineString.buffer(w/2,
  cap_style=1)` and `poly.buffer(0)` are JUSTIFIED-KEEP with measured
  blockers (spike §4.2: 32 of 66 vertices are GEOS offset-curve artifacts;
  §4.3: `buffer(0)` is an undocumented GEOS fixed point that can silently
  drop a self-intersecting zone's lobe).  `unary_union` and the
  `Polygon(...)`/`is_valid` container steps also stay in Python; the two
  `Point.buffer` via sites delegate to `circle_buffer_ring_py`.
- `router_v6/connectivity.py` (partial) — the four `_zone_*` predicates are
  GEOS `contains`/`touches`/`intersects` on `CopperZone.polygon`, the same
  "vendor GEOS" bar; the shim evaluates them and feeds the (i, j) union
  pairs to the Rust kernel.

### R24 physics discipline

N/A — spatial/router kernels with no physics-gated threshold; the
connectivity and capacity quantities are routing-analytic, not physics
fields.  No Chebyshev-style soundness proof is required.

## Bundle Analyzer — Verification by Induction (added 2026-08-09)

`router_v6/bundle_analyzer.py`'s GEOS seam — `MultiPoint(pads).convex_hull`,
`hull.buffer(m)`, and the `STRtree(points).query(footprint,
predicate="contains")` edge-cover query — is transcribed into
`bundle_analyzer.rs` (see that module's doc for the per-call verdicts and
the spike `docs/evidence/2026-08-09-bundle-analyzer-geos-spike.md`).  The
Rust ring's vertex *set* is asserted equal to shapely 2.1.2 / GEOS 3.13.1's
bit-for-bit (canonicalized — ring start/orientation are GEOS emission
artifacts, S1 §3.1, that do not change the region the predicate consumes).

### Base case: 3-pad triangle

For `pads = [(0,0), (10,0), (5,7)]`, `m = 1.5`:
- `convex_hull_ring` emits the closed CW ring `[(0,0), (5,7), (10,0), (0,0)]`
  — exactly GEOS's, vertex-for-vertex.
- `hull_buffer_ring` emits 67 points: the first is the offset of the
  closing edge at the first hull vertex `(0, -1.5)`, closure holds, and the
  corner arcs reproduce GEOS's `addDirectedFillet` fillet (22 segments on
  the 125.5° corner, `(int)(total/fillet + 0.5)` rounding, host-libm trig
  with `Angle::sinCosSnap`) — the same ring shapely produced.

### Induction hypothesis

`hull_buffer_ring` reproduces GEOS's `buffer` region for any convex ring
with n vertices.

### Induction step

The offset ring is built per hull vertex in ring order: each vertex's
contribution is `p_in` (the offset of the previous edge at the vertex), the
fillet arc, and `p_out` (the offset of the next edge), where every quantity
(`offset_endpoints`'s `sqrt(dx²+dy²)` scaling, the `atan2` start/end angles,
`nSegs`, the snapped `cos`/`sin` arc points) is a pure function of that
vertex and its two adjacent edges — no cross-vertex interaction, no shared
state beyond the running point list (which only dedups consecutive
duplicates within the vertex-snap distance).  Adding a vertex appends an
independent fillet block, so correctness for n vertices follows from
correctness for n-1.  The hull (`convex_hull_ring`) is the same shape of
argument: the Graham scan's pop decision is a pure orientation predicate
on each triple, and `cleanRing` drops points per-triple — element-wise.

### Empirical verification

The differential suite
(`packages/temper-placer/tests/router_v6/test_bundle_analyzer_rust_differential.py`)
pins the kernels against VERBATIM pre-migration oracles ("do not edit — they
are the reference"): hull vertex sets over 150 randomized pad sets plus
duplicate/collinear/sub-polygon edge cases; buffer vertex sets over 150
randomized `(pads, m)` pairs; the `buffer(0)` fast path; covered-edge id
sets over 60 randomized footprints including boundary-exact probes (ring
vertices, which `contains` must exclude); per-net edge covers; and the
end-to-end consumed BundleManifest surface (the exact fields
`_pipeline_route.py` serializes) over 40 randomized boards — all bit-exact.

The PBT suite (`test_bundle_analyzer_pbt.py`) contributes 5 properties
(hull contains its pads; buffer offset exactness at distance m; dilation
soundness; contains-predicate parity with shapely; hull convexity) each
with a mutation test proving a degenerate kernel violates it, plus 4 exact
metamorphic relations (midpoint-permutation equivariance, pad-order
permutation, ring reversal, duplicate pads).

The S2 spike measured, on shapely 2.1.2 / GEOS 3.13.1 (the production
pin): 400/400 random hulls with bit-identical buffer vertex sets, 0/2000
near-degenerate hulls where the input simplifier fires, and 1,920,000
contains probes (including 20,470 boundary-exact) with 0 disagreements.

Validity boundary (documented, not guarded): f64-underflow edge separations
(`|dx| < ~1e-162`) make GEOS itself emit NaN offsets that its noding drops;
real pads never reach this regime and the suites constrain generators to
float32 width.
