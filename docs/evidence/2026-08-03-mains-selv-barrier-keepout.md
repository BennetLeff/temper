<!-- provenance: commit=b8709225c1f5f8332c48693500fc544e57d35784 dirty=false -->

# MAINS_SELV_ISOLATION_BARRIER keepout — falsified on the current board (issue #518, plan R2)

**Date:** 2026-08-03
**Branch:** `feat/mains-selv-barrier-keepout`
**Issue:** #518 — Board & Netlist Gates: missing `MAINS_SELV_ISOLATION_BARRIER` keepout zone
**Plan:** `docs/plans/2026-08-02-002-feat-sealed-compartment-plan.md` R2
**Scope:** owner-GO'd keepout-only change. **No component moves, no board geometry change was made.**

> **Provenance note (rebase re-point).** The measurement session started on
> `origin/main` at `f6933d0a2` and ran all analysis against that tree.
> `origin/main` moved mid-task to `b8709225c` (`fix(io): import DesignRules at
> runtime — main fails regression with NameError (#649)`). Verified via
> `git diff --stat f6933d0a2 b8709225c -- pcb/temper.kicad_pcb
> power_pcb_dataset/ elec/domain_manifest.yaml` → **empty**: the landing commit
> does not touch the board, the DRC-ceiling dataset, or the domain manifest, so
> every number below is byte-identical on both trees. The header is re-pointed
> at the post-rebase base `b8709225c` (the persistent main commit the board
> content is measured at; board content hash `51e39844…` unchanged). This
> dispatch restarted the task from the salvaged analysis and **re-verified every
> number and re-derived the verdict independently** (see §9); the verdict is
> unchanged, but the *reasoning* was corrected and strengthened (§4c/§4d/§4e).

---

## 1. Executive summary

**The `MAINS_SELV_ISOLATION_BARRIER` keepout cannot be drawn on the current
board in a way that satisfies the gate (`scripts/check_isolation_keepout.py`),
for three independent, measured reasons — and the two reasons the prior
falsification believed were the blockers are NOT the real ones:**

1. **Macro-level domain interleave (real, verified, but NOT decisive).** HV and
   SELV pads occupy *every* 20 mm x-band of the 152×234 mm board (HV pads span
   x∈[21.2, 168.0], SELV pads span x∈[21.2, 171.0]; bounding boxes overlap
   completely). No straight bisector exists: the best vertical split still leaves
   **111 far-side pads** (and the best 8 mm band still contains **239 copper
   intruders**); the best horizontal split leaves **116 far-side pads**
   (82 intruders). **However, the gate accepts arbitrary polygons, not just
   straight bands** — so straight-split statistics are informative, not the
   obstruction.
2. **Pad-center curve inseparability (the DECISIVE obstruction for the far-side
   check).** The gate's far-side check (`check 6`, `check_isolation_keepout.py`
   L782–824) uses each pad's **center point**, and the barrier may be any
   polygon, so the question is topological: *does any simple curve (edge-to-edge
   arc, cap, or closed loop) keep every HV center on one side and every SELV
   center on the other?* **No.** The Delaunay triangulation of the 324 domain
   pad centers contains a **strictly alternating 12-pad bichromatic cycle**
   (C6.2→R8.2→K1.A2→R8.1→R75.1→C27.2→C9.1→U5.3→Q1.1→U5.1→U10.2→R27.2) — the
   classical topological obstruction to any simple-curve separator. And the loop
   form is equally impossible: **137 SELV centers lie inside the HV convex hull**
   (93 HV centers inside the SELV hull), so no closed loop can enclose one
   domain without the other. **The far-side check is unsatisfiable for every
   barrier form, at any placement.**
3. **Copper-exclusion (checks 4+5) fails independently of domain colors.** Zone
   outlines cover **85.7 %** of the board area; the copper-free space is only
   **12.6 %**, fragmented into **99 components**, and only **3** components
   touch two board edges — all corner scraps (largest 1425 mm²). No connected
   copper-free corridor spans the board, so **no edge-to-edge/cap keepout
   polygon can avoid every segment/via/pad/zone** even before any domain logic
   is applied.

**Correction of the prior falsification's K1/T1 claim.** The earlier analysis
called K1 (5.369 mm) and T1 (5.977 mm) "IRREDUCIBLE blockers": *an 8.0 mm-wide
barrier cannot fit between pad clusters <8.0 mm apart edge-to-edge*. That claim
overstated the gate's width check: `check_isolation_keepout.py` L675–685 only
requires `barrier_poly.buffer(-MIN_BARRIER_WIDTH_MM / 2.0)` to be **non-empty** —
i.e. the polygon must contain **one 8.0 mm disk somewhere**, not be 8.0 mm wide
everywhere. A thin barrier could in principle pass between K1's/T1's sub-8.0 mm
clusters. **The conclusion (no compliant barrier exists) is nevertheless
correct** — via the far-side and copper-exclusion obstructions above, which are
placement-independent and do not depend on the width check at all.

