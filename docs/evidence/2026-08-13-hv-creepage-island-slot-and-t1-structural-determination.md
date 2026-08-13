<!-- provenance: commit=b0f0dc806b760c3511e85147f222a2a8c554b0f4 (origin/analysis/slot-creepage-rescue,
     PR #1155's own tip) dirty=false throughout (git status --porcelain clean apart from this
     document; git grep -l "^<<<<<<< " empty). Own git worktree
     (/home/bennet/Desktop/temper-creepage-island-question, branch
     analysis/creepage-island-t1-structural), never the main checkout. pcb/temper.kicad_pcb
     sha256=b7d865b7946f55dcc0d907cccbbee12f730fd1878b30d417bd56004d1091c1d6, pcb/temper.kicad_pro
     sha256=f2d90755af04fea40357be3ba2ef94368a01b1afc34c450b42fad0b9e15a51ac -- byte-identical to
     PR #1152's and PR #1155's own recorded provenance for this same commit, so every figure PR
     #1155 published applies to the exact board examined here. No pcb/temper.kicad_pcb, footprint,
     DRU threshold, or enforced safety constant (HV_CREEPAGE_ENFORCED_MM or otherwise) was edited
     anywhere in this task. -->

# Resolving PR #1155's two open questions: does an island slot earn creepage credit, and is T1's slot structurally safe?

## Verdict, up front

