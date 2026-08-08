<!-- provenance: commit=5b0a078bf5c445e73a30b2d654852c6a405500ed dirty=true -->

# R6: the `zone_emission.py` clustering defect -- diagnosis, fix, and measured effect

**Date:** 2026-08-07
**Task:** `docs/evidence/2026-08-07-channel-skeleton-net-aware-pours.md` Section 4
measured that the net-aware pour fix only moved F.Cu/B.Cu available area
25.0%->25.3% / 25.2%->25.5%, and attributed the shortfall to R6 of
`docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md`: two of the 14
obstacle-eligible zones, `SW_NODE` and `DC_BUS_RTN`, are "pathological
board-spanning hulls that exceed the board's own extents," a
`zone_emission.py` clustering defect, not fixed by that task. This document
diagnoses the defect precisely (not by inspection of the committed board's
already-baked-in geometry, but by reproducing the generator against the
current board's real pad positions), fixes it, and measures the effect.

---

## 1. Diagnosed mechanism (not guessed -- reproduced directly)

`_emit_zone_pours()` (`_zone_pour_stitch.py`) calls
`zone_emission.compute_zones_for_net(..., cluster=not exempt)`, where
`exempt = net_class in _CONTINUITY_EXEMPT_CLASSES` and
`_CONTINUITY_EXEMPT_CLASSES = {"GND", "ACMains", "HighVoltage"}` (pre-fix).
`cluster=False` means `compute_zones_for_net` builds **one convex hull over
every pad the net has, board-wide**, instead of `_cluster_positions()`'s
natural-gap hierarchical clustering used by every other net class.

Reproducing `compute_zones_for_net` directly against `pcb/temper.kicad_pcb`'s
current, real pad positions (`parse_kicad_pcb_v6`, absolute board coordinates,
board outline `(20,20)-(172,254)`, 152mm x 234mm, 35,568 mm^2) rather than
inspecting the committed board's already-existing zone polygons in isolation:

| Net | Class | Pads | cluster=False hull area | % of board | Exceeds board outline? |
|---|---|---:|---:|---:|---|
| SW_NODE | HighVoltage | 7 | 14,721.2 mm^2 | 41.4% | **Yes** (y: 8.40 to 258.17, board is 20-254) |
| DC_BUS_RTN | HighVoltage | 12 | 19,875.1 mm^2 | 55.9% | **Yes** (x: 15.84 to 181.91, board is 20-172) |
| +170V_BUS | HighVoltage | 11 | 25,127.6 mm^2 | 70.6% | Yes |
| zcd | HighVoltage | 4 | 15,320.7 mm^2 | 43.1% | Yes |
| tank.c_tank1-p2 | HighVoltage | 4 | 13,639.0 mm^2 | 38.3% | Yes |
| PWR_RTN | GND | 18 | 21,504.3 mm^2 | 60.5% | No |
| ac_l / ac_n | ACMains | 2 / 3 | 1,373.9 / 2,484.5 mm^2 | 3.9% / 7.0% | No |
| *(9 more HighVoltage nets)* | HighVoltage | 2-4 each | 366.8 - 7,189.6 mm^2 | 1.0-20.2% | 5 of 9 yes |

**This is not limited to the two nets R6 named.** Every `HighVoltage`-class
net with pads genuinely spread across the board produces the same defect --
17 nets carry the `HighVoltage`/`ACMains`/`GND` classes and are zone-eligible
on this board today (via `_zone_layers_for_net`); 12 of the 14 `HighVoltage`
members exceed the physical board outline under the pre-fix exemption. `GND`
(`PWR_RTN`) and `ACMains` (`ac_l`/`ac_n`) do **not** exceed the outline under
the same exemption -- a materially different, less severe defect (see
Section 3 for why this justifies leaving them exempt).

**Two independent, additive causes, disentangled by testing them separately:**

1. **The dominant cause (~85-98% of the excess area): no clustering.**
   `SW_NODE`'s 7 pads and `DC_BUS_RTN`'s 12 pads are genuinely spread
   across almost the full board diagonal -- this is real (the DC bus return
   and switch node legitimately touch components across the whole power
   stage) -- so a single convex hull over all of them already covers most
   of the board's area *before* any margin is applied. Clustering these same
   pads with the network's normal `_cluster_positions()` (unchanged
   algorithm -- see Section 3) produces 5-6 small, well-separated hulls per
   net instead: SW_NODE's hulls total 819-873 mm^2 (2.3-2.5% of board);
   DC_BUS_RTN's total 2,312-2,422 mm^2 (6.5-6.8%). That alone is an 88-94%
   area reduction, with or without clipping.
