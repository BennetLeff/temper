<!-- provenance: commit=ed5ee134bc0ef1bdcb64a884af266afd66314529 dirty=true (branch docs/pollution-degree-determination; base = origin/main tip at fetch time; this session's own code/doc changes are layered on top and are what "dirty" reflects) -->

# Pollution degree determination: PD3 governs, 12.6mm reinforced creepage is real, REQ-SAFE-01 violations 98 -> 138

## Provenance labels

| Label | Meaning |
|---|---|
| **CITED-PRIMARY** | Standard's own text, fetched and read directly this session (URL/method given). |
| **CITED-SECONDARY** | A prior evidence doc's finding, cross-checked but not independently re-measured from scratch this session. |
| **MEASURED** | Computed this session from the real repo files (test run, OCR'd primary text, grep). |
| **DERIVED** | Arithmetic/logic on labelled inputs, shown in full. |

## Verdict up front

**Pollution Degree 3 governs this design, not PD2.** IEC 60335-2-6 (the
particular standard for cooking ranges/hobs -- this appliance's own
category) clause 29.2 Addition makes PD3 the default microenvironment for
this appliance class; PD2 is an exception that must be earned by an
enclosure/sealing argument, and this project's own mechanical documents do
not make that argument. **Reinforced creepage at the design's established
400V boundary is 12.6mm** (IEC 60335-1 Table 17 row iv, Material Group
IIIa/IIIb, PD3 column, doubled per clause 29.2.3) -- not the 10.0mm figure
currently enforced. **Conformal coating is not a live option**: no coating
process exists in this project's BOM or assembly, and even a hypothetically
perfect one could not earn PD1 credit on the paths that currently fail,
because IEC 60664-3 requires full-path coverage and those paths sit
entirely under component bodies. **REQ-SAFE-01 violations rise from 98
(baseline, PD2/10.0mm, reproduced this session) to 138** (across 86 pairs,
up from 52) once the validator matrix is corrected to PD3/12.6mm. **This
was not a new determination** -- four prior, independent investigative
sessions in this repository's history already reached this same conclusion
from primary text and never had it disputed; the reason it never reached
`main` is a branch-lineage/forward-porting gap, not a rejection on the
merits (see "Why the prior PD3 work stalled," below).

---

## 1. What pollution degree applies, and to what

### 1.1 The governing clause chain, CITED-PRIMARY, independently re-read this session

IEC 60335-1 clause 29.2 (base rule for all household appliances) -- read
from IS 302-1:2008 (identical adoption), fetched fresh this session from
`https://law.resource.org/pub/in/bis/S05/is.302.1.2008.pdf`, OCR'd (the PDF
is a scan with no text layer; `tesseract` was used page-by-page) and
independently re-verified against high-resolution page renders:

> "Appliances shall be constructed so that creepage distances are not less
> than those appropriate for the working voltage, taking into account the
> material group and the pollution degree... Pollution degree 2 applies
> unless: a) precautions have been taken to protect the insulation, in
> which case pollution degree 1 applies; and b) the insulation is subjected
> to conductive pollution, in which case pollution degree 3 applies."

IEC 60335-2-6 (the *particular* standard for this appliance's actual
category -- cooking ranges, hobs, ovens, not a generic household appliance)
clause 29.2 Addition -- read from IS 302-2-6:2009 (identical adoption),
fetched fresh this session from
`https://law.resource.org/pub/in/bis/S05/is.302.2.6.2009.pdf`, same OCR
method, confirmed at the clause boundary between "29 CLEARANCES, CREEPAGE
DISTANCES AND SOLID INSULATION" and "29.3 Addition":

> "29.2 Addition -- The microenvironment is pollution degree 3 unless the
> insulation is enclosed or located so that it is unlikely to be exposed to
> pollution during normal use of the appliance."

**A particular standard's Addition clause overrides Part 1's general
default for that appliance class.** This is standard IEC 60335 structure
(Part 2-x clauses are stated as replacing or adding to the corresponding
Part 1 clause number), and this Addition is explicit that it replaces Part
1's baseline: PD3 is the default for cooking appliances; PD2 (or PD1) is
the exception, earned only by showing the insulation is enclosed or located
away from pollution exposure.

