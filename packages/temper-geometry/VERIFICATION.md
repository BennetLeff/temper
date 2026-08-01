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
relationship to the Numba kernel's production formula (f32
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

**KTD8 spike verdict (2026-07-31):** the `edt` crate was evaluated as a
`scipy.ndimage.distance_transform_edt` replacement and rejected — its
distance field diverges from scipy's Euclidean transform even with a
False-border padding workaround (measured max diff 2.0–2.236 on random
masks); a Rust-native exact EDT is the recorded fallback for a
follow-up. The U4 perf win (the per-sample lookup hot loop) is
delivered by the batch; scipy's transform was never the hot loop.

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
wrappers; `_grid_core.py` no longer imports numba (the module's
documented cold-start cost — the migration's perf win). The Rust module
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