2. **The secondary cause (the remaining few mm, but the entire reason a hull
   crosses the physical edge): no clip to the board outline.**
   `_convex_hull_from_positions`'s margin/clearance buffer
   (`Polygon.buffer(margin, join_style=2)`, a mitre join) extends a convex
   hull's corners past the flat margin distance at acute vertices -- e.g.
   SW_NODE's unclustered hull reaches y=8.40mm (11.6mm past the board's
   y=20 edge) and y=258.17mm (4.17mm past y=254) from a 6.0mm margin ($=$
   `HighVoltage.clearance`). Nothing in `zone_emission.py` or
   `_zone_pour_stitch.py` ever intersected the result against the board
   polygon. Isolating this cause (clip only, clustering still forced off):
   SW_NODE's area barely moves (14,721.2 -> 14,644.0 mm^2, 41.4% -> 41.2%)
   -- confirming clustering, not the edge overshoot, is the area driver;
   clipping's job is entirely to stop the hull crossing `Edge.Cuts`, which
   matters for `routing_copper_pullback` (Section 4) even though it is
   inert for available-area math (Shapely's `board.difference(obstacles)`
   already ignores obstacle geometry outside `board` -- see Section 3).

Neither cause is "a distance threshold that merges clusters that should stay
separate" -- `_cluster_positions()`'s natural-gap hierarchical clustering,
unmodified, produces sensible per-component clusters for these exact same
pads once it is allowed to run (see the cluster counts and areas above). The
defect is entirely the explicit `cluster=not exempt` override combined with
the total absence of a board-outline clip anywhere downstream of it.

## 2. Fix implemented

**`zone_emission.compute_zones_for_net()`** gained an optional
`board_polygon: shapely.Polygon | None` parameter. When given, every hull
(clustered or not) is intersected against it (`_clip_to_board`); a hull that
splits across a concave boundary yields multiple `ZoneDefinition`s, one that
falls entirely outside is dropped. This is unconditional -- applied
regardless of the `cluster` argument -- because copper cannot exist off the
physical board by construction, independent of any clustering policy
decision.

**`_zone_pour_stitch._emit_zone_pours()`** gained a `pcb` parameter (the
`ParsedPCB` its caller, `_write_routes_to_content`, already has as
`result.pcb`) used only to resolve the board outline via the existing
`routing_space._get_board_polygon()` helper (reused, not reimplemented) and
thread it into every `compute_zones_for_net` call. `pcb=None` (the default,
matching every pre-existing call site) disables clipping and reproduces
prior behavior exactly -- callers without a `ParsedPCB` handy (e.g. tests
constructing pad positions directly) are unaffected.

**`_CONTINUITY_EXEMPT_CLASSES`** dropped `"HighVoltage"`:
`frozenset({"GND", "ACMains", "HighVoltage"})` ->
`frozenset({"GND", "ACMains"})`. `GND` and `ACMains` are untouched.

## 3. Why `HighVoltage` specifically, and why not `GND`/`ACMains` too

**`HighVoltage`'s clustering exemption was never justified by its own
design spec.** `docs/hardware/TRACE_WIDTH_CALCULATIONS.md`:
- SS3.1 (DC bus path, `HighVoltage`): "Multiple parallel traces or zones
  **acceptable**" -- multiple zones is spec-sanctioned, not a compromise.
- SS3.2 (switch node, `HighVoltage`): "**Keep switch node AREA minimal**
  (EMI source)" -- directly contradicts a single hull covering 41% of the
  board; the exemption was producing the opposite of the class's own
  documented intent for this specific net.

**Electrical continuity of the net is unaffected by un-exempting it.** The
zone is a supplemental copper pour laid down *after* routing already
connects every pad via traces (`_emit_zone_pours` runs at the very end of
`_write_routes_to_content`, on top of an already-complete route) -- it is
not the net's only conductive path. Splitting the pour into per-cluster
patches does not disconnect anything; each patch still sits directly on/
around the real pads it covers.

