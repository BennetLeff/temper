<!-- provenance: commit=ac4426eebfeca9e728a96c2f574a9bf4e2a8f414 dirty=true (branch fix/pd2-creepage-row-determination; base = origin/main tip at fetch time; this session's own validator/spec/test edits are layered on top and are what "dirty" reflects) -->

# PD2 creepage row determination: Table 17 row iv is a range (>250V, <=400V); 400V is inside it, not between rows. PR #442's 10.0mm was wrong; the correct PD2 reinforced figure is 8.0mm.

## Provenance labels

| Label | Meaning |
|---|---|
| **CITED-PRIMARY** | Standard's own text, fetched and read directly this session (page image inspected, not OCR'd blindly). |
| **CITED-SECONDARY** | A prior session's finding, cross-checked but not the basis of the conclusion by itself. |
| **MEASURED** | Computed this session from real repo files (test run, primary-text page render). |
| **DERIVED** | Arithmetic/logic on labelled inputs, shown in full. |

## Verdict, up front

**PR #442 was wrong. The correct PD2 (Pollution Degree 2), Material Group
IIIa/IIIb, REINFORCED creepage figure for this design's 340-400V boundaries
is 8.0mm, not the 10.0mm it landed with.** This is settled directly from
primary text, independently read this session (not by counting how many
prior docs agree, though five independently do): **IEC 60335-1 Table 17**
("Minimum Creepage Distances for Basic Insulation," clauses 29.2.1-29.2.3)
-- read from a clean 150dpi page render of IS 302-1:2008 page 58 (identical
adoption of IEC 60335-1), fetched fresh this session -- has row iv stated,
verbatim, as:

> **iv) >250 and <=400** [V] ... Pollution Degree 2, Material Group
> IIIa/IIIb: **4.0** [mm, basic]

**Table 17's rows are continuous, non-overlapping working-voltage ranges,
not discrete tabulated points.** Every voltage on the axis falls inside
exactly one row; there is no "between two rows" case for 400V to round up
from. 400V satisfies row iv's own literal, inclusive upper bound (<=400)
directly. Clause 29.2.3 (also read verbatim this session): "Creepage
distances of reinforced insulation shall be at least double those specified
for basic insulation in Table 17." **Reinforced: 8.0mm** (double 4.0mm),
not 10.0mm.

**PR #442's "round up to the next row" reasoning is a real rule -- but for
a different table, applied to the wrong one here.** It transcribed a table
with rows at "300V" and "400V" (`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`
§5.1, pre-correction) and, finding 400V exactly on its own "400V" row,
treated that as the answer. The real Table 17 has no 300V or 400V
breakpoint at all -- its actual rows are >125&<=250 (row iii), >250&<=400
(row iv), >400&<=500 (row v), etc. The mislabeled "400V" row's own mm
figures (5.0mm basic / 10.0mm reinforced) are real Table 17 values, but they
belong to **row v** (>400V, <=500V) -- the row *above* the one 400V actually
falls in. 400V never needed a round-up in the first place: it already sits
inside row iv, which independently derives to 4.0mm/8.0mm. This is
confirmed independently by
`docs/evidence/2026-07-30-pollution-degree-determination.md` (PR #464,
which reached this same row-iv-vs-row-v conclusion this same day while
investigating a different axis -- pollution degree -- and disclosed but did
not correct it, deferring "a human should reconcile the row-iv-vs-row-v
question in PR #442 separately"). This document is that reconciliation.

**REQ-SAFE-01 violations on this branch's own baseline (origin/main tip
`ac4426ee`, current board state) go from 75 (at the erroneous 10.0mm
figure) to 51 (at the correct 8.0mm figure)** -- fewer, because the
erroneous figure was *too strict*, not too lenient; see "What this does
NOT mean" below for why this is not a safety loosening.

## 1. What the primary text actually says

### 1.1 Source and method