1. **Question 1 (does a bounded/island slot earn creepage credit) is NOT closeable from any primary
   source available to this repo, and stays open in the same direction PR #1155 left it -- but the
   internal evidence inside this repo now points more clearly at the repo's own tool being the
   *less*-supported position, not the slot mechanism.** `scripts/measure_cross_domain_creepage.py`'s
   "a body-crossing pair can never be helped by a slot" claim is traced to its origin: it has been
   present, verbatim, unmodified, and **uncited** since the script's very first commit
   (`8302756d3`, 2026-07-29) -- it is not derived from IEC 60664-1, not derived from any prior
   determination document, and not even internally consistent with this same repo's own prior
   determination one day earlier (`docs/evidence/2026-07-28-conformal-coating-pd1.md`, which
   explicitly reasons the opposite for this exact part: "a slot is a board feature and reaches
   under the body; a coating is a surface film and does not"). Checked directly this session: the
   **current** edition of IEC 60664-1 (Edition 3.0:2020, and its Edition 3.1:2025 consolidated
   reissue) still carries the identical set of 11 groove/rib/joint worked examples as the 2002-era
   text PR #1155 read -- renumbered from clause 4.2 into new clause 6.8, but not expanded with any
   bounded/island-slot case. **No edition of the standard pictures this geometry, in either
   direction.** The honest verdict is not "the tool is right" and not "the derivation is proven" --
   it is that this is a real, unresolved reading gap in the standard itself, and this document says
   exactly what to ask a certification lab (§3.4).
2. **Question 2 (is T1's slot structurally safe) cannot be closed by FEA because this repo has none,
   confirmed by exhaustive search** -- no FEA tool, no mechanical/vibration qualification data, no
   board-cutout-under-component precedent anywhere in `docs/` or `scripts/` beyond the same
   qualitative note PR #1155 already cited. What *can* be established directly: T1's footprint
   (`pcb/libs/temper.pretty/CST3015.kicad_mod`) is **pure SMD, four pads, zero mechanical
   through-hole/standoff/locating features** -- the part's entire mechanical retention is its four
   solder joints, all of which sit on solid, unslotted board outside the candidate slot's
   `y=[-4.0,4.0]` span. The real question this reduces to is therefore **solder-joint fatigue life
   under thermal cycling**, not board fracture and not part pull-off from a hollowed slot -- see §4
   for why, and what a real answer would require.

---

## 1. Where `measure_cross_domain_creepage.py`'s "not fixable by a slot" claim actually comes from

**Git history, checked directly (`git log --all --format="%H %ad %s" --date=short -- scripts/measure_cross_domain_creepage.py`):**

```
6ef9dde86 2026-08-01 feat(safety): land pairwise HV<->SELV creepage measurement tool (PR #498 rework)
8302756d3 2026-07-29 feat(safety): add pairwise HV<->SELV creepage measurement tool
```

**`git log -p --all -- scripts/measure_cross_domain_creepage.py`** shows the exact text (script lines
103-155 in the current file) present, word-for-word identical, in the *first* commit that created
this script (`8302756d3`, 2026-07-29) and never touched again (the 2026-08-01 rework re-lands the
same docstring verbatim, per the diff). The load-bearing sentence:

> "A surface creepage path that runs under a component's own moulded body cannot be lengthened by a
> routed slot -- the slot would have to be milled underneath a mounted part."
> (`scripts/measure_cross_domain_creepage.py:103-105`)

**This sentence carries no citation anywhere in the module** -- no clause reference, no `Sources`
list entry, no link to a prior evidence document. Compare this to every other non-trivial claim in
the same docstring (the rotation convention, the pad-geometry model, the fab-tolerance figure), each
of which cites a specific prior evidence document or repo convention by name. This one does not,
because -- checked against every evidence document in `docs/evidence/` dated on or before
2026-07-29 (`git log --all --diff-filter=A --name-only` filtered to that date range) -- **there is
no prior determination document establishing it.** It is an assumption the tool's original author
encoded directly into the docstring, not a derived or cited position.

**It is also not even the more conservative reading available in this repo's own history at the
time it was written.** `docs/evidence/2026-07-28-conformal-coating-pd1.md` (committed the day
*before* the tool, on `feat/provable-safety-place-and-route`) reaches the opposite conclusion for
this exact geometry (§4.2 of that document, discussing `U7`, the ancestor of today's `U6`):

> "The entire 7.250 mm inter-row gap lies inside the package body outline, and the pads themselves
> tuck 0.125 mm under it. ... This is exactly the geometry TI's own layout note warns about, **and
> it is why a routed slot is the correct remedy for `U7` -- a slot is a board feature and reaches
> under the body; a coating is a surface film and does not.**"
> (`docs/evidence/2026-07-28-conformal-coating-pd1.md:356-358`)

That reasoning is physically precise about *why* a slot differs from a coating: a coating is applied
after the part is seated and cannot reach a surface a body already occupies; a slot is milled into
bare FR4 *before* assembly, so "the slot would have to be milled underneath a mounted part" (the
tool's stated justification) describes a sequencing impossibility that does not actually exist --
nothing is mounted yet when the board is drilled/routed. The tool's own convex-hull-based
classification method is honest about the direction of its error, in its own words:

> "Convex hull is a deliberate, documented over-approximation (never under-approximation) ... the
> unsafe direction here is under-reporting a body's extent (which would recommend 'add a slot' as a
> fix where a slot is physically impossible because it would have to run under the part), not
> over-reporting it (which merely mis-labels a genuinely-fixable pair as unfixable, **a conservative
> error**)."
> (`scripts/measure_cross_domain_creepage.py:107-113`)

**This is the load-bearing admission.** The tool's author designed `body_crossing` as a
*conservative screening bound* -- deliberately willing to mislabel a fixable pair as unfixable --
not as a compliance determination. It answers "how many pairs are hopeless even under the most
generous geometric assumption" (a sizing question, per the module's own stated motivation, §"Which
threshold is current" and the module's opening "Motivation" section), not "can a slot help this
specific pair." Treating its `body_crossing` verdict as a closing determination on T1/U6/T2 -- which
neither PR #1155 nor this document does -- would be using the tool for a purpose its own docstring
disclaims.

**Conclusion on origin:** the assertion is an uncited, underived assumption, and this repo's own
prior evidence (one day older) already reasoned the opposite way for the identical part class. This
does not, by itself, prove the slot mechanism is valid -- it only establishes that the repo's tool is
not the more-evidenced side of this disagreement. §2 below asks the standard itself.

---

## 2. Does a later edition of IEC 60664-1 (or -3, or -5, or IEC 60335-1's own text) address bounded/island grooves? -- checked directly, not assumed

PR #1155 and its predecessor both worked from IS 15382 (Part 1):2003, the Indian national identical
adoption of **IEC 60664-1 (2002-era text)** -- pre-dating the 2007 second edition per the current
edition's own foreword, below; its precise edition/amendment number was not independently verified
this session, consistent with the predecessor documents' own citation. Neither prior document checked a later
edition (`2026-07-28-isolator-creepage-slots.md` §8 flags this explicitly as UNVERIFIED: "The
current (2020+) edition of IEC 60664-1 was not read"). That gap is closed here.

**IEC 60664-1's own foreword states edition history directly** (fetched and read this session,
`pdftotext -layout` extraction of two independently-sourced preview documents -- see §5 Sources):

> "This third edition cancels and replaces the second edition published in 2007."
> (IEC 60664-1:2020, foreword)

So there are two editions between the 2002-era text PR #1155 read and today: Edition 2 (2007) and
**Edition 3.0 (2020-05)**, itself reissued as a **consolidated Edition 3.1 (2025-05)** incorporating
Amendment 1 -- the current, in-force text. Both were fetched directly this session
(`https://cdn.standards.iteh.ai/samples/100156/f010cc07edff461d9caa559635817555/IEC-60664-1-2020.pdf`
for 3.0; `https://assets.vde-verlag.de/iec-normen/preview-pdf/info_iec60664-1%7Bed3.1%7Den.pdf` for
3.1) and extracted with `pdftotext -layout`, the same tool the predecessor documents used on the
2002-era text.

**The current edition's own foreword lists every substantive change from the prior edition, in
full, and none of them is a new groove/slot worked example:**

> "This edition includes the following significant technical changes with respect to the previous
> edition:
> a) update of the Scope, Clauses 2 and 3,
> b) new structure for Clauses 4 and 5,
> c) addition of 1 500 V DC into tables in Annex B and F,
> d) update of distances altitude correction in a new Table F.10,
> e) addition of Annex G with a flowchart for clearances,
> f) addition of Annex H with a flowchart for creepage distances."
> (IEC 60664-1:2020, foreword; identical text confirmed independently in the 3.1:2025 consolidated
> preview at the same location)

