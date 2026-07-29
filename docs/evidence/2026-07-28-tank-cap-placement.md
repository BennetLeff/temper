<!-- provenance: commit=c83f5af91f0b65200788334edd9be7e7d58245fa dirty=true (base = origin/main, PR #401's merge. "Before" figures were measured on a clean checkout of that commit; "after" figures in the same tree with this branch's single-file edit to pcb/temper.kicad_pcb applied, hence dirty=true. Every before/after pair is labelled inline. The DRC noise study re-measured the *unmodified* board 26 times at this same commit.) -->

# Tank capacitor placement for the corrected `FKP1T031507G00JSSD`

Branch `fix/tank-cap-placement`, from `origin/main` at `c83f5af9`.

PR #401 corrected the resonant tank capacitors' MPN and footprint
*assignment* but deliberately did not touch `pcb/temper.kicad_pcb`. The board
therefore contradicted its own netlist: `elec/build/default.net` names
`Capacitor_THT:C_Rect_L41.5mm_W20.0mm_P37.50mm_MKS4` for C25/C26, while the
board still carried `C_Rect_L31.5mm_W13.0mm_P27.50mm_MKS4` — the land pattern
of the *mis-decoded* 15 nF part. This branch closes that gap.

**A valid placement exists.** It is applied here. Total component
displacement is 8.62 mm across two parts; nothing else on the board moved.

---

## Summary

| | Before (`c83f5af9`) | After |
|---|---|---|
| C25 footprint | `C_Rect_L31.5mm_W13.0mm_P27.50mm_MKS4` | `C_Rect_L41.5mm_W20.0mm_P37.50mm_MKS4` |
| C26 footprint | `C_Rect_L31.5mm_W13.0mm_P27.50mm_MKS4` | `C_Rect_L41.5mm_W20.0mm_P37.50mm_MKS4` |
| C25 origin | `(75.40, 47.11) rot 180` | `(73.42, 51.25) rot 180` |
| C26 origin | `(59.38, 27.25) rot 0` | `(59.38, 30.75) rot 0` |
| Courtyard overlaps board-wide | 11 | **11** |
| Courtyards outside `Edge.Cuts` | 2 | **2** |
| Pads outside `Edge.Cuts` | 0 | **0** |
| REQ-SAFE-01 violation records | 56 over 24 pairs | **56 over 24 pairs**, per-pair identical |

Diff: one file, 30 insertions / 30 deletions, confined to the two footprint
blocks.

---

## Part A — two claims in the brief did not reproduce

Both were re-measured from scratch against exact courtyard geometry
(`shapely`, circles honoured), not inherited.

### A.1 C25 does **not** overlap C5. That figure is an AABB artifact.

The brief states C25's new outline overlaps C5 — a D35 snap-in bus
electrolytic — by 7.60 × 1.32 mm. It does not. **C5's courtyard is a circle**
(`fp_circle (center 5 0) (end 22.75 0)`, r = 17.75 mm), not a rectangle.

| Measurement | Result |
|---|---|
| C25-new courtyard | `(35.650, 36.860)–(77.650, 57.360)` |
| C5 courtyard bounding box | `(71.150, 55.870)–(106.650, 91.370)` |
| **AABB × AABB overlap** | **6.500 × 1.490 mm → "OVERLAP"** |
| **Exact polygon intersection** | **`False`, area 0.000000 mm²** |
| **Exact minimum separation** | **2.0236 mm** |

Why: at y = 57.360 (C25's lowest edge) C5's circle spans x ∈ [81.781,
96.019]. C25's courtyard reaches x = 77.650. The corner the bounding-box
"overlap" occupies is empty board, by 4.131 mm.

The corrected part does fit beside C5 at the committed origin. It was never
the blocker.

### A.2 C26's 3.000 mm edge overhang reproduces exactly.

C26-new courtyard at the committed origin is `(57.130, 17.000)–(99.130,
37.500)`; `Edge.Cuts` is the rectangle `(20,20)–(172,254)`. y-min overhang =
**3.000 mm**, 126.000 mm² outside the board. This is real and is fixed here.

### A.3 The real defect the swap introduces is a *third* thing, unlisted.

With both caps on the new footprint at their committed origins, C25 and C26
collide with **each other** — 20.520 × 0.640 mm, 13.133 mm². Neither cap
collides with anything else.

So the footprint swap's exact cost is **two** defects, not the two claimed:

| Defect | Real? |
|---|---|
| C25 ↔ C5 overlap | **No** — 2.02 mm clear |
| C26 3.000 mm off the board edge | Yes |
| C25 ↔ C26 mutual overlap | Yes (not in the brief) |

---

## Part B — the board was already in this state, worse, before #401

A board-wide audit at `c83f5af9`, with the **committed** (old, small)
footprints, finds defects of exactly the kind the brief treats as new:

**11 pre-existing courtyard overlaps:**

| Pair | Area | Extent |
|---|---|---|
| C3 ↔ C4 | 568.186 mm² | 32.613 × 23.660 mm |
| C5 ↔ C7 | 128.988 mm² | 18.500 × 7.910 mm |
| C2 ↔ R13 | 90.637 mm² | 15.842 × 7.910 mm |
| C14 ↔ C5 | 26.438 mm² | 5.082 × 5.900 mm |
| C4 ↔ R56 | 10.306 mm² | 4.560 × 2.260 mm |
| C3 ↔ R56 | 10.306 mm² | 4.560 × 2.260 mm |
| K3 ↔ R12 | 3.762 mm² | 3.960 × 0.950 mm |
| C17 ↔ C2 | 0.610 mm² | 3.896 × 0.210 mm |
| C2 ↔ R32 | 0.230 mm² | 1.716 × 0.238 mm |
| C5 ↔ R51 | 0.226 mm² | 0.483 × 0.916 mm |
| D3 ↔ TP3 | 0.059 mm² | 0.100 × 0.871 mm |

C3 ↔ C4 is two D35 snap-in electrolytics 17.02 mm apart origin-to-origin when
they need ≥ 35 mm. That is not a marginal courtyard clip; it is physically
impossible to assemble.

**2 pre-existing footprints outside `Edge.Cuts`:** C3 hangs **7.810 mm** off
the north edge (161.424 mm² outside — 2.6× C26's overhang); U1 hangs
1.760 mm off the south edge.

KiCad's own DRC corroborates the count independently: `courtyards_overlap`
measures **11**, bit-stable across 8 runs, both before and after this change.

Consequence for the brief's acceptance criterion: **"confirm no footprint
overlaps remain and everything sits inside `Edge.Cuts`" is not reachable by
moving the tank capacitors.** It requires a board-wide re-place that is out
of scope here. What is achieved instead — and what is checked below — is that
this change adds none and removes none.

---

## Part C — the placement, and how it was found

### C.1 Constraint space

- **Board outline**: `Edge.Cuts` `gr_poly` `(20,20)–(172,254)`, 152 × 234 mm.
  Free area after subtracting all 159 other courtyards: 23 995.8 mm² of
  35 568.0 mm².
- **Keepouts**: none. The board carries **zero** keepout zones — which is
  also why `check_isolation_keepout.py` fails on `main` (see Part D).
- **Domain**: both tank nets (`SW_NODE`, `tank.c_tank1-p2`) classify as
  `VoltageDomain.DC_BUS` via `elec/domain_manifest.yaml`. Each cap therefore
  carries **114 `DC_BUS↔LV_CONTROL` reinforced pairs at 8.0 mm**
  (`max(clearance 6.0, creepage 8.0)`), enumerated by the repo's own
  `generate_domain_clearance_constraints()`.
- **Creepage model**: the board declares 0 `Edge.Cuts` cutouts, so the
  insulating surface is unbroken and creepage == clearance exactly.
- **Baseline margin**: at the committed positions with the **old** footprint,
  C25 and C26 clear all 114 pairs each — **0 below 8.0 mm**. That is why
  neither appears in the 56 REQ-SAFE-01 records, and it is the property this
  change had to preserve.

Feasible-region scan on a 0.5 mm grid for the 42.0 × 20.5 mm body: 2097
feasible origins at rot 0, 2097 at rot 180, 173 each at rot 90/270. A valid
placement plausibly exists — stated before searching for one.

### C.2 The solve

CP-SAT via the repo's `placer/cp_sat` machinery. Constraints enabled:

1. **Inside-outline** — body courtyard within `Edge.Cuts`, 0.5 mm margin.
2. **Body no-overlap** — Chebyshev ≥ 0 against every other courtyard. Round
   courtyards (the D35 snap-ins) are **slab-decomposed into 24 strips** so
   they are not treated as squares — the exact error Part A.1 documents.
   803 obstacle boxes from 166 footprints.
3. **Pair no-overlap** — C25 ↔ C26.
4. **Domain clearance** — Chebyshev ≥ 8.0 mm on **copper**, per
   `generate_domain_clearance_constraints()`. 228 disjunctions.
5. **Rotation** — 0/90/180/270.

Objective: minimise L1 displacement of the body centre from the committed
placement.

**A note on why the first solve was INFEASIBLE, because it matters.**
Encoding constraint 4 on *courtyards* — which is what
`domain_clearance.py`'s own `SeparatedConstraint` emission does — returns
INFEASIBLE. That encoding is sound but, for this part, badly over-conservative:
the tank cap's copper is two pads on the body centreline, so the courtyard
extends **10.25 mm beyond the copper on the y axis**. REQ-SAFE-01 has measured
**copper-to-copper** since PR #392. Re-encoding constraint 4 on the pad
bounding box (40.3 × 2.8 mm) while keeping constraint 2 on the body courtyard
— two different geometries because two different physical things are being
constrained — is OPTIMAL. Courtyard-Chebyshev ≥ 8 mm still *implies*
copper ≥ 8 mm, so the result remains conservative in the safe direction.

Result: **OPTIMAL**, 8.62 mm total displacement (9.62 mm with the 0.5 mm edge
margin actually applied).

A 0.5 mm body-to-body clearance on top is **INFEASIBLE** — the fit is genuinely
tight and courtyards must be permitted to touch. Courtyards are the clearance
envelope by definition, so this is the normal "just fits" condition, but it is
recorded rather than glossed.

### C.3 What moved

| Ref | From | To | Displacement |
|---|---|---|---|
| C25 | `(75.40, 47.11) rot 180` | `(73.42, 51.25) rot 180` | 1.98 mm left, 3.64 mm down |
| C26 | `(59.38, 27.25) rot 0` | `(59.38, 30.75) rot 0` | 3.00 mm down |

Rotations unchanged. Nothing else on the board moved. C26's new courtyard
top edge sits at y = 20.50 — the same 0.50 mm edge margin the old C26 had.

C25 ↔ C5 minimum separation in the applied placement: the CP-SAT slab
decomposition holds it clear; the tightest body gap in the region is ~0.75 mm.

---

## Part D — before/after, every gate

Measured at `c83f5af9` (before) and with this branch applied (after).

| Gate | Before | After | Δ |
|---|---|---|---|
| `check_isolation_keepout.py` | **FAIL** — 1 violation (no `MAINS_SELV_ISOLATION_BARRIER` zone; 0 keepouts on board) | **FAIL** — 1 violation, identical | none |
| `check_domain_partition.py` | PASS — 0 crossings, 0 isolator breaches, 0 chain defects | PASS — identical | none |
| `pytest tests/requirements/` | 1 failed, 293 passed, 5 skipped | 1 failed, 293 passed, 5 skipped | none |
| REQ-SAFE-01 records | **56 over 24 pairs** (11 intra-footprint) | **56 over 24 pairs** | **0 new, 0 resolved, 0 degraded** |
| `validate_footprints.py` (`lib.pretty`) | 0 errors, 2 warnings | identical | none |
| `validate_footprints.py` (`temper.pretty`) | 0 errors, 0 warnings | identical | none |
| `check_evidence_provenance.py` | PASS — 85 real, 33 allowlisted, 0 violations | PASS | none |
| Courtyard overlaps (geometric) | 11 | 11 | none |
| Courtyards outside `Edge.Cuts` | 2 (C3, U1) | 2 (C3, U1) | none |
| Pads outside `Edge.Cuts` | 0 | 0 | none |
| `ci_check_drc.py` | see Part E | see Part E | no regression |

### The per-pair clearance comparison

Every one of the 56 records was compared as a
`(pair, boundary, insulation, metric)` key with its measured distance:

```
BEFORE: 56 violation records over 24 pairs
AFTER:  56 violation records over 24 pairs

NEW violation records (regressions): 0
RESOLVED violation records:          0
COMMON records that got WORSE:       0
COMMON records that got BETTER:      0

VERDICT: no new violation records, no existing record degraded.
```

Neither C25 nor C26 appears in the violating set before or after. All 114
domain pairs per cap remain ≥ 8.0 mm.

---

## Part E — the DRC ratchet is nondeterministic, and flaky on `main` itself

`ci_check_drc.py` initially reported `shorting_items 200 > 199 (+1)` on the
modified board, which reads as a regression. It is not. **`kicad-cli pcb drc`
does not return a stable result on this board.**

The control: the **same, unchanged, committed** `pcb/temper.kicad_pcb`, run
8 times at `c83f5af9`.

| Category | Ceiling | Baseline × 8 | Modified × 8 | Verdict |
|---|---|---|---|---|
| `clearance` | 502 | 337–343 | 327–340 | noise; modified max ≤ baseline max |
| `shorting_items` | 199 | 152–169 | 149–169 | noise; identical max, lower min |
| `tracks_crossing` | 3 | 2–3 | 2–3 | noise, identical range |
| `courtyards_overlap` | 11 | **11, bit-stable** | **11, bit-stable** | unchanged |
| `solder_mask_bridge` | 154 | 154, bit-stable | 154, bit-stable | unchanged |
| `copper_edge_clearance` | 15 | 15, bit-stable | 15, bit-stable | unchanged |
| `hole_clearance` | 120 | 24, bit-stable | 24, bit-stable | unchanged |
| `annular_width` / `drill_out_of_range` / `hole_to_hole` / `via_diameter` | 4/4/1/4 | bit-stable | bit-stable | unchanged |
| `silk_*`, `lib_footprint_*`, `track_dangling`, `via_dangling`, `missing_courtyard`, `pth_inside_courtyard`, `holes_co_located` | 0 | bit-stable | bit-stable | unchanged |

**18 of 21 categories are bit-stable.** The 3 that vary are exactly the three
that flagged the apparent regression, and in all three the modified board's
range is contained within — or below — the baseline's.

Total violations, same unchanged file, 8 runs: **1470–1493 (spread 23)**.
Modified: **1467–1491**.

Running the real gate repeatedly settles it:

| Board | Gate runs | PASS | FAIL |
|---|---|---|---|
| `c83f5af9`, **unmodified** | 26 | 25 | **1** (`shorting_items 200 > 199`) |
| this branch | 17 | 15 | 2 (`shorting_items 201 > 199`) |

**The unmodified baseline fails the DRC ratchet intermittently.** The
`shorting_items` ceiling of 199 sits inside the run-to-run noise band, so the
gate is flaky on `main` independent of any change. This is a pre-existing
tooling defect, surfaced here, **not fixed here** — fixing it means either
making `kicad-cli` DRC deterministic or making the ratchet sample-and-bound,
both of which are their own change. No ceiling was raised, lowered, or
touched by this branch.

Filed as a follow-up. It is worth taking seriously: a ratchet whose noise band
straddles its own ceiling cannot distinguish a real +1 regression from a
re-run, which is the failure mode this repo's `check_vacuous_gates.py` family
exists to prevent.

---

## Part F — electrical consequence at 47 kHz / ~1.8 kW

### F.1 The tank nets carry no copper today

Direct measurement of `pcb/temper.kicad_pcb`: **zero** track segments and
zero vias on net 22 (`SW_NODE`) or net 153 (`tank.c_tank1-p2`), out of 2338
segments board-wide. Both tank pads on both caps had **0 copper landing on
them** before this change, and have 0 after.

So this move breaks no existing routing. It cannot: there is none. The
`track_dangling` (28) and `via_dangling` (5) DRC categories are bit-stable
across the change, confirming it.

### F.2 Loop geometry

Distances from the tank pads to the half-bridge and the coil:

| Anchor | Before | After | Δ |
|---|---|---|---|
| U6.2 (IGBT high, `SW_NODE`) | 114.84 mm | 110.07 mm | **−4.77 mm** |
| U5.3 (IGBT low, `SW_NODE`) | 210.32 mm | 207.29 mm | **−3.03 mm** |
| R30.1 (Litz coil, tank node) | 135.87 mm | 131.76 mm | **−4.11 mm** |
| C25.1 ↔ C26.1 (`SW_NODE` tie) | 25.52 mm | 24.85 mm | −0.67 mm |
| C25.2 ↔ C26.2 (tank-node tie) | 43.75 mm | **64.31 mm** | **+20.56 mm** |

Four of five shorten slightly. **The tank-node tie grows by 20.56 mm and that
must be stated plainly**, but the decomposition matters:

- **+18.48 mm is inherent to the corrected part.** The pitch goes 27.5 →
  37.5 mm, and the two caps are mounted anti-parallel (C25 rot 180, C26
  rot 0), so their pad-2s point away from each other and the tie grows by
  ~2 × 10 mm. Holding both caps at their *committed* origins with the new
  footprint already gives 62.23 mm.
- **Only +2.08 mm is attributable to this repositioning** (62.23 → 64.31 mm).

The anti-parallel orientation is the real cost driver, and it predates this
change. Re-orienting both caps to the same rotation so pad-1s and pad-2s pair
up would shorten the tie materially — but that is a larger re-place, and per
this repo's R22 bug-triage rule an architectural change is scoped as a
follow-up rather than inlined into a fix. Because the tank nets are unrouted,
the pad positions set only the endpoints; the actual loop area is still fully
determined by routing that has not happened yet. **Recommendation: settle the
tank orientation when the tank nets are routed, not before.**

### F.3 One genuine electrical improvement

The move pulls a foreign-net pad out of a copper pour.

The board carries `SW_NODE` pours on F.Cu and B.Cu (priority 70, 14 082 mm²).

| Pad | Net | Before | After |
|---|---|---|---|
| C25.1 | `SW_NODE` | in pour | in pour |
| C26.1 | `SW_NODE` | in pour | in pour |
| C26.2 | `tank.c_tank1-p2` | outside by 9.74 mm | outside by 12.59 mm |
| **C25.2** | **`tank.c_tank1-p2`** | **INSIDE the `SW_NODE` pour** | **outside by 6.47 mm** |

Before this change, C25.2 — a pad on a *different* net — sat inside the
`SW_NODE` pour, forcing a carved clearance void around a pad carrying the full
resonant current. After, both `SW_NODE` pads remain on their own pour and both
tank-node pads are clear of it. This is consistent with the `clearance`
category's lower minimum in the after-runs (327 vs a baseline minimum of 337).

---

## What is not fixed here

- The 11 pre-existing courtyard overlaps, C3's 7.810 mm and U1's 1.760 mm
  edge overhangs. Board-wide re-place, out of scope.
- `check_isolation_keepout.py`. Still failing, unchanged: no
  `MAINS_SELV_ISOLATION_BARRIER` keepout exists, and CP-SAT proves a barrier
  infeasible on the current component set with K2/K3 as the hard blockers.
- The 56 REQ-SAFE-01 records. Unchanged, per-pair, by construction.
- The flaky DRC ratchet (Part E). Surfaced and quantified; filed, not fixed.
- The anti-parallel tank orientation (Part F.2). Deferred to routing.

No gate was weakened, skipped, or allowlisted. No clearance or creepage
minimum, no entry in `elec/domain_manifest.yaml`, and no DRC ceiling was
modified. The board outline was not enlarged.
