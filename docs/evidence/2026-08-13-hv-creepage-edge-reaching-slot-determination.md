<!-- provenance: commit=96db2ccde669efa82d85fb494d5d152d8af8848f dirty=false (persistent main merge commit #1134 carrying the exact evidence file from merged PR #1194; the measured board commit remains recorded below)
     (own branch analysis/edge-slot-through-cut-rescue, based on origin/fix/board-schematic-resync.
     git status --porcelain clean apart from this document; git grep -l "^<<<<<<< " empty. Own
     git worktree (/home/bennet/Desktop/temper/.claude/worktrees/agent-a374c69e35366ad12), never
     the main checkout. pcb/temper.kicad_pcb sha256=b7d865b7946f55dcc0d907cccbbee12f730fd1878b30
     d417bd56004d1091c1d6, pcb/temper.kicad_pro sha256=f2d90755af04fea40357be3ba2ef94368a01b1afc3
     4c450b42fad0b9e15a51ac -- byte-identical to PR #1152/#1155/#1160/#1163's own recorded
     provenance for this same commit; every figure those documents published for T1/T2/U6
     applies to the exact board examined here. No pcb/temper.kicad_pcb, footprint, DRU
     threshold, or enforced safety constant (HV_CREEPAGE_ENFORCED_MM or otherwise) was edited
     anywhere in this task. No slot was cut. All geometry below was measured with `kiutils`
     (real board S-expression parse, read-only) and a `shapely`+`networkx` visibility-graph
     script reproducing PR #1155/#1160's own method to 4 decimal places before extending it,
     under this session's scratchpad -- never written into `pcb/`. -->

# Does an edge-reaching (through) slot rescue T1/T2/U6, and does it sidestep the island-slot standards question? Geometrically yes for T1 (and contingently T2); geometrically achievable but materially more expensive for U6; the standards question is narrowed to one end, not eliminated, for all three.

## Verdict, up front

| Part | Edge-reaching geometrically possible? | Arm length (courtyard to true board edge) | Extra reroute (arm only) | Creepage figure (unchanged from island baseline) | Standards question | Structural | Verdict |
|---|---|---:|---|---:|---|---|---|
| **T1** | **YES** -- south end, toward left edge (x=20) | 17.96mm | +3 segments / 3 nets | 13.265mm nominal / **12.830mm worst-case** (PASS, +0.230mm) | Narrowed to 1 end (north), not eliminated | Arm: low risk (open-board notch). Within-footprint portion: solder-joint fatigue, unchanged from PR #1160, still unclosed | **VIABLE, recommended over the pure island design** |
| **T2** | Contingent -- same footprint as T1, transfers directly **if placed** | Not evaluable (parked at (100,300), 46mm past the board's own bottom edge, unchanged from PR #1144/#1155) | N/A | Same as T1's, if placed | Same as T1's, if placed | Same as T1's, if placed | **NOT VIABLE TODAY** -- blocked by placement, exactly as PR #1155 found; this document does not change that |
| **U6** | **YES, but costly** -- north end, toward left edge, MUST stay below y=134.91 (only 2.0mm clearance from T1's own slot, a real coordination constraint) | 60.51mm (3.4x T1's) | +15 segments / 9 nets (5x T1's arm-only cost) | 14.85mm nominal / 14.11mm worst-case (unchanged from PR #1155, not independently re-derived here -- see §3.4) | Narrowed to 1 end (south), not eliminated | Arm: NEW, unassessed question (60mm interior cut, board-flatness/warpage during reflow) -- this repo has no FEA capability, same gap PR #1160 already established for T1 | **VIABLE, but the arm's own cost (length, reroute, and a new structural question) may make it a worse trade than accepting the island design's standards risk** |

**The core standards finding, established computationally this session, not just reasoned about**: making ONE end of a bounded slot reach the true board edge does **not** change the governing (worst-case) creepage figure at all, relative to the equivalent island design -- it is bit-for-bit the same number (§2.3 reproduces PR #1160's own minimized-T1 figures, 13.265mm nominal / 12.830mm worst-case, to 4 decimal places, for the edge-reaching variant). What changes is **which end governs**: the edge-open end offers **zero** available creepage path (there is no board past the true edge, on any layer -- this needs no clause citation, it follows from the physical absence of material), so the governing path is forced onto the *other*, still-closed interior end -- which is **exactly PR #1160's own already-flagged, uncited "around a closed interior end" derivation, unchanged**. The credit question is **reduced from two uncertain ends to one**, not eliminated. §2 gives the full argument, including a topological constraint (not previously stated in this repo) for why it cannot go further: reaching the true edge on **both** ends of a slot necessarily cuts the board into two mechanically disconnected pieces, which this task's own hard constraints forbid.

---

## 1. Geometric achievability -- measured against the real board, not assumed

### 1.1 Method

Real footprint courtyard (`F.CrtYd`) bounding boxes, in world frame, were extracted directly
from `pcb/temper.kicad_pcb` for all 168 footprints (`kiutils`, read-only). T1/T2/U6 positions,
rotations, and courtyard AABBs reproduce PR #1155's own cited figures exactly (T1
`(53.21, 148.91, 90deg)`, courtyard `x=[37.96,68.46] y=[136.48,161.34]`; U6
`(85.91, 142.43, 90deg)`, courtyard `x=[80.51,91.31] y=[136.48,148.38]`; T2 still at
`(100.0, 300.0, 0deg)` -- unchanged, still 46mm past the board's own bottom edge (254)).

For each part, a candidate **corridor** (a rectangle spanning from the part's courtyard edge to
each of the four board edges, at the row-direction band the original PR #1155/#1160 island slot
already used) was tested against every *other* footprint's courtyard for overlap. Where the
direct/wide corridor was blocked, a **narrower band** (matching the slot's own real width, not
the full courtyard) was tested, since a real slot only needs to be a few mm wide, not as wide as
the part's whole courtyard -- this materially changes the answer for U6 (§1.3).

### 1.2 T1 (and T2, contingently) -- clear corridor, both row-direction ends, toward the left edge

T1's courtyard sits 17.96mm from the board's own left edge (`x=20`), and 103.54/116.48/92.66mm
from the right/top/bottom edges respectively -- left is unambiguously nearest. A narrow-band
(≈4-8mm) corridor from T1's own slot ends (world `y≈130.5-138.5` at the north end, `y≈159.3-
167.3` at the south end) straight to `x=20` is **clear of every other footprint's courtyard** at
*both* ends. Existing-track conflicts differ sharply by end (checked directly, `Segment`/`Via`
bounding-box overlap against every trace on the real board):

| End | Corridor | Track conflicts |
|---|---|---|
| North (`y≈130.5-138.5`) | 20.0-37.96mm | 7 nets / 14 segments (`SHUTDOWN`, `hb.gate_hs.driver-p1`, `ina`, `power_in.bypass_relay-coil2`, `discharge.k_dis1-nc`, `RTD_SDI`, `inb`) |
| South (`y≈159.3-167.3`) | 20.0-37.96mm | **3 nets / 3 segments** (`discharge.k_dis1-coil2`, `rtd_pan.rail_monitor-outa`, `inb`) |

**South is recommended** -- same 17.96mm reach, 21% of the north option's reroute burden. Neither
option overlaps PR #1155's own within-footprint reroute set (`safety.uvlo_logic.mon-outa`, `y`,
`hb.gate_hs.driver-p2`, `sw` -- all 4 distinct from both arm option's nets), so the south-arm
design's **total** reroute is PR #1155's own 13 segments/4 nets **plus** 3 segments/3 nets = **16
segments / 7 nets**.

T2 shares T1's exact footprint. If T2 is ever placed (PR #1144's UNSAT courtyard-placement
finding is unchanged, re-confirmed directly this session by reading T2's real, committed
position), the identical local geometry transfers -- exactly the same convention PR #1155 already
used for the island design. This document does not solve T2's placement problem and does not
claim to.

### 1.3 U6 -- clear, but only via a narrow band, and only after a real coordination constraint with T1

U6's courtyard is 60.51/80.69/116.48/105.62mm from left/right/top/bottom respectively -- left is
nearest, but **3.4x farther than T1's own distance to the same edge**, because **T1's own
courtyard sits directly between U6 and the left edge** (`T1: x=[37.96,68.46]`, squarely inside
the straight path from `U6: x=[80.51,91.31]` to `x=20`).

A first pass, using the same generous courtyard-height band as T1's check, found U6's westward
corridor **blocked by T1 itself** at both the north (`y≈130.5-138.0`) and south (`y≈147.5-155.0`)
row-direction ends -- and the eastward corridor blocked by six other components (`J2`, `PS1`,
`R28`, `R53`, `U26`, plus more on the south side). **Narrowing the band to U6's own real slot
width (not its full courtyard height) changes this**: T1's courtyard starts at `y=136.48`; U6's
own north-end slot tip (per PR #1155's un-minimized U6 design, half-length 8.5mm from center
`142.43`) sits at `y=133.93` -- **2.55mm north of T1's own courtyard start**. A corridor held
strictly to `y=[128.91, 132.91]` (a 4mm band, 2.0mm clear of T1's own slot start at `y=134.91`,
not just T1's courtyard) is confirmed **clear of every other footprint's courtyard, all the way
to `x=20`** -- 60.51mm.

**This 2.0mm clearance is not free margin -- it is a real, load-bearing coordination constraint**,
not previously flagged anywhere in this repo: U6's own north-end slot and T1's independent slot
geometry sit close enough (U6's arm must cross the full x-range T1 occupies) that a wider or
differently-placed U6 slot could physically **merge** with T1's slot. If that happened, T1's own
slot would gain a *second* edge-contact point (via the merged connection through U6's arm out to
`x=20`) -- and per §2.4 below, touching the true board edge at two separate points on the same
connected void necessarily disconnects a region of the board, which this task's hard constraints
forbid. **The two designs must be built and verified together, not independently** -- a real
finding this document surfaces, not one carried over from PR #1155/#1160 (which never had to
consider two isolators' slots interacting, since neither reached an edge).

Existing-track conflicts in the validated `y=[128.91,132.91]` band: **9 nets / 15 segments**
(`safety.ovp.r_div_top1-p2`, `SHUTDOWN`, `hb.gate_hs.driver-p1`, `ina`,
`power_in.bypass_relay-coil2`, `discharge.k_dis1-nc` (7 of the 15), `RTD_SDI`, `inb`, `sw`) --
none overlapping PR #1155's own U6 reroute set (`safety.uvlo_logic.mon-outa`,
`hb.gate_hs.driver-p2`). **Total U6 reroute: PR #1155's 4 segments/2 nets + this arm's 15
segments/9 nets = 19 segments / 11 nets** -- roughly 5x T1's total.

South (`y≈147.5-155.0`, U6's other row-direction end) remains fully inside T1's own `y`-shadow in
either direction and was not pursued further -- north is U6's only viable edge-reaching option.

### 1.4 Does either design cut a pad or sever an un-reroutable conductor?

No pad is touched in either case -- both corridors are checked against courtyard bounding boxes,
which are a conservative superset of a part's real copper (IPC margin, the same convention PR
#1155 §4.1 used). Every track conflict found (§1.2, §1.3) is an ordinary copper segment on `B.Cu`
or `F.Cu`, reroutable in principle -- none is a via, plane pour, or a segment this document found
evidence of being structurally un-movable. **The reroutes themselves were not executed or proven
geometrically legal** -- same caveat PR #1155/#1160 both carried for their own reroute counts, not
resolved further here.

---

## 2. What the standard actually credits -- read again, not reconstructed

### 2.1 The clause, exactly as PR #1155/#1160 already transcribed it from the primary source (not re-fetched)

IEC 60664-1 clause 4.2 (2002-era text, IS 15382 (Part 1):2003) / clause 6.8 (current 3.0:2020 and
3.1:2025 editions, renumbered but unchanged in content per PR #1160 §2's direct TOC/figure-list
check):

> "Example 1 -- Condition: Path under consideration includes a parallel- or converging-sided
> groove of any depth with a width less than X mm. Rule: Creepage distance and clearance are
> measured directly across the groove as shown."
>
> "Example 2 -- Condition: Path under consideration includes a parallel-sided groove of any depth
> and equal to or more than X mm. Rule: Clearance is the 'line of sight' distance. Creepage path
> follows the contour of the groove."

**All 11 worked examples, in every edition checked (PR #1155's 2002-era read, PR #1160's
3.0:2020/3.1:2025 re-check), are 2D cross-sections of a groove, rib, joint, or screw head that is
implicitly infinite/edge-to-edge in the third dimension** -- none has a rounded or squared *end*
that a creepage path would need to detour around. This project's task frames "an edge-reaching
slot" as matching this literal picture. **That is only exactly true if the groove reaches a
boundary of the relevant surface on *both* sides of the pair being measured** -- which is what
every one of the 11 examples actually draws (the groove's cross-section spans the full width of
whatever object is being sectioned).

### 2.2 What actually changes when one end reaches the true board edge

A PCB slot with one end terminating at the board's real outline is not what any of the 11
examples pictures either -- it is a groove with **one** open end (matching Example 2's premise
along that side) and **one** closed, interior end (the same bounded/island geometry PR #1155/
#1160 already flagged as absent from every edition's worked-example set).

**The open end needs no derivation at all.** Past the board's true physical outline, there is no
FR4, no soldermask, no copper, on any layer -- a "creepage path" is by definition a distance
measured *along a continuous insulating surface*, and no such surface exists past where the board
simply stops. This is not an application of clause 4.2/6.8's groove examples; it is a more basic
fact about what a creepage path requires that the groove examples do not need to establish because
none of their pictured grooves has an edge that just runs out.

**The closed end still needs exactly the derivation PR #1160 already flagged as unresolved.**
Nothing about the other end reaching the true edge changes what happens at the interior end -- it
is still a bounded, island-shaped termination with two real walls and a rounded/square cap, still
not pictured in any of the 11 examples, still the same "path detours around the slot's nearest
end" mechanism PR #1155/#1160 derived (not cited) from the standard's general "most unfavorable
position" (i.e. shortest available path) principle.

**Net effect on the governing (shortest, worst-case) creepage figure: none**, and this is now
verified computationally (§2.3), not just argued. Since a path around the open end does not exist
at all, it can never be the *shortest* available path -- the governing path was always going to be
whichever end offered a valid detour, and in a symmetric island design (PR #1160's own minimized
T1: both ends at the same 14.0mm half-length) both ends already gave the identical number. Opening
one end up removes a redundant tie, not the actual minimum.

### 2.3 Computational verification -- reproducing PR #1155/#1160's own method, then extending it

`shapely`+`networkx` visibility-graph shortest-path search, the same method PR #1155 §2.2/PR #1160
§4.4 used (pad rectangles from the real footprint file, slot as a polygonal obstacle, Dijkstra over
boundary/corner points, interior-crossing test shrunk by 1 micron per PR #1155's own documented
bugfix). **Verification before extension**, exactly as both prior documents required of themselves:

```
PR #1155 island (T1, 28.0x8.0mm):        15.5323mm  [expect 15.532mm]  MATCH to 4 d.p.
PR #1160 minimized island (T1, 28.0x4.0mm): 13.2655mm  [expect 13.265mm]  MATCH to 4 d.p.
```

Then the new geometry: PR #1160's minimized main body (`x_local=[-14,14] y_local=[-2,2]`) plus a
4mm-wide arm turning 90 degrees at the south end (`x_local=[12,16]`) and running out to
`y_local=34.0` -- past the real 33.21mm needed to reach T1's true left edge at world `x=20`
(measured directly, §1.2), with 0.79mm of design margin so the cut fully merges with the board
outline even before fab tolerance is applied:

```
Edge-reaching (nominal):     13.2655mm  (pad2<->pad4[secondary]/pad3 pair)  -- IDENTICAL to
                                                                                PR #1160's minimized
                                                                                island, to 4 d.p.
Edge-reaching (worst-case, ±0.2mm/edge pessimistic, arm shrunk to y_local=33.8,
              still 0.59mm past the true 33.21mm requirement): 12.8296mm  -- matches PR #1160's
                                                                              12.830mm
```

**Diagnostic, confirming the governing-path mechanism explicitly**: `pad1<->pad4`, the pair
nearest the now-open south end, is *forced* onto the long way around the still-closed north end
once the south end offers no path -- **40.91mm**, nowhere near governing. `pad2<->pad3` (nearest
the unchanged north end) remains the minimum at 13.2655mm, exactly as it already was in the pure
island design. This confirms directly, not just by argument, that opening the south end changed
*which* pair governs but not *what number* governs.

### 2.4 A topological constraint this task's own hard constraints impose, stated for the first time in this repo

Could *both* ends reach the true edge, eliminating the closed-end derivation entirely? **No, not
without violating this task's own "does not disconnect a board region mechanically" constraint,
and this is a general fact about the board's shape, not a per-part measurement.** The board
outline is a single simple rectangle (`gr_poly`, 4 vertices, `pcb/temper.kicad_pcb`, confirmed
directly this session -- no existing internal slot or cutout anywhere on the board). Any single
connected cut (straight or curved) whose two ends land at two distinct points on that outline
necessarily separates the outline's enclosed region into two disconnected pieces -- an elementary
consequence of the Jordan curve theorem for a simple arc with both endpoints on the boundary of a
simply-connected planar region, not something specific to this board's component layout. A design
that touches the true edge at only **one** point per connected slot (as both T1's and U6's designs
above do) does not disconnect anything; a design that touches it at two points, for the *same*
connected void, does, unconditionally. **This is why §1.3's 2.0mm T1/U6 coordination clearance is
load-bearing**: if U6's arm merged with T1's slot, the combined void would touch the true edge at
two points (once via each part's own arm), disconnecting the board region between them.

**Consequence for the certification-lab question PR #1160 already drafted (§3.4 of that
document)**: this document does not close it. It sharpens it to a single, symmetric question that
applies identically to whichever end remains closed on either part's design -- exactly PR #1160's
own question, unchanged, now with one fewer path in play. **No creepage credit is claimed here for
the closed end beyond what PR #1160 already flagged as unresolved.** The credit that *is* claimed
(the open end offering zero path) rests on the physical absence of board material past a real,
measured board edge, not on an interpretation of clause 4.2/6.8's worked examples -- and is treated
in §2.3's computation as contributing nothing to the governing figure (consistent with the fact
that it can only ever remove a candidate path, never add a shorter one).

---

## 3. Mechanical consequence

### 3.1 T1 -- arm portion is a new, low-risk, ordinary edge feature; within-footprint risk is unchanged

T1's footprint (`pcb/libs/temper.pretty/CST3015.kicad_mod`, re-confirmed this session) is
SMD-only -- four rectangular pads, no through-hole or standoff feature, matching PR #1160 §4.1's
finding exactly. The **arm** (17.96mm x 4mm, from T1's own slot end at `y≈161-165` straight to the
board's true left edge) sits entirely **outside T1's own courtyard and every other component's
courtyard** (§1.2) -- it is an ordinary edge notch in open board, comparable in scale to routine
PCB features (mounting-hole cutouts, connector notches, panel-breakaway tabs) that do not
routinely receive FEA review on real boards. Qualitative judgment, not measured, consistent with
how PR #1160 §4.3(a) characterized T1's own within-footprint slot as low board-integrity risk.

**The within-footprint portion of the design is bit-for-bit unchanged from PR #1160's own
minimized main body** (`x_local=[-14,14] y_local=[-2,2]`) -- so **the solder-joint thermal-cycling
fatigue question PR #1160 §4.3(b) already identified as the real, open, unclosed risk is
unchanged by this document**. This repo still has zero FEA/structural/mechanical-analysis
capability (PR #1160's exhaustive `docs/`/`scripts/` search, re-confirmed not to have changed
since). **This document does not close that question; it does not need to re-open the search that
already established the gap.**

### 3.2 T2 -- identical to T1's, contingent on placement (unchanged)

Same footprint, same reasoning, same open solder-joint question -- contingent on T2 ever being
placed, exactly as §1.2 already states for the geometry itself.

### 3.3 U6 -- arm portion raises a genuinely new, unassessed structural question

U6's own within-footprint slot remains the same industry-standard, datasheet-recommended
ground-cutout-under-transformer-region technique PR #1155 §3.4 already characterized as low risk
(`HIGH_VOLTAGE_CLEARANCE_SPEC.md` §6.3, UCC21550 datasheet Figure 34). **The arm is materially
different from T1's**: 60.51mm long (versus T1's 17.96mm) -- not a small notch, but an interior
slit running most of the way across a substantial fraction of the board's width, passing close by
(within 2.0mm of) T1's own independent slot. A cut this long, this close to another removed-material
region, plausibly affects the board's flatness/warpage behavior during the reflow oven pass --
uneven thermal expansion across a long thin discontinuity is a real, physically motivated concern,
not a generic "no FEA was done" flag. **This repo has no capability to assess it** (same exhaustive
`docs/`/`scripts/` search PR #1160 already performed, nothing found for warpage/flatness analysis
either). This is a genuinely **new** open item this document surfaces -- distinct from, and in
addition to, T1's already-known solder-joint concern -- not a restatement of PR #1160's finding
under a new label.

---

## 4. Fab constraints

Checked directly against `docs/hardware/FAB_CAPABILITY.md` and
`docs/evidence/2026-08-13-jlcpcb-fab-capability-envelope.md` (PR #1142, pulled into this repo by
PR #1178's `fix/layer-architecture-ssot` branch), plus a direct re-check of JLCPCB's own live
capabilities page this session for the one figure neither prior document needed:

| Parameter | Floor | This design | Margin |
|---|---:|---:|---|
| PD3 groove-width minimum (IEC 60664-1 cl. 4.2/6.8, X) | 1.5mm | 4.0mm nominal / 3.6mm worst-case (main body and arm both) | PASS, 2.4x worst-case |
| Min. non-plated slot width (JLCPCB) | 1.0mm | 4.0mm / 3.6mm | PASS, 3.6x worst-case |
| Min. board-edge-to-copper (routed) | 0.2mm | Same margins PR #1160 already established for the within-footprint portion (0.25-0.45mm nominal); the arm itself carries no copper along its own length | PASS |
| Dimensional tolerance (regular precision) | ±0.2mm/edge | Applied pessimistically throughout §2.3/§4 | -- |
| **Internal (concave) corner radius** | **Not published anywhere found** | -- | **Real, unresolved fab-data gap** |

**The internal-corner-radius gap is new -- neither PR #1155, #1160, nor #1142's own JLCPCB
capability envelope needed it, because a pure island slot's corners are no different in kind from
this design's.** A live re-check of `jlcpcb.com/capabilities/pcb-capabilities` this session found
slot-width and edge-clearance figures (matching FAB_CAPABILITY.md exactly) but **no stated minimum
internal corner radius or CNC routing-bit diameter for non-plated slots**. This matters at exactly
two places in this design: where the arm meets the main body (a concave, ~90-degree interior
corner), and, negligibly, at the main body's own closed end. **This is not a blocking gap**: a
router bit of any real diameter can only *round over* a nominally sharp interior corner, which
only *removes more material* than the idealized rectangle -- strictly safe for creepage (the actual
groove only gets wider at that point, never narrower) and not a concern for the width margins
above (2.4-3.6x the relevant floors). It is a genuine open item for whoever executes the physical
Gerber/G-code geometry (a standard DFM step, not a novel constraint this design introduces), not a
reason to doubt the numbers in this section.

---

## 5. Routing consequence -- quantified, not just flagged

This board's channel utilization is **1.31** on 2 signal layers (PR #1172, cited by PR #1178),
**~0.657** once PR #1178's 6-layer declaration is counted (though PR #1178 itself notes the
router's actual routable-layer set today is still `{F.Cu, B.Cu}` -- the declaration alone does not
yet give the router occupancy-grid support for the new inner layers). Total 2-layer channel
capacity: **8546 mm²** against **11236.6 mm²** of demand (PR #1172's own figures).

A full-depth slot removes routable channel area on every layer it passes through -- both `F.Cu`
and `B.Cu` for this board's outer-layer router today. Treating the arm's footprint area as lost
channel on both layers (a proxy for PR #1172's own methodology, not a reproduction of it -- flagged
as an estimate, not an exact figure):

| Part | Arm dimensions | Arm area (1 layer) | Arm area (2 layers, both removed) | vs. total 2-layer capacity (8546mm²) |
|---|---|---:|---:|---:|
| T1 | 17.96 x 4.0mm | 71.84mm² | 143.68mm² | **1.68%** |
| U6 | 60.51 x 4.0mm | 242.04mm² | 484.08mm² | **5.66%** |

**This is on top of, not instead of, the within-footprint slots' own already-quantified area** (PR
#1160's minimized T1: 112mm²; PR #1155's un-minimized U6: 124.1mm² [`7.30x17.00`]) **and on top of
the reroute burden** (§1.2/§1.3: T1 total 16 segments/7 nets; U6 total 19 segments/11 nets) **on a
board already 31% over channel capacity at 2 layers.** U6's arm alone consumes very roughly 3.4x
T1's proportional share of total channel capacity, for a part that was already the more marginal
of the two on every other axis (arm length, reroute count, and §3.3's new structural question).
**This is a real cost a human should weigh, not a reason by itself to reject the U6 design** -- it
clears every hard geometric/fab/creepage requirement checked in this document.

---

## 6. What this changes and does not change

- **Does not change**: `HV_CREEPAGE_ENFORCED_MM`, any DRU threshold, `pcb/temper.kicad_pcb`, any
  footprint file, `elec/domain_manifest.yaml`, `scripts/measure_cross_domain_creepage.py`, or any
  ratchet ceiling. No slot was cut. No reroute was executed. T2's placement problem is untouched.
- **Does change**: PR #1160's own certification-lab question (§3.4 of that document) is now known
  to survive an edge-reaching redesign, not dissolved by it -- narrowed from two candidate paths to
  one, with the surviving one's creepage figure independently verified (§2.3) to be numerically
  identical to the already-published island design. A new, real coordination constraint between
  T1's and U6's independent slot geometries is surfaced (§1.3/§2.4) that neither prior document had
  reason to consider. A new, U6-specific structural question (§3.3) is surfaced, distinct from
  T1's already-known one. The routing/area cost of the edge-reaching option is quantified for the
  first time (§5), showing T1's version is cheap and U6's is materially more expensive on every
  axis measured.
- **T1's recommendation, if this design is pursued**: south-end arm (17.96mm, 3 extra
  segments/nets), not the north-end option (7 extra nets/14 segments) -- both geometrically clear,
  the south option is strictly cheaper.

---

## 7. What is NOT established here (explicit)

- **No certification-lab confirmation of the remaining closed end's creepage credit, for either
  part.** Exactly PR #1160's own open item, unchanged -- this document narrows which end it applies
  to, not whether it holds.
- **No FEA or physical thermal-cycling/warpage test for either part's design.** T1's solder-joint
  fatigue question is PR #1160's, unchanged. U6's arm-flatness/warpage question is new here, and
  equally unclosed -- this repo has no capability to answer either (PR #1160's exhaustive search,
  re-confirmed, not re-performed from scratch).
- **U6's own creepage figure with the arm was not independently re-derived via the full
  visibility-graph computation** -- only T1's was (§2.3). The topological/governing-path argument
  (§2.2, validated for T1) is extended to U6 analytically, not re-verified numerically; a
  straightforward, low-cost follow-up given §2.3's script already exists.
- **Neither reroute set (T1's 16 segments/7 nets, U6's 19 segments/11 nets) was checked for
  geometric legality** -- same caveat PR #1155/#1160 both carried for their own, smaller reroute
  counts.
- **JLCPCB's internal corner-radius figure could not be found anywhere, including a live re-check
  this session** -- reasoned, in §4, to be non-blocking, but not a sourced number.
- **T1's and U6's arm designs were checked for mutual non-interference (§1.3/§2.4) but the exact
  minimum safe clearance between two such designs was not derived from first principles** -- 2.0mm
  was confirmed sufficient for this specific geometry, not established as a general design rule.
- **PCBWay or another fab's slot-width/tolerance figures were not checked** -- same caveat every
  predecessor document in this chain has carried.
- **The routing-cost quantification in §5 is an area-based proxy, not a reproduction of PR #1172's
  own channel-capacity methodology** -- stated as an estimate, not verified against that tool.

---

## Files

- This document: `docs/evidence/2026-08-13-hv-creepage-edge-reaching-slot-determination.md`
- Extends, does not duplicate: `docs/evidence/2026-08-13-hv-creepage-slot-rescue-t1-t2-u6.md` (PR
  #1155 -- island-slot design, baselines, T2's placement blocker);
  `docs/evidence/2026-08-13-hv-creepage-island-slot-and-t1-structural-determination.md` (PR #1160
  -- the island-slot standards gap, T1's structural narrowing, the minimized-width slot this
  document's own within-footprint geometry reuses exactly); `docs/evidence/2026-08-13-hv-creepage-
  pd3-gap-measurement-and-plan.md` (PR #1152 -- original baselines); `docs/evidence/2026-08-13-
  annex-l-and-ekmq-pulse-current-acquisition.md` (PR #1170 -- confirmed IEC 60335-1:2020 Annex L
  unobtainable; this document does not re-attempt that acquisition); `scripts/measure_cross_
  domain_creepage.py` (not modified; its `body_crossing` wording correction is PR #1163's, not
  duplicated here); `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §6.1 (its "full board width" slot
  model is closer to this document's edge-reaching mechanism than to PR #1155/#1160's island
  model, though its own down-across-up-the-groove formula remains flagged wrong for a full-depth
  slot by the predecessor documents, unchanged here); `docs/hardware/FAB_CAPABILITY.md` and
  `docs/evidence/2026-08-13-jlcpcb-fab-capability-envelope.md` (PR #1142, pulled into
  `fix/layer-architecture-ssot`/PR #1178); `docs/evidence/2026-08-13-layer-architecture-decision.md`
  (PR #1178 -- 1.31/0.657 channel-utilization figures, cited in §5).
- Primary source: IEC 60664-1 clause 4.2/6.8, quoted verbatim from PR #1155/#1160's own direct
  reads (not re-fetched this session, per this task's instruction to build on their work).
- Fetched directly this session: `jlcpcb.com/capabilities/pcb-capabilities` (live re-check for
  internal corner radius only, §4 -- confirmed not published, all other figures matched
  FAB_CAPABILITY.md exactly).
- Measured this session, not committed (scratch, under this session's scratchpad, never written
  into `pcb/`): courtyard/track extraction (`kiutils`), corridor-blocking search, and the
  visibility-graph creepage computation (`shapely`+`networkx`, reproducing PR #1155/#1160's own
  method to 4 decimal places before extending it to the edge-reaching geometry).