Item (f), a new flowchart Annex for *dimensioning* creepage distances (a different question --
"how much creepage do I need," not "how do I measure a path across a groove") is the change closest
to this document's question, and it is not a new worked example.

**The groove/rib/joint/screw-head/floating-part worked-example set itself was located directly, by
table of contents and figure list, in both editions** (the actual clause body text is beyond the
paywalled preview's page range in both fetched documents, so this is TOC/figure-caption evidence,
not full-body-text confirmation -- stated plainly, not hidden): the measurement-method content
formerly under the 2002 text's clause 4.2 now lives under **clause 6.8 "Measurement of clearances
and creepage distances"** (renumbered as part of item (b)'s "new structure for Clauses 4 and 5" --
the content moved into a later-numbered clause 6, not clauses 4/5 themselves), immediately followed
by:

```
Table 1 -- Dimensioning of grooves ......................................... 46
Figure 4 -- Across the groove ............................................... 46
Figure 5 -- Contour of the groove ............................................ 47
Figure 6 -- Contour of the groove with angle ................................. 47
Figure 7 -- Contour of rib .................................................... 47
Figure 8 -- Uncemented joint with grooves less than X ......................... 48
Figure 9 -- Uncemented joint with grooves equal to or more than X ............. 48
Figure 10 -- Uncemented joint with a groove on one side less than X ........... 49
Figure 11 -- Creepage distance and clearance through an uncemented joint ...... 49
Figure 12 -- Creepage distance and clearance to a head of screw more than X ... 49
Figure 13 -- Creepage distance and clearance to a head of screw less than X ... 50
Figure 14 -- Creepage distance and clearance with conductive floating part .... 50
```
(IEC 60664-1:2020 TOC, page numbers as printed; the 3.1:2025 consolidated preview's TOC lists the
identical 11 figures and identical captions, at shifted page numbers only.)

**This is exactly 11 figures/examples -- the same count PR #1155 reported reading in full from the
2002-era text ("All 11 of clause 4.2's worked examples were read this session").** Every caption
describes an infinite-cross-section groove, rib, joint, or screw head, the same as the 2002 text;
none is captioned as an island, bounded, or finite cutout with two ends. A new bounded-slot example,
had one been added, would appear as a new numbered figure in this list (e.g. "Figure 15") -- there
is none. Converging with the foreword's own complete change-list (which does not mention grooves or
slots at all), this is strong -- though not full-body-text-literal -- evidence that **the current,
in-force edition of IEC 60664-1 has not added a bounded/island-slot worked example.** The reading
gap PR #1155 flagged is not a defect of citing an outdated edition; it is present in the current
edition too.

**IEC 60664-5** ("Comprehensive method for determining clearances and creepage distances equal to or
less than 2 mm") was also checked for scope applicability, not full text (WebSearch summary, not a
primary fetch -- flagged as the weaker-sourced claim in this section). Its own stated scope is
spacings **<=2mm**; every creepage figure in play here (baseline 8.1-9.1mm, slotted 14.1-15.5mm) is
3.5x-7.5x above that ceiling, so Part 5 does not govern this board's T1/U6/T2 question regardless of
what it says about grooves. Not relied upon for any load-bearing claim in this document.

