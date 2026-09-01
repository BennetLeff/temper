<!-- provenance: commit=96db2ccde669efa82d85fb494d5d152d8af8848f dirty=UNKNOWN -->
     dirty=false throughout (git status --porcelain clean apart from this document; git grep -l
     "^<<<<<<< " empty). Own git worktree (/home/bennet/Desktop/temper-slot-creepage-eval, branch
     analysis/slot-creepage-rescue), never the main checkout. pcb/temper.kicad_pcb
     sha256=b7d865b7946f55dcc0d907cccbbee12f730fd1878b30d417bd56004d1091c1d6, pcb/temper.kicad_pro
     sha256=f2d90755af04fea40357be3ba2ef94368a01b1afc34c450b42fad0b9e15a51ac -- byte-identical to
     PR #1152's own recorded provenance for this same commit, so every figure PR #1152 published
     (T1/T2 9.100mm, U6 8.100mm) applies to the exact board measured here. Extensions rebuilt in an
     isolated .venv (`make venv-isolate`, after `unset CONDA_PREFIX`); `scripts/check_stale_
     extensions.py` reported 10/10 fresh, and every extension surface used below (temper_placer's
     pin_geometry/pad_geometry/kicad_parser bindings) was independently confirmed to import and run
     -- freshness alone is not trusted per this session's own environment brief. `make netlist` was
     run in this worktree against its own origin/fix/board-schematic-resync base -- exit 0, build
     complete. No pcb/temper.kicad_pcb, footprint, DRU threshold, or enforced safety constant
     (HV_CREEPAGE_ENFORCED_MM or otherwise) was edited anywhere in this task -- every measurement
     below reads the real, unmodified board; every candidate slot geometry is a scratch-computed
     rectangle evaluated in Python, never written into pcb/. -->

# Do routed slots rescue T1/T2/U6's PD3 reinforced-creepage shortfall? Yes for U6 and T1's own geometry; T2 remains blocked by a placement problem a slot cannot touch.

## Verdict, up front

1. **The groove-width rule is real, re-verified from the primary source this session, and both
   candidate slots clear it by 4.6x-5.3x even under pessimistic fab tolerance.** IEC 60664-1 (2002) clause 4.2 (via IS 15382 (Part 1):2003,
   its identical Indian national adoption) sets the minimum groove width `X` at **1.5mm for
   pollution degree 3** -- fetched and read directly this session (`https://law.resource.org/pub/in/bis/S05/is.15382.1.2003.pdf`,
   pages 42-43 of the extracted text; §1 below quotes it in full). Every slot this document designs
   is 7.3-8.0mm wide -- 4.6x-5.3x the PD3 floor even under pessimistic fab tolerance. This is not
   the binding constraint for any of the three
   parts.
2. **U6 is geometrically VIABLE.** A 7.30 x 17.00mm slot cut through U6's own footprint (TI
   UCC21550BDWKR, `lib:SOIC16W_Isolated`) raises its governing creepage from the measured baseline
   **8.100mm** (reproducing PR #1152 exactly) to **14.85mm nominal / 14.11mm worst-case** under
   JLCPCB's own dimensional tolerance -- both clear 12.6mm with real margin. Real board clearance to
   U6's nearest neighbors (T1 at 12.05mm, J2 at 8.0mm) comfortably accommodates the slot. **Real,
   bounded cost found and reported, not hidden:** 4 existing routed track segments (2 nets) on
   `B.Cu` currently run through the slot's footprint and would need local rerouting first.
3. **T1's own footprint geometry is ALSO viable, independently established here for the first
   time** (this repo's prior work on T1/T2 measured the 9.100mm baseline and searched for a better
   *part*; it did not design a slot for this footprint). A 28.0 x 8.0mm slot raises T1's governing
   creepage from **9.100mm** to **15.53mm nominal / 14.83mm worst-case**, both clearing 12.6mm, and
   fits within T1's real, measured clearance to its nearest neighbors (R6 at 8.0mm, C17 at 16.4mm).
   **Real, bounded cost found:** 13 existing track segments (4 nets) on `B.Cu` run through the
   slot's footprint and would need rerouting. **Real, unresolved cost also flagged:** the slot
   removes board material directly beneath the center of a 23x30mm current-transformer body; no
   structural/FEA analysis was performed, and this is a materially heavier part than U6's SOIC IC.
4. **T2 is NOT rescued by this -- not because the creepage geometry fails (it's identical to T1's,
   same part, same footprint, same answer), but because T2 has no board location at all today.** A
   parallel, independent effort (PR #1144, re-verified in
   `docs/evidence/2026-08-13-ocp02-unplaced-subsystem-options.md`) already proved T2 (with C37/R65)
   UNSAT under pure courtyard geometry alone against the current, frozen 165-component layout --
   T2 sits parked off the board outline at `(100.0, 300.0)` in the real, committed file. A slot adds
   an *additional* ~28x8mm keepout-clear requirement around wherever T2 would sit -- strictly harder
   to satisfy than the bare-courtyard placement already proven impossible. **This document does not
   change T2's status: it is still blocked, by a different, prior problem a slot does not address.**
5. **One standards-interpretation question is not fully closed, and this document says so plainly
   rather than papering over it.** IEC 60664-1 cl. 4.2's own worked examples (all 11, read in full
   this session) describe an infinite-cross-section groove/rib/joint (a 2D profile), never a
   bounded, island-shaped through-slot with two ends sitting entirely beneath a component's own
   body. The "path detours around the slot's nearest end, on the exposed board surface past the
   part" mechanism this document (and a prior sibling document,
   `docs/evidence/2026-07-28-isolator-creepage-slots.md`) relies on is a **physically-reasoned,
   derived extension** of the standard's stated contour principle (§5 below gives the reasoning in
   full), not a literally-pictured case. It is consistent with documented industry practice
   (isolator-IC application notes route a trace around a slot's rounded end on the top copper
   layer) and with a real mechanism (the board material is genuinely absent there -- a creepage
   current has nothing solid to bridge along through the void), but it has not been checked against
   a certification lab's own interpretation of a bounded slot. **This is flagged, not resolved, in
   both this document and its predecessor.**