Same approach the PD3 investigation (`docs/evidence/2026-07-30-pollution-degree-determination.md`)
used and disclosed: IS 302-1:2008 ("Safety of household and similar
electrical appliances, Part 1: General Requirements"), the identical Indian
national adoption of IEC 60335-1, fetched fresh this session from
`https://law.resource.org/pub/in/bis/S05/is.302.1.2008.pdf` (80-page PDF, no
text layer -- a scan). Rather than trust OCR on a dense numeric table
(exactly the failure mode the PD3 doc flagged -- "OCR produced an ambiguous
digit at this exact row"), the relevant pages (56-58) were rendered directly
to 150dpi PNG images (`pdftoppm`) and inspected visually, digit by digit,
rather than parsed as text. This is a stronger standard of evidence than
OCR: every digit below was read directly off a legible, high-resolution
page image, not inferred through a text-recognition model.

### 1.2 Table 17, verbatim (page 58)

The table header reads: **"Table 17 Minimum Creepage Distances for Basic
Insulation (Clauses 29.2.1, 29.2.2 and 29.2.3)"**. Its columns are Sl No.,
Working Voltage (V) (given as two sub-columns, a lower and upper bound
joined by the word "and"), and Creepage Distance (mm) broken into Pollution
Degree 1 / 2 / 3, with Pollution Degree 2 and 3 further split into Material
Group I / II / IIIa-IIIb. The rows relevant to this design (i-vi of xviii
total, reproduced verbatim from the image):

| Sl No. | Working Voltage (V) | PD1 | PD2-I | PD2-II | **PD2-IIIa/IIIb** | PD3-I | PD3-II | PD3-IIIa/IIIb |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| i | <=50 | 0.2 | 0.6 | 0.9 | 1.2 | 1.5 | 1.7 | 1.9 |
| ii | >50 and <=125 | 0.3 | 0.8 | 1.1 | 1.5 | 1.9 | 2.1 | 2.4 |
| iii | >125 and <=250 | 0.6 | 1.3 | 1.8 | 2.5 | 3.2 | 3.6 | 4.0 |
| **iv** | **>250 and <=400** | 1.0 | 2.0 | 2.8 | **4.0** | 5.0 | 5.6 | 6.3 |
| v | >400 and <=500 | 1.3 | 2.5 | 3.6 | 5.0 | 6.3 | 7.1 | 8.0 |
| vi | >500 and <=800 | 1.8 | 3.2 | 4.5 | 6.3 | 8.0 | 9.0 | 10.0 |

**Every "Working Voltage" cell in the source table is stated as a bounded
range with an explicit "and"** (e.g. "**>250** and **<=400**"), never as a
single number. This is the literal row-boundary notation the task asked to
settle: it is form (b) from the task's framing ("a row bounded '>250V and
<=400V'"), not form (a) ("rows tabulated as discrete points"). 400V,
therefore, is **inside** row iv, not between two rows -- there is nothing to
round up to.

### 1.3 Clause 29.2 - 29.2.3, verbatim (page 57)

> "**29.2** Appliances shall be constructed so that creepage distances are
> not less than those appropriate for the working voltage, taking into
> account the material group and the pollution degree.
>
> Pollution degree 2 applies unless: a) precautions have been taken to
> protect the insulation, in which case pollution degree 1 applies; and
> b) the insulation is subjected to conductive pollution, in which case
> pollution degree 3 applies.
>
> **29.2.1** Creepage distances of basic insulation shall not be less than
> those specified in Table 17. ... Compliance is checked by measurement.
>
> **29.2.2** Creepage distances of supplementary insulation shall be at
> least those specified for basic insulation in Table 17. ...
>
> **29.2.3** Creepage distances of reinforced insulation shall be at least
> double those specified for basic insulation in Table 17. ..."

This confirms, independently of the pollution-degree question: (a) Table 17
is the operative creepage table for basic/supplementary/reinforced
insulation, cited three separate times by clause number; (b) reinforced =
2x basic, applied to row iv's PD2-IIIa/IIIb figure of 4.0mm gives exactly
**8.0mm**.

