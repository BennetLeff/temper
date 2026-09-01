<!-- provenance: commit=838096820b30ca3999aaa76fffa9ea736c6c89a0 dirty=false -->

# Freeform (non-straight) mains↔SELV barrier: feasibility on the committed placement

**Date:** 2026-08-04
**Board measured:** `pcb/temper.kicad_pcb` at `origin/main` `838096820`
(byte-identical to `28dc960de`, the base of the concurrent
`docs/evidence/2026-08-04-domain-first-resolve-keepout.md` — verified with
`git diff 28dc960de 838096820 -- pcb/temper.kicad_pcb elec/domain_manifest.yaml` = empty).
**Script:** `docs/evidence/scripts/2026-08-04-isolation-barrier-freeform-corridor.py`
(`uv run --no-sync python docs/evidence/scripts/2026-08-04-isolation-barrier-freeform-corridor.py`);
raw numbers in the sibling `.json`.
**Question, per PR #565:** the prior probes searched only *straight* corridors.
The gate requires edge-to-edge + exactly-two-regions, **not straightness**. Does
a non-straight, boundary-following corridor exist that satisfies all six checks
on the committed placement?

**No board file was modified.** `pcb/**`, `power_pcb_dataset/drc_ceiling.json`
and `elec/domain_manifest.yaml` are untouched.

---

## Verdict

**No.** A conforming `MAINS_SELV_ISOLATION_BARRIER` does not exist on the
committed placement — and now for a *different and much narrower* reason than
the prior NO-GO recorded.

| | Verdict | Binding obstruction |
|---|---|---|
| Board **as routed** | **Impossible, for a barrier of any shape** | Routed copper (traces + vias + 96 pours) occupies 31,087 of 35,568 mm² (87.4 %). Every one of the 101 HV copper pads has no admissible HV-side space at all. |
| Committed **placement**, assuming a full re-route | **Impossible, for a barrier of any shape** | **`R24` alone.** Its two HV pads are marooned in the SELV/analog corner; the widest copper-free channel joining them to the other 99 HV copper pads is **5.728 mm**, against the 8.000 mm the barrier needs. **Shortfall: 2.27 mm.** |

The second row is the decision-relevant one, and it is a much better result than
the prior evidence implies: **the placement is one component away from admitting
a conforming barrier**, not a whole-board re-solve away.

---

## 1. PR #565's premise is correct — check 4 does admit non-straight keepouts

Verified directly, not taken on trust. Three synthetic boards were built through
the `kiutils` API and run through the **real gate** (`check_isolation_keepout.run()`),
each barrier being a polyline buffered to 10 mm:

| Barrier shape | Gate state | Violations | Check 4 |
|---|---|---|---|
| `straight-baseline` — single vertical band | `clean` | none | PASSED |
| `serpentine-4-bend` — non-convex, bulges mid-board, 4 bends | `clean` | none | PASSED |
| `boundary-following-pocket` — enters and exits the **same** board edge, cordoning off an edge pocket rather than bisecting | `clean` | none | PASSED |

All three pass **all six checks**, not just check 4. So the admissible search
space is genuinely larger than the straight bands #563 tested: bends,
non-convexity, and cordoning off a pocket (rather than edge-to-edge bisection)
are all legal. #565's insight is sound, and the rest of this document searches
that larger space.

---

## 2. The prior NO-GO (#563) is stale on its own load-bearing input

PR #563's verdict rests on **K3's isolator straddle being −0.5 mm** ("K3 cannot
achieve even the 8.0 mm gate floor; its pad clusters overlap by 0.5 mm"). That
figure no longer describes the board:

- `de59c0458` *feat(pcb): K3 RT314012 swap …* (2026-08-03 17:26) — **not an
  ancestor of `origin/exp/barrier-corridor-feasibility`** (verified with
  `git merge-base --is-ancestor`). #563's branch predates the swap.
- `55226f8ad` *fix(pcb): re-solve placement to clear all 23 placement-fixable
  REQ-SAFE-01 pairs at PD2/8.0 mm (#517)* (2026-07-31) and `27ea686c5` (K2
  RT314012, 2026-08-01) also post-date parts of the prior analysis.