Because the gate's own hard rules forbid faking a zone ("Do NOT fake a zone",
`docs/plans/2026-07-31-002-fix-pr513-red-checks-and-board-debt-plan.md`; "never
shrink the barrier to make the gate pass", `check_isolation_keepout.py`
docstring), and because the dispatch explicitly forbids component moves, **no
keepout was added**. The gate stays red with a documented reason, exactly as
the prior falsification records prescribe (`docs/evidence/2026-07-28-isolation-keepout.md`,
`docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md` §"keepout falsified").

This re-confirms the 2026-07-31 handoff's verdict on the **post-wave-2 board**
(the K3 RT314012 swap + validator-gated re-solve, `de59c0458`): the re-solve
cleared REQ-SAFE-01 pair-wise (0/0) but did **not** create a mains/SELV
spatial partition — the pad centers remain curve-inseparable — so the keepout
gate remains falsified.

---

## 2. What the gate requires (exact contract)

`scripts/check_isolation_keepout.py` (`run()`, L565–828; exit 0 only if ALL
hold). Quoted semantics:

1. **Zone name** (L605–633): exactly one zone named `MAINS_SELV_ISOLATION_BARRIER`
   (`BARRIER_ZONE_NAME`, L167). Zero → `missing`; >1 → `duplicate`.
2. **Layer span** (L638–650): the zone's declared layers, after `*.Cu`
   wildcard expansion (`_expand_copper_layers`, L329–339), cover every copper
   layer the board's stackup declares (`F.Cu, In1.Cu, In2.Cu, B.Cu`).
3. **Keepout settings** (L652–669): `tracks/vias/pads/copperpour/footprints`
   all `not_allowed`.
4. **Width** (L675–685): `eroded = barrier_poly.buffer(-min_width / 2.0)`; a
   violation only if `eroded.is_empty`. **The implemented check requires the
   polygon to contain at least one 8.0 mm-diameter disk (inradius ≥ 4.0 mm),
   NOT 8.0 mm width along its whole length** — the module docstring's "at its
   narrowest" (L88–91) overstates what the code enforces.
5. **Partition** (L687–718): `board_poly.difference(barrier_poly)` yields
   **exactly two** non-empty regions — i.e. the barrier is a connected region
   spanning the board outline to outline (arc/cap) or a closed loop inside it.
   Arbitrary polygon shapes are accepted; **no straightness requirement exists
   anywhere in the check**.
6. **No intrusion** (L720–780): no segment/arc (buffered by width/2), via
   (by radius, with `_via_layer_span` ordinal expansion, L342–360), pad (by its
   exact bounding-circle radius, L750–765), or non-keepout zone polygon
   (L767–780) may intersect `barrier_poly` on a shared layer. **This is a
   barrier-vs-copper exclusion check — it never measures pad-to-pad clearance.**
7. **No far-side crossing** (L782–824): every HV-classified pad's **center
   point** (`_side_of(p.x, p.y)`, L785–793) must land in exactly one of the two
   partition regions, every SELV center in the other; a domain on both sides or
   both domains on the same side is a violation.

Consequences for the resolution question:

- The gate **accepts an arbitrary winding polygon** — the "no straight
  bisector" observation is *not* by itself an obstruction.
- The gate measures **barrier copper-exclusion** (check 5) and **pad-center
  side assignment** (check 6) — **not** pad-to-pad clearance. So sub-8.0 mm
  intra-footprint gaps (K1/T1) do not by themselves block a barrier whose
  width check only needs one 8.0 mm disk somewhere.
- The binding constraints are therefore **check 6** (a topological property of
  the pad-center arrangement) and **checks 4+5** (a property of the existing
  copper). Both are unsatisfiable on this board (§4c, §4d).

---

## 3. Measured board state (base `b8709225c`, board content hash `51e39844…`)

Loaded with the gate's own loader (`load_board` / `load_manifest`), so the
numbers below are the exact geometry the gate judges:

| property | value |
|---|---|
| board outline (`Edge.Cuts`) | `(20,20) (172,20) (172,254) (20,254)` — 152 × 234 mm |
| copper layers | `F.Cu, In1.Cu, In2.Cu, B.Cu` |
| footprints | 169 |
| pads | 527 (HV=103, SELV=221, other=203) |
| copper items | 2338 segments + 48 vias + 96 copper zones = 2482 |
| keepout zones (any name) | 0 |