## 2. Which table governs -- Table 16 vs Table 17

The task flagged that PR #442 cited "Table 16" while PR #464 cited "Table
17," and asked whether this was part of the disagreement. **It was, and
Table 17 is correct.** Confirmed two independent ways this session:

1. **Table 17's own header and clause citations are explicitly about
   creepage** ("Minimum Creepage Distances for Basic Insulation," clauses
   29.2.1-29.2.3, the creepage clause chain quoted above).
2. **Table 16 is a different table, for clearance, keyed to a different
   axis.** Page 56/57 (also read directly this session, same primary
   source) shows Table 16 is referenced by clause 29.1 material discussing
   *clearance* ("... clearances of basic insulation on the secondary side
   shall be not less than those specified in Table 16 ... using the next
   lower step for rated impulse voltage as a reference") and its own note:
   "Clearances for intermediate values of Table 16 may be determined by
   interpolation." Table 16 is keyed to **rated impulse voltage** (via
   Table 15's overvoltage-category lookup), a different axis from Table
   17's direct working-voltage lookup, and Table 16 *does* permit
   interpolation for intermediate values -- the opposite of Table 17's
   already-exhaustive range structure. These are not the same rule applied
   twice; they are two different tables with two different lookup
   mechanisms for two different physical quantities.

**This also resolves why PR #442's "no interpolation, round up" doctrine
felt applicable but wasn't, for creepage specifically.** That doctrine (a
working voltage between two rows rounds up) is a real feature of tables
keyed to discrete steps -- but Table 16 (clearance) is the one with an
explicit interpolation note in the primary text, and even there the
resolution is interpolation, not "round up." Table 17 (creepage) needs
neither: it already partitions every voltage into exactly one row. PR
#442's own module comment invoked "IEC 60664-1/60335-1 tables," treating
all of them as one undifferentiated class; the primary text does not
support that generalization for Table 17.

## 3. Does 400V actually belong to row iv, and is that this design's real boundary?