| Ref | Baseline (no slot) | Slot design | Nominal w/ slot | Worst-case w/ slot | vs 12.6mm | Physical fit | Existing routing conflict | Verdict |
|---|---:|---|---:|---:|---|---|---|---|
| **U6** | 8.100mm | 7.30 x 17.00mm | 14.85mm | 14.11mm | PASS (+1.51mm worst-case) | Fits, generous margin | 4 segments / 2 nets, `B.Cu` | **VIABLE** |
| **T1** | 9.100mm | 28.0 x 8.0mm | 15.53mm | 14.83mm | PASS (+2.23mm worst-case) | Fits, real margin | 13 segments / 4 nets, `B.Cu` | **VIABLE, with caveats** (reroute + unverified structural risk under a 23x30mm CT body) |
| **T2** | 9.100mm (same footprint) | identical to T1's | identical to T1's | identical to T1's | would PASS *if placed* | **N/A -- no placement exists** (off-board at 100,300; courtyard-UNSAT per PR #1144) | not evaluated (moot) | **NOT VIABLE TODAY** -- blocked by placement, not creepage |

---

## 1. The groove-width rule, re-verified from the primary source this session

`docs/evidence/2026-07-28-isolator-creepage-slots.md` (a sibling document on a different,
not-yet-merged branch of this repo, `feat/provable-safety-place-and-route` @ `b1499a16`, commit
`d14c365c5`) already fetched and quoted IS 15382 (Part 1):2003 = IEC 60664-1 (2002) clause 4.2 for
an earlier pass at U6/U3 (called `U7`/`U3` there, before this board's refdes renumber). Rather than
citing that quote at second hand, this session re-fetched the same primary source directly:

```
$ WebFetch https://law.resource.org/pub/in/bis/S05/is.15382.1.2003.pdf
$ pdftotext -layout <fetched PDF> -> 4538 lines (matches the sibling document's own "4536 lines"
  figure closely; the 2-line difference is pdftotext version/whitespace noise, not a different
  document -- same URL, same PDF, re-extracted independently)
```

Page 42 (clause 4.2), read directly this session, quoted verbatim:

> "The dimension X, specified in the following examples, has a minimum value depending on the
> pollution degree as follows:
>
> | Pollution degree | Dimension X minimum value |
> |---|---|
> | 1 | 0,25 mm |
> | 2 | 1,0 mm |
> | 3 | 1,5 mm |
>
> If the associated clearance is less than 3 mm, the minimum dimension X may be reduced to one
> third of this clearance."

And the two governing worked examples, same clause, page 42-43:

> **Example 1** -- "Condition: Path under consideration includes a parallel- or converging-sided
> groove of any depth with a width less than X mm. Rule: Creepage distance and clearance are
> measured directly across the groove as shown."
>
> **Example 2** -- "Condition: Path under consideration includes a parallel-sided groove of any
> depth and equal to or more than X mm. Rule: Clearance is the 'line of sight' distance. Creepage
> path follows the contour of the groove."

And the general principle used throughout this document's search method (same clause, page 42):

> "creepage distances and clearances measured between parts which can assume different positions in
> relation to each other, are measured when these parts are in their most unfavorable position."

**This board's working voltage (MAINS 340V pk, DC bus 400V pk/transient, Gate Drive Isolated 355V
peak-to-earth) is >250-<=400V, and PD3 is the figure that governs today**
(`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md:174,183`, PR #1152's §1.2, re-confirmed unchanged this
session -- `scripts/check_pd2_compartment_evidence.py` still fails, PD2's sealed-compartment
precondition still unmet). **X minimum at PD3 = 1.5mm.** Every candidate slot below (7.3-8.0mm wide)
clears this by 4.6x-5.3x worst-case; groove-width legitimacy is not what could kill this option for any of the three
parts.

