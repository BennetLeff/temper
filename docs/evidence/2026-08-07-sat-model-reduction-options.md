<!-- provenance: commit=6a5758b856a419d26c9a3c1a841b7e96eeaf5bc1 dirty=false -->

# SAT model reduction options for `#871`: five candidates evaluated; the deleted bundled encoding measured end-to-end for the first time, and it still OOMs

**Date:** 2026-08-07

**Task:** `docs/evidence/2026-08-07-pruned-encoding-measurement.md` established that
geographic pruning gives **0% reduction** on `pcb/temper.kicad_pcb` (14/110
nets directly observed) because this board's nets are not locally clustered
(median pin span 120.9mm against a 279mm board diagonal). Both the pruned and
unpruned paths `MemoryError` at 5.43GB under an 8GB `ulimit -v` cap, before
ever reaching Rust's `encode_to_cnf`. This task evaluates five structurally
different reductions against that same 22,493,900-primary-variable baseline,
and asks the harder question underneath all of them: is a monolithic SAT
formulation the wrong tool at this scale.

**Headline, stated up front:**

1. **The deleted "bundled encoding" (`docs/STRATEGY.md`'s own flagged lead)
   is still the highest-value option, and reviving it is cheaper than
   inventing something new — but this task's own live measurement (§3.4)
   found it currently `MemoryError`s too**, at essentially the same scale
   as the unbundled path: `BundleAnalyzer` produced only **8 bundle
   classes covering 21 of 110 nets** (89 stay unbundled, MEASURED) — an
   11.8% raw-variable reduction, not the order-of-magnitude the mechanism
   theoretically allows — because its exact-match grouping rule is too
   strict for this board's netclass diversity, and
   `_create_bundle_channel_vars` OOM'd inside the *same* function and
   failure mode as the unbundled path. Reviving bundling now means four
   fixes, not two — the missing PyO3 binding and the capacity-constraint
   bug (`_create_capacity_constraints`'s net-index/bundle-id collision,
   found this task, §3.3) were already known/found, but loosening the
   grouping rule and vectorizing `BundleAnalyzer`'s own `O(n_nets × E)`
   bottleneck (also found this task) turn out to matter more.
2. **Every locality-based option (pruning, block decomposition, net-class
   margins) hits the same wall**: this board's dominant-cost nets (`gnd` 86
   pins, `+3V3` 51 pins, `vcc` 13 pins) are inherently non-local, and no
   amount of geographic partitioning removes that. Bundling is different in
   kind — it groups nets by *type-signature similarity*, not proximity, and
   the theory is not defeated by the same measurement that killed pruning
   — but the theory and the code's actual grouping rule turn out to be two
   different things (§3.4).
3. **`simplify_tolerance`, the task brief's suggested skeleton-coarsening
   knob, is a documented no-op on the code path production actually uses**
   (found this task, §4). The real resolution knob is a hardcoded ~1mm
   boundary-sampling constant nobody has ever tuned.
4. **Net-class-aware margins are conclusively the weakest option** — MEASURED
   this task (§5): the "signal" net class's own median pin span (134.4mm)
   *exceeds* the HV class's (107.7mm). There is no clusterable subset hiding
   inside a net-class partition.

---

## 0. Baseline recap (from the merged U5/plane-fix measurement)

All MEASURED, from `docs/evidence/2026-08-07-pruned-encoding-measurement.md`
(commit `ed84ca27`, merged into this branch):

| Quantity | Value | Label |
|---|---|---|
| Channel-skeleton edges, by layer | F.Cu 114,622 / In1.Cu 29,956 / In2.Cu 29,956 / B.Cu 29,956 | MEASURED |
| Total edges | 204,490 | MEASURED |
| Nets attempted | 110 | MEASURED |
| Primary `NetChannelVar` count (unbundled, unpruned) | 204,490 × 110 = **22,493,900** | DERIVED, exact |
| Geographic pruning reduction (14/110 nets sampled) | **0%** | MEASURED |
| Peak RSS at `MemoryError`, unpruned | 5.43 GB (under 8GB `ulimit -v`) | MEASURED |
| Board size / diagonal | 152mm × 234mm / 279.0mm | MEASURED / DERIVED |
| Median net pin span (board-wide) | 120.9mm | MEASURED |