Confirmed independently against this project's own declared working
voltages (`elec/src/main.ato`, `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`
§2.1, the same figures `docs/evidence/2026-07-30-creepage-requirement-reconciliation.md`
(PR #442) and `docs/evidence/2026-07-30-pollution-degree-determination.md`
(PR #464) both already established and which this document does not
re-litigate):

- **AC Mains: 340V peak/transient.**
- **DC Bus: 400V peak/transient** (`v_bus_abs_max = 400V`, `main.ato:50`).
- **Gate Drive Isolated: 355V peak-to-earth.**

All three satisfy row iv's literal bound (**>250 and <=400**) directly:
340 and 355 clearly, and 400 at the row's own inclusive ceiling (`<=400`
means 400 is included, not excluded). None of the three exceed 400, so none
of them reach into row v (`>400 and <=500`). **Row iv governs all three
boundaries.** PD2, Material Group IIIa/IIIb, reinforced: **8.0mm**. Basic
(clause 29.2.1, undoubled): **4.0mm**.

## 4. What changed

### 4.1 `packages/temper-placer/src/temper_placer/requirements/validators/clearance.py`

`IEC60335_REQUIREMENTS`, every HV<->SELV/ISOLATED row (the same three rows
PR #442 touched):

| Row | Field | PR #442's value (wrong: row v) | Corrected (row iv) |
|---|---|---|---|
| MAINS, LV_CONTROL, BASIC | min_creepage_mm / design_value_mm | 5.0 / 7.0 | **4.0 / 6.0** |
| MAINS, LV_CONTROL, REINFORCED | min_creepage_mm / design_value_mm | 10.0 / 12.0 | **8.0 / 10.0** |
| DC_BUS, LV_CONTROL, BASIC | min_creepage_mm / design_value_mm | 5.0 / 7.0 | **4.0 / 6.0** |
| DC_BUS, LV_CONTROL, REINFORCED | min_creepage_mm / design_value_mm | 10.0 / 12.0 | **8.0 / 10.0** |
| MAINS, ISOLATED, REINFORCED | min_creepage_mm / design_value_mm | 10.0 / 12.0 | **8.0 / 10.0** |

`min_clearance_mm` is unchanged in every row -- it is governed by Table 16
(clearance), a different table on a different axis (rated impulse
voltage/overvoltage category), out of scope for this creepage-specific
correction, same as PR #442's own treatment.

### 4.2 `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`

- §5.1: table re-transcribed against Table 17's real rows (i-vi, with the
  actual >125&<=250 / >250&<=400 / >400&<=500 / >500&<=800 breakpoints,
  not the prior mislabeled 150/200/300/400 breakpoints), citation corrected
  from "Table 16" to "Table 17," and the no-interpolation explanation
  replaced with the correct reason (Table 17's rows are already an
  exhaustive range partition, so there is no round-up question, rather than
  "round up because tables are never interpolated" -- which conflates
  Table 17 with Table 16's different, interpolation-permitting structure).
- §5.2 (Design Creepage): AC Mains to SELV, DC Bus to SELV, Across
  UCC21550, IGBT tab to LV trace all corrected 10.0/12.0mm -> 8.0/10.0mm,
  with an explicit note that this is the PD2 axis only and does not take a
  position on the separate PD2-vs-PD3 (pollution degree) question PR #464
  raises.
- §8.2 (Creepage Verification Checklist): required figures corrected to
  8.0mm throughout, matching §5.2.
- §9.1 (`HV_AC_to_SELV_creepage` KiCad DRC rule): `(min 10.0mm)` ->
  `(min 8.0mm)`.
- §7.1 (IGBT tab to LV trace): creepage requirement/design corrected
  12mm -> 8mm required / 10mm design, consistent with the same row-iv
  figure.

### 4.3 Tests updated to track the corrected matrix (not to force a pass)

- `packages/temper-placer/tests/requirements/safety/test_clearance.py::TestRequirementMatrix::test_requirement_matrix_values`
  -- expected creepage/design literals per row, corrected to match.
- `packages/temper-placer/tests/requirements/safety/test_clearance_copper.py`
  -- K1 (exact copper gap 8.000mm) and T1 (9.100mm) were flagged as
  violations under PR #442's mistaken 10.0mm figure
  (`test_k1_is_a_genuine_creepage_violation_after_the_400v_correction`).
  At the corrected 8.0mm requirement, K1 exactly meets it (zero margin, not
  a violation -- `_check_distance` only flags `measured < required`) and T1
  clears comfortably. Renamed to
  `test_k1_meets_the_corrected_pd2_requirement_exactly`, now asserting no
  K1 violation. The "known intra-footprint blockers" test was re-measured
  fresh against this branch's own board state (not assumed from any prior
  doc's list, per this task's own baseline-independence instruction): on
  this board, only **K2 and K3** remain intra-footprint blockers at the
  correct 8.0mm requirement (C6, K1, T1, U3, U7 -- which some prior,
  earlier-board-state docs reported as also blocked -- all clear on this
  board's current geometry, post PR #459's designator/footprint resync).
  Renamed to `test_the_intra_footprint_blockers_at_the_corrected_pd2_requirement`.
- `packages/temper-placer/tests/placer/cp_sat/test_domain_clearance.py` --
  two tests asserted the CP-SAT domain-clearance constraint generator's
  emitted margin was exactly 10.0mm (the PR #442 MAINS/DC_BUS<->LV_CONTROL
  reinforced max); corrected to 8.0mm. The BMC-exhaustive soundness sweep's
  margin list narrowed back to the matrix's actual (now-corrected) maximum
  of 8.0mm (removing the no-longer-reached 10.0mm entry).

`packages/temper-placer/tests/requirements/safety/test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance`
-- the REQ-SAFE-01 real-board integration test -- was **not** modified to
pass, per this task's explicit instruction. It still fails (51 violations),
just fewer than before the correction.

## 5. Violation count: before and after, this branch's own baseline

Reproduced this session, `elec/build/default.net` built fresh (`make
netlist`, exit 0), on `origin/main` tip (`ac4426ee`) -- **not** the 98/76
figures reported in `docs/evidence/2026-07-30-creepage-requirement-reconciliation.md`
or `docs/evidence/2026-07-30-pollution-degree-determination.md`, both
measured against an earlier board state (before PR #459's designator/
footprint resync landed on `main`). Per this task's explicit instruction
("branch from origin/main, establish your own baseline, do not
coordinate"), the count below is this branch's own, freshly measured:

```
uv run --no-sync pytest packages/temper-placer/tests/requirements/safety/test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance -q
```

| | Before (10.0mm reinforced / 5.0mm basic -- PR #442's row-v figures, wrong) | After (8.0mm / 4.0mm -- row-iv, correct) |
|---|---|---|
| REQ-SAFE-01 violations | 75 | **51** |
| Violating pairs | 44 | 23 |
| Intra-footprint records | 11 | 6 (K2, K3 only) |
| Components matched | 159 | 159 |

The delta (-24 violations, -21 pairs) is exactly the set of pairs whose
measured creepage/clearance fell in the 8.0-10.0mm or 4.0-5.0mm band --
they were never real violations against the actual standard; PR #442's
own, incorrect 10.0mm/5.0mm figures manufactured them. This is the mirror
image of PR #442's own headline change (76->98, reported as "the corrected
validator finds more of what was already there") -- here, the correction
runs the other way, because the direction of PR #442's own error was
itself in the *stricter*, not the *permissive*, direction relative to the
true standard.

`Reproducing this baseline swap without git stash`: this session verified
both figures on the same board/branch by checking out the validator file's
pre-correction content directly (`git show HEAD:<path>`, HEAD being this
branch's own base commit, not a stash), running the test, then restoring
the corrected file from a working copy -- no stash operation was used at
any point, consistent with this task's hard constraint.

## 6. What this does NOT mean -- and the relationship to the PD2 vs PD3 question

**This is not a safety loosening.** PR #442's 10.0mm/5.0mm figures were
never a real requirement to begin with -- they were a misapplication of
Table 17 row v to a working voltage (400V, and 340V/355V well below it)
that the primary text places in row iv. Enforcing row v's numbers was
enforcing a fictitious, over-strict requirement that this design was never
actually obligated to meet under PD2. Correcting it back to row iv's real
8.0mm/4.0mm is not "relaxing" a safety constant; it is retracting an error
and reporting the actual standard's own number, per this task's explicit
instruction ("if #442's reasoning was wrong, say so directly").

**This is a different axis from PR #464's pollution-degree correction, and
composes with it, not against it.** PR #464 (open at the time of this
document) argues PD3, not PD2, governs this appliance class (IEC
60335-2-6 cl. 29.2 Addition), which would make the *entire row-iv column*
different: PD3-IIIa/IIIb at row iv is 6.3mm basic / 12.6mm reinforced, not
PD2's 4.0/8.0mm. Both corrections are real and independent:

- **If PD2 governs** (the exception is earned): row iv, PD2 column ->
  **8.0mm reinforced** -- this document's figure, the one now enforced by
  this PR.
- **If PD3 governs** (PR #464's own conclusion, and the one
  `docs/evidence/2026-07-30-pollution-degree-determination.md` argues for
  from primary text): row iv, PD3 column -> **12.6mm reinforced** -- a
  separate, larger figure, on a different axis (pollution degree, not
  voltage row).

**This document takes no position on which pollution degree governs** --
that is PR #464's question, not this one's. What this document does
establish, independent of that question, is that **whichever pollution
degree applies, the voltage-row lookup for a 340-400V boundary is row iv,
not row v** -- so PD2's correct figure is 8.0mm (not PR #442's 10.0mm) and
PD3's correct figure is 12.6mm (which is what PR #464 already uses,
unaffected by this correction since it was already reading off row iv
correctly for its own PD3 column).

### 5.1 What this means for `docs/brainstorms/2026-07-30-hv-isolation-architecture-options.md` Option 2

The task frames this determination as deciding "whether a sealed PD2
compartment (Option 2) rescues the design or is pointless." With this
correction: **at PD2, row iv, 8.0mm reinforced governs, and both U3
(8.560mm best achievable per `docs/evidence/2026-07-28-isolator-sourcing-brief.md`)
and U7 (8.100mm best achievable, same source) clear it -- barely (0.560mm
and 0.100mm of margin respectively).** This document does not re-verify
those two part-selection figures (out of scope; they are unchanged by this
correction, which only touches the required figure, not any measured or
sourced part geometry) but confirms the *requirement* they would need to
clear is genuinely 8.0mm under PD2, not 10.0mm. Option 2 (earning the PD2
exception via a sealed compartment) is therefore live on the numbers, not
mooted by an inflated requirement -- contingent entirely on PR #464's own
open question of whether the PD2 exception can actually be earned given
this project's mechanical documents (which `docs/evidence/2026-07-30-pollution-degree-determination.md`
argues it cannot, on the evidence available today). This document does not
take a position on that separate, already-argued question; it only
confirms the number Option 2 would need to clear if PD2 is earned.