**All 11 of clause 4.2's worked examples were read this session, not just Examples 1-2** (a
completeness check the predecessor document flagged as unperformed). None pictures a bounded,
finite, island-shaped cutout with two ends -- every example is a 2D cross-section of an
effectively-infinite-length groove, rib, joint, or recess. §5 below addresses what this does and
does not license for the actual slot geometry this document designs.

---

## 2. Method

### 2.1 Pad geometry -- re-derived and independently verified against PR #1152/#1146's figures

Local-frame (footprint-relative, rotation/translation-invariant) pad rectangles were extracted
directly from the real, current `pcb/temper.kicad_pcb` S-expression blocks for `T1`, `T2` (both
`temper:CST3015`, byte-identical footprint definitions), and `U6` (`lib:SOIC16W_Isolated`).

**Rotation convention, resolved the way `scripts/measure_cross_domain_creepage.py`'s own docstring
already establishes and this session independently confirmed by reproduction:** a pad's stored
`(at x y angle)` `angle` in this file is its ABSOLUTE world orientation, not an offset added to the
parent footprint's own placement angle. For LOCAL, footprint-relative geometry (what a slot design
needs -- it must be placement/rotation-independent, since T2 has no placement at all), the pad's
rotation *relative to the footprint's own unrotated frame* is `stored_absolute_angle -
footprint_placement_angle`. For T1/T2 and U6, the footprint's own placement angle is 90 degrees and
every relevant pad's stored angle is also 90 degrees, so **local pad rotation = 0** for all of them
-- their pads are axis-aligned in the footprint's own frame, not rotated within it.

**Verification, not assumption:** computing the governing (minimum) primary-to-secondary pad-edge
distance with this local geometry and zero rotation correction reproduces PR #1152's canonical
kernel figures exactly:

```
CST3015 (T1/T2) governing pair (pad1<->pad4, local frame): 9.1000mm
U6 governing pair (pin3<->pin14, local frame):              8.1000mm
```

Both match PR #1152's Rust-backed `pad_pair_distance`/`pin_world_position` kernel results to 4
decimal places (§3.2 of that document). This is the same independent-reproduction discipline PR
#1152 itself used against PR #1146.

### 2.2 Slot design -- visibility-graph shortest path, the same method a prior sibling document
### already established and computationally verified

`docs/evidence/2026-07-28-isolator-creepage-slots.md` §4.1 designed slots for U6's *predecessor*
footprint state (called `U7` there, different pad pitch/count than the current board) using: model
each pad as a rectangle, model the candidate slot as a rectangular obstacle, build a visibility
graph over the pads' boundary points and the slot's 4 corners, prune any edge whose segment crosses
the slot's interior, run Dijkstra for the shortest path between every primary-secondary boundary
point pair, and report the minimum over all pairs (the standard's own "most unfavorable position"
principle, §1 above). This document reimplements that exact method (`networkx` for the graph,
`shapely` for interior-crossing tests) against the CURRENT board's real pad geometry, verified with
a no-slot sanity check first (§2.1) and then applied to T1, T2, and U6.

**A silent bug was found and fixed during this reimplementation, reported for transparency:** an
early version's interior-crossing test flagged any segment merely *grazing* the slot's boundary
(e.g., running exactly along one edge, or touching a corner) as blocked, which made every slot wider
than the pin span report `creepage=inf` (no path found) -- an obviously-wrong result caught by the
"a slot should only ever help or do nothing, never disconnect the pads entirely" sanity check. Fixed
by testing intersection against the slot polygon's *interior* (shrunk by 1 micron), matching the
precedent document's own stated rule ("a segment that can validly graze a corner is kept, one that
would cut through the slot's interior is removed"). All numbers in §§3-5 are from the corrected
version.

### 2.3 Fabrication and board-edge data

- **Groove-width floor:** IEC 60664-1 cl. 4.2, PD3, X=1.5mm (§1).
- **Fab minimum non-plated slot width:** 1.0mm, `docs/hardware/FAB_CAPABILITY.md` row 5d (PR #1142,
  sourced from JLCPCB's own capabilities page, fetched 2026-08-13). Not the binding constraint for
  any design below (all are 7.3mm+).
- **Fab dimensional tolerance:** JLCPCB regular precision, ±0.2mm/edge (same document, and the same
  figure the predecessor slot document used for its own worst-case model). Applied pessimistically
  throughout -- every edge assumed to move the wrong way simultaneously, never assumed to cancel.
- **Fab minimum board-edge-to-copper (routed):** >=0.2mm, same source. Used as the minimum
  acceptable slot-to-pad copper clearance.
- **Board:** 1.6mm thick, 4 copper layers (F.Cu, In1.Cu, In2.Cu, B.Cu -- `pcb/temper.kicad_pcb`'s
  own `(general (thickness 1.6))` and `(layers ...)` blocks, read directly). A full-depth slot
  removes all 4 layers' worth of material in its footprint, consistent with the "no floor" model
  (§5) and with `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §6.1's own "Depth: Full board thickness"
  slot parameter.
