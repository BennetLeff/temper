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