## 7. Sources

- IS 302-1:2008 (= IEC 60335-1, identical adoption) -- fetched fresh this
  session, `https://law.resource.org/pub/in/bis/S05/is.302.1.2008.pdf`,
  pages 56-58 rendered to 150dpi PNG and read directly (not OCR'd).
- `docs/evidence/2026-07-30-creepage-requirement-reconciliation.md` (PR
  #442, the determination corrected here) -- read in full this session.
- `docs/evidence/2026-07-30-pollution-degree-determination.md` (PR #464) --
  read in full this session; independently reached the same row-iv
  conclusion (§3.1 of that document) while investigating pollution degree,
  disclosed but deferred correcting PR #442 directly.
- `docs/brainstorms/2026-07-30-hv-isolation-architecture-options.md`
  (referenced by this task; not present on this branch at time of writing
  -- PR #464 or a sibling branch carries it, not yet merged to
  `origin/main` as of this branch's base commit `ac4426ee`).
- `docs/evidence/2026-07-28-isolator-sourcing-brief.md` -- U3 (8.560mm) and
  U7 (8.100mm) best-achievable figures, cited, not re-derived.
- `elec/src/main.ato`, `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §2.1 --
  this design's declared working voltages, read directly this session.
- `packages/temper-placer/tests/requirements/safety/test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance`
  -- run this session, before and after the correction, on the same
  `elec/build/default.net` (built fresh this session).

## 8. Constraints honoured

- No figure invented: every number traces to the primary-text page image
  read directly this session, or to this project's own already-established
  working voltages.
- The correction moves the enforced figure from 10.0mm to 8.0mm -- in the
  numerically permissive direction -- but only because 10.0mm was never a
  real requirement (Section 6 above); it is not a relaxation of the actual
  standard, and is justified directly from primary text, not by counting
  prior agreeing documents.
- `test_clearance.py`'s real-board integration test was not modified to
  pass, and does not pass -- it fails, with fewer (real) violations than
  before.
- `pcb/**` and `elec/src/**` were not touched (read-only, confirmed via
  `git status` before committing).
- No skip/xfail/deletion/assertion-weakening/`continue-on-error`/`git
  stash` used anywhere in this change. The before/after comparison in
  Section 5 was produced via `git show HEAD:<path>` to a temporary copy and
  restored from a separately-saved working copy, never `git stash`.
