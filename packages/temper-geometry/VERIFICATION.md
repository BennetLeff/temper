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

**KTD8 spike verdict (2026-07-31):** the `edt` crate was evaluated as a
`scipy.ndimage.distance_transform_edt` replacement and rejected — its
distance field diverges from scipy's Euclidean transform even with a
False-border padding workaround (measured max diff 2.0–2.236 on random
masks); a Rust-native exact EDT is the recorded fallback for a
follow-up. The U4 perf win (the per-sample lookup hot loop) is
delivered by the batch; scipy's transform was never the hot loop.

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