Gate current state: **`violation`, 1 violation (`missing`)** — "No keepout zone
named 'MAINS_SELV_ISOLATION_BARRIER' found on the board". This is the #518 red.

---

## 4. Geometry analysis — why no compliant barrier exists

### 4a. Domain interleave (real, but only rules out STRAIGHT separators)

| domain | n | x bbox | y bbox | centroid |
|---|---|---|---|---|
| HV | 103 | [21.24, 168.00] | [21.24, 246.60] | (82.4, 139.6) |
| SELV | 221 | [21.24, 171.00] | [21.21, 252.67] | (94.0, 119.9) |

x-band occupancy (20 mm bins, board frame x=20..172):

| x band | 20–40 | 40–60 | 60–80 | 80–100 | 100–120 | 120–140 | 140–160 | 160–180 |
|---|---|---|---|---|---|---|---|---|
| HV pads | 21 | 18 | 15 | 16 | 8 | 9 | 10 | 6 |
| SELV pads | 57 | 15 | 11 | 23 | 44 | 25 | 16 | 30 |

Both domains occupy every band; centroids are only 22.9 mm apart on the 152 mm
width. **Informative but not decisive**: the gate accepts arbitrary polygons.

### 4b. Best straight-line split (informative only)

Exhaustive scan of every pad coordinate plus band midpoints, evaluating the
gate's own intrusion geometry (pads buffered by exact bounding radius,
segments by width/2, vias by radius, zones by polygon):

| orientation | best split position | far-side pads | copper intruders in 8 mm band |
|---|---|---|---|
| vertical (x) | x = 21.27 | **111** | **239** |
| horizontal (y) | y = 21.21 | **116** | **82** |

(The "best" splits degenerate toward the board edge.) Included because the
numbers are real and reproducible; not the obstruction — see §2.

### 4c. THE DECISIVE OBSTRUCTION — pad-center curve inseparability (check 6)

The far-side check uses pad **centers** and the barrier may be any polygon, so
the question is whether **any** simple curve separates the 103 HV centers from
the 221 SELV centers. Two independent, placement-independent results:

1. **Open-arc/cap separators: impossible.** The Delaunay triangulation of the
   324 centers contains a **strictly alternating bichromatic cycle of 12 pads**
   (every Delaunay edge is an empty-segment visibility adjacency, so this is a
   genuine topological obstruction, not a triangulation artifact):

   | # | pad | domain | (x, y) |
   |---|---|---|---|
   | 1 | C6.2 | SELV | (65.99, 211.76) |
   | 2 | R8.2 | HV | (71.25, 222.20) |
   | 3 | K1.A2 | SELV | (92.06, 221.40) |
   | 4 | R8.1 | HV | (71.25, 223.84) |
   | 5 | R75.1 | SELV | (80.48, 242.77) |
   | 6 | C27.2 | HV | (68.62, 242.00) |
   | 7 | C9.1 | SELV | (88.15, 252.67) |
   | 8 | U5.3 | HV | (23.72, 244.15) |
   | 9 | Q1.1 | SELV | (21.25, 217.11) |
   | 10 | U5.1 | HV | (23.72, 233.25) |
   | 11 | U10.2 | SELV | (38.83, 220.80) |
   | 12 | R27.2 | HV | (57.00, 223.10) |

   Colors around the ring: `SELV HV SELV HV SELV HV SELV HV SELV HV SELV HV` —
   strictly alternating. **No simple arc or cap can keep all HV centers on one
   side and all SELV centers on the other** (any such curve would have to pass
   between every adjacent pair around the ring, forcing a self-intersection).

2. **Loop separators: impossible.** The HV convex hull (30205 mm²) contains
   **137 SELV centers**; the SELV convex hull (32039 mm²) contains **93 HV
   centers**. A closed-loop barrier must enclose every pad of one domain and no
   pad of the other; since each domain's hull is stuffed with the other
   domain's centers, no loop exists.

⇒ **Check 6 is unsatisfiable for every barrier form.** This is the primary
reason the keepout cannot be drawn — and it is a property of the pad-center
arrangement, i.e. of the current floorplan, not of any keepout polygon.

### 4d. Copper-exclusion (checks 4+5) — unsatisfiable even ignoring domains

Using the gate's own geometry (segments by width/2, vias by radius, pads by
exact bounding radius, zone polygons):

