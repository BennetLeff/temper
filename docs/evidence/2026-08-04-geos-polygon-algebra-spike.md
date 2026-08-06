# S1 spike: GEOS polygon boolean algebra — can it be replicated in Rust?

<!-- provenance: commit=15110feccc6ec9389f0777d3cff1ce9f81b11068 dirty=false -->

**Date:** 2026-08-04
**Base:** `origin/main` @ `15110feccc6ec9389f0777d3cff1ce9f81b11068`
**Surface:** `router_v6/obstacle_map.py` (108 stmts), `router_v6/routing_space.py`
(99), `router_v6/placement_audit.py` (47) — the "GEOS boolean algebra" row of
§2.3 in `docs/evidence/2026-08-04-router-v6-migration-survey.md` (PR #741).

**No production code was changed, no Rust was written, and no Rust crate was
built.** Every number below is reproduced by
`tools/measurements/geos_polygon_algebra_spike.py` (shapely 2.1.2, GEOS 3.13.1,
numpy 2.3.5, CPython 3.12.13, darwin).

---

## 0. Verdict

| Module | stmts | Verdict |
|---|---:|---|
| `routing_space.py` | 99 | **NARROWING AVAILABLE.** The GEOS `difference` at `:95` has no consumer that needs its output *geometry*. Measured: 598,400/598,400 occupancy-grid cells identical without ever forming it. |
| `obstacle_map.py` | 108 | **SPLIT.** The `unary_union` at `:187` falls out with the same narrowing. Three of the four `buffer()` sites are portable; `LineString.buffer` (`:137`) and `buffer(0)` (`:108`) are **JUSTIFIED-KEEP** with named blockers below. |
| `placement_audit.py` | 47 | **NOT BLOCKED — and not worth porting.** Its GEOS output reaches nothing but a `verbose` `print`. Recommend **JUSTIFIED-KEEP — advisory diagnostics**, not a GEOS blocker. |

**The headline is the narrowing, not a keep.** The GEOS *polygon* does not have
to cross the module boundary. `RoutingSpace.available_area` exists to be
rasterized, and the rasterization is a per-obstacle point-in-polygon predicate
that does not need the union or the difference to have been computed at all.

**But the bit-exact-`==`-on-a-polygon question, asked literally, is answered
NO** (§3), and that matters for the two `obstacle_map` sites the narrowing does
*not* cover. Both answers are recorded because both are load-bearing.

---

## 1. Has this already been decided? — Partly.

**PR #695** ("Phase-4 geometry remainder — migrate `drc_inflate` compute to
Rust, R3-keep the GEOS surfaces") reached a JUSTIFIED-KEEP on
`inflate_pad_polygon` / `precompute_inflated_dims` / `precompute_from_pad_polygons`
with the named blocker *"GEOS buffer"*, measured as 169/169 bit-mismatches
against the closed form `bounds ± r`, worst deviation 2.4e-3 mm.

That verdict is **adjacent but not sufficient**, for two reasons:

1. **It measured a different thing.** #695 measured `buffer(r).bounds` against
   `bounds ± r` — the *bounding box* of a buffered polygon, where the 2.4e-3 mm
   comes from the polygonal round-join approximation being inscribed in the
   true offset arc. It did not measure whether the buffer *vertices themselves*
   are reconstructible. §4 below shows that for the `Point.buffer` case they
   are, exactly — so #695's number does not transfer to `obstacle_map.py:90`
   and `:157`.
2. **It never faced the type-crossing problem.** #695's kept functions return
   AABBs. Here `RoutingSpace.available_area` is annotated `MultiPolygon`
   (`routing_space.py:29`) and `build_obstacle_map` returns
   `dict[str, MultiPolygon]` (`obstacle_map.py:31`). "Is the polygon
   reproducible" and "does the polygon need to cross the boundary" are
   different questions, and #695 only ever had to answer the first.

Neither `docs/wave4-verdicts.yaml` nor `docs/evidence/` records a verdict for
these three modules. `docs/wave4-verdicts.yaml:111` records the *Voronoi*
spike-gate for `channel_skeleton`, which is a different GEOS entry point.
So: not already decided. Work was warranted.

---

## 2. The falsifier, stated before measuring

> **F.** *GEOS polygon boolean output is a canonical function of the input
> region.* Concretely: (a) two GEOS computations of the same region emit the
> same coordinate sequence; (b) an input vertex that changes no area does not
> change the output; (c) the non-input vertices GEOS emits are the textbook
> closed form; (d) the result is invariant under an exactly representable
> translation. **If all four hold, bit-exact `==` parity is an engineering
> problem, not a GEOS-artifact problem, and any JUSTIFIED-KEEP here would be
> unearned and should be overturned.**
>
> **G.** *The polygon is load-bearing across the module boundary* — i.e. some
> consumer of `RoutingSpace.available_area` or of `build_obstacle_map`'s return
> value needs the result *geometry* and not a derived predicate. **If G is
> false, the whole blocker dissolves regardless of F.**

**Did they fire?**

| | Prediction | Result | Fired? |
|---|---|---|---|
| **F(a)** canonical sequence | fails | fails, 0/181 | ✗ predicted |
| **F(b)** representation-independent | fails | fails, 0/94 | ✗ predicted |
| **F(c)** closed-form vertices | fails | fails, 88.4% | ✗ predicted |
| **F(d)** translation-invariant | **fails** | **HOLDS, 189/189** | **✓ FIRED** |
| **G** polygon load-bearing | holds | **fails** for every consumer traced | **✓ FIRED** |

**Two of five fired.** F(d) fired against me: an earlier version of this
measurement reported 192/192 translation failures, and that was **my test's
bug, not GEOS's** — the random coordinates were not exactly representable, so
`+1024` rounded the *inputs* and I was measuring my own translation. Rebuilt on
dyadic (`k/1024`) coordinates, GEOS `difference` is exactly translation
invariant, 189/189, worst drift `0.0`. The corrected result is in §3.4 and the
wrong one is not used anywhere.

G firing is the whole story of this document.

---

## 3. Is bit-exact polygon parity even the right bar? — No, and here is why not.

Gate **G2** (`docs/wave4-discipline-contract.md:23`) demands bit-exact `==`.
For a scalar that is unambiguous. For a polygon it is not, and the measurements
say so in four different ways.

### 3.1 There is no canonical coordinate *sequence* (P1)

`A − (B₁ ∪ B₂)` and `(A − B₁) − B₂` are the same set. GEOS computes both.

```
n = 181
identical coordinate sequence            : 0
identical vertex set, different sequence : 181
different vertex set                     : 0
example ring-start x: (-25.0, -25.0)
example ring-start y: (-25.0,  25.0)
```

The *vertex values are identical every time* — this is not numeric
non-determinism. What differs is which vertex the ring starts at. So `==` on
`list(poly.exterior.coords)` is **not a region-equality test**: it fails
181/181 on two GEOS results that are the same polygon. A Rust port asserting
`==` against a shapely oracle would be asserting against GEOS's ring-start
choice, which is an artifact of the traversal that produced it, not a property
of the answer. Any honest G2 assertion here has to be `==` on a *canonicalized*
ring (normalized start + winding), and that canonicalization is a decision the
contract does not currently make.

### 3.2 The output is a function of the input *representation* (P2)

Insert the exact midpoint of an edge into the subtrahend. Area is bit-identical
(the probe rejects any case where it is not). Re-run the difference:

```
n = 94   output unchanged: 0   output changed: 94
vertex-count delta: min +1 max +1     worst |area difference|: 0.0
```

GEOS carries the redundant collinear vertex straight through into the result,
94/94. So the output is not determined by the region being computed — it is
determined by how the region was written down. A Rust port would have to
reproduce GEOS's *retention* policy, not just its arithmetic.

### 3.3 Non-input vertices disagree with the closed form 88.4% of the time (P3)

Every vertex of a boolean result is either an input vertex or a computed
segment/segment intersection. For the latter:

```
n = 883
bit-mismatch vs the textbook determinant form : 781 (88.4%)
worst |delta|                                 : 4.263256414560601e-14 mm
worst ULP distance                            : 701
```

This is the **B6-class finding raised from a scalar to a vertex**. B6
(`docs/wave4-discipline-contract.md:54`) records GEOS point distance as
`sqrt(dx·dx + dy·dy)` diverging from `hypot` on ~12% of pairs by 1 ulp. Here
the divergence is 88.4% of pairs at up to **701 ulps**. GEOS does not use the
determinant form: it conditions the computation (translating the segments to a
local origin) and escalates to double-double arithmetic when the sign is not
robust. That algorithm, not a formula, is what a bit-exact port must transcribe.
`geo`, `geo-buffer` and `i_overlay` each use their own intersection
formulation.

> **Not measured — explicit UNKNOWN.** No Rust crate was benchmarked against
> these numbers, because building one is out of scope for this spike (the brief
> forbids `cargo`/`maturin`; the repo is at 91% disk with 71 worktrees and
> PR #735 unmerged). The claim made here is *"GEOS is not the closed form, by
> 701 ulps"* — which is measured. The claim *"crate X does not match GEOS"* is
> **not measured** and is stated as the (strong) prior it is. §7 gives the
> experiment that would settle it.

### 3.4 …but it *is* translation-invariant (P5) — F(d) fired

```
n = 189  (dyadic coordinates: the ±1024.0 shift is exact)
translation-invariant : 189
not invariant         : 0
worst coordinate drift: 0.0 mm
```

GEOS's conditioning is good enough that absolute coordinate magnitude does not
leak into the answer. Recorded because it fired against the prediction, and
because it means the *hard* part of a port is the intersection kernel and the
emission policy, not numerical conditioning.

### 3.5 Verdict on question 2

**Bit-exact `==` on a GEOS polygon is not a well-posed bar.** §3.1 and §3.2
show the emitted coordinate sequence is an artifact of the computation and of
the input's redundant vertices, not of the region. §3.3 shows the coordinate
*values* require transcribing GEOS's intersection kernel, not implementing set
difference. That is a "vendor GEOS" bar, not a "port GEOS" bar — which is
exactly the shape of the KTD8 verdict
(`docs/evidence/2026-07-31-edt-crate-ktd8-spike-rejected.md`).

**This is why question 4 is the one that matters.** If the answer to "can we
match GEOS's polygon" is "only by vendoring GEOS", the productive question is
whether anyone needs GEOS's polygon.

---

## 4. What does `buffer()` actually do? (P4, P7)

Measured, per call site, rather than assumed in either direction.

### 4.1 `Point.buffer(r, quad_segs=q)` — **portable, exactly**

`obstacle_map.py:90` (escape vias) and `obstacle_map.py:157` (pre-existing
vias).

```
Point.buffer(r, quad_segs=4): 16 verts, clockwise from +x;
  bit-mismatch vs cx + r*cos(-k*pi/8)  = 0/16   (worst 0.0)
Point.buffer(r, quad_segs=8): 32 verts, clockwise from +x;
  bit-mismatch vs cx + r*cos(-k*pi/16) = 0/32   (worst 0.0)
```

GEOS emits a `4q`-gon whose vertices lie **exactly** on
`(cx + r·cos(−kπ/2q), cy + r·sin(−kπ/2q))`, clockwise from `+x`, with the ring
closed by repeating vertex 0. Zero mismatches against the closed form at both
`quad_segs` values used in this repo.

This is a **positive, reusable result**: circular buffers are reconstructible.
The one dependency is that GEOS's `cos`/`sin` are the host libm's — which is
bit-exactness class **B1** (`docs/wave4-discipline-contract.md:49`), *already
solved in this repo* by `dlsym_math` in
`packages/temper-geometry/src/pad_geometry.rs`. A port would reuse that, not
invent anything.

Also recorded, because it is the other half of #695's finding: the `4q`-gon is
**inscribed** in the true circle.

```
quad_segs=4: inradius/r = 0.9807852804032304  (offset short by 1.921%)
quad_segs=8: inradius/r = 0.9951847266721969  (offset short by 0.482%)
```

For a *dilation* this under-covers the obstacle; for the **erosion** at
`occupancy_grid.py:461` it under-removes, so the C-space free area is
**over-reported by up to 1.921% of the inflation distance** (≈0.0024 mm at the
production inflation of 0.125 mm). Flagged as an observation, not a defect
claim — it is inside a 0.1 mm cell and no baseline is touched here.

### 4.2 `LineString.buffer(w/2, cap_style=1)` — **JUSTIFIED-KEEP, named blocker**

`obstacle_map.py:137` (pre-routed tracks).

```
LineString.buffer(r=0.1, cap_style=1): 66 vertices, 66 distinct
  bit-equal to an exact end-cap circle point : 34/66
  a minimal closed form needs                : 34 vertices
```

For a two-point line, the exact construction is two 16-segment round caps plus
two offset sides — 34 vertices, and exactly 34 of GEOS's 66 match that
bit-for-bit. The other **32 are artifacts of GEOS's offset-curve-plus-union
path** and have no closed form to target. This is a real, named blocker.

### 4.3 `poly.buffer(0)` — **JUSTIFIED-KEEP, named blocker, and a latent bug**

`obstacle_map.py:108`, the standard "repair an invalid polygon" idiom applied
to keepout/copper zones parsed from the board.

```
Polygon(bow-tie).is_valid = False
  .buffer(0) -> Polygon, area 1.0        (the two lobes total 2.0)
  wkt: POLYGON ((1 1, 2 2, 2 0, 1 1))
```

`buffer(0)` on a self-intersecting ring is **not a repair with a specification**
— it is whatever GEOS's noding and overlay happen to produce. On a bow-tie it
returns *one lobe* and silently discards the other. Nothing about that output is
derivable from a semantics; it is the algorithm's fixed point.

> **Latent correctness note (not fixed here, no baseline touched).** A
> self-intersecting zone polygon in a `.kicad_pcb` reaches
> `obstacle_map.py:108` and can lose half its area from the obstacle map — a
> missing-obstacle bug of exactly the class
> `docs/evidence/2026-07-30-router-copper-shorts.md` documents for vias.
> Recommend a follow-up issue; this spike does not have the board corpus to say
> whether any shipped board triggers it, so that is **UNKNOWN**.

### 4.4 `available_area.buffer(-0.125, quad_segs=4)` — the erosion

`occupancy_grid.py:461`. The production inflation is real: `_parse_nets.py:133`
sets `default_trace_width = 0.25` for every parsed board, and
`occupancy_grid.py:514` halves it, so `inflation_mm = 0.125 > 0.1` and the
branch fires. (On the `stage0_data.DesignRules` *dataclass default* of 0.2 it
would be exactly 0.1 and the branch would **not** fire — a discontinuity worth
knowing about when reading fixtures.)

```
available_area.buffer(-0.125, quad_segs=4):
  Polygon(83 rings, 2417 verts) -> Polygon(73 rings, 4901 verts)
  area 1132.453107849496 -> 1058.7786076693503
morphological identity (A−B)⊖D == (A⊖D) − (B⊕D):
  same vertex set = False, |area delta| = 2.2737367544323206e-13
```

Two things follow. The erosion **doubles the vertex count** of an
83-ring routing space — this is the offset-curve machinery of §4.2 at scale,
not a closed form. And the textbook morphological identity holds *numerically*
(area agrees to 2.3e-13 mm²) but **not vertex-for-vertex** — another instance of
§3.1/§3.3. Neither of these matters once §5 lands, because §5 removes the
erosion's polygon from the picture entirely.

---

## 5. Can the seam be narrowed? — **Yes. This is the result.**

### 5.1 Every consumer, traced

`RoutingSpace.available_area`, complete production consumer list (tests
excluded; `rg` over `packages/`, `tools/`, `scripts/`):

| Consumer | Line(s) | What it takes from the polygon | Needs the geometry? |
|---|---|---|---|
| `occupancy_grid.build_occupancy_grid` | `:439`, `:458`, `:461` | `.bounds`; `.buffer(-inflation, quad_segs=4)`; then `contains(area, cell_centres)` → **`bool` mask** | **No** — §5.2 |
| `channel_widths._build_edt` | `:139`, `:140`, `:159`, `:168` | `.bounds`, `.area`, then `shapely.contains_xy(area, grid)` → **`bool` mask** | **No** — same predicate |
| `channel_widths._compute_width_at_point` | `:231–247`, `:400–405` | `prep(area).contains(pt)`, then `polygon.exterior/interiors .distance(pt)` | **No** — point-in-polygon + point-to-ring distance, both **B6 class**, already a recorded and solved boundary |
| `channel_skeleton._extract_medial_axis` | `:80`, `:91` | the polygon itself, into `shapely.ops.voronoi_diagram` | **Yes** — but this is the **separately recorded** spike-gate at `docs/wave4-verdicts.yaml:111`, not this blocker |
| `visualization/routing_health` | `:357` | `.bounds` | **No** — 4 floats |

`build_obstacle_map`'s `dict[str, MultiPolygon]` return value, complete
production consumer list:

| Consumer | Line(s) | What it does |
|---|---|---|
| `stage2_orchestrator` | `:86` | passes it straight through |
| `routing_space.compute_routing_space` | `:91`, `:95`, `:104` | `.get(layer)`, `board.difference(obstacles)`, `obstacles.area` |
| `obstacle_map.validate_obstacle_map` | `:271`, `:283` | iterates **keys only** — never touches a polygon |

**`build_obstacle_map`'s MultiPolygon has exactly one production consumer that
looks at its geometry**, and that consumer is `compute_routing_space`. And
`RoutingSpace.obstacles` — the field whose comment says "Raw obstacles for SDF
generation" — has **zero readers anywhere in the repository**, production or
test. It is dead.

So the entire GEOS-polygon type surface of these two modules serves one
expression, `board.difference(obstacles)`, whose only non-Voronoi consumers
convert it back to a boolean raster.

### 5.2 The measurement: the raster does not need the polygon

Three ways to compute the occupancy mask, on a board built from the same
primitives `obstacle_map.py` uses (rotated rectangular pads,
`Point.buffer(r, quad_segs=8)` vias, `LineString.buffer(w/2, cap_style=1)`
tracks), on `build_occupancy_grid`'s own cell-centre lattice
(`cell=0.1`, `margin=2.0`):

- **A** `contains(board.difference(unary_union(obs)), p)` — production
- **B** `contains(board, p) & ~intersects(unary_union(obs), p)` — no difference
- **C** `contains(board, p) & ~⋁ᵢ intersects(obsᵢ, p)` — **no union, no difference**

```
seed     5: 340x440 = 149600 cells, 113121 free | A!=B 0 | A!=C 0
seed    17: 340x440 = 149600 cells, 113414 free | A!=B 0 | A!=C 0
seed   101: 340x440 = 149600 cells, 113501 free | A!=B 0 | A!=C 0
seed  2027: 340x440 = 149600 cells, 113384 free | A!=B 0 | A!=C 0
TOTAL 598400 cells: A!=B 0, A!=C 0
```

And on the **eroded C-space path production actually takes**:

```
inflation = 0.125 mm
149600 cells: A free 106079, C free 106079, A!=C 0
```

**Zero differing cells out of 598,400.** Neither `unary_union` nor `difference`
needs to be evaluated to produce the mask that `occupancy_grid` consumes.

This is not a coincidence, and the probe says why. It is the topological
identity `int(A ∖ B) = int(A) ∖ cl(B)` for closed `B`, combined with shapely's
own predicate semantics: `contains(g, pt) ⟺ pt ∈ int(g)` and
`intersects(o, pt) ⟺ pt ∈ cl(o)`. The identity is exact; the *only* way it can
fail is if a probe point sits closer to the difference-result boundary than the
§3.3 intersection error that placed that boundary.

Measured, adversarially — probe points forced **onto** obstacle vertices, edge
midpoints, and `available_area`'s own boundary vertices:

```
7361 boundary-exact probe points: A!=C 15
every disagreement lies within 1.175e-15 mm of the boundary
real 340x440 lattice: 220 cell centres exactly on a boundary,
  480 within (0, 1e-14) mm, min nonzero 4.441e-16 mm -- and 0 disagreements
```

The disagreement band is ~1.2e-15 mm wide. Even on a deliberately
lattice-aligned board where **220 cell centres land exactly on an obstacle
boundary**, A and C agree on every one of them, because both predicates decide
an exactly-on-the-edge point the same way. The 15 disagreements are all
constructed points inside the band and none is a cell centre.

### 5.3 The narrowing proposal

> **`RoutingSpace` should carry `(bounds, area, obstacle_polygons)` — not a
> GEOS difference result.** The cross-module type becomes the obstacle *list*
> plus the derived scalars, and each consumer rasterizes with the predicate it
> already uses.

Consequences, per module:

- **`routing_space.py` (99 stmts).** `board_polygon.difference(obstacles)`
  (`:95`) disappears. `.area` (`:79`, `:104`, `:105`) remains — polygon area is
  the shoelace sum, already class **B7** ("preserve the oracle's expression
  shape"), already solved. `_get_board_polygon` builds `box(...)`/`Polygon(...)`
  from coordinates: constructors, not algebra. **Portable.**
- **`obstacle_map.py` (108 stmts).** `unary_union` (`:187`) disappears — nothing
  downstream needed the merged polygon, only per-obstacle predicates.
  `Point.buffer(quad_segs=8)` (`:90`, `:157`) is portable per §4.1. What
  remains blocked is `LineString.buffer` (`:137`) and `buffer(0)` (`:108`).
  **Split verdict.**
- **`occupancy_grid.py` (264 stmts).** Already in the survey's **PORT** bucket,
  with the note "shapely confined to 2 lines". This narrowing removes those two
  lines rather than leaving a GEOS shim inside an otherwise-Rust module — i.e.
  it converts a partial port into a complete one. The C-space erosion moves
  from `available_area.buffer(-inflation)` to per-obstacle
  `buffer(+inflation)`, and for the via and pad primitives that is §4.1's exact
  circle. Better still, the inflation can be folded into the primitive at
  construction (`radius + inflation`), which removes the buffer-of-a-buffer
  entirely.
- **`channel_widths.py` (190 stmts).** Already a delegating module. Its two
  GEOS needs — point-in-polygon and point-to-ring distance — are B6-class
  predicates on *primitives*, not boolean-algebra results. Unaffected by this
  blocker either way; worth recording so it is not re-counted as GEOS-blocked.
- **`channel_skeleton.py` (214 stmts).** **Still blocked**, on
  `voronoi_diagram`, which is a different recorded gate
  (`docs/wave4-verdicts.yaml:111`). If the narrowing lands, `channel_skeleton`
  becomes the *only* remaining consumer that needs a GEOS polygon, so it also
  becomes the module that decides whether `available_area` can stop being a
  `MultiPolygon` at all. **This is the follow-on question this spike does not
  answer.**

### 5.4 `placement_audit.py` — not a GEOS blocker

Traced end to end. `PlacementAuditor` (`placement_audit.py:25`) has exactly one
production consumer: `placement_legalization.Legalizer` (`:21`), whose docstring
already states *"A false result is diagnostic only"*. Its consumer is
`_pipeline_core.py:279–302`:

- `legalizer.legalize()`'s **return value is used only to choose which
  `print` runs**, and both branches are inside `if self.verbose`.
- `check_collisions()` is called directly only under `if self.verbose`.
- The Stage-0.5 fence (`_pipeline_core.py:316`) asserts the invariant
  `drc_component_overlap` (`_pipeline_verify.py:137`), which is a **DRC check,
  not this auditor**.
- **No test in the repository references `router_v6/placement_audit` or
  `check_collisions`.**

So none of `MultiPoint.convex_hull` (`:66`), `hull.buffer(0.5)` (`:69`),
`intersects`/`intersection`/`area`/`centroid` (`:85–94`) feeds a verdict,
a baseline, or an assertion. Bit-exactness of this module is unobservable.

Two supporting measurements (P7), recorded because they would matter if it ever
*did* become observable:

```
MultiPoint.convex_hull: 4 verts, all of them input points: True
Polygon.intersection: 4 verts, 2 are input vertices, 2 are P3-class computed
```

`convex_hull` is a combinatorial selection — it invents no coordinates and is
exactly portable modulo the §3.1 ring-start convention. `intersection` is not.

**Recommendation: `placement_audit.py` is JUSTIFIED-KEEP — advisory
diagnostics**, in the same class as the recorded `profiling/**` and `testing/**`
entries. It should be removed from the GEOS-blocked bucket, not ported.

---

## 6. Statements moved

Against the survey's BLOCKED bucket (1,753 stmts / 12 modules), using the
survey's `stmts` metric:

| Module | stmts | Was | Becomes | Basis |
|---|---:|---|---|---|
| `routing_space` | 99 | BLOCKED | **PORT** (pending the narrowing) | §5.2, §5.3 |
| `obstacle_map` | 108 | BLOCKED | **PORT with 2 kept lines** (`:108`, `:137`) | §4.2, §4.3, §5.3 |
| `placement_audit` | 47 | BLOCKED | **JUSTIFIED-KEEP — advisory** | §5.4 |
| **Total out of BLOCKED** | **254** | | | |

Plus, not in the BLOCKED bucket but unblocked by the same finding:

| Module | stmts | Effect |
|---|---:|---|
| `occupancy_grid` | 264 | already PORT; the narrowing removes its 2 residual shapely lines, so the port can be complete rather than leaving a GEOS shim |

BLOCKED would fall from **1,753 → 1,499** (17% → ~15% of the 10,309
non-delegating `stmts`). Note the honest asymmetry: 254 statements *move out of
BLOCKED*, but 47 of them move to KEEP, not to PORT. The genuine new port
surface is **207 statements**, plus the completion of `occupancy_grid`'s 264.

---

## 7. Recommended ledger changes (recommendations only — nothing was edited)

`docs/wave4-verdicts.yaml`, `power_pcb_dataset/drc_ceiling.json` and every
baseline are **unmodified**.

1. **Do not add "GEOS polygon boolean algebra" as a blanket blocker.** The
   survey's §7.4 recommendation should be narrowed to the two named sites
   `obstacle_map.py:108` (`buffer(0)`) and `obstacle_map.py:137`
   (`LineString.buffer`), each with its §4 measurement.
2. **Record `placement_audit.py` as JUSTIFIED-KEEP — advisory diagnostics**,
   with `_pipeline_core.py:279–302` as the evidence that its output is
   `verbose`-only. Consider a RETIRE evaluation separately — that is a product
   question (does anyone want the advisory?), not a migration question.
3. **Record the narrowing as the precondition** for `routing_space` and
   `obstacle_map` entering PORT: `RoutingSpace` stops carrying a GEOS
   difference result, and `RoutingSpace.obstacles` (zero readers) is deleted.
4. **Record `Point.buffer(r, quad_segs=q)` as a solved primitive** in the
   bit-exactness catalog — `(cx + r·cos(−kπ/2q), cy + r·sin(−kπ/2q))`,
   clockwise from `+x`, `4q` distinct vertices, exact, with **B1**'s `dlsym`
   libm as the dependency. This is reusable well beyond `router_v6`.
5. **Open a follow-up issue** for the `buffer(0)` zone-repair lobe loss (§4.3),
   with the corpus question ("does any shipped board have a self-intersecting
   zone?") stated as UNKNOWN.

## 8. What would overturn this, and what is not verified

**Overturning the `buffer(0)` / `LineString.buffer` keeps.** Either becomes
portable the moment someone produces a construction matching GEOS's output
vertex-for-vertex. §4.2 gives the concrete target: 66 vertices for a two-point
line at `r=0.1`, of which 34 are the exact end-cap circle points and 32 are not.
Name the 32 and the keep falls.

**Overturning the narrowing.** The narrowing dies if any consumer of
`available_area` needs the geometry. §5.1 traces five and finds one —
`channel_skeleton`'s `voronoi_diagram`, itself a separately recorded gate. If
that gate resolves to "Voronoi stays Python", `available_area` must remain a
`MultiPolygon` **for that consumer** even if every other consumer takes a mask,
and the narrowing degrades from "delete the difference" to "compute it lazily,
only for `channel_skeleton`". That is still a win, but a smaller one. **This is
the single largest open dependency and it is not resolved here.**

**Not verified — stated explicitly rather than guessed:**

- **No Rust crate was measured.** `geo`, `geo-buffer` and `i_overlay` were not
  built or run (§3.3). The prior is strong and the mechanism is named, but
  "crate X mismatches GEOS by N ulps" is **UNKNOWN**.
- **No real board was measured.** §5.2 uses a synthetic board built from
  `obstacle_map.py`'s own primitives, because `temper_geometry` in the
  available venv is stale (`pad_core_half_extents_py` missing) and rebuilding
  it is out of scope. The predicate identity in §5.2 is topological and
  shape-independent, so the conclusion should transfer — but it has **not been
  run on `power_pcb_dataset`**, and it should be, before the narrowing lands.
- **`_create_pad_polygon`'s real output was not used** (same stale-crate
  reason); rotated rectangles were substituted. Pad shape does not enter the
  identity, but it is a substitution and is named as one.
- **Whether any shipped board has a self-intersecting zone** (§4.3): UNKNOWN.
- **Whether GEOS's `cos`/`sin` are the host libm on every CI platform**: shown
  here on darwin/CPython 3.12 only. B1 already assumes this repo-wide, so it is
  consistent, but this spike measured one platform.

---

## Reproducing

```
./.venv/bin/python tools/measurements/geos_polygon_algebra_spike.py
./.venv/bin/python tools/measurements/geos_polygon_algebra_spike.py --probe P6
```

The script imports only `shapely` and `numpy`, writes nothing, and needs no
Rust build. Probe ids map to sections: P1→§3.1, P2→§3.2, P3→§3.3, P4→§4.1/§4.4,
P5→§3.4, P6→§5.2, P7→§4.2/§4.3/§5.4.