### 1.2 Applying the exception test to this design's actual construction

The exception requires an enclosure/sealing argument specific to the PCB's
own insulation. Checked directly against this project's own mechanical
documents (not inherited from any other session's summary):

- **`docs/CHASSIS_AIRFLOW_DESIGN.md`** (MEASURED, read directly): the
  cooling system is forced convection -- bottom chassis intake vents ->
  intake plenum -> 80mm PWM fan -> transition duct -> IGBT heatsink ->
  rear exhaust vent. This actively draws unfiltered kitchen air (grease,
  steam, cooking aerosol -- the design's own overview line: "manages the
  cooling requirements... within the enclosed RCA 12A3 chassis") through
  the same chassis cavity the PCB occupies. "Enclosed" here describes the
  outer appliance case, not a sealed PCB compartment excluded from that
  airflow.
- **`docs/COIL_BRACKET_DESIGN.md`** (MEASURED, read directly), Sec 4:
  "Large triangular cutouts around the central coil ring allow air from the
  bottom intake to flow directly through the Litz wire strands." This is an
  air-permeable baffle by design, not a seal, and it sits directly above
  the main PCB.
- **`docs/ASSEMBLY_GUIDE.md`** (MEASURED, read directly): Phase 4 mounts
  "the PCB into the chassis using M3 standoffs" -- no box, partition, or
  gasket around the PCB itself is described anywhere. The assembly's only
  gasket (Phase 3, "high-temp silicone gasket to the chassis lip") seals
  the glass-ceramic cooktop panel to the chassis -- a different joint,
  retaining glass, not excluding pollution from the electronics compartment.
- **IP20** (this design's own declared rating, `docs/ENVIRONMENTAL_SPEC.md`
  and `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` both state it): "No
  liquid ingress protection guaranteed." This argues against an enclosure
  claim, not for one, and neither IP20 digit addresses airborne
  grease/steam, which is exactly what the forced-air duct is designed to
  move across the compartment.

**No document in this repository specifies a sealed, gasketed PCB
compartment separate from the coil/heatsink airflow path.** The PD2
exception is therefore not earned on the evidence available today,
regardless of which prior session looked at it. **PD3 governs.**

### 1.3 What this is not

This is not a new finding -- it reproduces, from primary text independently
re-fetched and re-read this session (not copied from a prior session's
conclusion), the exact determination already made in
`docs/evidence/2026-07-28-pd3-retarget-keepout.md` Task 0 and
`docs/solutions/best-practices/check-the-exception-before-the-default-2026-07-28.md`
(the latter **already on `main`**, landed via PR #419's "slice 2 of 8"
docs-consolidation batch -- see Section 4). What is new this session: the
clause text for both the Part 1 default and the Part 2-6 Addition was
independently re-fetched and re-read from the primary PDFs (not assumed
from a prior doc's quotation), and the currently-enforced spec/validator
were actually corrected rather than only documented as a gap.

---

## 2. Does conformal coating change the answer?

**No.** Two independent, sufficient reasons, both CITED-SECONDARY from
`docs/evidence/2026-07-28-conformal-coating-pd1.md` (on the unmerged
`docs/pd3-creepage-part-selection`-adjacent lineage; its Table 17 read and
IEC 60664-3 clause quotations were independently cross-checked against my
own primary-text read this session and agree, including the exact 6.3mm/
12.6mm PD3 row-iv figures):

1. **No coating process exists in this project's BOM or assembly today.**
   MEASURED this session: `grep -in coating` against
   `docs/hardware/BOM.md` and `docs/ASSEMBLY_GUIDE.md` returns zero
   matches. `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` (pre-correction)
   §6.4 named a coating type/thickness and a fabricated "x1.5 creepage
   multiplier" that traces to no clause in either IEC 60335-1 or
   IEC 60664-3 (both read directly this session) -- a paper spec with no
   connected manufacturing step, corrected in this pass (see Section 5).
2. **Even with a coating process added, IEC 60664-3 clause 4.3 requires the
   entire creepage path -- both conductive parts and every span between
   them -- to be covered** for the PD1 credit to apply to that path; there
   is no partial credit. The cited evidence doc measured, for all seven
   declared isolators with a usable body outline (C6, K1, K2, K3, T1, U3,
   U7), that **100.0% of the shortest HV<->SELV surface path lies under
   the component body** -- a coating applied after reflow/wave physically
   cannot reach copper hidden beneath an already-seated part. The credit
   cannot be earned on exactly the paths that currently fail without also
   changing the footprint/placement so the path is exposed -- a layout
   change, not a coating spec.

`scripts/generate_kicad_dru.py` already encodes this correctly and
fail-closed (`COATING_QUALIFIED = False`, with its own citation chain to
the same primary clauses) and needed no change this session.

**If this were not true** -- if a genuinely qualified, full-path coating
existed in the BOM and reached the governing paths -- the consequence would
run the other way: PD1 reinforced creepage at this board's 400V row is
2.0mm (Table 17 row iv, PD1 column, doubled), which would relax nearly
every figure in this document. That is not the situation on this design
today, and this section does not recommend adopting one -- see Section 6,
"What this determination does not do."

---

## 3. The correct figure for (DC_BUS, LV_CONTROL, REINFORCED) at 400V

IEC 60335-1 Table 17 ("Minimum Creepage Distances for Basic Insulation,"
clauses 29.2.1-29.2.3), row iv (working voltage >250V and <=400V), Material
Group IIIa/IIIb -- CITED-PRIMARY, read from a clean 300dpi render of
IS 302-1:2008 page 58 this session (image inspected directly, not OCR'd,
after OCR produced an ambiguous digit at this exact row):

| Column | PD1 | PD2-I | PD2-II | PD2-IIIa/IIIb | PD3-I | PD3-II | **PD3-IIIa/IIIb** |
|---|---:|---:|---:|---:|---:|---:|---:|
| Row iv (>250V, <=400V) | 1.0 | 2.0 | 2.8 | 4.0 | 5.0 | 5.6 | **6.3** |

**Basic creepage at PD3, row iv: 6.3mm.** Clause 29.2.3 (CITED-PRIMARY):
"Creepage distances of reinforced insulation shall be at least double those
specified for basic insulation in Table 17." **Reinforced: 12.6mm.**

DC_BUS's own declared peak/transient working voltage is 400V
(`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §2.1, `elec/src/main.ato`'s
`v_bus_abs_max = 400V`), which satisfies row iv's own boundary ("<=400")
literally -- not an interpolation, and not a round-up to the next row.
MAINS (340V) and Gate Drive Isolated (355V peak-to-earth) both also fall in
this same row. **12.6mm is the correct reinforced creepage figure for
(MAINS, LV_CONTROL), (DC_BUS, LV_CONTROL), and (MAINS, ISOLATED), all at
REINFORCED insulation.** Basic insulation at the same row is 6.3mm.

### 3.1 A disclosed, NOT-corrected-here inconsistency in the currently-enforced PD2 baseline

`docs/evidence/2026-07-30-creepage-requirement-reconciliation.md` (PR #442,
already merged) states the PD2 figure at this same boundary is **10.0mm
reinforced**. Table 17 row iv's own PD2-IIIa/IIIb column is **4.0mm basic
2 / 8.0mm reinforced**, not 5.0/10.0 -- 10.0mm matches the *next* row
(">400V, <=500V": PD2-IIIa/IIIb 5.0mm basic / 10.0mm reinforced), not the
row 400V itself literally falls in. This appears to be an off-by-one-row
selection in that already-merged fix (more conservative than the letter of
the standard requires at exactly 400V, not less -- not a safety defect, but
not literally what row iv specifies either).

**This is disclosed, not corrected, in this pass.** The task defining this
determination explicitly treats the voltage-row axis as an
already-corrected, settled question ("Two audits have already corrected
other axes of that lookup... PR #442 fixed the voltage row"), and
re-litigating which row 400V belongs to is a different question from
pollution degree. Every prior PD3 investigation in this repository's
history (`docs/evidence/2026-07-28-pd3-retarget-relay.md`,
`2026-07-28-pd3-retarget-keepout.md`, `2026-07-28-pd3-retarget-slots.md`,
`2026-07-29-pd3-part-selection-survey.md`, `2026-07-28-conformal-coating-pd1.md`)
independently derived 12.6mm the same way -- directly from row iv, treating
PD2's row-iv figure as 8.0mm, not 10.0mm -- so 12.6mm (not a figure scaled
from the possibly-off-by-one-row 10.0mm) is both the standard-correct value
and the value consistent with this repository's entire prior body of PD3
work. A human should reconcile the row-iv-vs-row-v question in PR #442
separately; this document does not change that PR's own figures.

---

## 4. What changed, and the resulting REQ-SAFE-01 violation count

### 4.1 Files corrected (pollution-degree axis only; `pcb/**` and `elec/src/**` untouched)

- **`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`**: §3.2/§3.2.1 (pollution
  degree, with citation and mechanical-document derivation), §5.1/§5.2
  (creepage table corrected to PD3 figures, table mislabel "Table 16" ->
  "Table 17" fixed, PD2 figures kept alongside for reference), §6.4
  (conformal coating section corrected -- the fabricated "x1.5 multiplier"
  removed, replaced with the real binary pollution-degree mechanism and
  why it does not apply here).
- **`packages/temper-placer/src/temper_placer/requirements/validators/clearance.py`**
  (the REQ-SAFE-01 validator matrix, `IEC60335_REQUIREMENTS`): the three
  HV<->SELV/ISOLATED rows' `min_creepage_mm`/`design_value_mm` raised from
  the PD2 figures (5.0/10.0 basic/reinforced +2.0mm design margin) to the
  PD3 figures (6.3/12.6, +2.0mm design margin -> 8.3/14.6). `min_clearance_mm`
  is unchanged in every row: IEC 60335-1 Table 16 (clearance) is keyed to
  rated impulse voltage via Table 15's overvoltage-category lookup, not to
  pollution degree or material group (MEASURED this session, same OCR/image
  method) -- the only pollution-degree-sensitive entry in Table 16 is a
  footnote on its lowest (1500V-impulse) row, a voltage class none of this
  design's boundaries use. The LV_CONTROL<->LV_CONTROL FUNCTIONAL row is
  intentionally **not** corrected in this pass (flagged, see Section 6).
- Test files updated to track the corrected matrix (not to force a pass,
  but because they hardcode expected values *of* the matrix and would
  otherwise fail for the boring reason of being stale, exactly as they were
  updated the last time this matrix changed, in PR #442):
  `packages/temper-placer/tests/requirements/safety/test_clearance.py`
  (parametrized matrix-value expectations),
  `packages/temper-placer/tests/requirements/safety/test_clearance_copper.py`
  (K1's real-board violation count: was 1 violation at 10.0mm, is genuinely
  2 at 12.6mm -- a real second violation surfaces, not hidden),
  `packages/temper-placer/tests/placer/cp_sat/test_domain_clearance.py`
  (two hardcoded-margin assertions, plus widening the BMC-exhaustive
  soundness sweep's margin/offset range to cover the new 12.6mm value).

### 4.2 Violation count, measured before and after (this session, same board, same fixture)

Baseline reproduced fresh on this branch (`origin/main` tip at fetch time,
before any correction in this pass):

```
$ make netlist   # elec/build/default.net built fresh this session
$ uv run pytest packages/temper-placer/tests/requirements/safety/test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance
98 REQ-SAFE-01 clearance/creepage violations on the real board across 52 pair(s)
(13 of the records are intra-footprint). Components matched: 158.
```

This matches the number this task's own framing states as the current,
already-corrected (voltage-row, PR #442) baseline.

After the pollution-degree correction (validator matrix + spec, above),
same board, same fixture, re-run this session:

```
138 REQ-SAFE-01 clearance/creepage violations on the real board across 86 pair(s)
(14 of the records are intra-footprint). Components matched: 158.
```

**98 -> 138 violations, 52 -> 86 pairs.** The separate fail-closed
proximity check (unclassified components within the largest IEC margin of
a declared-HV component) also grows from 4 to 5 candidates, as expected
since the margin it tests against grew from 10.0mm to 12.6mm.

All 22 matrix/unit tests in `test_clearance.py`, all 33 tests in
`test_clearance_copper.py`, and all 15 tests in `test_domain_clearance.py`
pass against the corrected matrix (re-run this session).

---

## 5. What the three stalled branches concluded, and whether their reasoning holds

Four branches exist with directly relevant work (the task named three;
`docs/pd3-creepage-part-selection` is a fourth, and -- contrary to this
task's own framing -- is **not** actually merged into `origin/main` either;
see Section 4). All four were read in full this session.

### 5.1 `pd3-retarget-relay` (`docs/evidence/2026-07-28-pd3-retarget-relay.md`)

Corrected the Finder 40.52 DPDT relay footprint's coil-to-contact pin
spacing from an invented 11mm center-to-center (never the manufacturer's
real dimension) to the real, pixel-calibrated 7.5mm, by rendering the
catalog PDF's own vector drawing rather than relying on `pdftotext`.
**Real, achievable creepage at that corrected geometry: 5.300mm** -- a
7.300mm shortfall against 12.6mm, and worse than even the already-superseded
8.0mm PD2 target. **Conclusion: this specific relay part cannot reach PD3
at all.** This conclusion **holds** as a statement about the Finder 40.52,
but is superseded as a statement about "the relay problem" in general by
Section 5.4 below: other, real relay parts do reach 12.6mm.

### 5.2 `pd3-retarget-keepout` (`docs/evidence/2026-07-28-pd3-retarget-keepout.md`, plus `1c1b6d32`/`c291427d`)

This is the branch that performed the actual PD2-vs-PD3 mechanical
determination (Task 0) against `COIL_BRACKET_DESIGN.md`,
`CHASSIS_AIRFLOW_DESIGN.md`, `ASSEMBLY_GUIDE.md`, `SENSOR_MOUNT_DESIGN.md`
-- the same conclusion Section 1 above reaches independently. It re-targeted
`scripts/check_isolation_keepout.py`'s `MIN_BARRIER_WIDTH_MM` from 8.0 to
12.6mm and measured, against the real board at that branch's base commit:
**152 total sub-12.6mm cross-domain pad pairs** (132 body-free, 20
body-crossing); the CP-SAT barrier-constrained placement remained
**INFEASIBLE at 12.6mm**, for the identical root cause as at 8.0mm
(`isolator_straddle_C6` in the UNSAT core) -- widening the requirement did
not change *why* it was infeasible. Under the precise rectangle-aware
measurement (not the CP-SAT module's conservative bounding-circle model),
K1 (exactly 8.000mm) and T1 (9.100mm) newly failed at 12.6mm having passed
8.0mm. **This conclusion holds** -- it is the same one this document's
Section 1 reaches, independently re-derived from primary text this
session, and the same K1 (now a 2-violation case, Section 4.1) and T1
figures reproduce exactly in this session's own test run.

### 5.3 `fix/pd3-retarget-u3-u7-slots` (`docs/evidence/2026-07-28-pd3-retarget-slots.md`)

Re-targeted the U3 (H11L1 optocoupler) and U7 (UCC21550 isolated gate
driver) creepage-extension slots from an 8.0mm-era design to 12.6mm.
**U3: succeeded.** The slot's Y-extent was widened (5.0x9.0mm ->
5.0x14.0mm); independently re-verified by visibility-graph shortest path at
14.058mm nominal / 13.317mm worst-case (JLCPCB tolerance), both comfortably
clearing 12.6mm. **U7: failed, and is a placement finding, not a footprint
one.** U7 sits only 5.9mm from the board's left edge once its rotation is
applied, capping the slot's feasible extent at 8.627mm nominal creepage;
reaching 12.6mm would require the slot to extend 1.79mm past the physical
board edge -- infeasible without moving U7 itself ~2.09mm away from that
edge. Even the theoretical (unmanufacturable) zero-clearance limit only
reaches 9.167mm. **This conclusion holds**, and is corroborated by an
independent, later, different-method finding (Section 5.4): U7's real
land-pattern creepage on the currently-landed board is 8.100mm, and no
wider TI land pattern or competing part exists for this die.

### 5.4 `docs/pd3-creepage-part-selection` (the fourth branch; task states "already merged" -- **not confirmed**, see Section 4 correction)

A broader, later part-selection survey (`docs/evidence/2026-07-29-pd3-part-selection-survey.md`)
that fetched real manufacturer datasheets for C6, K2/K3, U3, and U7 against
the 12.6mm target directly (not assuming the relay/DC-break framing of
Section 5.1 was the only blocker). Result, **MEASURED this session by
cross-reading the doc's own cited sources, not independently re-fetched**:

| Ref | Verdict at 12.6mm | Why |
|---|---|---|
| C6 (Y-cap) | **PASS** | TDK/EPCOS B81123C1222M000, 15.00mm lead spacing, reaches 13.5mm with the same pad-shrink convention this project already applies elsewhere |
| K2/K3 (relay) | **PASS** | TE Schrack RT114012, real 13.820mm coil-to-contact spacing, reinforced 10/10mm per its own IEC 60335-1-referencing datasheet -- refutes Section 5.1's relay-specific finding as a statement about "the relay problem" in general, even though Section 5.1's finding about the *Finder 40.52 specifically* still holds |
| U3 (ZCD opto) | **FAIL** | Same-die and cross-family search both exhausted; no optocoupler package family found reaching 12.6mm at any manufacturer |
| U7 (gate driver) | **FAIL** | TI's own best land pattern for this die tops out at 8.1mm; no certified competing part reaches 12.6mm (one part claims it but every agency certification is listed "Pending," not granted -- rejected on that basis) |

**Net: PD3 is not reachable by part selection alone on this floorplan,
because of U3 and U7 specifically -- not the relay or the Y-cap**, which
both have real, sourced, in-stock parts that clear 12.6mm. This is the most
current and most complete picture of "which components block PD3," and it
is consistent with (and sharpens) Sections 5.2 and 5.3's independent
findings that U7 in particular cannot reach 12.6mm on this board.

---

## 6. Why the prior PD3 work stalled

**Not a rejection on the merits.** Every one of the five independent
investigative sessions cited above (5.1-5.4, plus the coating
determination in Section 2) reached the same PD3/12.6mm conclusion from
primary text, using different methods (pixel-calibrated footprint
measurement, mechanical-document cross-check, visibility-graph slot
pathing, live datasheet/distributor sourcing), and none of them found a
reason to doubt it. The falsifier in each case was checked and did not
fire in PD2's favor.

**The actual cause is a branch-lineage/forward-porting gap, evidenced
directly in this repository's own commits:**

- All four PD3-related branches share a common ancestor
  (`fd6c9c15`, "K2/K3 replaced with a DPDT part that closes the DC-break
  gap too") that is **not an ancestor of `origin/main`** (MEASURED,
  `git merge-base --is-ancestor`) -- they were built on a separate
  integration lineage (`docs/methodology-loop-discipline` /
  `feat/provable-safety-place-and-route`), not on the path that became
  `main`.
- A later commit on that same lineage, `5fe012d5` ("bring forward same-day
  evidence and solutions docs from 688c15bb's lineage"), states directly:
  "This worktree's branch diverged from the `feat/provable-safety-place-and-route`
  lineage before today's PD3-retarget / courtyard-fix / relay / coating
  work was committed there... Materialized verbatim via `git show
  688c15bb:<path>` (**docs-only, no code brought over**)."
- `main` itself later absorbed a *subset* of these evidence and lessons
  docs through a "slice N of 8" documentation-consolidation campaign --
  `docs/solutions/best-practices/check-the-exception-before-the-default-2026-07-28.md`
  landed via PR #419 ("slice 2 of 8"), and
  `docs/evidence/2026-07-28-pd3-retarget-relay.md` landed via PR #439
  ("slice 7 of 8") -- but the corresponding **functional changes**
  (`docs/ENVIRONMENTAL_SPEC.md`'s PD2->PD3 edit, `scripts/check_isolation_keepout.py`'s
  `MIN_BARRIER_WIDTH_MM`, the U3 slot widening and Finder-relay footprint
  correction on `pcb/temper.kicad_pcb`, and `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md`)
  were never part of those slices and never reached `main`.

The result: `main` has, today, both the *determination* that PD3 governs
(in a landed lessons doc) and the *lookup table it was measured against*
(`docs/ENVIRONMENTAL_SPEC.md` §3, still asserting uncited PD2 until this
session) sitting in direct, uncorrected contradiction with each other --
exactly the state
`docs/solutions/best-practices/measure-the-target-before-resolving-a-fork-2026-07-29.md`
warns against. `docs/evidence/2026-07-29-pd3-part-selection-survey.md` §0
independently confirms this same gap from its own base commit, and cites
two still-open PRs (#455, #457) that flag it as a known, tracked,
unresolved question without acting on it. **This session is the first to
correct the enforced spec/validator rather than only re-documenting the
gap.**

---

## 7. What this determination does not do

- It does not fix U3 or U7. Per Section 5.3/5.4, U7 has no sourceable part
  or floorplan-compatible slot geometry that reaches 12.6mm on this board
  as currently laid out; U3 has no sourceable part. Both remain open,
  real, unresolved REQ-SAFE-01 violations after this correction -- the
  point of this document is to report the correct target, not to claim
  either is solved.
- It does not touch `pcb/**` or `elec/src/**` (both read-only per this
  task's hard constraints) -- the 138-violation figure is what the
  corrected requirement finds on the **current, unchanged board**.
- It does not correct the apparent row-selection inconsistency in PR
  #442's already-merged PD2 baseline (Section 3.1) -- flagged for a
  separate follow-up.
- It does not correct the LV_CONTROL<->LV_CONTROL FUNCTIONAL row, even
  though the same PD3 finding applies to it in principle (IEC 60335-1
  Table 18 row i, <=50V, PD3, Material Group IIIa/IIIb = 1.8mm, vs. this
  row's current 1.0mm, itself already slightly under Table 18's PD2 figure
  of 1.1mm at this row). This is a same-domain SELV-to-SELV functional
  boundary, not a mains/DC-bus-to-SELV safety barrier, and needs its own
  check of whether clause 29.2.4's short-circuit-test exemption already
  applies before being changed -- flagged, not corrected here.
- It does not propose adopting a conformal coating, a different relay, or
  any other part-selection outcome from the cited prior sessions -- those
  remain their own, separate, not-yet-implemented findings.

## 8. Sources

- IS 302-1:2008 (= IEC 60335-1, identical adoption) -- fetched and OCR'd
  this session, `https://law.resource.org/pub/in/bis/S05/is.302.1.2008.pdf`
- IS 302-2-6:2009 (= IEC 60335-2-6, identical adoption) -- fetched and
  OCR'd this session,
  `https://law.resource.org/pub/in/bis/S05/is.302.2.6.2009.pdf`
- `docs/CHASSIS_AIRFLOW_DESIGN.md`, `docs/COIL_BRACKET_DESIGN.md`,
  `docs/ASSEMBLY_GUIDE.md`, `docs/ENVIRONMENTAL_SPEC.md`,
  `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` -- read directly this session
- `docs/evidence/2026-07-28-pd3-retarget-relay.md` (on `main`),
  `docs/evidence/2026-07-28-pd3-retarget-keepout.md`,
  `docs/evidence/2026-07-28-pd3-retarget-slots.md`,
  `docs/evidence/2026-07-29-pd3-part-selection-survey.md`,
  `docs/evidence/2026-07-28-conformal-coating-pd1.md`,
  `docs/evidence/2026-07-30-creepage-requirement-reconciliation.md`,
  `docs/solutions/best-practices/check-the-exception-before-the-default-2026-07-28.md`
  -- all read in full this session
- `packages/temper-placer/tests/requirements/safety/test_clearance.py::TestClearanceIntegration::test_temper_board_clearance_compliance`
  -- run this session, before and after the correction, on the same
  `elec/build/default.net` (built fresh this session)