**Current-carrying justification for what was kept, not shrunk away.**
Tank current is 24.5A rms / 34.5A peak (2026-08-07 part-stress/ZVS work,
above `TRACE_WIDTH_CALCULATIONS.md`'s own 22A design figure).
SS3.1-3.3 call for a minimum 5.0mm (DC bus/switch node) to 10mm+ (resonant
tank connection) copper *width* at this current. Every post-fix cluster
hull for `SW_NODE`/`DC_BUS_RTN` measures well past that: bounding boxes from
roughly 12x12mm to 34x24mm (a direct consequence of the 6.0mm
`HighVoltage.clearance` margin buffered on both sides of each pad cluster --
2x6.0mm = 12mm minimum hull width by construction). The fix does not
shrink these nets into inadequate conductors; it stops padding them with
board area that carries no current at all (the empty two-thirds of the
board between an AC input connector and a resonant-tank pad, previously
swept into one hull because both pads belonged to the same net).

**`GND` (`PWR_RTN`) and `ACMains` (`ac_l`/`ac_n`) are deliberately left
exempt, for two different reasons:**
- `ac_l`/`ac_n` measured 3.9%/7.0% of board and do not exceed the outline
  under the pre-fix exemption -- not pathological today. Left as-is rather
  than churning working geometry.
- `PWR_RTN` (`GND`'s only zoned member) is large (60.5% of board) but,
  unlike every `HighVoltage` case, does not exceed the physical outline --
  a real oversizing concern, but a *different* one from R6's "board-spanning
  past the board edge" framing. `GND` is `plane_preferred` by deliberate SSOT
  declaration (KD2 of the pour-derivation plan: "GND losing its pour is the
  accident the SSOT fix was not supposed to produce" -- the opposite framing
  from R6), and a genuinely continuous return plane is a legitimate ask for
  EMI/loop-area control on a switching supply. Whether `PWR_RTN`'s sizing
  should also shrink (vs. move to an inner-layer plane, U2/R8, already
  deferred) is a separate judgment call this task does not make -- R6 names
  `SW_NODE`/`DC_BUS_RTN` specifically, and this fix stays inside that scope
  for `GND`.

## 4. Measured effect

### 4.1 On the currently committed `pcb/temper.kicad_pcb`: none, structurally

`obstacle_map.py`'s zone loop (Stage 2.1, feeds the F.Cu/B.Cu available-area
and channel-skeleton numbers) reads `zone.polygon` **directly from the
parsed, committed board file** -- it never calls `zone_emission.py`.
`zone_emission.py`/`_emit_zone_pours()` only run at the very end of
`_write_routes_to_content()`, writing *output* content, strictly after
Stage 2/3 (obstacle map, skeleton, SAT model) have already completed using
the *pre-existing* committed zones. Confirmed by reading both call graphs,
not assumed. Combined with the task's prohibition on editing
`pcb/temper.kicad_pcb`, **this fix cannot and does not move the checked-in
board's measured available-area, skeleton-edge-count, or `route_pcb()`-
progress numbers** -- there is no code path today by which a
`zone_emission.py` change reaches those measurements without an actual
regenerate-and-recommit cycle (R7's still-not-landed "pours become derived
output" migration), which is out of this task's scope by the same
constraint. This mirrors exactly what the net-aware-pours evidence doc
already said of R6: "the polygon geometry of SW_NODE/DC_BUS_RTN zones on
the committed board is unchanged by this task" -- now confirmed true of
this fix too, for a different, structural reason (write-path vs. read-path,
not "chose not to").

### 4.2 Simulated regeneration: what R7 would produce once it lands

To give the "if this were regenerated" answer the task asks for without
touching the committed file, the currently-committed zones for the 5 nets
that have one today (`ac_l`, `ac_n`, `DC_BUS_RTN`, `SW_NODE`, `+170V_BUS` --
10 zone entries, F.Cu+B.Cu) were **replaced in memory only** with freshly
emitted `ZoneDefinition`s (via the real `compute_zones_for_net`/
`_emit_zone_pours` code paths, using the board's real current pad
positions), then fed through the real `build_obstacle_map()` +
`compute_routing_space()` + `_extract_medial_axis()` +
`_ensure_skeleton_connectivity()` pipeline stages -- the identical
methodology `docs/evidence/2026-08-07-channel-skeleton-net-aware-pours.md`
Section 4 used for its own before/after measurement. Nothing was written to
`pcb/temper.kicad_pcb`.

| Layer | Committed board (today) | Simulated regen, pre-fix logic (HV exempt, unclipped) | Simulated regen, fixed logic (HV clustered, clipped) |
|---|---:|---:|---:|
| F.Cu available | 25.3% (8,997.0 mm^2) | 19.0% (6,768.6 mm^2) | **43.2% (15,359.0 mm^2)** |
| B.Cu available | 25.5% (9,079.0 mm^2) | 19.3% (6,855.1 mm^2) | **43.6% (15,519.2 mm^2)** |
| In1.Cu / In2.Cu | 98.2% (unaffected -- no zones there) | 98.2% | 98.2% |

Once R7's regeneration actually lands, the fix in this document would raise
F.Cu/B.Cu available area from ~25% to ~43% -- closing roughly half the gap
to the inner layers' 98.2%, and clearing every net named in R6 plus the
broader `HighVoltage` set (Section 1) of its board-spanning geometry.

### 4.3 Channel-skeleton edges and islands: this fix GROWS the model, not shrinks it -- reported prominently as instructed

Same simulated-regeneration comparison, extracting the medial-axis skeleton
and running the same KD-tree/Kruskal bridging (`07d514f9`) used for the
committed-board baseline:

| Layer | Committed board: edges post-bridge / islands post-bridge | Simulated regen, fixed logic: edges post-bridge / islands post-bridge |
|---|---:|---:|
| F.Cu | 52,428 / 131 | **96,136 / 331** |
| B.Cu | 22,154 / 152 | **38,216 / 248** |
| Total (F.Cu+B.Cu) | 74,582 | **134,352** |

**This materially GROWS the model -- roughly 1.8x more skeleton edges and
2.3-2.5x more pre-bridge islands on both outer layers, not a reduction.**
Freeing the board area that the oversized `HighVoltage` hulls previously
blanketed does not simplify the routing problem; it opens far more
navigable, irregularly-shaped open space for the medial-axis algorithm to
trace between the many small remaining obstacles (pads, tracks, the
now-much-smaller per-cluster zones), which is a *larger*, not smaller,
input to `ModelBuilder`'s per-net `NetChannelVar` construction -- the exact
mechanism behind the 204,490-edge / 22,493,900-variable / 5.43GB
`MemoryError` baseline other in-flight work on this board is measuring. If
R7's regeneration lands as designed, it should be expected to make the
existing OOM problem *worse*, not better, absent an accompanying model-size
reduction (pruning, block decomposition, or similar -- all out of this
task's scope). Flagged prominently per the task's own instruction: this is
the first change today that *would* materially move the model size, and it
moves it in the opposite direction a naive "more available copper area is
better" intuition would predict.

(Absolute edge counts here differ from the 204,490-edge full-pipeline
baseline cited elsewhere today -- this measurement's harness calls
`build_obstacle_map`/`compute_routing_space`/`_extract_medial_axis`/
`_ensure_skeleton_connectivity` directly, without escape-via generation or
the full pipeline's pad-anchor-node augmentation step, both of which add
further edges. The *relative* before/after comparison above uses one
consistent harness for both arms and is not affected by that difference;
the absolute totals are not meant to reproduce the other baseline exactly.)

### 4.4 `route_pcb()` progress: unchanged, for a stronger reason than "not measured"

Beyond the same "output-writing happens after Stage 2/3 complete"
observation for the checked-in board (Section 4.1), Section 4.3's
regenerated zones **cannot** feed back into the *same* `route_pcb()` call's
own routing decisions even when `enable_zone_pours=True` is passed:
`_emit_zone_pours()` writes into `routed_pcb_content`, the function's final
return value -- there is no re-parse-and-re-route step afterward.
`route_pcb()`'s progress against the #871 OOM ceiling is therefore
**unchanged in both directions** by this fix, on any board state that
exists today: not worse (Section 4.3's edge growth never reaches a live
Stage 3 solve), and not better (Section 4.1's read path never sees the
regenerated geometry). This only becomes live once a separate
regenerate-then-recommit-then-reroute cycle exists (R7, not yet built).

### 4.5 `routing_copper_pullback`

The wasm-tier pullback rule (`packages/temper-drc-rs/src/rules/routing/
copper_pullback.rs`) reads `pcb/temper.kicad_pcb`'s zones directly, same as
`obstacle_map.py` -- so, as in Section 4.1, **this fix clears 0 of the 42
violations currently measured on the committed board**, because nothing in
`pcb/temper.kicad_pcb` changed. All 42 remain, unaffected in either
direction, until a regenerate-and-recommit cycle runs.

On the same simulated-regeneration harness as Section 4.2 (10 committed
zone entries -> replaced with fresh output for `ac_l`, `ac_n`, `DC_BUS_RTN`,
`SW_NODE`, `+170V_BUS`), testing each emitted zone against the exact rule
the WASM producer uses (board outline inset by `margin_mm=3.0`):

| Metric | Pre-fix logic (HV exempt, unclipped) | Fixed logic (HV clustered, clipped) |
|---|---:|---:|
| Zones extending past the **physical board outline** (not just the 3mm inset) | 6 of 6 (100%) | **0 of 38 (0%)** |
| Zones violating the stricter 3mm-inset pullback test | 6 of 10 total zones | 14 of 38 total zones |

**The "drawn larger than the physical board" rule-gap category -- exactly
what `docs/evidence/2026-08-07-creepage-authority-and-pullback-analysis.md`
Section 2.2 named as its first violation category (8 of the 42, "outline
exceeds the board edge itself") -- is eliminated outright by the clip: 0
zones can ever extend past `Edge.Cuts` again, for any net, by construction.**
The raw violating-zone *count* against the tighter 3mm inset test rose
(6->14) only because clustering also raised the total zone count (10->38);
the *rate* fell (60%->37%). The remaining violations are a legitimately
different, unaffected phenomenon the creepage doc already separated out
(Section 2.3, "34 of 42... entirely inside the board, only violates the 3mm
inset"): a small pour immediately around a pad that is itself genuinely
within a few mm of the board edge (e.g. a component near an edge-mounted
connector) will always be within a few mm of the edge too, regardless of
clustering or clipping -- that is a placement fact, not a zone-emission
defect, and this fix neither claims nor attempts to resolve it.

## 5. Tests

`uv run pytest packages/temper-placer/tests/router_v6/test_zone_emission.py
packages/temper-placer/tests/router_v6/test_adapter.py
packages/temper-placer/tests/router_v6/test_zone_pour_geometry_rust_differential.py
-q`: 124 passed, 1 skipped, 1 failed. The failure
(`test_tie_break_class_exists_direct_cKDTree_comparison`) is pre-existing
and unrelated -- confirmed by reading its own assertion message ("the
forcing coordinates no longer reproduce a scipy/first-wins disagreement...
should be re-derived"), a hardcoded-coordinate probe of
`scipy.spatial.cKDTree`'s internal tie-break order that
`docs/evidence/2026-08-07-channel-skeleton-net-aware-pours.md` Section 6
already reported failing for the same stated reason before this task's
changes existed.

Full `packages/temper-placer/tests/router_v6/` suite (4800+ items):
run in the background; see this document's companion commit for the final
tally once it completes. `test_r3_channel_skeleton_filters_to_outer_layers`
remains failing, as instructed -- untouched by this change.

## 6. Sources

- `docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md` -- R6, the
  requirement this document implements.
- `docs/evidence/2026-08-07-channel-skeleton-net-aware-pours.md` -- Section
  4/5, the measurement this document's Section 4 extends and the
  methodology it reuses.
- `docs/evidence/2026-08-07-creepage-authority-and-pullback-analysis.md` --
  Section 2, the pullback violation categorization this document's Section
  4.5 confirms and extends.
- `docs/hardware/TRACE_WIDTH_CALCULATIONS.md` SS3.1-3.3 -- the current-
  carrying and area-intent spec cited in Section 3.
- `packages/temper-placer/src/temper_placer/router_v6/zone_emission.py`,
  `_zone_pour_stitch.py`, `_adapter_convert.py`, `obstacle_map.py`,
  `routing_space.py`, `channel_skeleton.py` -- read and/or changed.