Re-measured on today's `origin/main`, using **exact rotated pad outlines**
(rect / roundrect / circle / oval), for every component carrying copper of both
domains — a barrier must pass between such a component's own two domains:

| ref | HV cu pads | SELV cu pads | gate's circle model (mm) | **exact geometry (mm)** | ≥ 8.0 ? |
|---|---|---|---|---|---|
| C6 | 1 | 1 | 8.0000 | **8.0000** | yes (zero margin) |
| U7 | 5 | 4 | 8.0671 | 8.1000 | yes |
| U3 | 2 | 3 | 8.3322 | 8.5600 | yes |
| T1 | 2 | 1 | 5.9773 | 9.1000 | yes |
| K2 | 4 | 2 | 11.9572 | 12.7600 | yes |
| **K3** | 4 | 2 | 11.9572 | **12.7600** | yes |
| PS1 | 2 | 2 | 34.9768 | 35.5000 | yes |

**K3 measures 12.760 mm, not −0.5 mm** — independently corroborated by the K2/K3
footprint's own `descr` field, which computes "15.26 − 1.5 − 1.0 = 12.760 mm
edge-to-edge" from the RT314012 datasheet. The −0.5 mm figure was an
*axis-projected* cluster gap for a straight axis-aligned corridor, which is the
right measure for a straight band and the wrong one for a freeform corridor.

Board-wide, across all 101 HV × 221 SELV copper pads:

- **Minimum HV↔SELV copper separation = 8.0000 mm** (`C6.1` PWR_RTN ↔ `C6.2` gnd).
- **Zero pairs below 8.0 mm.** Next closest: `U7.9`↔`U7.8` at 8.100 mm.

Prior docs recorded 2.115 mm (2026-07-28) and 0.178 mm (2026-08-01) as the
nearest cross-domain pair. Those are stale: `#517`'s re-solve was explicitly
aimed at this and achieved it. **The placement now meets the 8.0 mm pairwise bar
exactly.**

Two measurement caveats worth carrying forward:

- **K1 has no HV copper.** `K1.13` and `K1.14` (the Faston contact tabs) are
  declared on `F.Fab` only — zero copper on any layer. The gate's check 5
  correctly skips them; **check 6 does not**, and still requires them on the HV
  side. They are excluded from the impossibility proofs here (a copper-free pad
  may legally fall inside the barrier, where `_side_of` returns `None` and drops
  it), but the asymmetry between checks 5 and 6 is worth a look — *not* changed
  here, since the gate is behaving correctly on everything it is being asked.
- The gate models every pad as its **circumscribing circle**. That is the right
  conservative choice for an intrusion test, but it over-states elongated pads:
  it reports T1 at 5.977 mm where the true geometry is 9.100 mm, and it was the
  sole reason an earlier pass of this analysis wrongly flagged T1 and K1 as
  blockers. Both models are reported above; neither changes the verdict.

---

## 3. Method — a shape-independent impossibility test

The results below do not depend on searching candidate polygons.

