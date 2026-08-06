<!-- provenance: commit=c60825861f337fa7d7c6d0ec8e9240c5aa97c74a dirty=false (re-pointed 2026-08-05: 61c222730f4c00e6afc7f2539dbe3102ed4d7fdf was the pre-merge run-C re-run artifacts commit, orphaned by force-push; this evidence landed with the general-convex encoding merge c60825861f337fa7d7c6d0ec8e9240c5aa97c74a (#674), which is the cited commit) -->

# General-convex (diagonal-edge) zone encoding for fixed copper — the run-C unlock (issue #651)

**Date:** 2026-08-04. **Base:** origin/main at `28dc960de` (post-#666).
**Measurement tree:** clean at `7acaddd56` (see header); the run-C re-run
artifacts (`gap1_runc_envelope_*.json/.csv`) were regenerated on this tree
by `gap1_runc_envelope_probe.py --variant C_60_s0` and carry the same
commit.

## Question

The 2026-08-03 envelope probe
(`docs/evidence/2026-08-03-gap1-runC-envelope-probe.md`) established that
run-C's infeasibility is *encoding-level*, not geometric: the fixed-copper
zone encoder (#567) applies its polygon-exact half-plane encoding only to
**convex rectilinear** zones, and the 54/96 zone items with diagonal edges
(including every board-spanning pour) fall back to axis-aligned bounding
boxes. The DC_BUS_RTN pour's AABB (4.26, −5.25)–(160.15, 232.98) contains
the whole board, so C27 pad 2's encoded zone constraint was unsatisfiable
on-board: **0 encoded-clear cells vs 14,973 exact-clear**. This change
extends the #567 encoding to *any* convex polygon (diagonal edges allowed)
and re-measures run-C with the fixed encoder.

## The encoding: one half-plane per edge, one literal per edge

A convex polygon is the intersection of its edge half-planes
`Z = ∩_i {n_i·p <= d_i}` (n_i the outward unit normal). A pad is disjoint
from Z iff it lies wholly outside **at least one** edge half-plane — a
single `BoolOr` over one literal per edge, the exact analogue of the #567
rectilinear BoolOr:

* **Axis-aligned edge** (x = c or y = c): the #567 form `("x"|"y", coord,
  sign)` — exact for convex rectilinear zones, unchanged.
* **Diagonal edge**: `("n", a, b, r)`, the pad clears iff
  `min over pad of (a·x + b·y) >= r`. Because the pad's world rect is
  axis-aligned, the minimum of a linear form over it is attained at a
  single corner whose identity is fixed by the sign of the coefficients,
  so each diagonal edge is **one** linear literal (no per-corner
  disjunction):

      min over pad of (a·x + b·y)
        = a·(x_center+ox) + b·(y_center+oy) − |a|·hwx − |b|·hwy

  with `x_center`, `y_center` the component placement vars and `ox`, `oy`,
  `hwx`, `hwy` the pad's rotation-table vars (all affine in the placement,
  `AddElement` over the four quadrant rotations). Coefficients
  `(a, b) = 100·(dy, −dx)` and the offset `r` are integers (CP-SAT
  requires integer linear coefficients), computed at **100× the model
  resolution** (0.0001 mm) so sub-0.1 mm edges keep their true slope
  (see the two soundness bugs below), then scaled to model-unit integer
  coefficients.

### Soundness proof (R24 item 1 — Chebyshev-style, conservative direction)

For a convex polygon the disc-dilation is exactly the intersection of the
shifted edge half-planes, `Z ⊕ disc(margin) = ∩_i {n_i·p <= d_i + margin}`
(the standard offset-polygon identity). If the encoded predicate declares
a pad clear, some edge literal holds — the pad's minimum of `n_i·p` is at
least `d_i + margin`, i.e. *every* pad point satisfies
`n_i·p >= d_i + margin`. For every pad point p and zone point q:

    n_i·(p − q) = n_i·p − n_i·q >= (d_i + margin) − d_i = margin

so by Cauchy–Schwarz `|p − q| >= n_i·(p − q) >= margin` (n_i is unit).
Hence `dist(pad, Z) >= margin`: **encoded-clear implies exact-clear — no
false negatives**. Convexity is exactly the `Z ⊆ {n_i·p <= d_i}` property
the proof needs (it fails at a reflex vertex, which is why non-convex
zones keep the bbox fallback).

The integer grid erodes the continuous bound (pad-edge rounding up to
0.01 mm, vertex rounding up to ~0.007 mm), so the diagonal edges embed
`margin + _GRID_HEADROOM_MM` (0.07 mm total shift) in `r`, rounded UP
(ceil — a larger RHS is stricter, the conservative direction); the R24
post-solve audit (`audit_fixed_copper`) recomputes the exact clearance
from resolved coordinates and hard-fails on any mismatch, catching any
residual encoding bug at solve time.

### Two soundness bugs found and fixed during this change (both would have shipped under-constrained — the #567 error class)

1. **Tiny-edge slope destruction.** Quantizing the diagonal direction to
   the 0.01 mm model grid turned the sub-0.1 mm arc segments rounding the
   +15V_LS strip's ends (0.025 mm each) exactly horizontal, rotating their
   half-planes enough to exclude polygon vertices — **1,534 unsound cells
   on the real board** (encoded-clear but overlapping). Fixed by computing
   the direction at 100× model resolution (0.0001 mm; error <= ~0.0001 mm
   of line shift). Caught because the probe re-measurement showed
   encoded-clear (44,190) > exact-clear (42,871) for K3 pad 3 vs +15V_LS.
2. **Margin-shift unit mismatch.** The `(margin + headroom)` shift was
   written at model scale (100/mm) while `d0` and the edge length were at
   fine scale (10000/mm), making the encoded clearance 100× too small
   (~0.0007 mm instead of 0.07 mm) — a residual unsoundness on *every*
   pair. Fixed by shifting at the fine scale.

After both fixes, re-measured on the real board: **0 unsound cells across
all 7 run-C conflict pairs** at 0.5 mm grid resolution over the full
displacement envelopes.

## Conservatism (encoded-overlap but exact-clear — safe direction, documented)

* **Grid headroom**: the diagonal edges shift by margin + 0.02 mm, so a
  pad at exact clearance in (margin, margin + 0.02) is encoded-overlap —
  measured max excess 0.02 mm on the run-C geometry class.
* **Chamfer corners**: at each vertex the offset polygon's corner (the
  intersection of the two shifted edge lines) pokes beyond the true
  disc-dilation arc by up to `margin·(1/sin(θ/2) − 1)`; the production
  board's sharpest zone vertex (28.7°, the +3V3 triangle) bounds this at
  0.15 mm. (Larger for very sharp or nearly-degenerate vertices.)
* **Large pad vs small polygon**: a pad comparable to or larger than the
  polygon can poke into every edge strip while staying far from the
  polygon — unbounded in principle (measured 19 mm for a 10 mm pad next
  to a 15 mm triangle), the same class as the bbox fallback, hence
  `slack_mm` stays `inf` for zones.

All three are over-constraining (safe); the soundness direction is what
R24 requires and it holds.

## All 96 zone items are convex — the bbox fallback is unreachable on the board

Checked every zone polygon on `pcb/temper.kicad_pcb`: **96/96 convex**
(42 rectilinear, 54 with ≥1 diagonal edge), 0 non-convex, 0 degenerate.
The bbox fallback (`edges=None`) is therefore dead on the production board
— retained only as the documented sound fallback for a hypothetical future
non-convex pour.

## BMC-exhaustive validation (R24 item 2)

`tests/placer/cp_sat/test_fixed_copper.py::TestZoneGeneralConvexBMC`:

* **Soundness sweep**: 4 diagonal-edge convex polygons (45° triangle,
  mixed-winding quad, hexagon, sharp 28.7° triangle) × pad sizes
  (0, 1×1, 3×2) × 4 rotations × 61×61 position grid — encoded-clear ⇒
  exact-clear, **0 counterexamples** (checked > 50,000).
* **Half-plane containment invariant** (the direct soundness
  precondition): for every diagonal edge, `max over polygon of
  (a·x + b·y) <= r` — verified on a **capsule with sub-0.05 mm arc edges**
  (the +15V_LS shape class that failed before the fine-scale fix) plus the
  four sweep shapes. This O(V) check is what would have caught bug 1
  immediately.
* **Board-spanning regression** (the run-C unlock): a DC_BUS_RTN-class
  pentagon whose AABB contains the whole test board must clear 0 cells via
  the bbox fallback (precondition) and ≥ 90% of the 1,064 exact-clear
  cells via the half-plane encoding, with 0 unsound.
* **Run-C-geometry conservatism**: small pads vs the board-spanning
  pentagon — measured excess ≤ 0.02 mm (the embedded headroom) at all pad
  sizes and rotations.
* Existing rectilinear exactness (`encoded == oracle`) and non-convex bbox
  soundness tests unchanged and green.

## run-C re-run on the real board (the #618/#651 verdict update)

`gap1_runc_envelope_probe.py --variant C_60_s0` (identical formulation to
the 2026-08-03 probe: nothing pinned, rotations fixed, 60 mm Manhattan
cap, 12,101 SeparatedConstraints, fixed-copper for FREE={K3,C27} at margin
0.05 mm, timeout 300 s):

| (ref, pad) vs zone | pre-fix encoding | encoded-clear (old) | exact-clear | encoded-clear (new) |
|---|---|---|---|---|
| C27 pad 2 vs DC_BUS_RTN | BBOX | **0** | 14,973 | **14,966** |
| K3 pad 2 vs SW_NODE | BBOX | 208 | 19,709 | 19,692 |
| K3 pad 5 vs SW_NODE | BBOX | 3,448 | 21,496 | 21,478 |
| K3 pad 4 vs SW_NODE | BBOX | 3,225 | 22,936 | 22,919 |
| K3 pad 1 vs SW_NODE | BBOX | 3,225 | 23,793 | 23,777 |
| K3 pad 3 vs SW_NODE | BBOX | 4,575 | 24,834 | 24,806 |
| K3 pad 3 vs +15V_LS | BBOX | 39,630 | 42,869 | 42,852 |

(cap 120 mm envelope grid, 0.5 mm steps, edge-margin gated — the probe's
exact `encoded_zone_reachability` table.)

**The encoding-level blocker is gone**: C27 pad 2 vs DC_BUS_RTN encoded-
clear jumps **0 → 14,966 of 14,973 exact** (99.95%), and every other pair
recovers ≥ 99.9% of its exact-clear region. Every zone's demand is now
reachable by the solver's own encoded predicate anywhere the component can
actually go.

**Solve status: `C_60_s0` is STILL infeasible (2.5 s, unsat core 15,285).**
The ~2 s timeout-class infeasibility persists because the remaining
blockers are now *real compound conflicts, not the encoding* — exactly the
probe's honest caveat: moving the free refs to their exact zone-clear
positions produces **14 new exact fixed-copper violations** at the naive
candidate (K3 pad 2/4 vs the GATE_HS zone at 0.035/0.000 mm, K3 pads vs
the ESP32 module's pads io41/io42/gpio35/gpio36, K3 pad 4 vs two segments;
measured 2026-08-03 and reproduced unchanged on this tree). The zone side
is satisfiable per-ref (C27: 1.0 mm, K3: 37.5 mm displacement within the
60 mm cap); run-C feasibility is now a genuine compound placement search,
not a foregone conclusion, and the residual infeasibility is attributable
to the non-zone conflicts the probe already documented. This is the
follow-up tracked in #618/#651: zone-geometry / isolation-slot decisions
are only justified if the exact compound problem is still infeasible after
a *sound* encoding, which this change is.

## What remains

1. Run-C compound feasibility under the sound encoding is still open: the
   14 non-zone conflicts (GATE_HS zone vs K3 pad 2/4, ESP32 module pads,
   two segments) need placement search or a zone-geometry/slot decision —
   the probe's documented follow-up, tracked on #618/#651.
2. Non-convex zones keep the bbox fallback (none exist on the board;
   convex-hull half-planes would be a sound-but-conservative future
   tightening if one ever appears).
3. The rectilinear #567 path remains margin-only (its <= 0.015 mm
   quantization residual is audit-caught and documented); the diagonal
   path is the headroom-protected form.

## Artifacts

- `packages/temper-placer/src/temper_placer/placer/cp_sat/fixed_copper.py`
  — `_convex_polygon_edges`, `("n", a, b, r)` diagonal edges,
  `_add_no_overlap`/`encoded_overlap_edges` diagonal handling, soundness
  proof and conservatism analysis in the module docstring.
- `packages/temper-placer/tests/placer/cp_sat/test_fixed_copper.py` —
  `TestZoneGeneralConvexBMC` (soundness sweep, half-plane containment,
  board-spanning regression, run-C-geometry conservatism).
- `gap1_runc_envelope_matrix.json` / `gap1_runc_envelope_zones.json` /
  `.csv` — regenerated on this tree by the probe (run-C re-run + the
  encoded-reachability table above).

## Provenance

Measured on the clean tree at `7acaddd56` (see header). `pcb/` and `elec/`
were untouched; the only src/ change is `fixed_copper.py` (+ tests + this
doc + the regenerated probe artifacts). The two soundness bugs above were
found and fixed within this change, on this branch, before merge.