**IEC 60335-1** (this project's own governing appliance standard, `docs/specs/HIGH_VOLTAGE_
CLEARANCE_SPEC.md:7`) has no independent creepage-measurement-geometry annex of its own for this
question -- its Clause 29 states minimum creepage *figures* (Table 17, already cited by this
project's spec) and cross-references IEC 60664-1/60664-3 for pollution degree, material group, and
(implicitly, since 60335-1 does not restate it) the geometric measurement method itself. It does not
supersede or extend the groove-measurement rule.

**Net effect on Question 1's second bullet:** checked directly, not assumed -- no edition of IEC
60664-1 (2002, 2007 by inference from the "cancels and replaces" statement, or the current
2020/2025 text), nor IEC 60664-5 (out of scope by spacing), nor IEC 60335-1's own text, resolves the
island/bounded-slot question either way. This is a genuine gap in the standard's own worked
examples, not a documentation gap in this repo.

---

## 3. What the measurement rule actually is, and the honest verdict

**What the standard unambiguously does say (both editions, PD3, X=1.5mm, re-verified this session
against the 2002-era primary text and cross-checked for figure/table continuity into the current
edition in §2):**

- Example 1: a groove narrower than X is bridged -- measured straight across, as if absent.
- Example 2: a groove `>= X` wide is followed by contour -- clearance is line-of-sight, creepage
  "follows the contour of the groove."
- The general principle governing every example: creepage is measured "when parts are in their most
  unfavorable position" -- i.e., along the *shortest available surface path*, whatever detour that
  requires.

**What the standard does not say, in any edition checked:** what "follows the contour" means when
the groove does not extend the full width of the insulating surface -- i.e., when the groove is a
bounded island with two ends rather than an edge-to-edge feature. Every one of the 11 examples, in
every edition, draws a 2D cross-section of a feature that is implicitly infinite in the third
dimension (a groove, rib, or joint running the full width of the part being sectioned). A PCB slot
milled under an SMD component is not that: it has two real ends, both still surrounded by solid
board.

**This document's own reasoning on the measurement question (DERIVED, same mechanism as both prior
sibling documents, not a new argument invented here):** creepage is defined as the shortest path
along a continuous insulating surface. A full-depth slot removes that surface entirely within its
own footprint -- there is no surface to walk along "over" or "through" the slot region by any
definition of creepage, because creepage is a *surface* distance and the surface is physically
gone there. The only two candidate paths are (a) down one wall, along the *underside* of the board,
and up the far wall -- which for a bounded island slot requires walking around the underside void
too, since the underside directly beneath the slot is the same hole, not a floor (this is the point
`docs/evidence/2026-07-28-isolator-creepage-slots.md` §3 already worked out and flagged as a
correction to `HIGH_VOLTAGE_CLEARANCE_SPEC.md` §6.1's uncited "2 x slot width + surface across slot"
formula, itself never corrected on this branch, confirmed by `git log --oneline -- docs/specs/
HIGH_VOLTAGE_CLEARANCE_SPEC.md` showing no commit since); or (b) around whichever end of the slot is
nearer, on the top surface, never leaving the continuous board surface that still exists there. Path
(b) is never longer than path (a) (going around the end adds zero board-thickness traversal; going
under adds two), so (b) is the true governing (shortest, per the standard's own "most unfavorable
position" -- read here as *most favorable to the current*, i.e. shortest -- principle) path. This is
consistent with, not a departure from, the standard's stated contour principle; it is simply applying
that principle to a geometry (an island) none of the standard's own pictures show.

**Verdict:** this is **not resolvable from the primary sources available**, in either direction.
§1 establishes the repo's own tool is the weaker-evidenced side of the internal disagreement
(uncited, contradicted by this repo's own one-day-older determination). §2 establishes the standard
itself -- current edition included -- simply does not picture this geometry. The physically-reasoned
derivation in this document and its predecessor is not naive: it correctly applies the standard's
stated general principle (shortest available surface path) to a case the standard's worked examples
don't cover, and it matches documented industry layout practice (isolator-IC application notes
routing a trace around a slot's rounded end on the top copper layer). But "consistent with the
standard's principle" and "explicitly validated by the standard's own text" are not the same claim,
and this document does not conflate them. **T1's and U6's slot-rescued creepage figures (14.1-15.5mm
worst-case) are DRC-passing under this document's and PR #1155's shared reading, and are NOT
established as compliance-closing** for a reinforced mains/SELV barrier.

### 3.4 What to ask a certification lab, and what to hand them

If this design is pursued, the question to put to the test house/certification body performing IEC
60335-1 review (framed to get a decisive, not a hedged, answer):

> "For a fully-through, full-board-thickness, non-plated PCB slot that does not reach the board's
> outer edge (a bounded/island cutout, both ends terminating inside the board, entirely underneath a
> surface-mount component's own body silhouette but clear of any solder pad or lead), is the
> governing creepage path from a pad on one side of the slot to a pad on the other (a) the
> straight-line distance ignoring the slot (i.e., the slot does not count because the path is
> considered to run under/through the component regardless), (b) a path that detours around the
> slot's nearest end and stays on the top surface, or (c) something else (e.g., is the slot
> disregarded entirely because it sits beneath a mounted body, on the theory that the moulded
> package itself -- not just the missing PCB material -- is part of what defines the creepage
> surface)? Please cite the specific clause/example (IEC 60664-1 or IEC 60335-1) your answer relies
> on, since clause 4.2/6.8's own worked examples do not appear to picture this exact geometry."

Evidence to supply with that question: (1) this document and PR #1155's full geometry (pad
positions, slot dimensions, worst-case fab tolerance model); (2) the component's actual mechanical
drawing/datasheet (Coilcraft CST3015 document 1608-2 for T1, UCC21550 datasheet Figure 34 for U6),
since the answer may hinge on standoff height and whether the moulded body is considered part of the
insulating boundary; (3) a physical sample or accurate 3D render showing the slot fully milled with
the part unmounted, so the lab can see there is no ambiguity about "is there really no floor."

---

## 4. T1's structural question: what supports it, what this repo can and cannot analyze, and whether a smaller slot exists

### 4.1 What supports T1 after the slot -- measured directly from the real footprint file

`pcb/libs/temper.pretty/CST3015.kicad_mod`, read in full this session:

```
(pad "1" smd rect (at 7.68 -6.85) (size 9.0 4.8) (layers "F.Cu" "F.Paste" "F.Mask"))
(pad "2" smd rect (at -7.68 -6.85) (size 9.0 4.8) (layers "F.Cu" "F.Paste" "F.Mask"))
(pad "3" smd rect (at -6.88 6.95) (size 3.0 4.6) (layers "F.Cu" "F.Paste" "F.Mask"))
(pad "4" smd rect (at 6.88 6.95) (size 3.0 4.6) (layers "F.Cu" "F.Paste" "F.Mask"))
```

**T1 is SMD-only: four rectangular reflow pads, nothing else.** No `thru_hole` or `np_thru_hole` pad,
no locating peg, no adhesive-dot callout, no standoff feature anywhere in the footprint file --
checked directly, not inferred. `F.Fab` body outline is `x=[-11.5,11.5] y=[-15.0,15.0]` (23.0 x
30.0mm, matching the part's datasheet body size per the footprint's own `descr`); courtyard is
`x=[-12.43,12.43] y=[-15.25,15.25]`. **The part's entire mechanical retention is its four solder
joints.**

PR #1155's slot, `x=[-14.0,14.0] y=[-4.0,4.0]`, sits **entirely inside the gap between the two pad
rows** (primary at y=[-9.25,-4.45], secondary at y=[4.65,9.25] -- both derived directly from the pad
centers/sizes above). Both pad rows, and therefore all four solder joints, remain on solid,
four-layer, full-board-thickness FR4, with normal copper/plating support -- **the slot never removes
material a pad or lead relies on.** The removed area (28.0 x 8.0mm = 224mm²) is roughly a third of the
23 x 30mm = 690mm² body footprint (224/690 = 32.5%), independently reproducing PR #1155's own "roughly
a third" figure (§4.4 of that document).

### 4.2 Does this repo have any structural/mechanical/FEA capability or precedent? -- exhaustive search, confirmed empty

```
$ grep -rli "fea\b|finite element|structural analysis|mechanical analysis|vibration|fatigue|solder joint" docs/ scripts/
```

**No hit anywhere in either tree** for FEA, finite-element, structural/mechanical stress analysis,
vibration/shock qualification, or solder-joint fatigue, beyond substring false-positives on unrelated
senses (`docs/hardware/PART_STRESS_AUDIT.md` is electrical part-stress derating, not mechanical;
`scripts/mpn_fabrication_gate.py` is part-sourcing, not fabrication mechanics). `docs/hardware/`,
`docs/specs/`, and the assembly documentation were checked directly for mounting-hole/standoff/
chassis-mount notes, board-thickness rigidity analysis beyond the bare `(general (thickness 1.6))`
declaration in the board file itself, and any vibration/shock spec for shipping or cooktop-operation
handling -- none exists. **The only precedent for a board cutout under a component anywhere in this
repo's history is the qualitative U7/U3 note `docs/evidence/2026-07-28-isolator-creepage-slots.md`
§4.3 already gives** ("Board rigidity was assessed qualitatively... not via structural/FEA analysis"),
already cited by PR #1155; nothing beyond it exists. **This repo has zero structural/mechanical
analysis capability, for any component, board-wide** -- a real gap, not a hidden one. If this
determination needs to close further than qualitative reasoning, that capability would need to be
built or outsourced (an actual FEA workflow, or a mechanical-engineering/certification consultant).

### 4.3 Characterizing the real concern -- explicitly qualitative engineering judgment, not a measured or cited fact

Three candidate failure mechanisms, assessed against the geometry in §4.1:

- **(a) Board/substrate integrity (cracking, excessive flex) -- LOW CONCERN.** The slot is entirely
  interior to the footprint, bordered by solid board on all four sides at real distances (0.45mm/
  0.65mm to the nearest pad edge per PR #1155 §4.1, and much more to the courtyard/board edges per
  §4.2 of that document). This is a hole cut in the middle of a supported plate, not a cantilevered or
  free-hanging tab -- and it is a materially easier case than the U7/U3 precedent already judged
  low-risk (U7's own slot ran to within 0.3mm of the board's outer edge; T1's is fully interior, with
  tens of millimetres of solid board to the nearest true edge).
- **(b) Solder-joint fatigue life for the four pads under thermal cycling -- THE REAL OPEN QUESTION.**
  An induction-cooktop controller sees repeated power on/off cycling and the CTE-driven expansion/
  contraction that comes with it. Removing FR4 from *between* the two pad rows (never under either
  row individually) reduces the local flexural stiffness of the board in the span between the two
  solder-joint groups by roughly a third of the footprint's area (§4.1), concentrated exactly in the
  region between them -- structurally closer to "a bridge with a soft middle span between two stiff
  piers" than to an unsupported overhang. A more compliant span between two rigid anchor groups is a
  physically plausible mechanism for concentrating cyclic strain at the joints themselves. This is a
  real, specific concern -- more specific than PR #1155's generic "no FEA was performed" flag -- but it
  is **reasoned, not measured**: no stiffness, strain, or cycle-life number has been computed, and this
  repo has no tool to compute one (§4.2).
- **(c) Part retention / pull-off -- LOW CONCERN, reduces to (b).** There is no adhesive or mechanical
  fastener to fail (§4.1); retention is entirely a function of solder-joint integrity, i.e. mechanism
  (b), not an independent failure mode.

**Conclusion: the open risk is (b), solder-joint thermal-cycling fatigue, not board cracking or part
retention as independent concerns.** This narrows PR #1155's flag but does not close it -- only an
actual mechanical/thermal-cycling review (FEA or a physical qualification sample) can do that, and
this repo has neither capability today.

### 4.4 Would a smaller or repositioned slot meaningfully reduce this risk?

PR #1155's own numbers already show the 28.0 x 8.0mm design is close to the minimum achievable at
real worst-case margin, not an unminimized first guess -- both of its two free dimensions are already
pinned against a real constraint, not chosen with slack:

- **Length is pinned by the worst-case-tolerance margin, not chosen loosely.** PR #1155 §4.1 found
  that stopping exactly at T1's own courtyard edge (half-length 12.43mm, vs. the chosen 14.0mm) gives
  only 12.617mm nominal creepage -- technically over 12.6mm but with a worst-case figure that fails
  outright. The chosen 14.0mm half-length (1.57mm past the courtyard on each end) is what survives
  JLCPCB's own ±0.2mm/edge worst-case tolerance with real headroom (14.83mm worst-case vs. 12.6mm
  required). Shrinking the length back toward the courtyard-edge minimum trades away exactly the
  margin that makes the design pass under pessimistic fab tolerance, for at most ~1.57 x 2 x 8.0 =
  ~25mm² of area savings (11% of the slot) before nominal creepage itself starts to fail.
- **Width is pinned by the pad gap itself, not by choice.** The slot must fit inside the 4.55mm real
  gap between the pad rows (primary inner edge y=-4.45, secondary inner edge y=4.65) while keeping
  >=0.2mm worst-case copper clearance to each row -- the 8.0mm width already leaves only 0.45mm/0.65mm
  nominal (0.25mm/0.45mm worst-case) to the nearer row. There is very little room to widen the
  clearance margin further without narrowing the slot toward JLCPCB's clearance floor on one side,
  and narrowing the slot *shortens* the around-the-end detour, working against the creepage margin at
  the same time it would reduce removed area -- the two constraints move in opposite directions, so
  there is no width choice that meaningfully helps both.
- **The gap between the pad rows is the hard floor on removable-area fraction.** Because the only
  available width for the slot is that 4.55mm gap, and the length is set by the courtyard-plus-margin
  requirement above, there is no rectangle placement that reaches 12.6mm with real worst-case margin
  while removing substantially less of the board area *between* the pad rows -- which is precisely the
  region §4.3(b)'s fatigue mechanism concerns. A ~10-15% smaller design (trading creepage margin down
  toward the 12.6mm floor) is geometrically possible but does not change the qualitative structural
  picture, since the mechanism scales with the *fraction of the inter-row span* affected, not with
  small changes in slot width once the slot already spans nearly the whole gap.

**Net finding: no meaningfully smaller slot exists that both clears 12.6mm with real worst-case
margin and removes substantially less material.** PR #1155's design is close to the achievable
minimum for its own margin requirements, not an unminimized starting point that a follow-up pass
could easily shrink.

---

## 5. Reroute achievability for U6's and T1's displaced tracks -- is "needs a reroute" actually cheap here?

This task's framing states "a parallel measurement found 40 nets currently have no legal routing path
at all on this board." **This document could not trace that figure to a source.** Searched
`docs/evidence/` on this worktree's own branch (`analysis/slot-creepage-rescue` / `fix/board-
schematic-resync`) for "40 nets", "no legal routing path", "unroutable", and "structurally
unroutable" -- no document with that figure. Checked the one other branch in this repo performing a
place-and-reroute experiment close in time to this task, `feat/board-place-and-reroute`
(`/home/bennet/Desktop/temper/.claude/worktrees/agent-a9db7d83e26a8a246`, commit `26469fd4a`,
2026-08-12) directly: its own evidence document, `docs/evidence/2026-08-12-place-and-reroute-
connectivity.md` (present, unmodified, in this worktree too), measures a **different** quantity on a
**different, not-landed** board state -- a full from-scratch re-place of all 168 components followed
by one fresh routing pass, reaching 34/112 (30.4%) nets *fully connected*. "Not yet fully connected
by one particular routing run on a from-scratch re-placed board" is not the same claim as
"structurally has no legal path at all," and that document neither uses the phrase "no legal routing
path" nor reports a figure of 40. **This document does not confirm or refute the 40-nets claim -- its
source was not found in the branches available here, and that gap is reported rather than
papered over.**

**What this document does check directly: whether the six specific nets T1's and U6's reroutes touch
are implicated in any routing-difficulty finding that does exist.** PR #1155 names them exactly --
U6: `safety.uvlo_logic.mon-outa` (3 segments), `hb.gate_hs.driver-p2` (1 segment); T1: `safety.
uvlo_logic.mon-outa` (2 segments), `y` (1 segment), `hb.gate_hs.driver-p2` (8 segments), `sw` (1
segment). All four distinct net names confirmed present in the real, current `pcb/temper.kicad_pcb`
this session (`grep -n` for each, matching nets 145/59/161/150 respectively). The one concentrated
routing-difficulty finding this repo does have close to this board state --
`docs/evidence/2026-08-12-place-and-reroute-connectivity.md` §5's `clearance`-regression cluster,
"dominated by the `rtd_pan`/`SHUTDOWN`/`vcc`/`safety.ovp-line` cluster around `U27`... and `U26`" --
**names none of the four nets T1/U6's reroutes touch.** This is not a proof that a legal reroute
exists: the repo's actual structural-reachability tool
(`packages/temper-placer/src/temper_placer/router_v6/routability_check.py`'s `check_routability`) is
built on Stage-2 pipeline occupancy-grid state produced during a placement run, not something
invocable standalone against the already-placed, already-mostly-routed committed board file for a
bounded local reroute question, and it was not run here for that reason -- a real, stated gap, not a
hidden one. But combined with PR #1155's own measured real spare clearance in the exact direction
each reroute would need to extend beyond the new slot (U6: 8.95mm/4.90mm spare to the T1/J2
courtyards; T1: 6.43mm/14.83mm spare to the R6/C17 courtyards, both from PR #1155 §3.2/§4.2), there is
no evidence in this repo that these six nets belong to whatever set the "40 nets" figure describes.

**Recommended next step if this needs to be tightened**: run `check_routability` (or a bounded local
variant scoped to just the freed slot regions plus a margin) for exactly these six nets against the
real, current board's occupancy state -- a small, well-scoped extension of existing tooling, not a
new capability, and a cheaper check than a full place-and-reroute experiment.

---

## 6. What this changes and does not change

- **Does not change**: `HV_CREEPAGE_ENFORCED_MM`, any DRU threshold, `pcb/temper.kicad_pcb`, any
  footprint file, `elec/domain_manifest.yaml`, `scripts/measure_cross_domain_creepage.py`'s own
  code or behavior, or any ratchet ceiling. No slot was cut. This document does not weaken the
  tool's `body_crossing` classification (per this task's hard constraint) -- it argues the tool's
  classification was never designed to answer the compliance question PR #1155 and this document
  ask, using the tool's own docstring as the source for that argument, not a code change.
- **Does change**: PR #1155's two open questions are answered as far as primary-source research and
  repo-internal analysis can take them, without either side of Question 1 being manufactured. Q1 is
  now known to be **unresolvable from any edition of the governing standard** -- a checked, positive
  finding, not an absence of one -- with a specific certification-lab question and evidence package
  drafted (§3.4), and the repo's own contrary tool is now shown to be an uncited assumption that
  contradicts this repo's own earlier, more careful reasoning (§1), rather than an independent
  confirmation of the conservative reading. Q2's open structural risk is now identified specifically
  as **solder-joint thermal-cycling fatigue** (not board cracking, not part retention, both of which
  are now ruled low-risk with reasons given), confirmed **not** meaningfully reducible by a smaller
  slot design given PR #1155's own margin requirements (§4.4) -- so the remaining path to closing it
  is an external mechanical/thermal-cycling review, not further repo-side geometry work, and this
  repo has no capability to perform that review itself (§4.2). The reroute-achievability caveat is
  checked against the one related repo measurement that exists and found not to implicate any of the
  six nets actually in question (§5), though the "40 nets" figure's own source remains untraced.
- **T2 remains unchanged and out of scope**, exactly as it was for PR #1155 -- blocked by placement
  (PR #1144), not by creepage or structure, and neither question this document answers touches that
  blocker.

**Net verdict on whether this rescues T1/U6:** both remain **geometrically VIABLE, with the same two
caveats PR #1155 already carried, now sharpened rather than resolved** -- (1) the creepage credit
itself rests on a physically-reasoned derivation that no edition of the governing standard confirms
or denies, with a certification-lab question ready to ask (§3.4); (2) T1's specific structural risk
is solder-joint thermal-cycling fatigue, not the vaguer "no FEA was performed" of PR #1155, still
unclosed because this repo has no mechanical-analysis capability (§4.2-4.3). Neither caveat is closed
by this document, and neither should be read as closed by DRC-passing creepage numbers alone.

---

## Files

- This document: `docs/evidence/2026-08-13-hv-creepage-island-slot-and-t1-structural-determination.md`
- Extends, does not duplicate: `docs/evidence/2026-08-13-hv-creepage-slot-rescue-t1-t2-u6.md`
  (PR #1155 -- the two open questions this document resolves); `docs/evidence/2026-08-13-hv-
  creepage-pd3-gap-measurement-and-plan.md` (PR #1152 -- the original 9.100mm/8.100mm baselines);
  `docs/evidence/2026-07-28-isolator-creepage-slots.md` (the predecessor slot design, U7/U3, the
  same standards-reading gap first flagged); `docs/evidence/2026-07-28-conformal-coating-pd1.md`
  (the sibling document whose "a slot is a board feature and reaches under the body" reasoning
  contradicts `measure_cross_domain_creepage.py`'s docstring, §1); `scripts/measure_cross_domain_
  creepage.py` (git-history-traced, not modified); `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §6.1
  (its slot model, already flagged wrong by the predecessor document, remains uncorrected on this
  branch, confirmed by `git log`).
- Also extends: `docs/evidence/2026-08-12-place-and-reroute-connectivity.md` (the one related-but-
  distinct routing-connectivity measurement checked for net-name overlap in §5);
  `packages/temper-placer/src/temper_placer/router_v6/routability_check.py` (the repo's actual
  structural-reachability tool, checked and found not directly invocable for this bounded local
  question -- flagged as a recommended follow-up, §5).
- Primary sources fetched and read directly this session:
  - IS 15382 (Part 1):2003 = IEC 60664-1 (2002-era text), re-confirmed present via the predecessor
    documents' own citation, not re-fetched this session (no new claim needed beyond what PR #1155
    already verified).
  - IEC 60664-1:2020 (Edition 3.0), preview/foreword/TOC:
    `https://cdn.standards.iteh.ai/samples/100156/f010cc07edff461d9caa559635817555/IEC-60664-1-2020.pdf`
  - IEC 60664-1{ed3.1} (2025-05 consolidated), preview/foreword/TOC:
    `https://assets.vde-verlag.de/iec-normen/preview-pdf/info_iec60664-1%7Bed3.1%7Den.pdf`
  - IEC 60335-1:2020 (Edition 6.0), sample/normative-references list:
    `https://cdn.standards.iteh.ai/samples/101518/78945351a99747cd8a166a9ac8688b50/IEC-60335-1-2020.pdf`
  - `pcb/libs/temper.pretty/CST3015.kicad_mod` -- read directly this session for T1's real
    mechanical/footprint geometry.