- **Zone outlines cover 85.7 % of the board area** (30470 / 35568 mm²).
- **Copper-free space is 12.6 %** (4481 mm²), fragmented into **99 components**.
- Only **3** free-space components touch two board edges: comp 0 (166 mm²,
  bottom+left), comp 2 (92 mm², right+top), comp 5 (1425 mm², left+top) — all
  corner scraps, none of them a through-corridor, and all far too small to host
  an 8.0 mm-disk-containing barrier that also bisects the board.

⇒ **No edge-to-edge or cap keepout polygon can exist in copper-free space** —
checks 4+5 fail even before any domain logic is applied.

### 4e. K1/T1 correction (what the earlier falsification got wrong — and why it doesn't matter)

Measured (verified this session, unchanged): K1 (bypass relay Omron G4A-1A-E)
HV↔SELV edge gap **5.369 mm** (Faston tabs r=3.23 vs coil pads r=0.90, centers
9.50 mm apart); T1 (CT Coilcraft CST3015-100ED) **5.977 mm** (pad 1 r=5.10 vs
pad 4 r=2.75, centers 13.85 mm apart).

The prior doc called these "irreducible blockers" on the theory that the
barrier must be 8.0 mm wide *everywhere*. **The code does not implement that**:
check 3 only fails when the erosion collapses to empty (L675–685), i.e. it
requires one 8.0 mm disk somewhere. A barrier that is thin between K1's/T1's
clusters and bulges to ≥8.0 mm elsewhere would pass check 3. **The K1/T1 gaps
are therefore NOT by themselves the obstruction.**

They remain relevant as *secondary* observations: any future *re-solve* must
either keep these isolators' HV and SELV pads on opposite sides of the corridor
(requiring the corridor to pass between sub-8.0 mm clusters, which a
fixed-8.0 mm corridor of the CP-SAT model — `isolation_barrier.py`,
`DEFAULT_CORRIDOR_WIDTH_MM = 8.5` — cannot do) or swap them for parts with
≥ 8.0 mm internal separation. But the *gate* is blocked by §4c/§4d regardless
of what happens to K1/T1.

---

## 5. What a compliant zone would look like (for the future floorplan + re-solve)

When the domain-first re-solve lands — the ONLY change that can make the
pad centers separable (§4c) — the zone that makes the gate pass is a single
KiCad keepout, serialized by kiutils (see
`scripts/tests/test_check_isolation_keepout.py` `build_board` for the
round-trip-tested form):

```
  (zone (net 0) (net_name "") (layers "F.Cu" "In1.Cu" "In2.Cu" "B.Cu")
    (name "MAINS_SELV_ISOLATION_BARRIER") (hatch none 0.0)
    (priority 50)
    (connect_pads (clearance 0.254))
    (min_thickness 0.254)
    (keepout (tracks not_allowed) (vias not_allowed) (pads not_allowed) (copperpour not_allowed) (footprints not_allowed))
    (polygon (pts (xy <edge1...>) ...))
  )
```

- **Name** exactly `MAINS_SELV_ISOLATION_BARRIER` (the gate matches on this
  string; a second such zone is a `duplicate` violation).
- **Layers**: all four copper layers (or `*.Cu`, which `_expand_copper_layers`
  accepts as a wildcard).
- **Polygon**: the gate accepts ANY simple edge-to-edge polygon. The natural
  target is a strip ≥ 8.5 mm wide (8.0 + margin) at the isolation-barrier
  corridor the CP-SAT model uses (`isolation_barrier.py`: vertical corridor,
  `barrier_axis=0`, `DEFAULT_CORRIDOR_WIDTH_MM = 8.5`, board-centreline position
  ≈ x∈[91.75, 100.25] in board frame). **Only valid once the re-solve places
  all HV-only components at x < 91.75 and all SELV-only at x > 100.25 and no
  copper crosses the corridor** — i.e. once the pad centers are separable,
  which today they are not (§4c).
- **Keepout settings** all `not_allowed` (tracks, vias, pads, copperpour,
  footprints).

---

## 6. DRC ceiling + baseline — NOT touched, with rationale

**No board change was made** (`git diff --stat origin/main -- pcb/` empty), so:

- `power_pcb_dataset/drc_ceiling.json` is **untouched**: the recorded input
  hash `51e39844b18aa37c84e4cc0b011acc51dc24cb1282359e1334ecbdf6ed07d9af`
  still matches `pcb/temper.kicad_pcb` exactly, and
  `scripts/check_measurement_provenance.py` still PASSES (verified — see §8).
  No re-measurement was needed or performed; the 120-sample ceiling record
  from the wave-2 write (`2026-08-02-k3-swap-and-board-write` entry) remains
  valid. There is therefore no before/after per-type table and no
  `Ceiling-Approval:` trailer — nothing moved.