Let `C` be the union of all copper on all layers (check 1 makes the barrier span
every copper layer, so copper anywhere obstructs it) and `F` the copper-free
region. A conforming barrier `B` satisfies `B ⊆ F` (check 5) and is ≥ 8.0 mm wide
everywhere (check 3's stated contract), formalised the standard way: `B` is a
union of discs of radius 4.0 mm.

**Test 1 (Part B).** Every such disc lies in `F`, so `B ⊆ O := opening(F, 4 mm)`
— the union of *all* 8 mm-inflatable copper-free regions — for every barrier of
every shape. Hence `board \ O ⊆ board \ B`. If an HV copper pad and a SELV copper
pad share a connected component of `board \ O`, that component is a connected
subset of `board \ B`, so they are on the *same* side of every conforming
barrier, and check 6 fails universally.

**Test 2 (Part C).** Checks 4 and 6 together demand **one** region holding every
HV copper pad. The HV region may occupy, at most, `K = {points ≥ 4 mm from all
copper}` (the barrier's centreline must live there) plus any blob of the
remaining space carrying **no SELV copper** (absorbing an HV-only or
unclassified-only blob into the HV region is legal). If the HV copper pads fall
into two or more connected components of that maximally permissive space, no
conforming barrier exists: the stranded pads cannot share a region with the
rest, and cannot sit inside the barrier either (check 5 forbids copper there).

Both tests are conservative in the safe direction — the ambient is the board
outline *expanded by 50 mm*, so barriers that leave and re-enter the outline are
allowed; buffers use 64 segments/quadrant; connected components use Shapely's
decomposition, which splits point-touching regions apart and so makes "same
component" harder to trigger. Test 2 is run at two raster resolutions (0.40 mm
and 0.25 mm) and the verdicts must agree.

---

## 4. Results

### 4.1 Board as routed — impossible, any shape

Obstacles: 2,338 traces + 48 vias + 96 pours + 525 pads. Copper covers
**31,087 mm² of the 35,568 mm² board (87.4 %)**.

| corridor width | 8 mm-inflatable free space in board | regions of `board \ O` | mixed-domain regions |
|---|---|---|---|
| 8.00 mm | 2,537.7 mm² | 3 | **1** |
| 4.00 mm | 3,307.2 mm² | 7 | 1 |
| 1.00 mm | 4,293.5 mm² | 20 | 1 |

One region of `board \ O` holds **97 HV and 218 SELV copper pads at once**.
Test 2 agrees and is blunter: at 0.25 mm raster, **all 101 HV copper pads have no
admissible HV-side space at all**. The verdict does not change even if the
required width is dropped to 1 mm — recorded to show the obstruction is
structural, **not** an argument for lowering `MIN_BARRIER_WIDTH_MM`.

This corroborates, by an independent method, the concurrent finding in
`docs/evidence/2026-08-04-domain-first-resolve-keepout.md` that the pours alone
foreclose checks 4+5.

### 4.2 Committed placement, assuming a full re-route — impossible, and `R24` is why

Obstacles: the 525 pads only (exact rotated outlines). Copper covers 1,284 mm²
(3.6 %).

Test 1 **passes** at 8.0 mm: 103 regions, **zero** mixed-domain regions. So the
pads *are* separable by some subset of the 8 mm-inflatable free space — the
pairwise bar is met, exactly as `#517` intended. This is a real change from the
prior evidence and is why the straight-corridor NO-GO does not settle the
freeform question.

Test 2 **fails**, identically at both raster resolutions:

```
reroutable   cell=0.40mm: HV copper reachability -> SPLIT into 2
    STRANDED: 2 HV pad(s) ['R24.1', 'R24.2']
reroutable   cell=0.25mm: HV copper reachability -> SPLIT into 2
    STRANDED: 2 HV pad(s) ['R24.1', 'R24.2']
```

`R24` is the half-bridge high-side gate resistor:

| pad | position (mm) | net | domain |
|---|---|---|---|
| `R24.1` | (32.305, 21.240) | `hb.power_loop.q_high-g` | HV |
| `R24.2` | (30.655, 21.240) | `SW_NODE` | HV |

It sits in the **top-left corner** (1.24 mm from the `y = 20` board edge),
surrounded by the current-sense / RTD / IO cluster:

| distance | neighbour | domain | net |
|---|---|---|---|
| 8.510 mm | `C28.2` | SELV | `gnd` |
| 8.568 mm | `C28.1` | unclassified | `I_SENSE` |
| 8.742 mm | `C18.2` | SELV | `gnd` |
| 8.837 mm | `R37.1` | SELV | `RTD_CS_N` |
| 9.186 mm | `C18.1` | unclassified | `ina` |

Every one of those clears 8.0 mm individually — `R24` passes the *pairwise*
clearance bar. What it fails is *connectivity*: the barrier must leave `R24` on
the same side as the other 99 HV copper pads, and the widest copper-free channel
back to them is too narrow to carry an 8 mm corridor along both its flanks.
Bisecting on corridor half-width (0.20 mm raster):

| corridor width available to reach `R24` | HV reachability |
|---|---|
| ≥ 6.00 mm | split — `R24` stranded |
| **5.728 mm** | **threshold** |
| ≤ 5.00 mm | connected |

**Widest available channel: 5.728 mm. Required: 8.000 mm. Shortfall: 2.27 mm.**

`R24` also looks misplaced on its own terms: its net `hb.power_loop.q_high-g` is
shared with `R23` at (44.68, 115.35) and `U5` at (23.72, 233.25) — the
half-bridge high-side gate drive is scattered across the full 234 mm board
height, and `R24` is the copy that ended up in the analog corner.

---

## 5. Minimum change that would admit a conforming barrier

State plainly, because it is much smaller than the prior evidence implies:

1. **Move `R24`** out of the current-sense/RTD corner and into the HV cluster —
   or widen the channel to it by ≥ 2.27 mm. This is the *only* connectivity
   blocker in the re-routable model; the other 99 HV copper pads are already one
   connected reachable set. Its net-mates (`R23`, `U5`) suggest where it belongs.
2. **Re-route, including re-pouring.** §4.1 is unconditional: the committed
   copper forecloses the barrier regardless of placement, and the four big power
   pours are the dominant term. A keepout must be placed *before* the pour, not
   carved out after.

Item 1 is a single two-pad component. Item 2 is the larger cost, and it is
unavoidable on any path to this gate going green.

**Not proposed, and deliberately not done:** lowering `MIN_BARRIER_WIDTH_MM`,
relaxing any of the six checks, or "fixing" the gate. 8.0 mm is a reinforced
creepage figure for the voltage/pollution class; the 2.27 mm shortfall is a
placement defect, not a case for a 5.73 mm barrier. The gate is behaving
correctly and should stay red until the board earns green.

---

## 6. Relationship to the open PRs

| PR | Status after this analysis |
|---|---|
| **#551** (floorplan re-solve plan) | Its premise ("all 14 full-height columns mix HV and SELV") is about *straight* full-height columns and remains true, but it is no longer the binding constraint. The re-solve it proposes is far larger than what §5 shows is needed. Its "nearest HV↔SELV pad 1.372 mm, 24 pad pairs within 8 mm" is **stale**: the current board's minimum is 8.0000 mm with zero pairs below. |
| **#562** (probe requirements) | Satisfied; the probe ran. |
| **#563** (straight-corridor CP-SAT NO-GO) | **Stale on its load-bearing input.** Its K3 straddle (−0.5 mm) was removed by `de59c0458`, which is not in its branch. K3 now measures 12.760 mm. Its NO-GO should not be cited as settling the freeform question — it never tested one. |
| **#565** (re-scope; "the gate does not require straightness") | **Premise verified** (§1). Its proposed second probe (polyline corridor, ≤ 25 mm budget) is now unnecessary in that form: §4.2 answers the freeform question directly and identifies a single-component fix, which is well inside any 25 mm budget. |

---

## UNVERIFIED / limits of this analysis

- Check 3 as *implemented* tests only that `barrier.buffer(-4.0)` is non-empty —
  strictly weaker than its docstring's "≥ 8.0 mm at its narrowest". This analysis
  uses the **stricter, documented** reading (barrier = union of 4 mm discs);
  under the weaker implemented reading a barrier with one fat lobe and a thin
  neck would pass. Flagged, not exploited, and not changed.
- Check 6 includes copper-free pads (`K1.13`, `K1.14`) that check 5 excludes.
  Those two pads are excluded from the impossibility proofs; nothing here depends
  on them.
- Test 1 and Test 2 are both **necessary** conditions. Both fail, so the
  impossibility verdicts are sound. The converse is not claimed: if `R24` moves,
  Test 2 would pass, but *sufficiency* — that a single connected polygon then
  exists leaving exactly two regions — is **not** established here. A
  minimum-length planar min-cut over the re-routable model does find a finite
  separating curve (shortest such curve ≈ 1,273 mm at 0.3 mm raster), but the
  minimum-*length* cut cordons off 4 HV and 12 SELV territories rather than
  bisecting, and no construction tried here reached exactly two regions. Treat
  §5 item 1 as necessary, not proven sufficient.
- Raster resolution 0.25–0.40 mm; the `R24` verdict agrees at both, and the
  channel-width bisection was run at 0.20 mm. The 8.0000 mm `C6` figure is exactly
  at the floor, so any future analysis at coarser resolution will spuriously
  block there.
- The IEC 60335-1 / 60664-1 provenance of the 8.0 mm figure is unchanged and
  still carries the UNVERIFIED-at-primary caveat recorded in
  `docs/evidence/2026-07-28-isolation-keepout.md`.
