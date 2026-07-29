<!-- provenance: commit=fd6c9c15d61700ff034445a1b67d31190ef2c162 dirty=false -->

# K2/K3 relay land pattern re-targeted to PD3 (12.6mm): the Finder 40.52's
# real, fixed pinout cannot reach it -- quantified, not reduced

Base commit: `fd6c9c15` (`merge: K2/K3 replaced with a DPDT part that closes
the DC-break gap too`), branch `docs/methodology-loop-discipline` as it stood
at that commit (checked out directly on a new local branch
`pd3-retarget-relay` in this worktree, per this task's own instruction to
target the named commit rather than the branch's later tip). Work done in
worktree `.claude/worktrees/agent-a5e39612e5d2b78d8`.

**This is a re-targeting pass on top of the 8.0mm-era relay-replacement
work** (`docs/evidence/2026-07-28-relay-replacement-implementation.md`).
Files touched: `pcb/libs/temper.pretty/Relay_DPDT_Finder-40.52.kicad_mod`
(corrected geometry, see below) and this evidence doc. `elec/src/` was
**not** touched -- see "Why `elec/src/` did not need to change" below.
`pcb/temper.kicad_pcb` was **not** touched (per the task's hard rule; the
pre-existing board-resync requirement from the prior pass is unaffected,
confirmed unchanged below).

## FALSIFIER

> "The Finder 40.52 land pattern can reach 12.6 mm board creepage within its
> fixed pinout. If it cannot, that is a part-selection or board-level
> finding -- quantify the shortfall rather than reducing the target."

**Did NOT fire in the Finder's favour. It cannot reach 12.6mm, and it cannot
even reach the prior 8.0mm target.** The governing (shortest) coil-to-contact
edge-to-edge PCB creepage, using the manufacturer's real, fixed pin
positions, is **5.300mm** -- a **7.300mm shortfall** against 12.6mm and a
**2.700mm shortfall** against the already-superseded 8.0mm figure. No routed
slot closes any part of this gap (see Task 2). **The creepage target was not
reduced; the footprint was corrected to reality, and the resulting number is
reported as-is.**

## The critical prior-work finding, stated up front

The 8.0mm-era footprint (`docs/evidence/
2026-07-28-relay-replacement-implementation.md`) claimed 9.2mm edge-to-edge,
"clearing the 8.0mm target with 1.2mm margin." **That figure was never a
measurement of the real, physical Finder 40.52.** That document's own text
says so, in its own words: the 11mm coil-to-contact center-to-center spacing
was *"a deliberate design choice, not a trace of the manufacturer's own
recommended PCB pattern"* and *"a DELIBERATE CHOICE by this footprint's
author"* -- an invented layout, adopted because the catalog's own dimension
drawing "rendered ambiguously under this session's PDF text-extraction."

**This session resolved that ambiguity** (Task 1, below) by pixel-calibrating
the catalog's own vector drawing rather than relying on `pdftotext`. The real
manufacturer spacing is **7.5mm center-to-center**, not 11mm -- a THT relay's
pins are cast rigidly into its base at the manufacturer's chosen positions;
a footprint cannot place pads wherever is convenient and still describe a
physically real, solderable part. **The prior footprint did not describe a
buildable Finder 40.52.** This is corrected here as a byproduct of the PD3
re-target, independent of whether 12.6mm is reachable.

## Provenance labels

| Label | Meaning |
|---|---|
| **CITED-PRIMARY** | Standard's own text, read this session or (where stated) inherited from an already-committed evidence doc at this base commit. |
| **CITED-SECONDARY** | Manufacturer document, fetched and read this session. |
| **MEASURED** | Computed this session from the real files (catalog PDF pixels, or the saved `.kicad_mod`), script/method shown. |
| **DERIVED** | Arithmetic on labelled inputs, shown in full. |
| **ASSUMED** | Not established; flagged for a human. |

---

## Task 1 -- the achievable coil-to-contact pad spacing, MEASURED from the real part

### 1.1 Method: pixel-calibrated reading of the catalog's own vector drawing

`pdftotext -layout` and raw-mode extraction of the Finder "40 SERIES
PCB/Plug-in relays 8-10-12-16A" catalog (cat. S40EN,
`https://cdn.findernet.com/app/uploads/S40EN.pdf`, fetched fresh this
session) page 3 confirms the dimension figures on the type-40.52 "Copper
side view" drawing (7.5, 5, 5, 2.5, 20, 29, and the pin-diameter callout) are
**not present in the PDF's text layer at all** -- CONFIRMED, grepped the
`pdftotext` output for these tokens, none appear near the drawing (they are
vector-drawn glyphs, the same difficulty every prior session in this
project's evidence chain hit with this exact drawing).

This session rendered page 3 at 300dpi (`pdftoppm`), cropped to the type
40.52 "Copper side view" region, and recovered a precise px/mm calibration
two independent ways that agree:

1. From the drawing's own two labelled reference chains, both anchored to
   the same left-edge datum: "2.5" (datum to coil pin) and "20" (datum to
   the farthest contact pin), combined with the independently-labelled "29"
   (full case width, matching the separate p.10 outline drawing's stated
   29mm case length exactly).
2. Solving `calib` such that both chains are simultaneously consistent with
   the pixel positions of three independently-detected vertical reference
   lines (coil-pin extension line, farthest-contact-pin extension line, and
   the case's right `Edge.Cuts`-equivalent boundary) gives **11.415 px/mm**
   (vs. the theoretical 300dpi/25.4 = 11.811 px/mm -- a ~3.4% discrepancy,
   plausible PDF-rendering/measurement noise, not a methodology error).

Using this calibration, the **pixel positions of the actual pin dots**
(detected independently, not merely inferred from the dimension labels)
land within 0.5mm of the round-number positions the labelled dimension
chains predict:

| Feature | Predicted from labels (mm, case-left-edge = 0) | MEASURED pixel position (mm) | Agreement |
|---|---:|---:|---|
| Coil pin (A1) | 2.5 | 2.5 (exact, used as calibration anchor) | -- |
| First contact pin ("12") | 10.0 | 9.77 | within 0.23mm |
| Middle contact pin ("11") | 15.0 | ~15.0 | consistent |
| Farthest contact pin ("14") | 20.0 | 20.0 (calibration anchor) | -- |
| Case right edge | 29.0 | 29.0 (calibration anchor) | -- |

**Result: coil pin (A1/A2) to nearest contact pin ("12"/"22") = 10.0 - 2.5 =
7.5mm center-to-center, MEASURED.** This is not the same number as the row
separation (also 7.5mm) by derivation -- it is a numeric coincidence of this
specific compact relay's tooling, confirmed as two independently-labelled
dimensions in the same drawing, not one figure copied for two purposes.

**A second, independent finding from the same drawing, also corrected this
session:** the real physical pin order, left-to-right (nearest-coil to
farthest), is **NC - COM - NO** (e.g. pole 1: pin "12"=NC nearest the coil,
"11"=COM in the middle, "14"=NO farthest) -- not COM-NC-NO as the prior
footprint placed them. This does not change any pin's *function* (the
`Relay_DPDT` component's `signal COM1 ~ pin "11"` etc. mapping in
`elec/src/components.ato` is unaffected -- see "Why `elec/src/` did not need
to change" below) but it does mean the prior footprint's pad *positions*
for "11" and "12" were transposed relative to where the manufacturer
actually puts those two legs.

**Pin diameter: 1.5mm** (drawing's own circled-diameter callout, MEASURED),
not the ~1.0mm drill the prior footprint used -- a genuine, independent
defect: a 1.0mm drill cannot physically accept this part's real 1.5mm round
leads at all.

### 1.2 What this means for achievable creepage

With the real 7.5mm center-to-center spacing and realistic pad sizing for a
1.5mm pin (1.7mm drill, 2.2mm pad diameter -- 0.25mm annular ring, standard
THT practice, DERIVED not from safety-margin gaming but from ordinary
manufacturability rules):

```
edge-to-edge = center-to-center - r(coil pad) - r(contact pad)
             = 7.5mm - 1.1mm - 1.1mm
             = 5.3mm
```

**5.3mm is the maximum achievable straight-line PCB edge-to-edge creepage
for this part's fixed pinout, full stop.** It cannot be increased by
choosing a different footprint layout for the *same* part -- the 7.5mm
center-to-center is fixed by the manufacturer's tooling, not a footprint
design choice, and smaller pads only buy back the difference between 1.7mm
(true minimum viable drill for this pin) and whatever smaller value one
might try; even a maximally aggressive 1.5mm-exact drill / 1.7mm pad
(no annular ring at all, not manufacturable) would only reach 5.8mm.

**This already fails the prior 8.0mm PD2-era target by 2.2-2.7mm.** The
prior session's claimed 9.2mm pass was against invented geometry, not this
real part.

---

## Task 2 -- is a routed slot available? No, and the reason is specific to this part's construction

### 2.1 The PD3 groove-width minimum, cited (not re-derived, since it is already committed at this base commit)

`docs/evidence/2026-07-28-isolator-creepage-slots.md` Section 2 (already
present at base commit `fd6c9c15` -- confirmed via `git log`, no need to
re-fetch or re-derive) establishes, **CITED-PRIMARY, IS 15382 (Part 1):2003
= IEC 60664-1 (2002) clause 4.2**, quoted there verbatim:

> "The dimension X ... has a minimum value depending on the pollution degree
> as follows: PD1 = 0.25mm, **PD2 = 1.0mm, PD3 = 1.5mm**. If the associated
> clearance is less than 3mm, the minimum dimension X may be reduced to one
> third of this clearance."

**This directly answers the task's coordination point: the PD2 minimum
groove width (1.0mm) does NOT carry over to PD3 -- PD3's minimum is
1.5mm.** This is 1.5x the PD2 figure, cited from the standard's own text as
already read and quoted by a sibling pass at this same base commit.

### 2.2 Why the groove-width number does not matter here -- the relay's own body blocks the option entirely

The same already-committed document (`isolator-creepage-slots.md` Section 3)
establishes, as a DERIVED correction to this repo's own
`HIGH_VOLTAGE_CLEARANCE_SPEC.md` model, that a routed slot's creepage benefit
comes from forcing the path to detour **around the slot's end, on an exposed
top surface** -- not from travelling down through the board's thickness
(there is no floor to walk across under a full-depth slot). This means a
groove only helps where the direct pad-to-pad path runs across **exposed,
uncovered PCB surface.**

**It does not run across exposed surface here.** The Finder 40.52's own
courtyard/body outline (`F.Fab`/`F.CrtYd`, unchanged this session) is a
single, continuous 29 x 12.4mm rectangle -- MEASURED against the catalog's
own p.10 outline drawing (exact match, no window, gap, or cutout feature
anywhere in that drawing) -- and it **fully covers** the entire coil-to-
contact pin field (coil at x=-12.0, farthest contact at x=+5.5, both well
inside the body's x=[-14.5,+14.5] span). The relay's own one-piece moulded
base physically sits on top of the board directly over this region.

**This is the identical failure mode this project's own
`docs/evidence/2026-07-28-creepage-determination-brainstorm.md` Section 7
already established for the incumbent Omron G5LE-1**, quoted verbatim from
that already-committed table: *"K2/K3 ... COM contact to coil pin across the
relay's own base ... Groove helps? No -- the relay body sits on the board;
a slot cannot lengthen a path that runs over the part's own case."* That
finding was made about the G5LE-1's construction; it generalizes directly to
the Finder 40.52 because both are the same class of part (a single
continuous THT relay base spanning coil and contact pins with no internal
gap) -- confirmed for the Finder 40.52 specifically this session, not
assumed to carry over.

**Consequence: a routed slot between the coil and contact pads would sit
entirely beneath the relay's own plastic base.** It would provide no
creepage benefit (the base already bridges directly across at the same
short distance, with no exposed surface for a groove to lengthen), and
cutting one there would remove board material directly under the part's own
mechanical support with nothing to show for it. **No slot was added to this
footprint.** The PD3 groove-width citation above (1.5mm) is established and
cited as the task requires, but it is moot for this specific part: the
question "is my groove wide enough" never arises because no groove is
usable here at all.

### 2.3 What board thickness would have bought, if the body did not block it (for completeness)

Purely for the record (this path is foreclosed by 2.2, not adopted): this
board's thickness is 1.6mm (MEASURED, `pcb/temper.kicad_pcb`'s
`(general (thickness 1.6))`, and independently corroborated in
`docs/hardware/TRACE_WIDTH_CALCULATIONS.md`). Even under the (here,
inapplicable) down-through-the-board model the sibling doc's Section 3
explicitly derives is *wrong* for a fully-enclosed slot, the maximum
achievable would have been `5.3mm + 2 x 1.6mm = 8.5mm` -- still 4.1mm short
of 12.6mm. Board thickness was never going to be the deciding factor either
way.

---

## Task 3 -- footprint updated and independently re-verified

`pcb/libs/temper.pretty/Relay_DPDT_Finder-40.52.kicad_mod` was rewritten
with:

- Pin diameter corrected: 1.5mm real pin -> 1.7mm drill / 2.2mm pad
  (previously 1.0mm drill / 1.8mm pad -- the old drill could not accept the
  real pin at all).
- Coil pins repositioned to the real, measured center-to-center: A1/A2 at
  x=-12.0mm (previously x=-11.0mm, the invented figure).
- Contact pins repositioned to the real order and pitch: "12"/"22" (NC) now
  nearest the coil at x=-4.5mm, "11"/"21" (COM) in the middle at x=+0.5mm,
  "14"/"24" (NO) farthest at x=+5.5mm -- previously "11"/"21" sat nearest the
  coil (x=0) and "12"/"22" in the middle (x=5), a transposed pair.
- Body/courtyard/silkscreen outline (29 x 12.4mm) unchanged -- this was
  already correct (matches the catalog's p.10 outline drawing).

**Independent re-parse verification** (script re-reads the saved
`.kicad_mod` text directly via regex extraction of every `pad` block's
actual `(at ...)` and `(size ...)` values -- not the design intent, not the
`descr` text, the literal saved geometry):

```
Parsed 8 pads from pcb/libs/temper.pretty/Relay_DPDT_Finder-40.52.kicad_mod:
  11: pos=(0.500,3.750)    pad_dia=2.200mm
  12: pos=(-4.500,3.750)   pad_dia=2.200mm
  14: pos=(5.500,3.750)    pad_dia=2.200mm
  21: pos=(0.500,-3.750)   pad_dia=2.200mm
  22: pos=(-4.500,-3.750)  pad_dia=2.200mm
  24: pos=(5.500,-3.750)   pad_dia=2.200mm
  A1: pos=(-12.000,3.750)  pad_dia=2.200mm
  A2: pos=(-12.000,-3.750) pad_dia=2.200mm

All coil<->contact pairs, sorted by edge-to-edge distance:
  A1 <-> 12: center-to-center=7.500mm  edge-to-edge=5.300mm
  A2 <-> 22: center-to-center=7.500mm  edge-to-edge=5.300mm
  A1 <-> 22: center-to-center=10.607mm edge-to-edge=8.407mm
  A2 <-> 12: center-to-center=10.607mm edge-to-edge=8.407mm
  A1 <-> 11: center-to-center=12.500mm edge-to-edge=10.300mm
  A2 <-> 21: center-to-center=12.500mm edge-to-edge=10.300mm
  A1 <-> 21: center-to-center=14.577mm edge-to-edge=12.377mm
  A2 <-> 11: center-to-center=14.577mm edge-to-edge=12.377mm
  A1 <-> 14: center-to-center=17.500mm edge-to-edge=15.300mm
  A2 <-> 24: center-to-center=17.500mm edge-to-edge=15.300mm
  A1 <-> 24: center-to-center=19.039mm edge-to-edge=16.839mm
  A2 <-> 14: center-to-center=19.039mm edge-to-edge=16.839mm

GOVERNING (shortest): 5.300mm  (A1 <-> 12)
  vs old PD2 8.0mm target: FAIL  (margin -2.700mm)
  vs PD3 12.6mm target:    FAIL  (margin -7.300mm)
```

The same script, run against the **unmodified** pre-session footprint first
(as a self-check), exactly reproduced the prior session's claimed figure
(`A1 <-> 11: edge-to-edge=9.200mm`), confirming the script itself is correct
and that the difference between 9.2mm and 5.3mm is entirely the corrected
geometry, not a measurement-method artifact.

**Note the governing pair changed identity, not just distance**: at the
correct geometry, `A1<->"12"` governs (NC nearest the coil); at the prior,
invented geometry, `A1<->"11"` governed (COM nearest the coil, because that
session placed "11" first). This is the direct, physical consequence of the
NC/COM position swap described in Task 1.

---

## Task 4 -- 12.6mm is unreachable for this part; shortfall quantified; what would be required

**Quantified shortfall: 12.6mm - 5.3mm = 7.3mm.** No PCB-level remedy closes
any part of this (Task 2). This is a **part-selection or board-level
finding**, exactly as the falsifier anticipated, and the target is **not**
being reduced to accommodate the part.

**What would actually be required, categorically (no unverified MPN
proposed here, per the hard rule -- seven fabricated MPNs were found in this
project this week, and this task's own instruction is explicit: fetch and
cite a manufacturer datasheet for any replacement, which is out of this
task's scope to do responsibly in the time available)**:

1. **A physically larger relay family**, with a coil-to-nearest-contact-pin
   center-to-center spacing of at least **~14.4-14.8mm** (12.6mm + a
   realistic pad-diameter pair for whatever pin gauge that family uses) --
   roughly double the Finder 40.52's 7.5mm. This is not a same-family
   variant: the Finder 40 series' other members (40.31/51/61/62) share the
   identical 29 x 12.4mm case tooling and the identical 2.5mm/7.5mm/5mm
   dimension scheme (MEASURED from the same catalog page, same drawing
   family) -- switching within this family does not help. A genuinely
   different, larger mechanical class of PCB power relay would be needed,
   and any such candidate would need the full three-way re-verification this
   project's own evidence chain already applies (reinforced coil-to-contact
   isolation + a rated DC break at 170-200V + fail-safe NC topology) --
   exactly the process that selected the Finder 40.52 over AZ770-1C-12D,
   ALZN1B12W, and rejected Omron G5NB-1A-HA for topology in the first place.
   **Not attempted in this pass**; flagged as the concrete next step for
   whoever owns the BOM.
2. **A board-level change** does not help on its own: board thickness was
   never the binding constraint (Task 2.3), and the relay's own body
   physically forecloses the slot option regardless of board thickness.
3. **Accepting the component's own internal EN 61810-1 rating** (Finder's
   stated "Reinforced (8mm)") as satisfying the board-level requirement,
   instead of measuring the PCB pad-to-pad path -- **this is the genuine
   safety-engineer question the task named, addressed directly below.**

---

## The conflation question, addressed directly (per the task's explicit instruction)

**Two different quantities, kept separate throughout this document:**

1. **The part's own internal coil-to-contact isolation**: Finder's
   catalog-stated "Reinforced (8mm)" per EN 61810-1, for both poles. This
   figure is unchanged by anything in this session -- it is the
   manufacturer's own type-tested rating of the relay's internal
   construction (coil bobbin to contact set, inside the sealed/vented case),
   governed by EN 61810-1, not by this board's pollution degree. **This
   session did not touch it and could not change it if it wanted to.**
2. **PCB surface creepage between the coil-side and contact-side pads**:
   governed by IEC 60335-1 / IEC 60664-1 at this board's pollution degree
   (PD3, 12.6mm, per `docs/ENVIRONMENTAL_SPEC.md` Section 3.1, already
   corrected and cited at this base commit). **MEASURED this session at
   5.3mm, for the reasons above.**

**Is the part acceptable when (2) fails but (1) states 8mm?** This document
does **not** resolve that question, and states plainly why it cannot:
whether the appliance-level board requirement is satisfied by the
component's own EN 61810-1 certification (which may test a different,
possibly more favourable, physical path -- e.g. down through the case's own
internal insulation, or along a longer internal creepage path the
manufacturer's own construction provides that a naive PCB pad-to-pad
measurement does not capture) is a determination that requires comparing
EN 61810-1's own test conditions (pollution degree assumptions, working
voltage, material group) against IEC 60335-1/60664-1's PD3 requirement for
*this* appliance -- a standards-interpretation question for a safety
engineer, not something this pass can settle by geometry alone. **What this
document establishes with confidence: the PCB pad-to-pad path, considered on
its own, does not meet either 8.0mm or 12.6mm, and no board feature can fix
that for this specific part's construction.** Whether the component's own
8mm internal rating is an acceptable *substitute* for that missing PCB
margin is the open question, reported rather than assumed either way.

---

## Task 5 -- what changes if PD2 governs after all

A sibling determination may find that IEC 60335-2-6 clause 29.2's exception
(*"unless the insulation is enclosed or located so that it is unlikely to be
exposed to pollution"*) applies, restoring PD2 (8.0mm) instead of PD3
(12.6mm). **Structuring this so both answers are usable, as the task asked:**

| If PD3 governs (current default, per `ENVIRONMENTAL_SPEC.md` Sec 3.1) | If PD2 governs (enclosure argument accepted) |
|---|---|
| Target: 12.6mm. Real PCB path: 5.3mm. **FAILS by 7.3mm.** | Target: 8.0mm. Real PCB path: 5.3mm. **STILL FAILS, by 2.7mm.** |
| No slot available (Task 2). | No slot available (Task 2) -- the enclosure argument changes the *pollution degree*, not the relay's own construction, so the body-blocks-the-groove finding is unchanged either way. |
| Part's own internal rating (8mm) also does not clear 12.6mm on its own, even hypothetically, if it were accepted as the governing figure. | Part's own internal rating (8mm) would **exactly** meet an 8.0mm PD2 target -- zero margin, the same "arithmetically a pass, practically not one" caution `docs/evidence/2026-07-28-creepage-determination-brainstorm.md` Section 8 already raised for `K1`'s identical zero-margin case. |

**The one thing that does NOT change between the two branches: the raw PCB
pad-to-pad measurement (5.3mm) fails under both PD2 and PD3.** The PD2/PD3
question only matters for whether the *component's own* internal rating
(8mm, unaffected by pollution degree, since it is an EN 61810-1 figure, not
an IEC 60335-1 one) could be argued to substitute for the missing PCB
margin -- and even then, only at PD2, and only with zero margin. **At PD3,
no combination of "accept the internal rating" and "the PCB path" reaches
12.6mm.** This is reported for both branches rather than resolved, per the
task's instruction.

---

## Why `elec/src/` did not need to change

`elec/src/components.ato`'s `Relay_DPDT` component declares
`signal COM1 ~ pin "11"`, `signal NC1 ~ pin "12"`, etc. -- these are **pin
identity assignments** (which schematic signal a given pad name represents),
not physical position claims. The correction in this session is entirely a
**physical position** correction (where pad "11" and pad "12" actually sit
on the board, matching the manufacturer's real pin layout) -- the pad
*names* and what they mean electrically are unchanged and were already
correct. `elec/src/modules.ato`'s `BusDischarge` docstring cites the
manufacturer's own 8mm internal rating and DC-break/coil-budget figures,
none of which reference the (now-corrected) PCB pad geometry, so no update
was needed there either. Confirmed by grep: no `9.2mm`/`11mm center` string
appears anywhere in `elec/src/`.

---

## UNVERIFIED (explicit list)

- **The catalog's dimension figures were read via pixel-calibration of a
  rendered PDF page, not the manufacturer's own CAD/STEP export.** Two
  independent internal-consistency checks (label-chain arithmetic vs.
  detected pixel positions of the actual pin dots) agree to within 0.5mm,
  which is strong corroboration, but a human should cross-check against
  Finder's real CAD file (downloadable from findernet.com) before this
  footprint is used to fabricate a board -- flagged in the footprint's own
  `descr`, per this project's established convention.
- **Whether EN 61810-1's own test conditions for the "Reinforced (8mm)"
  rating are comparable to, stricter than, or more lenient than IEC
  60335-1/60664-1's PD3 assumptions for this appliance** is not established
  here -- this is the explicit safety-engineer question this document
  surfaces rather than answers (see "The conflation question" above).
- **The category-level "~14.4-14.8mm-pitch relay family" requirement (Task
  4, item 1) is a derived lower bound, not a search result.** No specific
  replacement part was fetched, read, or proposed this session, per the hard
  rule against unverified MPNs; this is flagged as the concrete next step,
  not attempted here.
- **Whether the sibling's IEC 60335-2-6 cl. 29.2 enclosure-exception
  determination has concluded** was not checked beyond confirming no such
  resolution is yet committed in this repo (`grep` for "enclosure argument"
  / "unlikely to be exposed to pollution" across `docs/` finds the question
  posed in five places, resolved in none). Task 5's table is structured to
  be correct either way, not contingent on that sibling's outcome.
- **Pad annular ring (0.25mm at 1.7mm drill / 2.2mm pad) was chosen from
  ordinary THT manufacturability convention, not from this project's target
  fabs' (JLCPCB/PCBWay) own published minimum-annular-ring figures**, which
  were not fetched this session. The qualitative conclusion (5.3-5.8mm
  regardless of reasonable pad choice, both well short of 8.0mm and 12.6mm)
  is insensitive to this within any plausible range.
- **Board rigidity/mechanical-support consequences of the relay's own base
  sitting over the pin field** were not analysed (no slot was cut, so this
  does not arise from this session's change, but it is inherent to the
  part's construction regardless of footprint).

## Hard rules -- compliance checklist

- **Creepage target never reduced.** 12.6mm (and, for completeness, the
  superseded 8.0mm) are both reported as failing against the real,
  MEASURED 5.3mm PCB path -- the footprint was corrected to reality, not the
  target relaxed to match the footprint.
- **No unverified MPN proposed.** The existing `40.52.7.012.0000` is
  unchanged; `scripts/mpn_fabrication_gate.py` run against this change:
  PASSED, 0 new violations (118 parts inspected, 10 pre-existing allowlist
  entries unchanged). No replacement part number is proposed anywhere in
  this document -- Task 4's "~14.4-14.8mm" figure is a derived requirement
  on a future part, not a part number.
- **No `git stash`** used anywhere this session.
- **No `run_in_background`, no `Monitor`, no waiting on background jobs.**
  Everything foregrounded, including `uv sync --all-packages` (run exactly
  once, into this fresh worktree's previously-empty `.venv`, ~27GiB free
  disk headroom confirmed beforehand).
- **No additional worktrees.** Checked out `fd6c9c15` on a new local branch
  inside the one worktree already assigned to this task.
- **Commits made after each meaningful step**: the footprint correction was
  committed on its own before this evidence doc was written.
- **Coordination**: touched only
  `pcb/libs/temper.pretty/Relay_DPDT_Finder-40.52.kicad_mod` and this
  evidence file. Did not touch `elec/src/` (not needed, see above),
  `pcb/temper.kicad_pcb`, `scripts/generate_kicad_dru.py`,
  `scripts/check_isolation_keepout.py`, or either `H11L1_DIP6_Isolated`/
  `SOIC16W_Isolated` footprint (sibling-owned files, per the task's own
  roster).
- Not pushed.

## Verification (all commands run this session, this worktree)

| Check | Result |
|---|---|
| `make netlist` | build complete |
| `check_domain_partition.py` | exit 0 |
| `capacity_budget_gate.py` | exit 0 |
| `mpn_fabrication_gate.py` | exit 0 (0 new violations) |
| `check_derived_doc_drift.py` | exit 0 |
| `check_copper_net_consistency.py` | **exit 3, 146 violations -- confirmed IDENTICAL to the pre-existing baseline reported in `docs/evidence/2026-07-28-relay-replacement-implementation.md`** (same violation count, same two root causes: `power_in.ntc-no` orphaned net and the K2/K3 pin-mapping resync still pending). Pre-existing, not caused or worsened by this session's footprint-library-only edit (confirmed: `pcb/temper.kicad_pcb` untouched, `git status --short` clean on that file throughout). Not fixed, per the task's own instruction to confirm-not-fix. |
| `check_rust_drc_presence.py` (`TEMPER_REQUIRE_RUST_DRC=1`) | exit 0 |
| `check_undeclared_imports.py` | exit 0 |
| `check_stale_extensions.py` | exit 0 (9/10 fresh, `temper-constraints` missing in lenient local-dev mode -- matches every prior session's baseline) |
| `check_net_classification.py` | exit 0 |
| `check_pll_range_consistency.py` | exit 0 (4/4 checks agree) |
| `check_isolation_keepout.py` | exit 3 (unchanged -- no keepout zone exists; HV pad count 87, matching the pre-existing board-staleness explanation already on record, not a new regression) |
| `check_measurement_provenance.py` | exit 5 (unchanged, pre-existing `drc_ceiling.json` provenance-tag defect) |
| `validate_footprints.py pcb/libs/temper.pretty` | 0 errors, 0 warnings, 7 footprints checked |
| `uv run --no-sync python -m pytest elec/validation -q` | 30/30 passed |

**Nine of the ten tracked gates are green; the tenth
(`check_copper_net_consistency`) fails for the pre-existing, already-reported
reason, confirmed unchanged by this session's edit. The two designated-
exception gates fire exactly as expected.**