- **Real neighbor clearances:** measured directly from `pcb/temper.kicad_pcb`'s real component
  positions/rotations via `kiutils`, courtyard-layer (`F.CrtYd`) world-frame bounding boxes for
  every footprint on the board, nearest-neighbor search in the direction each candidate slot needs
  to extend.
- **Existing routing conflicts:** every `Segment`/`Via` in `pcb/temper.kicad_pcb`'s trace list whose
  world-frame bounding box overlaps a candidate slot's world-frame bounding box, reported by layer
  and net name (via `board.nets`).

---

## 3. U6 (TI UCC21550BDWKR, `lib:SOIC16W_Isolated`) -- VIABLE

### 3.1 Geometry and slot design

Local frame: primary pins (1-8) at local x=-4.875, secondary pins (9,10,11,14,15,16 -- 12/13 don't
exist on the DWK package) at x=+4.875, both rows spanning local y=[-4.445,+4.445] on a 1.27mm pitch.
Pad size 1.65 x 0.6mm, local rotation 0. Governing baseline pair: pin3<->pin14 (both at y=-1.905),
**8.1000mm**, reproducing PR #1152 exactly (§2.1).

Candidate slot (local frame, centered on the footprint origin): **x=[-3.65,+3.65], y=[-8.5,+8.5] --
7.30mm wide x 17.00mm long.** The 7.30mm width leaves 0.40mm nominal copper clearance to each pad's
inner edge (pad inner edge at x=∓4.05); the 17.00mm length extends the slot's ends well past the
outermost pin (y=±4.445) and past the package body's own F.Fab outline (y=[-5.15,5.15]) into
genuinely exposed board.

| Check | Nominal | Worst-case (±0.2mm/edge, pessimistic) | Requirement | Result |
|---|---:|---:|---|---|
| Governing creepage with slot | 14.85mm | 14.11mm (slot shrinks) | >=12.6mm | **PASS**, +1.51mm worst-case margin |
| Slot-to-pad copper clearance | 0.40mm | 0.20mm (slot grows toward pad) | >=0.2mm (JLCPCB) | **PASS**, exactly at the floor in the worst case |
| Groove width (IEC cl. 4.2 legitimacy) | 7.30mm | 6.90mm | >=1.5mm (PD3) | **PASS**, 4.9x floor nominal / 4.6x worst-case |
| Fab min. non-plated slot width | 7.30mm | 6.90mm | >=1.0mm | **PASS**, 7.3x floor nominal / 6.9x worst-case |

The copper-clearance worst-case sitting exactly at JLCPCB's own 0.2mm floor (not above it) is a real,
zero-margin condition -- a production design would want either a slightly narrower slot (with a
correspondingly smaller creepage margin, still comfortably >12.6mm at 7.10mm-worst-case width per
the table) or a design-for-manufacture review before committing to exactly 3.65mm half-width.

### 3.2 Physical room

U6 sits at `(85.91, 142.43, 90deg)`. Real courtyard-to-courtyard gaps to its nearest neighbors:
**T1 at 12.05mm** (toward the slot's local +y end) and **J2 at 8.0mm** (toward local -y). The slot's
17.00mm length only needs to reach 3.10mm past U6's own courtyard edge on each side (courtyard
half-length 5.4mm vs. slot half-length 8.5mm) -- both ends land with **8.95mm spare before T1's
courtyard and 4.90mm spare before J2's courtyard.** Room is not a binding constraint here.

### 3.3 Existing routing conflict -- real, bounded, not evaluated further