Pre-fix baseline for scale comparison (`docs/evidence/2026-07-27-stage3-model-and-rewrite.md`, MEASURED, 108 nets, 20,734-edge skeleton — **10× smaller** than today's, predating the plane-classification fix):

| Quantity | Value |
|---|---|
| Raw model (vars / constraints) | 3,876,012 / 43,050 |
| CNF (vars / clauses), Sinz encoding | 42,145,777 / 78,107,180 |
| CNF/raw variable blowup ratio | **~10.87×** |
| Stage 3 end-to-end wall (post-fix, this same skeleton) | 52.67s |
| Solve outcome | SAT, 0 conflicts, 0 decisions |

That last row matters for §7: whenever this pipeline's SAT solve has been
allowed to run to completion, it needed **zero search** — the bottleneck has
never been CDCL, always model size.

---

## 1. Layer-wise decomposition — MEASURED-arithmetic, real but capped well short of the naive estimate

**Mechanism:** solve one 2D SAT instance per copper layer instead of one
4-layer model, reconciling via placement afterward through an inter-layer
contract (a net's channel path on layer A must terminate at a via node whose
layer-B assignment picks it up consistently).

**Arithmetic (DERIVED from the MEASURED per-layer edge counts above) — and
this is where the task brief's "naively ~4× smaller" assumption breaks:**

| Layer | Edges | Share of total | Raw vars if solved alone (× 110 nets) |
|---|---:|---:|---:|
| F.Cu | 114,622 | 56.06% | 12,608,420 |
| In1.Cu | 29,956 | 14.65% | 3,295,160 |
| In2.Cu | 29,956 | 14.65% | 3,295,160 |
| B.Cu | 29,956 | 14.65% | 3,295,160 |

The plane-classification fix that just landed (`8abcec24`) is exactly what
makes this split uneven: it opened F.Cu/B.Cu from the plane-condemnation
fallback to real routing, and F.Cu alone came back at **3.8× the size of any
one inner layer**. Solved sequentially (one layer's model in memory/solve at
a time, freeing memory between), **peak** model size is bounded by the
largest layer, not the average:

```
22,493,900 / 12,608,420 = 1.78×   (peak-memory reduction, DERIVED)
```

**not** 4×. Applying the pre-fix baseline's own measured ~10.87× CNF blowup
ratio to F.Cu's 12.6M raw vars projects to roughly **137M CNF variables for
F.Cu's layer alone** (ESTIMATED by extrapolation, not measured) — i.e. even
the *smaller* per-layer problem is still far larger than the pre-fix
full-board CNF (42.1M vars) that this pipeline already needed a ~30×
algorithmic fix to solve in reasonable time.

**Total work is unchanged**: the four sequential solves sum back to the same
22.49M raw variables — this is a peak-memory lever, not a total-compute one,
and it likely *costs* more wall time (four separate Rust encode/solve
round-trips, each paying the ~27.78s "CaDiCaL loading a large CNF into
watch-list structures" fixed cost the pre-fix baseline already measured
dominates even a 0-conflict solve).

**What breaks:** the inter-layer via contract does not exist today.
`_create_via_vars` (`constraint_model.py:643`) is layer-agnostic by
construction — it iterates the union of all skeleton nodes across every
layer into one flat via-anchor set, not four per-layer sets. Reconciling four
independently-solved layer assignments into one consistent via plan is a
real distributed constraint problem with no existing scaffolding — closer in
shape to the abandoned bundling CEGAR loop (§3) than to a mechanical
partition.

**Verdict: real mechanism, but capped at ~1.8× by a distribution the
project's own recent plane fix created, and it requires new inter-layer
reconciliation machinery that does not exist. Not sufficient alone.**

---

## 2. Net-batching / incremental solve — the strongest non-bundling option, and it is corroborated by numbers already on record

**Mechanism:** partition the 110 nets into batches of size `B`; solve batch
`i`'s SAT model with batches `1..i-1`'s chosen routes already fixed (removed
as live variables, their consumed capacity subtracted from
`channel_widths.edge_widths` for the next batch).

**Arithmetic:** peak raw vars per batch ≈ `B × 204,490` edges (ignoring the
smaller via-var term for a first-order estimate). For `B = 10`:

```
10 × 204,490 = 2,044,900 raw vars   (≈11× smaller than the 22.49M peak, DERIVED)
```

This is not merely a projection — it is **directly corroborated by an
existing MEASURED data point**: §6 of the merged pruning-measurement doc
shows the pruning-ON run reached **2.6M `NetChannelVar` instances at net
13/110** without crashing (operator-killed only because the flat-rate trend
was already unambiguous, not because of resource exhaustion). A ~2M-variable
raw model on *this* skeleton is therefore already known to survive
construction under the same 8GB cap this task must respect. Separately, the
pre-fix full-board raw model (3,876,012 vars, on a *10× smaller* skeleton)
is already proven to encode and solve end-to-end (42.1M CNF vars, 52.67s, 0
conflicts) well inside typical memory budgets. A `B=10` batch's raw model on
today's skeleton (2.04M) is smaller than that already-solved pre-fix
full-board model — giving real, if indirect, evidence this is tractable
without a new prototype run.

**Ordering:** route highest-priority/most-capacity-hungry nets first — HV/AC
nets (`safety_category` in `netclass_rules.yaml` already tags these; note
this is a *taxonomy* only — `_net_policy.py::_allow_forced_segments` was
checked this task and is no longer class-conditional, it was generalized to
unconditional `False` by
`docs/plans/2026-07-24-001-fix-forced-segment-fail-closed-plan.md`, so no
live per-class special-casing exists to reuse today, only the label), then
power/ground (highest pin count, most capacity pressure), then signal nets
by descending span or pin count. This is standard negotiated-congestion/
rip-up-reroute practice; the `safety_category` field already present in
this repo's netclass SSOT gives batching its priority axis for free even
though nothing currently branches on it at solve time.

**What breaks:** joint optimality. A net routed in an early batch can
foreclose a later batch's net — the union of per-batch SAT-optimal solutions
has no guarantee of board-wide optimality, and a batch going UNSAT doesn't
distinguish genuine infeasibility from a bad ordering artifact. This is
functionally re-implementing a rip-up-reroute router on top of repeated
one-shot SAT calls, which is a real departure from "one joint model, one
proof of global feasibility" — the reason SAT was chosen in the first place.
Given the project already accepts a 48/96 = 50.0% completion rate from the
*monolithic* model, this is a difference of degree, not of kind, for a
project that has already made this tradeoff once.

**Verdict: real, tractable, and the best-evidenced of the non-bundling
options. Main cost is engineering the batch/fix-and-continue loop and
re-deriving capacity between batches — conceptually simple compared to
option 1's missing via contract.**

---

## 3. Bundled/hierarchical edge encoding — the highest-value lead, confirmed

### 3.1 What it was

`docs/STRATEGY.md` (§"The bundled encoding was deleted by a refactor and
nobody noticed", 2026-07-27) and its underlying
`docs/evidence/2026-07-27-bundled-encoding.md` give the full history:

- **Built and wired end-to-end on 2026-06-29** (`docs/plans/2026-06-28-002-feat-net-bundling-lazy-grounding-plan.md`,
  now `status: stale`): a `BundleAnalyzer` (Python, still present at
  `packages/temper-placer/src/temper_placer/router_v6/bundle_analyzer.py`,
  422 lines) partitions nets into equivalence classes — two nets bundle iff
  they share an identical `TypeSignature` (`net_class`, `trace_width`,
  `clearance`, `has_diff_pair`, `pin_layer_set`) **and** their geometric
  footprints overlap with Jaccard index > 0.5. `ModelBuilder` has a working
  `_create_bundle_channel_vars` path (`constraint_model.py:599`) that
  creates **one `NetChannelVar` per bundle per edge** instead of one per net
  per edge — `O(n_nets × E) → O(bundle_count × E + |unbundled|)`.
- **The PyO3 entrypoint (`solve_topology_rust_bundled`) was dropped on
  2026-07-08** when `packages/temper-rust-router/src/lib.rs` was replaced
  wholesale during the `temper-rust-router-core` crate split (`b27851fe`,
  `87bda65e`). The Watchdog/CEGAR solve loop (412 lines today, 415 at the
  2026-07-27 measurement — mechanical drift only, per that doc's own note
  on later no-op lint/dead-code passes —
  `temper-rust-router-core/src/watchdog.rs`, re-counted this task) and the
  homomorphism-expansion code (`extract_bundled`/`expand_assignments`, 349
  lines today, `extraction.rs`, re-counted this task) survived the split as
  compiled, `pub`, but **uncalled** library code — confirmed at HEAD by this
  task: `cargo clippy --release` is silent (unused-but-public isn't a lint
  hit) and `import temper_rust_router;
  'solve_topology_rust_bundled' not in dir(...)`.
- **`route_pcb()` never exposed `enable_bundling` at all** — confirmed this
  task by reading `_adapter_convert.py`'s `route_pcb()` signature (no such
  parameter). Only `RouterV6Pipeline.__init__` accepts it directly.
- Undetected for three weeks because the only tests exercising
  `enable_bundling=True` instantiate `ModelBuilder` directly and never touch
  `RouterV6Pipeline`, so they never import the missing symbol.

**Flipping the flag today crashes before Stage 3 builds a single variable**
(`ImportError`, reproduced by the 2026-07-27 doc) — not a worse model, not a
wrong model, no model at all.

### 3.2 Why bundling is not defeated by the pruning measurement, even though it also depends on geometry

This is the load-bearing distinction of this whole task. Geographic pruning
asks *"is this edge near this net's pins?"* — a **locality** question, and
this board's answer is almost always yes-for-everything (median span
120.9mm against a 279mm diagonal). Bundling asks a different question
entirely: *"do these two nets' footprints overlap each other?"* — a
**mutual-similarity** question. Two nets that each individually span most of
the board (exactly the property that makes pruning useless) are, for that
same reason, *very likely* to have high Jaccard overlap with each other —
bundling is not just undefeated by non-locality, it is **structurally
favored** by it, in the cases where multiple nets share a `TypeSignature`.