- Measured this session, not committed (scratch, per this repo's own convention for read-only
  analysis scripts): the `measure_cross_domain_creepage.py` git-history/blame trace, the net-name
  grep against the real board for T1/U6's reroute nets.

## What is NOT established here (explicit)

- **No certification-lab confirmation of Question 1.** The specific question and evidence package are
  given in §3.4; obtaining an actual answer is outside this document's scope.
- **No FEA or physical thermal-cycling test for T1's slot.** §4.3(b) is qualitative engineering
  reasoning about mechanism, explicitly labeled as such, not a stress or cycle-life computation. This
  repo has no capability to produce one (§4.2).
- **The six reroute nets' legal-path existence is not formally proven**, only checked against the one
  related repo measurement that exists and found not to overlap with it (§5); `check_routability` was
  not run against the real board for these nets.
- **The "40 nets have no legal routing path" claim's source was not found** in the branches available
  to this worktree; it is neither confirmed nor refuted here.
- **PCBWay or another fab's tolerance/slot-clearance figures were not checked** (the same caveat PR
  #1155 already carried forward from its own predecessor document) -- does not affect Q1/Q2 directly,
  but §4.4's margin arithmetic still relies on JLCPCB's own published figures.
- **The IEC 60664-1:2020/2025 figure-list evidence in §2 is TOC/figure-caption evidence, not full
  clause body text** -- the paywalled preview documents fetched this session did not expose the full
  clause 6.8 text, only its foreword (full) and table of contents/figure list (complete for the
  relevant range). Stated as a limitation in §2, not hidden.