4 track segments, 2 nets, both on `B.Cu`, currently route through the slot's world-frame footprint
(`x=[77.41,94.41], y=[138.78,146.08]`): `safety.uvlo_logic.mon-outa` (3 segments) and
`hb.gate_hs.driver-p2` (1 segment -- U6's own pin-14 net, plausible given it has to leave the
package somewhere nearby). These would need local rerouting before the slot could physically be
milled. Not attempted here (out of this task's scope -- evaluate and specify, not execute); a
bounded, ordinary place-and-route task, not a structural blocker.

### 3.4 Structural consideration

U6 is a 16-lead SOIC-W IC (~7.5 x 10.3mm body), light, with leads distributed along both long edges
rather than concentrated at a few large pads. Removing board material in the strip between its two
pin rows is **already the industry-standard, explicitly-recommended layout technique for this exact
class of part** -- `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §6.3 already states "Ground plane
cutout under transformer region (center of package); Per UCC21550 datasheet Figure 34 layout
recommendation" for this specific device, and a parallel recommendation for the ADUM1250. Low
structural risk, consistent with established practice already documented in this repo (not a new
claim invented for this document).

**Verdict: VIABLE**, subject to (a) the reroute of 2 nets/4 segments, and (b) the general
standards-interpretation caveat in §5, common to all three parts.

---

## 4. T1 (Coilcraft CST3015, `temper:CST3015`) -- VIABLE, with caveats

### 4.1 Geometry and slot design

Local frame: primary pads (1,2) at local y=-6.85 (x=±7.68, size 9x4.8mm), secondary pads (3,4) at
local y=+6.95 (x=∓6.88, size 3x4.6mm), local rotation 0 for all four. Governing baseline pair:
pad1<->pad4 (and mirror pad2<->pad3), **9.1000mm**, reproducing PR #1152/#1146 exactly.

Unlike U6 (8 pins per side, spread along the row direction), CST3015 has only 2 pads per side, and
the primary pads already span nearly the component's *entire* width (x=[3.18,12.18] and
[-12.18,-3.18] against a courtyard half-width of only 12.43) -- there is almost no free board
between the outermost primary pad edge and the courtyard boundary (0.25mm, the standard IPC
courtyard margin, not extra room). A slot therefore has to extend **past the component's own
courtyard**, not just past its pins, to reach genuinely exposed board.

Candidate slot (local frame): **x=[-14.0,+14.0], y=[-4.0,+4.0] -- 28.0mm long x 8.0mm wide,**
centered in the primary/secondary gap (0.45mm clearance from the primary row's inner edge, 0.65mm
from the secondary row's).

| Check | Nominal | Worst-case (±0.2mm/edge) | Requirement | Result |
|---|---:|---:|---|---|
| Governing creepage with slot | 15.53mm | 14.83mm (slot shrinks) | >=12.6mm | **PASS**, +2.23mm worst-case margin |
| Slot-to-pad copper clearance | 0.45mm / 0.65mm | 0.25mm / 0.45mm (slot grows) | >=0.2mm | **PASS** |
| Groove width (IEC cl. 4.2 legitimacy) | 8.0mm | 7.6mm | >=1.5mm (PD3) | **PASS**, 5.3x floor nominal / 5.1x worst-case |
| Fab min. non-plated slot width | 8.0mm | 7.6mm | >=1.0mm | **PASS**, 8.0x floor nominal / 7.6x worst-case |

Precisely at the component's own courtyard edge (slot half-length 12.43mm, exactly matching the
courtyard), creepage lands at 12.617mm -- technically over 12.6mm nominally but with essentially
zero margin and a worst-case figure that would fail. The 14.0mm half-length above was chosen
specifically to clear the worst-case fab tolerance with real margin, at the cost of extending
1.57mm past the component's own courtyard boundary on each end (into real, measured, available
neighbor clearance -- see §4.2).

### 4.2 Physical room

T1 sits at `(53.21, 148.91, 90deg)`, mid-board (not near any board edge -- the outline is
`(20,20)-(172,254)`). Real courtyard-to-courtyard gaps to its nearest neighbors, along the direction
the slot needs to extend (T1's own row/pad-spread axis): **R6 at 8.0mm** and **C17 at 16.4mm.** The
chosen slot (half-length 14.0mm vs. courtyard half-length 12.43mm) reaches 1.57mm past T1's own
courtyard on each end -- **6.43mm spare before R6's courtyard, 14.83mm spare before C17's.** Room is
not the binding constraint, though it is tighter than U6's case (T1's own pads already consume
nearly the full courtyard width, leaving a smaller absolute margin between "creepage-adequate" and
"neighbor-adequate" than U6 has).

### 4.3 Existing routing conflict -- larger than U6's, still bounded

**13 track segments across 4 nets**, all on `B.Cu`, run through the slot's world-frame footprint
(`x=[49.21,57.21], y=[134.91,162.91]`): `safety.uvlo_logic.mon-outa` (2 segments), `y` (1 segment),
`hb.gate_hs.driver-p2` (8 segments -- the same net that also crosses U6's slot region, consistent
with a gate-drive route passing near both parts), and `sw` (1 segment, likely the switch-node bus).
This is a real reroute burden, roughly 3x U6's, but the same category of ordinary place-and-route
work, not a geometric impossibility -- not attempted here, out of scope.

### 4.4 Structural consideration -- the real open question for this part

CST3015 is a 23 x 30mm body (per its own footprint description: primary "0.82mm extension per
side" beyond a 7.36 x 3.8mm physical terminal; the component itself is a wound ferrite-core current
transformer, materially heavier than a molded SOIC IC). The candidate slot sits directly in the
primary/secondary gap, i.e., **beneath the center of the transformer's own body** -- both pad rows
(and their solder joints) remain on solid, unslotted board (the slot's y-span, [-4.0,4.0], sits
entirely inside the gap between the pad rows at y=[-9.25,-4.45] and [4.65,9.25]), but roughly a
third of the footprint's total area, directly under the ferrite core's own mass, loses direct board
backing.

**No structural or FEA analysis was performed.** This is the same category of caveat the
predecessor slot document flagged for its own (much lighter) SOIC/DIP designs ("Board rigidity was
assessed qualitatively... not via structural/FEA analysis"), but T1/T2 is a materially different,
heavier part class, and that qualitative comfort does not automatically transfer. This is reported
as an **open, unresolved risk**, not dismissed: a real design would need a mechanical/vibration
review (relevant given the induction-cooktop application's shipping/handling and the part's own
mass) before committing to milling the board out from under a 23x30mm transformer's center.

**Verdict: VIABLE, with caveats** -- the creepage geometry, groove-width legitimacy, and available
board clearance all check out with real margin, but this is conditioned on (a) rerouting 4 nets, (b)
a mechanical/structural review this document could not perform, and (c) the general
standards-interpretation caveat in §5.

---

## 5. T2 (Coilcraft CST3015, same footprint as T1) -- NOT VIABLE TODAY, and the reason is placement, not creepage

**T2's footprint is byte-identical to T1's** (`temper:CST3015`) -- both instances of the identical
part, so T2's intrinsic, footprint-relative slot-design numbers are **exactly §4's numbers**: a
28.0 x 8.0mm slot would raise T2's governing creepage from 9.100mm to 15.53mm nominal / 14.83mm
worst-case, clearing 12.6mm with the same margin, for the same groove-width-legitimacy reasons.
**This is genuinely new information** -- no prior document in this repo had designed a slot for
CST3015's footprint at all; PR #1146/#1152 established the 9.1mm baseline and the part-search
conclusion ("no better CT at 1:100 ratio, >=50A"), not whether a slot could rescue the footprint
geometry itself.

**But T2 has nowhere to be.** Read directly from the real, committed `pcb/temper.kicad_pcb` this
session:

```
(footprint "temper:CST3015" ...)
  (at 100.0 300.0 0)
  (property "Reference" "T2")
```

The board outline is `(20,20)-(172,254)` -- **T2 sits at y=300, 46mm past the board's own bottom
edge (254).** This is not a placement to evaluate a slot against; it is a parking spot for a
component the current layout has nowhere to put.

This is not new information from this document -- it is the documented, independently re-verified
finding of a parallel effort: PR #1144 (`fix/t2-repair-entrypoint`) proved T2, jointly with its two
companion components `C37` (`c_filter`) and `R65` (`r_burden`, the OCP-02 subsystem), **UNSAT under
incremental placement repair against the current, frozen 165-component board, on pure courtyard
geometry alone** -- no creepage, no clearance, no routing, just "do the courtyard rectangles fit
anywhere." `docs/evidence/2026-08-13-ocp02-unplaced-subsystem-options.md` independently re-ran this
same check this same day (`temper-placer repair-unplaced pcb/temper.kicad_pcb --refs T2,C37,R65`,
PR #1144's own tool): infeasible in 1.6-2.0 seconds, not a solver timeout. That document went
further and empirically shrank T2's courtyard down to 16.6x smaller than its real physical size
(a synthetic, non-physical part) -- **still infeasible, at every size tested.** Room for T2's own
bare footprint does not exist anywhere in the current layout; a slot design that additionally
requires ~28x8mm of *clear neighbor-free space* around wherever T2 would sit is a strictly harder
placement constraint than the bare-courtyard case already proven impossible, not an easier one.

**Consequence for this task's central question:** a slot does not rescue T2, but not because the
creepage mechanism fails -- it is because T2's problem is placement, which is prior to and
independent of creepage, and this document's scope (per its hard constraints) does not include
re-placing the board. **If T2's placement problem is ever solved** (full re-place, board growth, or
de-scoping OCP-02 and re-adding it later with a resolved layout -- all evaluated and ranked in the
OCP-02 options document, none executed there either), **then this document's §4 geometry transfers
directly**: the same 28x8mm slot design that works for T1 would work for T2, since they are the same
part in the same footprint. That is a real, actionable fact for whoever picks up T2's placement
problem next -- but it does not change T2's status today.

---

## 6. The standards-interpretation question, stated plainly

Both this document and `docs/evidence/2026-07-28-isolator-creepage-slots.md` rely on a derived
principle: a full-depth, board-edge-to-board-edge... no -- a **bounded** slot (one that does not
reach the board's own outline, an island-shaped cutout) forces the creepage path to detour around
whichever end is nearest, on the exposed top (or bottom) copper surface, because there is no
material left at the bottom of a full-depth cut for a "down the wall, across, up the other wall"
path to use (that model, which `HIGH_VOLTAGE_CLEARANCE_SPEC.md` §6.1 currently states, is itself
flagged as likely wrong for a full-depth slot by the same predecessor document, for the same reason:
directly beneath a through-slot's footprint is more hole, not a floor).

**Why this is physically reasonable, not just convenient:** the slot genuinely removes the board's
insulating surface in its footprint -- there is no continuous FR4/soldermask surface there for a
creepage current to bridge along, regardless of whether a component's plastic body ends up
suspended above that void after assembly (a seated SMD part's body is elevated off the board by its
own standoff height; it does not touch the board surface except at the solder joints themselves).
The board surface elsewhere -- including the areas still nominally "under" the component's body
silhouette but on either side of the slot -- remains a real, physically present dielectric surface
regardless of what sits above it. This is the mechanism the predecessor document's own visibility-
graph computation implements, and it is consistent with documented industry practice (isolator-IC
application notes route a trace around a slot's rounded end on the top copper layer, not through a
cross-section).

**Why it is not fully closed:** IEC 60664-1 cl. 4.2's own 11 worked examples (§1, all read this
session) are uniformly 2D profile views of an effectively-infinite-length feature. None pictures a
bounded island cutout with two real ends whose "around-the-end" detour is itself the point (as
opposed to a straightforward "does the path fit inside the groove or bridge over it" question, which
is what all 11 examples actually address). **This repo's own `scripts/measure_cross_domain_
creepage.py` takes a more conservative position** -- its docstring states flatly that "a surface
creepage path that runs under a component's own moulded body cannot be lengthened by a routed slot,"
and classifies every one of T1/T2's, U6's, K1's, and C6's governing pairs as `body_crossing`
("NOT fixable by a slot"), reproduced directly this session:

```
$ uv run --no-sync python scripts/measure_cross_domain_creepage.py --min-creepage-mm 12.6
  [BODY]   8.000mm  C6.1(PWR_RTN) <-> C6.2(gnd)                    (crosses: C6)
  [BODY]   8.000mm  K1.13(...) <-> K1.A1(...)                       (crosses: K1)
  [BODY]   8.100mm  U6.14(hb.gate_hs.driver-p2) <-> U6.3(+3V3)      (crosses: U6)
```

That script's classification is correct about the DIRECT, unmodified straight-line path (which is
indeed under each part's own body -- the same fact `docs/evidence/2026-07-28-conformal-coating-
pd1.md` uses to correctly rule out coating). It is a simplifying heuristic, not a slot-geometry
computation -- it never models a candidate slot or runs a shortest-path search with one in place
(§2.2's method is a different, more expensive computation that script does not attempt). This
document's position -- consistent with, and reusing, the predecessor slot document's already-
computationally-verified U6/U3 designs -- is that the "under body" fact correctly forecloses
*coating* (which needs post-assembly physical access to the surface) but does **not** automatically
foreclose a *slot* (which is milled into the bare board before assembly, and removes the surface
entirely rather than needing access to it). **This is a real disagreement between two pieces of this
repo's own evidence, reported here rather than silently favoring one.** Given the reinforced
mains/SELV stakes, this should be checked against a certification lab's own interpretation of a
bounded slot before either T1's or U6's design is treated as compliance-closing, not just
DRC-passing.

---

## 7. What this changes and does not change

- **Does not change**: `HV_CREEPAGE_ENFORCED_MM`, any DRU threshold, `pcb/temper.kicad_pcb`, any
  footprint file, `elec/domain_manifest.yaml`, or any ratchet ceiling. No slot was cut. No part was
  respecified.
- **Does change the board's outlook, per the task's own framing**: PR #1152 ranked T1/T2 as "the one
  genuinely open item with no known fix anywhere." That is no longer accurate in the narrow,
  footprint-geometry sense -- **T1's own footprint, with a slot, plausibly reaches 12.6mm**, subject
  to the reroute cost, the unverified structural question (§4.4), and the standards-interpretation
  caveat (§6). **T2 remains open**, but for a different, already-identified reason (placement, PR
  #1144) that this document does not resolve and that a slot cannot resolve on its own.
- **U6's fallback path (discrete digital isolator redesign, PR #1152 §3.3) may not be needed** if
  the slot design in §3 is accepted: it reaches 12.6mm within U6's *existing* footprint, a land-
  pattern change rather than a schematic/BOM redesign -- a materially cheaper path than swapping to
  `ISO7741FQDWWRQ1` plus a local secondary-side driver, if the §6 standards question resolves
  favorably.

---

## 8. What is NOT established here (explicit)

- **No certification-lab confirmation of the bounded-slot "around-the-end" mechanism.** §6 states
  the disagreement plainly; this document does not resolve it, and treats it as the single largest
  remaining risk to relying on either slot design for actual compliance sign-off.
- **No structural/FEA analysis for T1/T2's slot** (§4.4) -- flagged as open, not dismissed.
- **The 13-segment (T1) / 4-segment (U6) reroutes were not attempted.** This document establishes
  that they are necessary and gives their exact nets/layers/locations; it does not verify the
  reroute is itself geometrically feasible in the freed-up space (a smaller, more ordinary
  place-and-route question than T2's placement problem, but genuinely unchecked here).
- **T2's placement problem is not solved here** and this document does not attempt to solve it --
  it is explicitly out of scope (this task's hard constraints forbid editing `pcb/temper.kicad_pcb`,
  and re-placing 165+ components is PR #1144/the OCP-02 options document's territory, not this
  one's).
- **Clearance (through-air) was not re-derived here.** T1/T2/U6's baseline straight-line distances
  (9.1mm, 8.1mm) already comfortably exceed every reinforced-clearance figure in
  `HIGH_VOLTAGE_CLEARANCE_SPEC.md` §4 (all <=8.0mm at this board's voltage row); a slot only affects
  creepage, never clearance, per the standard's own definitions and per this repo's established
  convention (§3 of the predecessor slot document) -- not re-derived, only relied upon.
- **JLCPCB's ±0.2mm regular-precision tolerance figure is for one named fab**, per
  `docs/evidence/2026-08-13-jlcpcb-fab-capability-envelope.md`'s own caveat; not cross-checked
  against PCBWay or another house for this specific tolerance number.

---

## Files

- This document: `docs/evidence/2026-08-13-hv-creepage-slot-rescue-t1-t2-u6.md`
- Cites, does not duplicate: `docs/evidence/2026-08-13-hv-creepage-pd3-gap-measurement-and-plan.md`
  (PR #1152 -- the task, the 9.100mm/8.100mm baselines, the 5-of-8-isolators-fail finding);
  `docs/evidence/2026-08-13-ocp02-unplaced-subsystem-options.md` (T2's independent placement-UNSAT
  finding, PR #1144 re-verification); `docs/evidence/2026-08-13-jlcpcb-fab-capability-envelope.md`
  and `docs/hardware/FAB_CAPABILITY.md` (PR #1142 -- fab slot-width/tolerance figures);
  `docs/evidence/2026-07-28-isolator-creepage-slots.md` (the predecessor slot design + IEC cl. 4.2
  citation, on a different not-yet-merged branch -- re-verified against the primary source directly
  in this document rather than trusted at second hand); `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`
  (governing 12.6mm figure, §6.1's slot model this document corrects); `scripts/measure_cross_
  domain_creepage.py` (the production pairwise-creepage tool, its `body_crossing` heuristic
  discussed and disagreed with in §6).
- Primary source fetched and read directly this session: IS 15382 (Part 1):2003 = IEC 60664-1
  (2002), <https://law.resource.org/pub/in/bis/S05/is.15382.1.2003.pdf>, clause 4.2 in full (all 11
  worked examples).
- Measured this session, not committed (scratch, per this task's "into a scratch path" instruction):
  local-frame pad-geometry extraction, the visibility-graph slot-design search
  (`networkx`+`shapely`), and the real-board neighbor/routing-conflict queries (`kiutils`), all
  under this session's scratchpad.