The caveat, found by reading `bundle_analyzer.py`'s `TypeSignature` grouping
(§"analyze()", `bundle_analyzer.py:248`): bundling only fires **within** a
`TypeSignature` group of size ≥ 2. `gnd`, `vcc`, and `+3V3` — the board's
three highest-arity nets (86 / 13 / 51 pins, per the merged U5 doc) — are
each the **sole member of their own `net_class`** (there is exactly one
ground net, one `vcc`, one `+3V3`). A singleton type-signature group cannot
bundle with anything, by construction (`bundle_analyzer.py:277-282`,
`unbundled.append(ni)` for `len(net_indices) == 1`). So bundling's benefit
is concentrated in the **signal** class (98/110 nets, per §5's own
classification below), not in the three nets that individually dominate
per-net variable cost — worth stating plainly before the live measurement
below, so the number is read correctly.

### 3.3 A real correctness bug, found this task, independent of the missing binding

`_create_capacity_constraints` (`constraint_model.py:683-737`) builds each
edge's capacity constraint by iterating `for net_idx, net in
enumerate(self.nets)` — **real net indices, 0..109** — and looking up
`self.model.net_channel_vars[(net_idx, edge_id)]`. But
`_create_bundle_channel_vars` (`constraint_model.py:599-641`) stores bundle
variables keyed by **`(bundle_id, edge_id)`**, where `bundle_id` ranges
`0..bundle_count-1` — a **different, smaller index space that silently
collides with real net indices**. The consequence, read directly from the
code:

- A bundled net at real index `net_idx = 57` (say, belonging to bundle 3)
  has **no** entry at `(57, edge_id)` — only `(3, edge_id)` exists, keyed by
  bundle id — so the capacity-constraint loop silently contributes **no
  term at all** for net 57 on that edge.
- If `net_idx` happens to numerically coincide with some `bid` (common,
  since both start at 0 and cover overlapping small ranges), a term **is**
  added — but using `design_rules.get_rules_for_net(self.nets[net_idx].name)`,
  i.e. **the wrong net's** trace-width/clearance, not any width belonging to
  the bundle's actual members.

This bug's *presence* is a straightforward code read, not something that
needed a live run to confirm — but note that §3.4's live measurement never
actually reaches `_create_capacity_constraints` (the `MemoryError` fires
earlier, inside `_create_bundle_channel_vars` itself), so this bug remains
verified by inspection only, not by an observed bad constraint at runtime.

This means capacity constraints — the mechanism that keeps two nets from
being routed through the same physical copper beyond its width — are
**silently near-vacuous for the bundled path today**, independent of and in
addition to the missing solve binding. Reviving bundling is not just
"restore the PyO3 stub" (`docs/evidence/2026-07-27-bundled-encoding.md`'s
own framing); it needs `_create_capacity_constraints` to sum per-bundle
width contributions from every net inside a bundle, keyed consistently with
how `_create_bundle_channel_vars` names its variables.

### 3.4 Live measurement: bundled model size on the actual production board

Because `_create_bundle_channel_vars` and `BundleAnalyzer.analyze()` are
pure Python — the missing PyO3 binding is only reached by the *solve* call,
several steps later — this task drove `RouterV6Pipeline` directly with
`enable_bundling=True` (bypassing `route_pcb()`, which doesn't expose the
flag, per §3.1) and monkeypatched the missing `solve_topology_rust_bundled`
symbol to capture inputs and abort cleanly, so the real (unmodified)
`BundleAnalyzer` and `ModelBuilder` ran against the production board under
this task's own 8GB `ulimit -v`, `TEMPER_MODEL_TRACE=1`, guarded and
polled in-turn per the task's rules.

**MEASURED, this task, from two runs (see §"live-measurement methodology"
under Sources for exactly what each captured) — and it revises §3.2's
optimistic framing materially:**

```
Bundle analysis: 8 bundle classes for 110 nets
n_bundles=8, n_unbundled=89, bundle_sizes=[7, 2, 2, 2, 2, 2, 2, 2]
```

— the first line printed directly by `RouterV6Pipeline`'s own verbose
Stage 3 log; the second, fuller breakdown from this task's own instrumented
re-run of the identical `BundleAnalyzer.analyze()` call (deterministic —
both runs agree exactly on covered-edge counts per net, `PYTHONHASHSEED=0`).
**7 + (7×2) = 21 nets are captured by the 8 bundles; the other 89 (81% of
all nets) remain `unbundled` singletons**, receiving full per-net
`NetChannelVar` cost exactly as in the unbundled path. The realized
channel-var-creating unit count is therefore `8 + 89 = 97`, against 110
unbundled — a raw-variable reduction of only

```
110 / 97 = 1.134×   (11.8% fewer NetChannelVar instances, DERIVED, exact)
22,493,900 → 19,835,530
```

— far short of what's needed to close an 8GB gap the unbundled path already
missed by construction alone (§0's 5.43GB peak was for channel vars *and*
via vars *and* everything up to the crash point; a ~12% smaller channel-var
term alone was never going to be enough, and wasn't: see below).

**The 8 realized bundles, read from the manifest, are not what §3.2's
theory anticipated.** §3.2 predicted board-spanning same-class nets (large
footprints, high mutual Jaccard *because* they're both nearly board-wide)
as bundling's best case. What actually bundled is the opposite pattern —
**small, physically-adjacent, same-sub-circuit pin pairs**: relay coil
terminals (`power_in.bypass_relay-coil1`/`-coil2`), gate-driver bootstrap
bias pins (`hb.gate_hs.driver-p1-1`/`-p2`), an RTD chip's SPI lines
(`sdi`/`sdo`), a discharge relay's normally-open contacts
(`discharge.k_dis1-no`/`discharge.k_dis2-no`), and one 7-net cluster of
short safety-interlock signal nets converging near the same op-amp/latch
area (`RELAY_CTRL`, `power_in.q_relay_drv-g`, `safety.fault_any_or-y2`,
`safety.fault_or-y2`, `safety.ovp.comp-inp`, `safety.thermal.comp-inp`,
`safety.uvlo_logic.mon-outa`). These are exactly the kind of nets §5 already
found have small spans (several of §5's own "8 nets with span ≤15mm" list
appear here, e.g. `discharge.k_dis1-no`/`discharge.k_dis2-no` bundled
together). Meanwhile every board-spanning net named throughout this
document — `gnd`, `vcc`, `+3V3`, `SHUTDOWN`, `PWM_HS`, `PWM_LS`, `GATE_HS`,
`GATE_LS`, `SW_NODE` — sits in the **unbundled** list. §3.2's theoretical
mechanism (mutual overlap independent of locality) is still correct as
stated, but in practice on this board the `TypeSignature` exact-match
requirement (width/clearance/pin-layer-set, not just `net_class`) is
apparently satisfied far more often by genuinely nearby sibling pins on the
same component/sub-circuit than by unrelated board-spanning nets that
merely happen to share a coarse netclass — the extra precision in the
signature is, in effect, smuggling locality back in through a side door.

**Then `ModelBuilder.build()` `MemoryError`'d — inside
`_create_bundle_channel_vars`, the *bundled* variable-creation loop itself
(`constraint_model.py:641`, `self.model.add_variable(var)`) — the same
function and the same failure mode (`add_variable`'s dict assignment) as
the unbundled path's original OOM** (§0). Peak RSS climbed steadily and
roughly linearly from ~1GB (post-`BundleAnalyzer`) to the ~8GB `ulimit -v`
ceiling over about 100 seconds (MEASURED via periodic `ps` sampling: 3.1GB
at t=440s, 5.78GB at t=482s, `MemoryError` at t=491s), a growth profile
consistent with the unbundled path's own 5.43GB peak-RSS OOM (§0) — same
order of magnitude, not a small model that happened to hit an unrelated
ceiling.

**The underlying mechanism, read directly from `bundle_analyzer.py`'s
grouping rule (§3.2): `TypeSignature` equality requires an *exact* match**
on `trace_width` and `clearance` (both continuous mm values, rounded to 4
decimals — `bundle_analyzer.py:242-243`) **and** `pin_layer_set`, not just
`net_class`. 98/110 nets share `net_class == "signal"` (§5), but two signal
nets only bundle if their netclass-derived width/clearance and their
components' pin-layer footprints coincide exactly — a much narrower
condition than "both are signal-class," and this board has **11 distinct
netclasses** in `netclass_rules.yaml` (`ACMains`, `HighVoltage`,
`HighVoltageIsolated`, `FinePitch`, `Power`, `GND`, `GateDriveHV`,
`GateDriveSELV`, `HighSpeed`, `Signal`, `HighCurrent`), each imposing its
own width/clearance and further subdividing the already-coarse `net_class`
groups `TypeSignature` starts from. **This is the real, previously
unquantified reason bundling under-delivers on this board**, independent
of both the missing PyO3 binding (§3.1) and the capacity-constraint bug
(§3.3).

**A second, independent scalability problem, found this task and not
previously documented anywhere in the repo**:
`BundleAnalyzer._compute_covered_edges` (`bundle_analyzer.py:185-199`) is
itself an **unvectorized `O(n_nets × total_edges)` loop** — for every net,
it iterates *all* 204,490 skeleton edges across all 4 layers and calls
`footprint.contains(Point(midpoint))` (a raw, unprepared Shapely call) on
each one, to decide the net's Jaccard-comparable edge cover. MEASURED this
task: 110 nets, ~391s wall total, ~3.5s/net average (one clear outlier: net
1 alone took 80.6s, ~145,360/204,490 edges covered — almost certainly one
of the board-spanning high-arity nets). This is the *exact same shape* of
problem — one unvectorized geometric predicate evaluated once per
(net, edge) pair — that the U5 pruning measurement already flagged as
costly (§0's "~4× slower per net" finding) and that the recently-fixed
island-bridging pass (`07d514f9`) already solved once elsewhere in this
same pipeline with a KD-tree. `BundleAnalyzer` was never run at production-board
scale before this task (`docs/evidence/2026-07-27-bundled-encoding.md`
explicitly lists this as **UNVERIFIED**: *"Whether `BundleAnalyzer`...
still produces correct `BundleManifest`s against a real board's
`pcb.nets`/`stage2.skeletons`... it is exercised only by the same
ModelBuilder-level unit tests... never through the full pipeline"*) — this
task is the first time it has been, and it both completes (eventually) and
reveals its own unrelated performance problem in the process.

**Revised bottom line for bundling, incorporating this measurement**:
reviving it requires **four** fixes, not two —
(1) the missing PyO3 binding,
(2) the capacity-constraint net-index/bundle-id collision (§3.3),
(3) **a `TypeSignature` grouping rule loose enough to actually bundle a
useful fraction of this board's nets** (e.g. matching on `net_class` alone,
or a netclass-family grouping, rather than exact width/clearance/pin-layer
equality) — the single highest-leverage unfixed item, since the measured
8-bundle/89-unbundled split only removes 11.8% of primary channel
variables (110→97 effective units, DERIVED, exact), nowhere close to
enough to fit this task's own 8GB gate, and
(4) vectorizing `_compute_covered_edges` (KD-tree/STRtree over edge
midpoints, mirroring `07d514f9`'s fix for the structurally identical
island-bridging problem), since analysis alone taking ~6.5 minutes is not
acceptable pipeline overhead even once the grouping itself is fixed.

---

## 4. Skeleton coarsening — the task's suggested knob is a no-op; the real one is unexploited and unmeasured

`204,490 edges / (152mm × 234mm = 35,568 mm²) = 5.75 edges/mm²` (MEASURED /
DERIVED, matches the task brief's figure).

**The task brief's implied lever, `simplify_tolerance`, does not work on the
code path production uses today.** Read directly from both implementations:

- `channel_skeleton.py::_extract_medial_axis_single` (lines 255-263):
  *"`simplify_tolerance` is threaded through for signature parity; it is a
  documented no-op on this path (spike §8: GEOS's Voronoi edges here are
  always exactly 2 coordinates, and Douglas-Peucker simplification of a
  2-point line is the identity...)"*
- `temper-geometry/src/channel_skeleton.rs` (lines 46-52), the Rust port
  actually compiled and running today, same claim, same reasoning, plus:
  *"spade's undirected Voronoi edges are likewise always two circumcenters
  ... so the same holds structurally here, not just empirically for GEOS."*

Setting `simplify_tolerance` to any value today changes nothing. This is the
same shape of finding as bundling's missing binding — a knob that exists in
every function signature involved and does nothing.

**The real resolution knob**, found by reading `sample_ring`
(`channel_skeleton.rs:67-97`, verbatim port of
`channel_skeleton.py`'s boundary-sampling loop): each routing-space polygon
boundary is sampled at

```rust
let num_points = (dist as i64).max(2);   // dist = edge length in mm
```

— i.e. **roughly one Voronoi input site per 1mm of boundary**, hardcoded,
not exposed as a parameter anywhere in the call chain from
`extract_channel_skeleton()` down. This directly sets Voronoi diagram
density and therefore the skeleton's edge count.

**ESTIMATED, not measured — no Rust rebuild/prototype was run for this
option** (time was spent on the higher-value bundling prototype instead,
per the task's own steer): raising this spacing to 2mm or 3mm would roughly
linearly reduce boundary-sample-point count, and Voronoi complexity for
points distributed along a bounding curve scales close to linearly with
site count, so a proportional (~2×, ~3×) edge-count reduction is a
reasonable order-of-magnitude expectation — but this is unverified against
real capacity/DRC-validity impact. Coarser channel edges reduce the
router's ability to represent capacity precisely near tight, fine-pitch
areas (the `FinePitch` netclass's 0.1mm clearance / 0.127mm trace width
corridors need sub-mm resolution to remain representable at all), so a
single global constant is the wrong shape for this fix — it would need to
be adaptive (coarse in open plane area, fine near dense components), which
is materially more engineering than changing one constant.

**Before coarsening anything, a documented, already-scoped, non-legitimate
contributor to the current edge count should be fixed first.** Read
directly from `channel_skeleton.py:469-484` (the island-bridging function's
own docstring, cross-referenced against this task's merged U5 doc §1):
`obstacle_map.py`'s zone loop unions every zone on a layer into that
layer's obstacle polygon **net-blind** (regardless of which net the pour
belongs to), so F.Cu/B.Cu measure only **~25% available routing area**
versus **~98%** on the inner layers — pours the router will never actually
route through still carve the medial axis into many small, spurious
pockets that then require the just-added KD-tree/Kruskal bridging pass to
reconnect. This is a defect, not legitimate routing-resolution need, and
the already-scoped, not-yet-implemented "pours become derived output" fix
(`docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md`, per
`channel_skeleton.py:482-484`'s own docstring) is the correct place to
remove that inflation.
Coarsening the medial axis on top of an artificially-fragmented obstacle map
would coarsen legitimate and artifact-driven density together, indiscriminately.

**Verdict: mechanism identified precisely (and the task's own suggested
knob shown to be inert), but UNMEASURED — no prototype was built this task.
Fix the upstream obstacle-map defect first; it targets exactly the
inflation this option is chasing without touching skeleton resolution at
all.**

---

## 5. Net-class-aware margins — MEASURED, conclusively the weakest option

Reused the exact production predicate functions
(`constraint_model.py::_pin_world_positions` / `_pin_span` — the same code
U5's own geometric analysis is built on, not a re-derivation) in a
standalone script, cross-tabulated by `net_classification.classify_net_type`
against `pcb/temper.kicad_pcb`:

| net_class | n | median span | mean span | n(span ≤ 15mm) |
|---|---:|---:|---:|---:|
| signal | 98 | **134.4mm** | 129.0mm | 8 (8%) |
| power | 8 | 236.4mm | 214.8mm | 0 (0%) |
| hv | 3 | **107.7mm** | 148.2mm | 0 (0%) |
| ground | 1 | 242.0mm | 242.0mm | 0 (0%) |

MEASURED, this task (script:
`/tmp/claude-1000/.../scratchpad/net_span_by_class.py`, run against
`pcb/temper.kicad_pcb` sha256 `1cce4a08...`, unchanged).

**The obvious hypothesis — that `signal` nets, being logic/control rather
than power distribution, might be locally clustered even though the board
as a whole is not — is directly falsified by this table.** The `signal`
class's own median span (134.4mm) *exceeds* the `hv` class's median
(107.7mm). Signal nets are, if anything, *more* globally distributed than
HV nets on this board, because they connect scattered sensing/control
points (RTD sense lines, gate-drive control, watchdog, safety interlocks)
across the whole board rather than concentrating in one power section.

Only 8/110 nets (7.3%) have span ≤15mm board-wide, regardless of class:
`y1`, `rtd_pan.r_high_top-inp`, `safety.latch-b2`, `safety.fault_or3-b2`,
`safety.fault_or-a2`, `discharge.k_dis1-no`, `discharge.k_dis2-no`,
`DISCHARGE_CTRL`. These happen to all be `signal`-class, but membership in
the class isn't what identifies them — per-net span already does, and
per-net-span-based pruning is exactly what §0 already measured at 0%
aggregate benefit. Net-class as a partitioning key adds **no** discriminating
power beyond what per-net geographic pruning already tried and failed at.

**Verdict: confirmed the weakest option, now closed rather than merely
suspected — there is no clusterable subset hiding inside a net-class
partition on this board.**

---

## 6. Cross-cutting finding: locality vs. similarity

Every option above sorts into exactly two families:

- **Locality-based** (pruning, layer-wise-by-geometry, net-class margins,
  and block decomposition below): asks "is X *near* Y?" — defeated on this
  board because the dominant-cost nets (`gnd`, `vcc`, `+3V3`, and most
  `signal` nets too, per §5's own table) are not near anything in
  particular; they are distributed across most of the 279mm diagonal.
- **Similarity-based** (bundling): asks "is X *like* Y?" — genuinely
  independent of locality, and in the specific case of same-class
  board-spanning nets, actively favored by the same non-locality that
  defeats the first family — **in theory.** §3.4's live measurement shows
  the *implemented* similarity test (`TypeSignature` exact-match on
  continuous width/clearance plus pin-layer set, not just `net_class`) is
  strict enough that only 8 bundle classes actually formed on this board —
  the theoretical advantage is real, but the code as it exists today
  doesn't yet cash it in.

This is the single most important structural fact this task surfaces: it is
not that "reduction is hard on this board" in general — it is that **one
specific family of reduction technique (geometric partitioning) is
structurally the wrong shape for this board's net topology**, while a
different family (equivalence-class merging) is not — though realizing
that theoretical advantage in practice still requires loosening the one
implementation that was already built once before being lost to a
refactor (§3.4).

---

## 7. Is a monolithic SAT formulation the wrong tool here?

**Partially, and the STRATEGY.md build-order already names the intended
alternative — but with the same non-locality caveat, and it is explicitly
not being worked on right now.**

`docs/STRATEGY.md` (v3.0, 2026-07-25, no newer version exists in this
worktree) build-order step 8: *"Block decomposition of routing on the
atopile hierarchy... Subdivides the one loop that is still monolithic
(`METHODOLOGY.md` §3.4)"*, gated explicitly on step 2 (seam contracts)
landing first. `METHODOLOGY.md` §3.4 names the decomposition directly:
route one atopile block (`hb.*`, `tank.*`, `safety.*`, `discharge.*`,
`power_in.*`, `thermal.*`, `rtd_pan.*`) at a time, freezing it before moving
to the next, with boundary contracts where blocks share nets.

**Checked this task**: of 162 unique net names on `pcb/temper.kicad_pcb`,
only 60 (37%) carry an atopile block prefix (MEASURED, direct grep on the
board file); the rest — including every one of the highest-arity nets named
throughout this document (`gnd` 86 pins, `vcc` 13, `+3V3` 51) — are flat,
unprefixed, board-global names. Block decomposition would shrink the
*signal*-net portion of the problem, but the same handful of dominant-cost
nets that defeat pruning would necessarily cross every block boundary as
shared contracts, still touching most of the skeleton — **the identical
limitation §0/§6 already measured, wearing a different name.**

Per `docs/STRATEGY.md`'s own track-status table (unchanged as of this
worktree): **"Pipeline (place & route)" is `paused pending track 1`**, and
**"Router/placer hygiene" is `HALTED`** — the "Verification correctness"
track is the sole active WIP-limited track, and step 8 is gated behind step
2, which hasn't landed. So: yes, block decomposition is already the
project's own named intended architecture — and no, it is not authorized to
start yet, independent of this task's findings.

**On the narrower question — is SAT/CDCL itself the bottleneck** — the
evidence says no. Every full-board solve this pipeline has ever completed
succeeded with **0 conflicts, 0 decisions** (§0's pre-fix baseline,
re-confirmed at production scale). The solver is not struggling to search;
it has never had to search. The cost is entirely in **constructing and
loading an encoding that is uniformly dense (one variable per (net, edge)
pair, no candidacy filter of any kind) at a scale where even Python object
overhead for the raw model alone (22.5M objects ≈ 5.43GB observed) exceeds
the memory gate before the solver is ever invoked.** That argues for
shrinking the *encoding*, not replacing the *solver* — which is exactly
what both bundling (§3) and batching (§2) do, and what block decomposition
would also do if it weren't blocked by the same non-local dominant nets and
by project governance.

---

## 8. Recommendation

**Still recommend reviving the bundled encoding (§3) over inventing
something new — but §3.4's live measurement changes the fix order.**
Before this task, the known blocker was "restore the PyO3 stub." This
task's own run shows that alone would not be enough: `BundleAnalyzer`
produced only 8 bundle classes for 110 nets, and the resulting model
`MemoryError`'d at essentially the same scale as the unbundled path,
never reaching the missing binding at all. Fix order, highest-leverage
first:

1. **Loosen `TypeSignature` grouping** (`bundle_analyzer.py:22-28`) —
   the single highest-leverage unfixed item found this task. Exact-match
   on continuous `trace_width`/`clearance` plus `pin_layer_set` is why
   only 8 bundles formed against 11 distinct netclasses; grouping on
   `net_class` alone (or a coarser netclass-family key) is the first
   thing to try and measure, before anything else here is worth doing.
2. **Vectorize `BundleAnalyzer._compute_covered_edges`** (§3.4) — its own
   unvectorized `O(n_nets × E)` loop (~391s wall, MEASURED, this task) is
   a second, independent scalability problem, structurally identical to
   the island-bridging problem `07d514f9` already fixed elsewhere in this
   same pipeline with a KD-tree — the same fix shape applies here.
3. Fix `_create_capacity_constraints`'s net-index/bundle-id key collision
   (§3.3) — required for the bundled path to be *correct*, independent of
   the missing binding, and currently undiscovered by any test in the repo.
4. Extend `_create_via_vars` to be bundle-aware — today it ignores
   `enable_bundling` entirely and remains full per-net cost, and would
   become the dominant term once (1) actually shrinks `NetChannelVar`.
5. Rebuild `solve_topology_rust_bundled` in
   `packages/temper-rust-router/src/lib.rs` over the still-compiled,
   still-uncalled `Watchdog`/`extract_bundled`/`expand_assignments` core
   (761 lines already exist and compile, `cargo clippy --release` silent —
   re-verified this task) — real, scoped work, not "invent a new
   architecture," but only worth doing once (1)-(4) mean the model
   Rust would receive actually fits in memory.
6. First-ever integration test coverage for `Watchdog::solve` against real
   (non-synthetic) constraint data before trusting its output.

Re-run this task's own measurement script after (1) to get a real
bundle-count/reduction number before investing in (5)-(6) — that is the
fast, cheap checkpoint this task did not have time to iterate to.

**Pair with net-batching (§2) as the near-term, low-engineering-risk
fallback or complement regardless of how bundling's fix-order plays out**,
since it is corroborated by numbers already on record (a 2.6M-variable raw
model already survived construction under this task's own 8GB cap) without
requiring any Rust work or changes to `bundle_analyzer.py`'s grouping
logic, and it is the one option in this document that does not depend on
guessing how much a code change will help before measuring it.

**Do not pursue net-class-aware margins (§5, conclusively the weakest,
MEASURED) or skeleton coarsening via `simplify_tolerance` (§4, a no-op) as
currently framed.** Fix `obstacle_map.py`'s net-blind pour-unioning defect
before considering any deliberate coarsening — it is already-scoped,
already-attributed, and removes non-legitimate edge-count inflation the
coarsening options would otherwise coarsen indiscriminately alongside real
signal.

**Layer-wise decomposition (§1)** is real but capped at ~1.8× (not the
naive ~4×) by the same plane fix that made this measurement possible in the
first place, and needs a from-scratch inter-layer via contract. Not
recommended as a first move, but worth revisiting once bundling has
proven out and the remaining bottleneck is better characterized.

---

## Sources

- `docs/evidence/2026-08-07-pruned-encoding-measurement.md` — this task's
  starting baseline (204,490-edge skeleton, 22,493,900 primary vars, 0%
  pruning reduction, both paths OOM before CNF, board/net-span geometry).
- `docs/evidence/2026-07-27-stage3-model-and-rewrite.md` — pre-fix baseline
  (3,876,012 raw vars → 42,145,777 CNF vars, ~10.87× Sinz blowup, 52.67s
  end-to-end SAT phase, 0 conflicts/0 decisions) and Part 2's original
  `O(n_nets × E)` diagnosis naming bundling as the fix.
- `docs/evidence/2026-07-27-bundled-encoding.md` — full bundling history:
  built 2026-06-29, PyO3 entrypoint dropped 2026-07-08, why it went
  undetected, and the scoped restoration plan this task's recommendation
  builds on directly.
- `docs/STRATEGY.md` — "The bundled encoding was deleted by a refactor and
  nobody noticed"; build-order step 8; track-status table (Pipeline paused,
  Router/placer hygiene HALTED).
- `docs/METHODOLOGY.md` §3.4 — block decomposition on the atopile hierarchy,
  gated on §3.3 (seam contracts).
- `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py` —
  `_create_channel_vars`/`_create_bundle_channel_vars`/`_create_via_vars`/
  `_create_capacity_constraints` (§3.3's bug), `_pin_world_positions`/
  `_pin_span` (reused directly for §5's measurement).
- `packages/temper-placer/src/temper_placer/router_v6/bundle_analyzer.py` —
  `TypeSignature`, Jaccard clustering, `analyze()` (§3.2's singleton-class
  finding).
- `packages/temper-placer/src/temper_placer/router_v6/channel_skeleton.py`,
  `packages/temper-geometry/src/channel_skeleton.rs` — `simplify_tolerance`
  no-op (§4), `sample_ring`'s hardcoded ~1mm boundary-sampling constant,
  and the island-bridging docstring attributing outer-layer fragmentation
  to `obstacle_map.py`.
- `packages/temper-placer/src/temper_placer/router_v6/net_classification.py` —
  `classify_net_type` (ground/power/hv/signal precedence, used by §5's
  measurement).
- `pcb/temper.kicad_pcb` (sha256 `1cce4a0872051675b0339de3378ff7ec2c16bb4b035c999dfa408dec5ecbc3f6`, unchanged by this task) — direct grep for net-name hierarchy prefixes (§7).

### §3.4's live-measurement methodology, for reproduction

`route_pcb()` doesn't expose `enable_bundling` (§3.1), so this task drove
`RouterV6Pipeline(enable_bundling=True, ...)` directly, mirroring
`route_pcb()`'s own empty-placements branch (layer-constraint resolution,
netclass injection) so the model is built under the same production config
`scripts/route_board.py` uses. Both `BundleAnalyzer._compute_covered_edges`
and `BundleAnalyzer.analyze` were monkeypatched (not modified in-place) to
print progress and capture the manifest immediately after `analyze()`
returns, before `ModelBuilder.build()`'s subsequent OOM — the missing
`solve_topology_rust_bundled` symbol was also monkeypatched (per §3.1,
never reached in this run; captured for completeness on an earlier,
now-superseded run of the same script that let `ModelBuilder.build()`
proceed and observed the `MemoryError` directly). Two runs: the first
(`ulimit -v 8388608`, `TEMPER_MODEL_TRACE=1`, `TEMPER_REWRITE_TRACE=1`,
`PYTHONHASHSEED=0`, no wall-time budget beyond an outer `timeout 1800`)
producing the `MemoryError` traceback and the "8 bundle classes for 110
nets" line quoted in §3.4; the second, identical setup but with `analyze()`
short-circuited immediately after capturing the manifest (avoiding a
second ~7-minute wait to re-observe the already-established OOM), for the
bundle-size/unbundled-net-name breakdown. Both runs backgrounded and
polled in-turn per the task's rules, never left to run unattended past a
turn boundary.
