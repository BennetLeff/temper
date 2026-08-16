---
module: packages/temper-geometry
tags: [geometry, clearance, creepage, halo, zone-generator, property-tests, rust, safety]
problem_type: bug-fix-and-guard
date: 2026-08-16
---

# Geometry Invariant Types — ClearanceHalo guards three measured geometry bugs (2026-08-16)

**Purpose**: three geometry-correctness bugs found during zone-generator
verification (#1257, `c261907bc`) were each "close but not right" — nothing
caught them until DRC measurement on the real board. This changeset adds a
`ClearanceHalo` type (`packages/temper-geometry/src/clearance_halo.rs`) whose
constructors make the conservative-superset property *unrepresentable to get
wrong*, plus four property tests, each mutation-verified to fail on the bug
it targets.

**Branch**: `feat/geometry-invariant-types-v2` (worktree
`/tmp/opencode/agent-geom-types-v2`), base `origin/main` @ `6ac839e28`.
Commit: `ea301e807` (type + tests), this doc is the follow-up commit.

<!-- provenance: commit=ea301e807f24d7b7a03b5934dc1f11a75f6d7b91 dirty=false -->

---

## 1. The three bugs

All three lived in the same neighbourhood: the per-obstacle halo construction
behind the Rust zone-pour generator (`zone_generator.rs`, #1257) and its
`geo::BooleanOps` union. All three were approximations that *looked* right
and were only exposed by DRC on the production board.

### 1.1 Inscribed polygon undercut — 12.49 vs 12.60 mm

A regular n-gon built from vertices at radius `R` is **inscribed**: its
edges — the points of closest approach to the centre — sit at
`R·cos(π/n)`, not at `R`. The carve distance in a DRC-aware pour is the
edge-to-edge gap, so an un-inflated halo undercuts the required separation
by `R·(1 − cos(π/n))`. For a 12.6 mm creepage halo at 24 segments that is
**0.11 mm**; DRC measured **12.49 mm actual vs 12.60 mm required** on the
production board.

The zone generator already carries a runtime patch for this
(`halo_radius_inflate()`, `1/cos(π/n)`), but the patch is a scaling constant
on a hand-written `disc()` helper — no structural force keeps the next
halo-building call site from forgetting it. The fix is a *circumscribed*
polygon: vertices at `R/cos(π/n)`, edges tangent to the clearance disc.

### 1.2 Rect-pad corner reach — 12.48 vs 12.60 mm

A rectangular pad's furthest point from its centre is a **corner** at
half-diagonal `hypot(w/2, h/2)`, not an edge midpoint at `max(w, h)/2`. A
disc halo of radius `max(w, h)/2 + clearance` therefore puts its boundary
only `max(w,h)/2 + clearance − hypot(w/2, h/2)` from the corners — for the
3.0×2.0 mm PTH relay pad and a 12.6 mm creepage figure, that is
`14.1 − 1.803 = 12.297 mm < 12.6 mm`; DRC measured **12.48 mm actual vs
12.60 mm required**.

### 1.3 Library panic on 500+ overlapping halos

`geo` 0.28's sweep-line `BooleanOps` panicked
("unable to compare active segments!" / "segment not found in
active-vec-set", georust/geo#1174) when hundreds of overlapping halos
produced nearly-coincident collinear edges with floating-point noise —
measured on the production board: **every zone-eligible net panicked with
500+ obstacles**. Fixed upstream only in 0.29 (i_overlay engine). A library
bug, but a stress test on the union of 500 overlapping halos would have
caught it before production.

---

## 2. The type: `ClearanceHalo`

`packages/temper-geometry/src/clearance_halo.rs`. The polygon field is
**private**; the only two constructors are the only places the three
approximations can be made.

**ConservativeSuperset contract** (module doc, stated as a theorem):

```
from_circular_pad(center, radius, clearance, eps)
    ⇒  halo ⊇ disc(center, radius + clearance)
       every edge at distance exactly radius + clearance (tangent)
       every vertex within eps of the disc  (tight, never under-covering)
       ⇒  min distance(pad boundary, halo boundary) ≥ clearance  (exact)

from_rect_pad(center, w, h, corner_radius, rotation, clearance, eps)
    ⇒  halo ⊇ rect ⊕ disc(clearance)  for ANY corner_radius and rotation
       (rect ⊆ disc(hypot(w/2, h/2)) ⇒ circular construction at the
        half-diagonal is a conservative superset of the rounded rect's
        Minkowski sum)
```

Design points:

* **Circumscribed, not inscribed.** Vertices at `r/cos(π/n)` where
  `r = radius + clearance`; edges tangent to the clearance disc (bug 1.1's
  fix, made structural).
* **Tight.** `n = ⌈π / acos(r/(r+eps))⌉` bounds the vertex overshoot by
  `eps` (from `r·sec(π/n) ≤ r + eps`). Smaller `eps` → more sides → less
  wasted board area; the containment guarantee holds for *any* `eps`.
  Capped at `MAX_SIDES = 2048` (documented: the cap can only loosen
  tightness, never the superset guarantee — that holds for any n ≥ 3).
* **Half-diagonal, not half-width** for rect pads (bug 1.2's fix).
  `corner_radius` and `rotation` are accepted-and-ignored, documented: the
  rounded rect ⊆ full rect ⊆ `disc(half_diag)`, and a disc is
  rotation-invariant.
* **`contains`** uses `geo::Contains`, which requires `CoordPos::Inside` —
  points exactly on the polygon boundary are *not* contained. Callers that
  probe boundary-adjacent geometry should sample with a small margin.

## 3. The four property tests

Deterministic parameter sweeps (no proptest — a dev-dependency would
exclude them from the wasm Worker tier; these run there). Each is
registered in the generated wasm registry (`8370` total, `+4`).

| # | Test | Guards |
|---|------|--------|
| 1 | `circumscribed_polygon_contains_circle` | **Bug 1** (inscribed undercut) |
| 2 | `rect_halo_contains_all_four_corners` | **Bug 2** (half-width corner reach) |
| 3 | `stress_500_overlapping_halos_union_no_panic` | **Bug 3** (geo panic) |
| 4 | `min_distance_from_pad_boundary_to_halo_boundary_meets_clearance` | **All three** |

(Test numbering is the natural 1↔1↔1↔1 mapping; an earlier draft of the
dispatch labelled them 2/3/1 — the mapping above is the correct one.)

**Test 1** sweeps radii `[0.1, 1.0, 5.0, 12.6, 50.0]` × epsilons
`[0.001, 0.01, 0.1]`, clearance 0. Asserts (a) all 1000 sampled points on
the circle are contained — an inscribed polygon fails this between adjacent
vertices; (b) every edge sits at distance ≥ radius from the centre — the
DRC-relevant edge-to-edge gap; (c) vertex overshoot ≤ eps — catches
over-inflation. Sample angles carry a fixed `1e-4` rad offset: geo
`Contains` excludes boundary points, the circumscribed polygon's edges are
tangent to the sampled circle, and `1e-4` is irrational relative to `π` so
no sample can ever land on an edge (argument in the helper's doc comment).

**Test 2** uses clearance `0.001` mm — large enough that corners are
strictly inside the correct halo (no boundary/tangency risk), small enough
that a half-width halo still fails on the `(5.0, 0.3)` pad whose
half-diagonal exceeds `max(w,h)/2` by only ~4.7 µm.

**Test 3** unions 500 halos two ways — a 1-D chain at 0.01 mm spacing (the
dispatch's shape) and a dense 25×20 grid at 0.01 mm spacing of identical
octagons (the near-coincident-collinear-edge shape that crashed 0.28) — via
the same incremental fold `zone_generator.rs` uses in production. Asserts
no panic, non-empty, area > 1, probe point contained. Runs green on geo
0.29.3's i_overlay engine.

**Test 4** asserts the fundamental invariant: for circular pads
`(1.0/0.5, 2.0/2.0, 3.0/12.6)` and rect pads (incl. the 3.0×2.0 relay pad)
at the production 12.6 mm creepage figure, min distance from the pad
boundary (sampled) to the halo boundary ≥ clearance − 1e-6. The tolerance
is pure floating-point slack — the geometric guarantee is exact `≥ C`,
independent of the constructor's `eps` (eps bounds the vertex overshoot
*outward*, which can only add margin).

## 4. Mutation evidence — the tests fail on the bugs they name

Each property test was validated against a deliberately broken
construction, in the same worktree, before being reverted:

| Mutation | Result |
|----------|--------|
| `vertex_r = r` (inscribed instead of `r/cos(π/n)`) | **3 of 4 tests fail** (1, 2, 4) |
| `half_diag = max(w,h)/2` (half-width instead of half-diagonal) | **2 of 4 tests fail** (2, 4) |

Test 3's guard is structural (it exercises the exact 500-halo union path
that panicked on 0.28; the crash was in the library, not the constructor,
so it is not mutation-testable here — its value is the regression gate on
geo's engine).

## 5. Verification

* `cargo test -p temper-geometry`: **8444 passed, 0 failed** (incl. the 4 new).
* `cargo clippy --all-features --all-targets -- -D warnings` (local
  rustc 1.97.1): **3 errors, all pre-existing** in `zone_generator.rs`
  (type_complexity L598, too_many_arguments L662, len_zero L810) —
  confirmed identical on a pristine `origin/main` scratch checkout;
  this changeset adds zero new lints.
* wasm Worker tier: `cargo build --target wasm32-unknown-unknown
  --features wasm-test-registry` — **compiles**, registry gate
  (`scripts/gen_wasm_test_registry.py --check`) green.
* Stress test wall time ~0.6 s for the whole module's 4 tests.

## 6. Follow-up (deliberately not in this commit)

The zone generator adopts `ClearanceHalo` in a separate changeset (its
`disc()`/`capsule()`/`ZoneObstacle::halo_polygon` become thin wrappers over
the type — the half-diagonal and inflation conventions already match). No
pyo3 surface is added here: the type is a Rust-side construction guard, and
no Python consumer exists yet (YAGNI; adding one would be speculative
surface for zero call sites).

---

# Delta (second changeset, same day): structural verification, tracks/vias, zone-generator adoption

**Scope**: the first changeset (#1258) made the polygon field private and the
construction circumscribed; the guarantee was *by construction*. This
changeset adds the task's second layer — a [`ConservativeSuperset`] ZST marker
whose only constructor runs a witness-based containment check, so a
`ClearanceHalo` can only exist if the containment was *verified*, not just
assumed — plus the track/via constructors and the zone-generator adoption
that §6 deferred. Base `origin/main` @ `607cc7bd6` (the #1258 merge), dirty
at measurement time (this delta was uncommitted when its tests ran).

<!-- provenance: commit=607cc7bd662b14eb3e34e65859e9a5d74dedb3dc dirty=true -->

## 7. Structural verification: the `ConservativeSuperset` marker

The first changeset's guarantee is "the polygon field is private, so the
only two constructors are the only places the approximations can be made".
That is true but *assumed*: nothing at construction time checks that the
formula actually produced a containing polygon. This changeset adds the
check:

* `ConservativeSuperset` — a ZST marker whose **only** constructor,
  `verified(polygon, witnesses, description)`, asserts every witness is
  inside the halo polygon (boundary-inclusive: the witnesses that pin the
  circumscription sit exactly on the polygon's edges, so geo's interior-only
  `Contains` is the wrong probe here; the crate's winding predicate with its
  1e-12 on-edge tolerance is used).
* Witnesses are sampled from the **true shape's boundary** at exactly the
  points where an undercut would show: for circles, the edge-midpoint
  directions (where an inscribed polygon dips inside by `r·(1−cos(π/n))`),
  the vertex directions, and a uniform sample; for rect pads, the actual
  rotated boundary (straight edges, corner arcs, and the four sharp corners
  — the farthest points); for capsules, the straight sides and both cap
  semicircles including the cap-edge-midpoint directions.
* The geometric proof condition is checked too: every polygon edge's
  distance from the shape (centre for circles, segment for capsules) is ≥
  the true radius. Combined with convexity (circumscribed regular polygons /
  capsules), this *proves* containment, with the witnesses as belt.
* If the check fails, the side count is increased and retried (capped at
  `MAX_SIDES`, then panics loudly — a halo that cannot hold its guarantee is
  a programming error, and silence is exactly how the three bugs shipped).

Two construction defects were found **by this machinery during
development**:

1. **Bounding-box-corner witnesses are geometrically wrong for a circle.**
   An early draft (per the dispatch's sketch) verified "every vertex of the
   true circle's bounding box is inside the polygon". Those points sit at
   `r√2` from the centre — they are NOT on the circle — and no circumscribed
   polygon ever contains them, so the retry loop ran to its cap (first
   symptom: a 15-minute test timeout). Fixed: all witnesses are ON the true
   boundary.
2. **Off-origin rotation double-translation** (found by the proptest, not
   the example tests): a draft of the rect-witness builder subtracted
   `center` twice from already-local coordinates, moving every witness
   outside the halo whenever `center ≠ (0,0)`. Every origin-centred example
   passed; the randomized property (centres in `[-50, 50]²`) failed
   immediately on `cx = −43.3`. Pinned in
   `packages/temper-geometry/proptest-regressions/clearance_halo.txt` (the
   committed proptest regression file re-runs the failing input first on
   every future run).

## 8. New constructors: tracks and vias

* `from_track(start, end, width, clearance, eps)` / `from_track_with_segments`
  — a circumscribed capsule (Minkowski sum of the segment and the clearance
  circle). Every polygon edge is at distance ≥ `width/2 + clearance` from
  the segment; the capsule polygon being convex, this implies the entire
  true capsule is contained (tube argument). Verified by the edge-distance
  condition AND cap/straight-side witnesses.
* `from_via(position, diameter, clearance, eps)` — a circular pad of radius
  `diameter/2`.
* `*_with_segments` variants for all shapes (the zone generator's fixed-24
  convention; the zone generator's own `disc`/`capsule` area tests confirm
  the adopted polygons are bit-identical to the old construction).

## 9. Zone-generator adoption (the §6 follow-up, done)

`ZoneObstacle::halo_polygon` now builds every halo through `ClearanceHalo`:

| obstacle | constructor | shape |
|---|---|---|
| `Pad` | `from_rect_pad_with_segments(position, 2·half_w, 2·half_h, 0.0, rot, clearance, 24)` | disc at the half-diagonal |
| `Via` | `from_circular_pad_with_segments(position, diameter/2, clearance, 24)` | disc |
| `Track` | `from_track_with_segments(start, end, width, clearance, 24)` | capsule |

The polygons are geometrically identical to the previous hand-rolled
`disc`/`capsule` (same circumscribed vertices at `r/cos(π/24)` — verified by
the zone generator's `disc_halo_area` / `capsule_halo_has_positive_area`
tests passing unchanged). The half-diagonal convention and the
`1/cos(π/24)` inflation that the DRC findings established are now enforced
by the type rather than by one-line fixes. `disc`/`capsule` are retained,
gated to test builds, as the reference construction the area tests compare
against.

## 10. Randomized properties (proptest) — without losing the wasm tier

The first changeset deliberately avoided proptest ("a dev-dependency would
exclude them from the wasm Worker tier"). The nested-gated-module pattern
solves the trade-off: the randomized properties live in
`tests::proptests` (its own wasm-registry census entry, excluded as a
proptest dev-dependency), while the deterministic example tests stay in
`tests` and remain wasm-registered (10 tests, up from 4). Three proptest
properties: circle containment + clearance floor, rect corners + clearance
floor (off-origin, rotated — caught defect 7.2), track clearance floor.

## 11. Verification (this changeset)

* `cargo test -p temper-geometry`: **8489 passed, 0 failed** (baseline
  8444 + 13 new in clearance_halo + 8 zone-generator tests, all green).
* `cargo clippy --lib --tests`: 0 warnings (one pre-existing
  `zone_generator.rs` test-style `len() >= 1` fixed; the pyo3-surface
  type_complexity / too_many_arguments warnings are pre-existing in the
  merged `zone_generator.rs` and untouched here).
* wasm registry: `scripts/gen_wasm_test_registry.py --crate
  temper-geometry --check` green — `clearance_halo::tests` (10) registered,
  `clearance_halo::proptests` (3) excluded by the generator's own
  predicate; `cargo build --no-default-features` verified.
* geo 0.28 panic reproduction (for the record; the repo now pins geo 0.29):
  a one-shot `MultiPolygon::union` of 500 varying-radius halos panicked on
  geo 0.28 (`segment not found in active-vec-set: 791`, reproduced
  2026-08-16); the fold+snap pattern the zone generator uses completed
  (1 poly, 717 mm²). The stress test in the module guards the fold pattern
  and now also runs under geo 0.29.