- `power_pcb_dataset/baselines/temper_production_baseline.yaml` is **untouched**:
  `drc_errors: 1046`, `drc_warnings: 472` are properties of the unchanged
  board; the golden-check's numbers cannot move if the board does not.

A future board change that *does* land the keepout must, in the same PR,
re-measure the 120-sample ceiling and update both files per AGENTS.md.

---

## 7. Decision and next steps

- **This PR adds no keepout** — the honest outcome, per the repo's own
  falsification precedent. The `Board & Netlist Gates` isolation-keepout step
  stays red with a documented reason (#518 remains open).
- **Why R2 as scoped (keepout-only, no component moves) cannot land:**
  the gate is unsatisfiable for any polygon on the current floorplan — the
  far-side check is blocked topologically (§4c) and the copper-exclusion
  checks are blocked physically (§4d). Drawing a keepout now would be faking a
  zone; the plan's own R2 rationale ("marks where the partition/gasket meets
  the PCB") presupposes a partition that does not yet exist spatially.
- **The actual unblock requires a domain-first re-solve** — the plan's R1
  workstream. Specifically:
  1. **A barrier-constrained re-solve** that produces a real spatial partition
     (HV-only at x < corridor, SELV-only at x > corridor, no copper crossing
     the corridor). This is the *necessary* condition: without it the pad
     centers stay curve-inseparable and NO keepout can pass, regardless of
     parts. The alternating ring of §4c involves resistors/capacitors/U5/Q1/
     U10/C6/R8/R75/C27/C9 — **not just the isolators** — so swapping K1/T1
     alone would NOT unblock the gate.
  2. **K1/T1 footprint work** (swap to parts with ≥ 8.0 mm internal HV↔SELV
     pad separation — the K2/K3 RT314012 class for K1) is then required so the
     re-solve's fixed-8.5 mm corridor can pass between these isolators' HV and
     SELV pads (§4e). It is a *constraint on the re-solve*, not a standalone
     fix.
  3. Only then does the keepout of §5 become drawable, in the same PR as the
     re-solve that makes it valid, with the 120-sample DRC-ceiling re-measure.
- **Alternative (not recommended):** a deliberate, owner-signed change to
  `check_isolation_keepout.py` to relax check 6 (e.g. per-isolator barrier
  continuity instead of domain-wide pad-center separation — which is what the
  exact-copper REQ-SAFE-01 pair-wise validator already models per pair). This
  weakens a fail-closed safety gate and must not happen without an explicit
  owner decision; issue #518 is the right place to record it.

---

## 8. Gates

| gate | result |
|---|---|
| `scripts/check_isolation_keepout.py` | violation (1: missing) — unchanged, pre-existing #518 |
| `scripts/check_measurement_provenance.py` | **PASSED** (board hash `51e39844…` matches ceiling record; no board change) |
| evidence provenance (`scripts/check_evidence_provenance.py`) | **PASSED** for the files in this change; the gate overall reports 1 pre-existing main violation (`docs/evidence/2026-08-02-validation-portfolio-review.md`, no provenance stamp — unrelated to this change, not introduced here) |
| import linter (`scripts/import_linter_gate.py`) | 0 new violations |
| ruff (touched files) | clean |
| pytest `tests/placer/cp_sat/test_isolation_barrier.py` | green (unchanged code) |
| pytest `tests/placer/cp_sat/test_isolation_barrier_rust_differential.py` | green (unchanged code) |
| pytest `scripts/tests/test_check_isolation_keepout.py` | green (unchanged code) |

## 9. Reproduction

```bash
uv run --no-sync python docs/evidence/scripts/2026-08-03_mains_selv_barrier_falsification.py
# expected: HV bbox x[21.24,168.00] / SELV bbox x[21.24,171.00];
# best split vertical 111 far-side / 239 intruders, horizontal 116 / 82;
# BLOCKERS: ['K1 5.369mm', 'T1 5.977mm']  (informative, NOT decisive);
# bichromatic Delaunay cycle: FOUND (12 vertices), strictly alternating: True;
# HV hull contains 137 SELV centers / SELV hull contains 93 HV centers;
# copper-free 12.6%, 99 components, 3 touch >=2 edges, zone outlines 85.7%;
# gate state=violation (1: missing)
```

The 12-pad ring, the convex-hull counts, and the free-space statistics were
independently re-derived on this restart; the Delaunay criterion was validated
against hand-built cases (clean split=separable, alternating ring=inseparable,
zipper=separable) inside the script itself.
