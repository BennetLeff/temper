<!-- provenance: commit=019b43416f06440a430db574259fe47fb2515b43 dirty=false (branch docs/recover-standards-primary-text, base origin/main 756968706). This is a STANDARDS-TEXT determination, not a board measurement: nothing was measured on pcb/** and pcb/** was never opened for writing. Every voltage figure is quoted from docs/evidence/2026-08-12-hv-clearance-adequacy.md at commit de7d3a113 (PR #1080, branch analysis/hv-clearance-adequacy, not on main), read first-hand this session; no simulation was re-run here (ngspice is not installed in this environment -- `which ngspice` returns nothing -- so the 570.5 Vrms figure is CARRIED FORWARD, not independently reproduced). Primary text read this session from IS 302-1:2008, the Bureau of Indian Standards identical adoption of IEC 60335-1, published under India's RTI Act: <https://archive.org/download/gov.in.is.302.1.2008/is.302.1.2008_djvu.txt>, 312769 bytes, sha256=2695a4bc1b2c87dd24a6126d984d01ad30be53c8d905ff196b73241b73f99251 -- the same artifact and the same byte count docs/evidence/2026-07-28-conformal-coating-pd1.md records having read. It is an OCR'd scan of a 2008 (IEC 60335-1 Ed. 4.2-era) edition; see Sec 7 for what that costs. -->

# Clause 29.2.4 is recovered, and it does **not** exempt this pair. Functional insulation has its own creepage table — Table 18 — and at 570.5 Vrms Table 18 is **numerically identical to Table 17**. The exemption it offers is conditional on passing clause 19 with the gap short-circuited, a test nobody has run. The 6.3mm (PD2) / 10.0mm (PD3) requirement stands against 2.0mm provided.

**Verdict, up front.**

1. **The primary text is recovered.** IEC 60335-1 clause 29.2.4 reads, in full:
   *"Creepage distances of functional insulation shall be not less than those
   specified in Table 18. However, creepage distances may be reduced if the
   appliance complies with 19 with the functional insulation short-circuited.
   Compliance is checked by measurement."* Quoted verbatim from IS 302-1:2008.
   Sec 2.

2. **"Functional insulation" is the right classification, and it buys nothing
   here.** The clause does not waive creepage; it redirects it to **Table 18,
   Minimum Creepage Distances for Functional Insulation**, a table that has
   never been transcribed in this repository beyond one row. Transcribed in
   full in Sec 3. Its band **>500 and ≤800 V** reads **6.3mm** at PD2 /
   material group IIIa-IIIb and **10.0mm** at PD3 — **the same two numbers**
   `docs/evidence/2026-08-12-hv-clearance-adequacy.md` derived from Table 17.
   The reclassification changes the citation and not the figure.

3. **The reason it buys nothing is a 500 V cliff, and this board is 14% over
   it.** Table 18 *is* more lenient than Table 17 — but only below 500 V
   working voltage. From >500 V upward the two tables are **row-for-row
   identical to the bottom of both tables** (Sec 3.2, verified value-by-value
   from a single OCR pass so the comparison cannot be a cross-source artifact).
   Had the tank node measured ≤500 Vrms it would have taken Table 18's
   >400–500 row, 4.0mm PD2 / 6.3mm PD3, a genuine concession. It measures
   **570.5 Vrms**. The concession expires 70.5 V below the number.

4. **The exemption is a conditional, and the condition is unmet.** "May be
   reduced **if** the appliance complies with 19 with the functional insulation
   short-circuited" is a clause-19 abnormal-operation test, whose acceptance
   criteria are clause 19.13's: no flames, no molten metal, no ignitable gas in
   hazardous amounts, temperature rises within Table 9, and an electric
   strength test after cooling. **No such test, simulation, or analysis exists
   anywhere in this repository** (Sec 5.3). The exemption therefore does not
   apply to this pair today. It is *available* and, on my reading of the fault
   path, *plausibly winnable* — Sec 5 lays out how — but it is unearned.

5. **The direct answer to "functional, therefore exempt is not automatic."**
   The standard agrees, and says so structurally. Clause **19.11.2(a)** makes
   *"short circuit of functional insulation, **if clearances or creepage
   distances are less than the values specified in 29**"* a **mandatory** fault
   condition. The shortfall does not excuse the board from the requirement; it
   **triggers** an obligation. And the acceptance criterion for that fault
   condition is clause 19.13, which is a **fire** criterion. The task's worry —
   "a creepage breakdown across a resonant tank at 570 Vrms is a direct short
   across a high-energy circuit, and fire is a hazard IEC 60335-1 addresses in
   its own right" — is not an objection the standard overlooked. It is the
   exact thing the exemption's condition tests.

6. **So the finding for the owner stands, with its citation corrected.**
   Provided 2.0mm; required **6.3mm at PD2, 10.0mm at PD3**, per **Table 18**
   (functional), not Table 17 (basic). PD3 governs the as-built board
   (`docs/evidence/2026-08-11-pd2-decision-record.md:40-58`). **3.2× to 5.0×
   short**, on a distance no rule in this repository measures for this net pair.

7. **Two facts I could not establish, named rather than assumed.** (a) Whether
   the clause-19 route terminates the fault at all depends on the **mains fuse
   F1**, and F1's time-current behaviour against *this* fault has never been
   analysed — `elec/src/modules.ato:665-673` records, unresolved, that **"No I2t
   coordination analysis […] has been found anywhere in this repo"**, and
   `docs/hardware/BOM.md:77` records that F1's holder footprint is still a stub
   that does not match the real part's drilling diagram. The exemption's
   terminating mechanism is a component whose clearing behaviour is
   uncharacterised. (b) Whether IEC 60664-4 (>30 kHz
   stress) modifies any of these figures at 44–50 kHz; the string `60664-4`
   still appears zero times in this repository. Sec 6.

8. **Cite-to-nothing count.** 237 distinct `docs/evidence/` paths are cited from
   non-`docs/` code. **15 were absent from `origin/main`** — the 2 this PR
   recovers plus **13 others**, of which **8 are recoverable from side branches
   and 5 exist in no commit anywhere**. Four of the 13 are cited by
   `scripts/generate_kicad_dru.py` itself. Sec 8.

**Nothing is changed by this PR but the two recovered documents and this
determination.** No netclass value, no creepage constraint, no board file, no
constant, no gate.

---

## 1. What was missing, and where it was

`scripts/generate_kicad_dru.py` — the script that generates the DRC rules a
fabricator's board is checked against — cites two evidence documents seven
times between them, and neither had ever been on `main`. Not deleted:
`git log --all --diff-filter=D` returns nothing for either path. They were
authored on side branches and never merged.

| Path | Recovered at | Introduced | Branches carrying it |
|---|---|---|---|
| `docs/evidence/2026-07-28-creepage-determination-brainstorm.md` | `cbb0638fb` | `880405ed9` | `origin/docs/methodology-loop-discipline`, `origin/feat/provable-safety-place-and-route`, `origin/fix/strategy-board-facts-gate` |
| `docs/evidence/2026-07-28-conformal-coating-pd1.md` | `50df12f32` | `7994ce7dc` | `origin/docs/methodology-loop-discipline`, `origin/feat/provable-safety-place-and-route` |

Both are restored verbatim at their latest side-branch revisions, with one
disclosed one-line edit: the coating doc's provenance stamp carried an 8-char
SHA prefix (`f8b5f43c`), which `scripts/check_evidence_provenance.py` rejects
by design; it was expanded to the full SHA it already named
(`f8b5f43c235eb12cc3f4d7a9ecddc69d8b5a1d62`, verified by `git rev-parse`). Both
files now pass that gate. No normative quotation and no measurement was touched.

**What they contain that nothing else on `main` does:** IEC 60335-1 Table 15
(rated impulse voltage), Table 16 (clearances), **Table 17 in full** (basic
creepage), clauses 29.1 / 29.1.3 / 29.1.5 / 29.2 / 29.2.3, IEC 60335-2-6's
clause 29.2 Addition, and Annexes J / K / L / M. Every creepage and clearance
number this project has argued about for a month traces to those two files.

**What they do *not* contain, and why this document exists:** the text of
clause **29.2.4**. The coating doc's source inventory says it read
*"29.1, 29.2, 29.2.1–29.2.4"* (line 801), but it quotes only 29.2.1 and 29.2.3;
29.2.4 is named in that inventory line and nowhere else in either file.
Recovering the documents was therefore necessary but not sufficient, and the
prior determination's caveat survived the recovery. I went back to the same
primary source those documents cite and read the clause directly.

---

## 2. Clause 29.2.4 — the primary text

Read this session from IS 302-1:2008 (the BIS identical adoption of
IEC 60335-1), lines 8128–8133 of the archive.org OCR text layer. **Verbatim,
with OCR spacing normalised and OCR digit damage marked:**

> **29.2.4** Creepage distances of functional insulation shall be not less than
> those specified in Table 1[8]. However, creepage distances may be reduced if
> the appliance complies with 19 with the functional insulation
> short-circuited.
>
> Compliance is checked by measurement.

*(The OCR renders "Table 18" as "Table 1 8" — a space inside the numeral, the
same artifact it produces at "IS 1401" and "Table 1 6" elsewhere. Table 18
exists in the document, is titled "Minimum Creepage Distances for Functional
Insulation", and its own caption reads "(Clauses 29 2 A and L-2)" — OCR for
"(Clauses 29.2.4 and L-2)". The cross-reference is bidirectional and
unambiguous.)*

**The four immediate neighbours, for contrast — all verbatim from the same
pass:**

> **29.2.1** Creepage distances of basic insulation shall not be less than
> those specified in Table 17.
>
> Except for pollution degree 1, if the test of 14 has been used to check a
> particular clearance, the corresponding creepage distance shall not be less
> than the minimum dimension specified for the clearance of Table 16.

> **29.2.2** Creepage distances of supplementary insulation shall be at least
> those specified for basic insulation in Table 17.

> **29.2.3** Creepage distances of reinforced insulation shall be at least
> double those specified for basic insulation in Table 17.

And the **clearance** analogue, which is where the asymmetry that matters lives:

> **29.1.4** For functional insulation, the values of Table 16 are applicable.
> However, **clearances are not specified** if the appliance complies with 19
> with the functional insulation short-circuited. Lacquered conductors of
> windings are considered to be bare conductors.

**The wording difference is deliberate and it is the single most important
detail in this document.** For *clearance*, passing clause 19 short-circuited
means clearances *"are not specified"* — a waiver. For *creepage*, the same
condition means creepage *"may be reduced"* — not a waiver, and reduced to no
stated floor. Whatever else 29.2.4 does, it does not delete the creepage
requirement. Sec 4.2 takes up what "reduced" can mean.

**The definition that makes the classification, clause 3.3.5, verbatim:**

> **3.3.5 Functional Insulation** — Insulation between conductive parts of
> different potential which is necessary only for the proper functioning of the
> appliance.

---

## 3. Table 18 — transcribed in full, for the first time in this repository

### 3.1 The table

**IEC 60335-1 / IS 302-1:2008 Table 18, "Minimum Creepage Distances for
Functional Insulation" (Clauses 29.2.4 and L-2).** CITED-PRIMARY. Columns as
printed: pollution degree 1 (one column, material group not discriminated),
then pollution degree 2 and pollution degree 3 each split by material group
I / II / IIIa-IIIb. All values in mm.

| Working voltage (V) | PD1 | PD2 I | PD2 II | PD2 IIIa/IIIb | PD3 I | PD3 II | PD3 IIIa/IIIb |
|---|---:|---:|---:|---:|---:|---:|---:|
| ≤50 | 0.2 | 0.6 | 0.8 | 1.1 | 1.4 | 1.6 | 1.8 |
| >50 and ≤125 | 0.3 | 0.7 | 1.0 | 1.4 | 1.8 | 2.0 | 2.2 |
| >125 and ≤250 | 0.4 | 1.0 | 1.4 | 2.0 | 2.5 | 2.8 | 3.2 |
| >250 and ≤400 | 0.8 | 1.6 | 2.2 | 3.2 | 4.0 | 4.5 | 5.0 |
| >400 and ≤500 | 1.0 | 2.0 | 2.8 | 4.0 | 5.0 | 5.6 | 6.3 |
| **>500 and ≤800** | **1.8** | **3.2** | **4.5** | **6.3** | **8.0** | **9.0** | **10.0** |
| >800 and ≤1 000 | 2.4 | 4.0 | 5.6 | 8.0 | 10.0 | 11.0 | 12.5 |
| >1 000 and ≤1 250 | 3.2 | 5.0 | 7.1 | 10.0 | 12.5 | 14.0 | 16.0 |
| >1 250 and ≤1 600 | 4.2 | 6.3 | 9.0 | 12.5 | 16.0 | 18.0 | 20.0 |
| >1 600 and ≤2 000 | 5.6 | 8.0 | 11.0 | 16.0 | 20.0 | 22.0 | 25.0 |
| >2 000 and ≤2 500 | 7.5 | 10.0 | 14.0 | 20.0 | 25.0 | 28.0 | 32.0 |
| >2 500 and ≤3 200 | 10.0 | 12.5 | 18.0 | 25.0 | 32.0 | 36.0 | 40.0 |
| >3 200 and ≤4 000 | 12.5 | 16.0 | 22.0 | 32.0 | 40.0 | 45.0 | 50.0 |
| >4 000 and ≤5 000 | 16.0 | 20.0 | 28.0 | 40.0 | 50.0 | 56.0 | 63.0 |
| >5 000 and ≤6 300 | 20.0 | 25.0 | 36.0 | 50.0 | 63.0 | 71.0 | 80.0 |
| >6 300 and ≤8 000 | 25.0 | 32.0 | 45.0 | 63.0 | 80.0 | 90.0 | 100.0 |
| >8 000 and ≤10 000 | 32.0 | 40.0 | 56.0 | 80.0 | 100.0 | 110.0 | 125.0 |
| >10 000 and ≤12 500 | 40.0 | 50.0 | 71.0 | 100.0 | 125.0 | 140.0 | 160.0 |

**Table 18's two notes, verbatim:**

> **1** For PTC heating elements, the creepage distances over the surface of
> the PTC material need not be greater than the associated clearance for
> working voltages less than 250 V and for pollution degrees 1 and 2. However,
> the creepage distances between terminations are those specified in the table.
>
> **2** For glass, ceramics and other inorganic insulating materials that do
> not track, creepage distances need not be greater than the associated
> clearance.

**Neither note helps.** Note 1 is about PTC heating elements. Note 2 is about
non-tracking inorganic materials; FR-4 is an organic laminate with a CTI and it
tracks — that is the entire reason material group IIIa/IIIb is the column this
board sits in. The "creepage need not exceed clearance" escape hatch is
explicitly reserved for materials this board is not made of.

**Two transcription cross-checks, because a single OCR pass on a table is
exactly the failure mode this project has already been burned by** (a 6.0mm
figure was carried for months citing "Table 16, working isolation at 400V" — a
row that does not exist):

- **Internal, from this repo, written by a different agent from a different
  render.** `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md:207-211` and
  `packages/temper-placer/src/temper_placer/requirements/validators/clearance.py:245-249`
  both independently record "Table 18 row i, ≤50V, Material Group IIIa/IIIb
  reads **1.1mm PD2 / 1.8mm PD3**". My OCR pass reads that row as
  `0.2 | 0.6 0.8 [damaged] | 1.4 1.6 1.8` — the PD3 IIIa/IIIb cell is 1.8 ✓,
  and the one cell OCR damaged is precisely the PD2 IIIa/IIIb cell those two
  files independently give as **1.1** ✓. That is a two-way confirmation of both
  the column layout and the one damaged value.
- **Structural, within the same OCR pass.** Table 18's printed row labels run
  `i)` at ">50 and ≤125" through `xvii)` at ">10 000 and ≤12 500", while Table
  17's run `i)` at "≤50" through `xviii)` at the same final band. Table 18's OCR
  simply dropped the "i)" on its ≤50 row; every band label is otherwise
  one-for-one with Table 17's, and both tables terminate on the same band. The
  row *bands* of the two tables are identical. Only the *values* differ, and
  only below 500 V.

### 3.2 The 500 V cliff — the load-bearing structural fact

Both tables were read in the **same** OCR pass, from the **same** file, so this
comparison carries no cross-source risk. Material group IIIa/IIIb (the column
this board sits in), in mm:

| Working voltage (V) | T17 basic PD2 | **T18 functional PD2** | T17 basic PD3 | **T18 functional PD3** | Relief? |
|---|---:|---:|---:|---:|---|
| ≤50 | 1.2 | **1.1** | 1.9 | **1.8** | yes |
| >50 and ≤125 | 1.5 | **1.4** | 2.4 | **2.2** | yes |
| >125 and ≤250 | 2.5 | **2.0** | 4.0 | **3.2** | yes |
| >250 and ≤400 | 4.0 | **3.2** | 6.3 | **5.0** | yes |
| >400 and ≤500 | 5.0 | **4.0** | 8.0 | **6.3** | yes |
| **>500 and ≤800** | **6.3** | **6.3** | **10.0** | **10.0** | **none** |
| >800 and ≤1 000 | 8.0 | 8.0 | 12.5 | 12.5 | none |
| >1 000 and ≤1 250 | 10.0 | 10.0 | 16.0 | 16.0 | none |
| … every remaining band … | identical | identical | identical | identical | none |

**IEC 60335-1's functional-insulation creepage concession exists only below
500 V working voltage. At and above 500 V, Table 18 and Table 17 are the same
table.**

I did not expect this and I want to be explicit that it is the *opposite* of
the intuition the task set out to test. "Functional insulation is generally
treated more leniently than basic insulation" is true in IEC 60335-1 — for five
rows. `tank.c_tank1-p2` ↔ bus rails measures **570.5 Vrms**
(`docs/evidence/2026-08-12-hv-clearance-adequacy.md` Sec 3.2, worst
OCP-01-passing point, carried forward not re-measured). Had it come in at
≤500 Vrms, Table 18 would have given 4.0mm PD2 / 6.3mm PD3 instead of Table
17's 5.0 / 8.0 — a real 20% concession. It comes in **70.5 V, or 14%, above the
band edge**, on the first row where the concession is gone.

### 3.3 Applying it

Inputs, all carried forward from `docs/evidence/2026-08-12-hv-clearance-adequacy.md`
at `de7d3a113` and unchanged here:

| Quantity | Value | Source |
|---|---|---|
| Working voltage, `tank.c_tank1-p2` ↔ bus rails | **570.5 Vrms** | ngspice, worst OCP-01-passing corner (L −10%, C −10%, 48 kHz) |
| Material group | IIIa/IIIb (generic FR-4, CTI unstated) | repo-wide assumption; IEC 60335-1 merges IIIa and IIIb into one column, so the choice between them is immaterial |
| Pollution degree | **PD3 as-built**, PD2 as target | `docs/evidence/2026-08-11-pd2-decision-record.md:40-58` |
| Provided | **2.0mm** | `HighVoltage` netclass clearance in `pcb/temper.kicad_pro`; identical to the surface path on a flat, ungrooved, uncoated board with `COATING_QUALIFIED = False` |

Clause 29.2 fixes the three inputs the table is indexed by:

> **29.2** Appliances shall be constructed so that creepage distances are not
> less than those appropriate for the working voltage, taking into account the
> material group and the pollution degree.

and clause 3.1.3's Note 2 settles that the resonant swing counts:

> **2** Working voltage takes into account resonant voltages.
>
> **3** When deducing the working voltage, the effect of transient voltages is
> ignored.

**Result: Table 18, band >500 and ≤800 V, material group IIIa/IIIb →
6.3mm at PD2, 10.0mm at PD3.** Against 2.0mm provided: **3.2× short at the
target pollution degree, 5.0× short as built.**

Identical to the figures `docs/evidence/2026-08-12-hv-clearance-adequacy.md`
derived from Table 17. That document reached the right number by the wrong
table, and said so — it flagged the mismatch between Table 17's header
("**Basic** Insulation") and the pair's functional character as its own
caveat. The caveat is now closed: the correct table gives the same answer.

---

## 4. Does the exemption apply?

### 4.1 The classification is functional — on a premise I am adopting, not proving

Clause 3.3.5 requires the insulation to be *"between conductive parts of
different potential which is necessary **only** for the proper functioning of
the appliance."* For `tank.c_tank1-p2` ↔ `+170V_BUS` / `DC_BUS_RTN`:

- **Different potential:** yes, 570.5 Vrms measured.
- **Necessary only for proper functioning:** this holds **if and only if**
  neither side is accessible and no shock barrier is crossed. Both nets are
  hazardous-live, mains-derived through the voltage doubler
  (`elec/src/main.ato:511-522`), and both are internal PCB nets. A breakdown
  between them shorts one part of the hazardous-live domain to another; it does
  not connect a hazardous-live part to an accessible part, to earth, or to
  SELV. So its failure mode is malfunction (and, potentially, fire), not
  electric shock.

**The fact I cannot establish from this repository, named as the rules
require:** *accessibility*. Nothing in the repo commits an enclosure geometry
for the PCB compartment —
`docs/evidence/2026-08-11-pd2-decision-record.md:40-58` records that the
"sealed gasketed PCB compartment" exists **only as a prescriptive release
requirement** in `docs/ENVIRONMENTAL_SPEC.md` §3.1, with no cover, gasket,
partition, or inspection geometry committed anywhere. The board outline is a
plain rectangle in a **forced-air-vented** cavity. **What determines it:** the
clause-8 accessibility assessment (test probe B of IS 1401 / IEC 61032) applied
to the finished appliance. If either net turns out to be reachable by the test
probe, the pair is not functional insulation at all and the analysis restarts
against basic or reinforced — a strictly worse outcome, never a better one.
Every party to this discussion so far, including
`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md:118-123`, has treated
same-domain HV↔HV as functional; I am adopting that and flagging its unproven
premise, not re-deriving it.

### 4.2 The exemption's condition, and what "reduced" leaves open

29.2.4's second sentence: *"However, creepage distances may be reduced if the
appliance complies with 19 with the functional insulation short-circuited."*

Three things follow directly from the text.

**(a) It is a test, not a declaration.** "Complies with 19" is compliance with
clause 19, *Abnormal Operation*, whose acceptance criteria are clause 19.13's,
verbatim:

> **19.13** During the tests the appliance shall not emit flames, molten metal,
> or poisonous or ignitable gas in hazardous amounts and temperature rises
> shall not exceed the values shown in Table 9.
>
> After the tests and when the appliance has cooled to approximately room
> temperature, the enclosure shall not have deformed to such an extent that
> compliance with 8 is impaired and the appliance shall comply with 20.2, if it
> can still be operated.
>
> […] When the insulation, other than that of Class III appliances, has cooled
> down to approximately room temperature, it shall withstand the electric
> strength test of 16.3, the test voltage, however, being as specified in
> Table 4.

**(b) The board's shortfall makes that test mandatory anyway.** Clause 19.11.2
lists the fault conditions applied to electronic circuits, and (a) is first:

> **19.11.2** The following fault conditions are considered and, if necessary,
> applied one at a time, consequential faults being taken into consideration:
>
> **a)** short circuit of functional insulation, **if clearances or creepage
> distances are less than the values specified in 29**;

The conditional in 19.11.2(a) is satisfied by this board: 2.0mm is less than
the 6.3/10.0mm that clause 29 (via 29.2.4 → Table 18) specifies. **So the
short-circuit fault condition is owed regardless of whether anyone wants to
claim the 29.2.4 reduction.** The relationship between the two clauses is not
"undersize the gap *or* run the test" — undersizing the gap is what *summons*
the test. A board that met 6.3/10.0mm would not owe it.

Clause 19.11.2 also fixes how the test terminates:

> For simulation of the fault conditions, the appliance is operated under the
> conditions specified in 11 but supplied at rated voltage. […] In each case,
> the test is ended if a non-self-resetting interruption of the supply occurs
> within the appliance.

**(c) "Reduced" is not "waived", and the standard states no floor.** Set
29.2.4 beside 29.1.4 (Sec 2): clearances *"are not specified"*; creepage *"may
be reduced"*. Two readings are available and **the standard does not choose
between them**:

- **Reading A (de-facto waiver).** "May be reduced" is loose drafting for the
  same waiver 29.1.4 grants, and a passing clause-19 test leaves the creepage
  distance at the designer's discretion. Under this reading, 2.0mm would be
  acceptable *once the test passes*.
- **Reading B (bounded reduction).** The drafters used different words in
  adjacent clauses because they meant different things: clearance can be
  dispensed with because a passing clause-19 test proves the flashover is
  survivable, but creepage cannot, because tracking is a *progressive,
  cumulative* failure that a single fault-injection test does not model. Under
  this reading the reduction is real but bounded, and how far is a judgement
  a certification body makes on the evidence.

**I am not choosing between them and I am not going to invent a reduced
figure.** Nothing in clause 29, Annex L, or Annex M states a floor for a
reduced functional creepage distance, and this project has already paid once
for a confidently reconstructed number. The distinction is decision-relevant
only *after* a clause-19 test passes; it is moot today.

### 4.3 Determination

**The 29.2.4 exemption does not apply to `tank.c_tank1-p2` ↔ bus rails as the
design stands.** Not because the pair fails to be functional insulation — it
is, on the accessibility premise of Sec 4.1 — but because the exemption is
conditional on a clause-19 test result that does not exist, and because
19.11.2(a) independently obliges that same test given the shortfall.

The requirement in force is therefore **Table 18, >500 and ≤800 V, material
group IIIa/IIIb: 6.3mm at PD2 and 10.0mm at PD3**, against **2.0mm** provided,
with PD3 governing as built.

**Stated as three separate propositions, so the standard's voice is not
confused with mine:**

- *What the standard says:* functional-insulation creepage takes Table 18;
  Table 18 at this band equals Table 17; the figure may be reduced only if the
  appliance complies with clause 19 with the gap short-circuited; and a gap
  short of clause 29 makes that short-circuit a mandatory 19.11.2(a) fault
  condition judged by 19.13's fire criteria.
- *What I conclude:* the exemption is unearned today, the 3.2×–5.0× shortfall
  is real and reportable, and the route to closing it is either geometry
  (distance, slot, or qualified coating) or a clause-19 test — not an argument
  from the word "functional".
- *What I am not asserting:* that the clause-19 test would fail. Sec 5 is my
  best reading of the fault, and it reads *survivable*. But a reading is not a
  test, and 29.2.4 asks for the test.

---

## 5. The clause-19 route, mapped for whoever runs it

This section exists because the determination above is a "not yet", not a "no",
and the difference matters to what the owner should do next. **Everything in
this section is DERIVED BY HAND from committed circuit topology. No simulation
was run** — ngspice is not installed in this environment. It is offered as a
map for the test, not as a result.

### 5.1 What "the functional insulation short-circuited" physically means

Per 19.11.2, a dead short from `tank.c_tank1-p2` to a DC bus rail, with the
appliance running under clause 11 conditions at rated voltage. Take the short
to `+170V_BUS`. From `elec/src/main.ato:817, 823-824` and
`elec/src/modules.ato:551-557` the topology is:

```
SW_NODE ─┤ 3×100nF ├─ tank.c_tank1-p2 ─[ L 88µH ]─ tank-out ─[CT1 pri]─ PWR_RTN
```

The short creates **two** new current paths, and they behave very differently:

- **Path 1 — through the coil.** `+170V_BUS` → short → `L` → `tank-out` →
  **CT1 primary** → `PWR_RTN`. This puts ~170 V DC across 88 µH plus the coil's
  DCR and the CT primary. Current ramps at 170 V / 88 µH ≈ **1.93 A/µs**,
  reaching OCP-01's ~50 A peak threshold (49.9 A as dimensioned by the burden
  resistor, `elec/src/modules.ato:1618-1619`; quoted as 50.1 A at
  `elec/src/main.ato:82`) in roughly **26 µs**. Critically, this path runs **through CT1's primary**, which
  is exactly where OCP-01 senses (`main.ato:823-824`: *"Tank return passes
  THROUGH the CT primary"*). **OCP-01 sees this fault.**
- **Path 2 — through the tank caps and the bridge.** `+170V_BUS` → short →
  300 nF → `SW_NODE` → whichever IGBT is on → the other rail. This path does
  **not** traverse the coil or CT1, so OCP-01 is blind to it, and it dumps
  ½CV² ≈ 17 mJ per switching edge into IGBT and ESR losses. Its magnitude is
  set by loop inductance and ESR, neither of which I can bound from the repo.

### 5.2 The part of it that is not obviously safe

**OCP-01 tripping does not stop Path 1.** OCP-01 acts by turning the IGBTs off.
Path 1 does not go through the IGBTs — it runs from the bulk doubler
capacitors, through the short and the coil, back to the doubler midpoint. Gate
shutdown is irrelevant to it. The fault current continues, sourced by the bus
capacitors and then by the mains through the rectifier, until something opens
the circuit.

What opens it is **F1, the 16 A mains fuse** (`elec/src/modules.ato:657-664`).
That is a *"non-self-resetting interruption of the supply … within the
appliance"*, which 19.11.2 accepts as ending the test. So the clause-19 story
has a plausible happy ending: OCP-01 trips in tens of microseconds, the bus
caps discharge into the coil, F1 clears, and the appliance is then judged
against 19.13 (no flames, no molten metal, Table 9 temperature rises, and a
post-cooling electric strength test per 16.3).

**Three specific things could break that story, and a reviewer must check each:**

1. **F1's clearing behaviour is uncharacterised.** `elec/src/modules.ato:665-673`
   flags, as an unresolved open question, that *"No I2t coordination analysis
   between this fuse, NTC_Inrush (ntc, below), and bypass_relay's switch-in
   timing has been found anywhere in this repo"* — and F1 is a **time-lag**
   (slow-blow) 16 A link on a 15 A continuous branch load, i.e. deliberately
   slow. On this fault the coil, the CT1 primary, and the PCB traces carry the
   fault current for however long F1 takes. That duration is the input to
   19.13's Table 9 temperature-rise criterion, and nobody has it. This is the
   single most actionable item in this document.
2. **F1's holder footprint is a stub.** The BOM does carry the fuseholder
   (`F1_HOLDER` = Schurter `0031.2510`, `docs/hardware/BOM.md:45`, added
   2026-07-26 to close the earlier "HOLDER GAP" at
   `elec/src/modules.ato:675-681`) — but `docs/hardware/BOM.md:77` records that
   **"New footprint required, not yet drawn"**: the committed PCB stub
   (`Fuse:Fuse_Holder_5x20mm`, 2-pin THT, 22.5mm pitch) does not match the FUP's
   real ~30.48mm drilling diagram. A clause-19 test is run on hardware, and the
   part that ends it is not yet on the board as the real part.
3. **OCP-01 is the only over-current channel on the board.** OCP-02's second CT
   in `DC_BUS_RTN`, which would see Path 2, is designed in `elec/src/modules.ato`
   but **has not been placed on `pcb/temper.kicad_pcb`**
   (`modules.ato:2628-2640`, *"the second CST3015-100ED footprint (23.0 × 30.0mm)
   has not been placed"*). So the as-built board's protection against Path 2 is
   nothing.

### 5.3 Nothing in this repository has run this test

Searched: no clause-19 fault-injection deck exists under
`simulation/harness/nets/` (the ten decks there cover OCP-01, OCP-02 option A,
OVP-01, THM-01/02, UVL-02 ×2, and the ZVS margin sweep — all *trip-point*
characterisations, none a 19.11.2 fault injection), and `19.11.2` appears in no
document. The 29.2.4 exemption has been named as an open question three times
in this repo — `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md:212`,
`packages/temper-placer/src/temper_placer/requirements/validators/clearance.py:251`,
`docs/evidence/2026-07-30-pollution-degree-determination.md:472` — and answered
zero times. This document answers what the clause *says*; it cannot answer
whether the appliance passes a test nobody has performed.

---

## 6. What a qualified reviewer must still check

Ordered by how much each could move the answer.

1. **Run, or formally waive, the 19.11.2(a) fault condition.** This is the whole
   determination. It is owed independently of the 29.2.4 reduction, because the
   creepage distance is below clause 29's figure. Acceptance is 19.13's.
2. **Characterise F1's clearing behaviour on this fault, and draw the real
   holder footprint.** The clause-19 route terminates on F1; F1's I²t
   coordination is an open question the repo itself flags, and its footprint is
   still a stub (Sec 5.2, items 1–2). Nothing else on the as-built board
   interrupts Path 1.
3. **Decide Reading A vs Reading B of "may be reduced" (Sec 4.2c).** Only
   matters once (1) passes, but it decides whether the answer is then "2.0mm is
   fine" or "2.0mm is still not fine, but less short". A certification body, not
   this repository, resolves it.
4. **Establish accessibility (Sec 4.1).** If test probe B can reach either net,
   the pair is not functional insulation and the requirement rises to basic or
   reinforced. This is the one open item that could make the situation *worse*.
5. **IEC 60664-4 at 44–50 kHz.** Still unaddressed; `60664-4` appears zero times
   in this repository, on any branch reachable from `origin/main`. Carried
   forward verbatim from `docs/evidence/2026-08-12-hv-clearance-adequacy.md`
   Sec 3.3, whose framing I endorse: it could only move the requirement up.
6. **Confirm the pollution degree.** Every figure here doubles between PD2 and
   PD3 columns. `docs/evidence/2026-08-11-pd2-decision-record.md:40-58` says PD3
   governs as built; IEC 60335-2-6 clause 29.2's Addition makes PD3 the default
   for this appliance class. 6.3mm is the *best* case and it is not the current
   case.
7. **Verify Table 18 against a clean edition.** Sec 7.

---

## 7. What this determination rests on, and where it is weak

**Source.** IS 302-1:2008, the BIS identical adoption of IEC 60335-1, published
under India's RTI Act — the same artifact, byte count, and URL that
`docs/evidence/2026-07-28-conformal-coating-pd1.md` records reading. It is an
**OCR'd scan of a 2008 edition**, corresponding to IEC 60335-1 Ed. 4.2-era text.
Two consequences:

- **Edition risk.** Clause and table numbering, and the values themselves, could
  differ in the current IEC edition. Every prior determination in this project
  rests on the same source, so this is a project-wide exposure, not one this
  document introduces — but it is the reason nothing here should be treated as
  a certification result.
- **OCR risk on Table 18 specifically.** Table 17 was cross-checked
  cell-for-cell against a Broadcom reproduction of IEC 60664-1 by
  `docs/evidence/2026-07-28-creepage-determination-brainstorm.md` §3.4. **Table
  18 has no comparable external cross-check in this repository.** What it has
  instead is (i) the internal two-way confirmation of its ≤50 V row from two
  repo files written independently of this session, including recovery of the
  one OCR-damaged cell (Sec 3.1), and (ii) the structural row-band alignment
  with Table 17 from the same pass. That is weaker than Table 17's
  corroboration and I am flagging it rather than levelling the two.

**What is *not* at risk from OCR.** The clause 29.2.4 text itself is prose, read
cleanly, with a bidirectional cross-reference to Table 18 that OCR corruption
could not manufacture. And the load-bearing conclusion — *no relief from the
table swap at this working voltage* — would survive even a moderately damaged
Table 18, because it depends only on Table 18's >500–800 V row equalling Table
17's, and both were read in the same pass.

**Carried forward, not re-verified here:** the 570.5 Vrms working voltage, the
923.7 V peak, the rule inventory showing no creepage constraint for HV↔HV, and
the 2.0mm provided figure — all from
`docs/evidence/2026-08-12-hv-clearance-adequacy.md` at `de7d3a113`, which
measured them live against kicad-cli 10.0.5 and ngspice-42. I read that
document in full and re-derived nothing from it. If its 570.5 Vrms figure is
wrong low — if the true working voltage is ≤500 Vrms — then Table 18's
>400–500 row applies and the requirement drops to 4.0mm PD2 / 6.3mm PD3. Still
2.0–3.2× short. **There is no plausible correction to the working voltage that
makes 2.0mm compliant**: on Table 18 at material group IIIa/IIIb, 2.0mm meets
PD3 only at ≤50 V (1.8mm) and meets PD2 only up to 250 V (2.0mm exactly). A
node measured at 570.5 Vrms would have to be wrong by more than a factor of two
before 2.0mm became defensible even at the target pollution degree.

---

## 8. Cite-to-nothing: the defect class, counted

Method: every `docs/evidence/<path>` string appearing in a non-`docs/` file with
a code-ish extension (`.py .rs .yaml .yml .toml .sh .ato .json .dru .cfg .ini
.txt`), with Python/Rust string-concatenation and comment-wrapped continuations
rejoined before matching, then tested against `origin/main` with
`git cat-file -e`.

- **237** distinct `docs/evidence/` paths cited from code.
- **219** present on `origin/main`.
- **18** absent, of which **3 are not real defects**: two are elided prose
  references inside comments (`docs/evidence/...-spike.md` in
  `packages/temper-geometry/src/channel_skeleton.rs:25`,
  `docs/evidence/2026-08-11-...execution.md` in
  `packages/temper-placer/tests/router_v6/test_constraint_model_rust_differential.py:95`)
  and one is a deliberate test fixture
  (`docs/evidence/does-not-exist-2026-07-30.md` in
  `scripts/tests/test_known_failure_pins.py:226`).
- **Genuine cite-to-nothing paths: 15.** This PR recovers **2**. **13 remain.**

| Missing path | Cited by | Recoverable from |
|---|---|---|
| `2026-07-28-drc-coating-failopen-fix.md` | `scripts/tests/test_generate_kicad_dru.py` | `4b2436ccf` |
| `2026-07-28-drc-courtyard-condition-fix.md` | **`scripts/generate_kicad_dru.py`**, its test | `af7d3e827` |
| `2026-07-28-drc-creepage-constraint.md` | **`scripts/generate_kicad_dru.py`**, its test | `2a8f8abce` |
| `2026-07-28-drc-rule1-netclass-redo.md` | **`scripts/generate_kicad_dru.py`**, **`packages/temper-placer/configs/netclass_rules.yaml`**, its test | `be3983c34` |
| `2026-07-28-zone-layer-classification-fix.md` | `scripts/check_net_classification.py`, `packages/temper-placer/tests/router_v6/test_adapter.py` | `dfa67029a` |
| `2026-08-07-persistent-radius-index-rust-migration.md` | `router_v6/constraints_spatial_index.py` | `c33b18c14` |
| `2026-08-07-radius-pairs-rust-migration.md` | `packages/temper-geometry/src/persistent_radius_index.rs` | `d697e1b0f` |
| `2026-08-07-scipy-keeps-re-triage.md` | **11 files** across `temper-geometry`, `temper-design-bundle`, `temper-placer` | `73ddab178` |
| `2026-07-26-measurement-provenance.md` | `scripts/_lib/provenance.py`, `scripts/check_evidence_provenance.py` | **no commit anywhere** |
| `2026-07-27-resync-net-ordinal-fix.md` | `scripts/check_copper_net_consistency.py`, its test | **no commit anywhere** |
| `2026-08-07-via-var-characterization.md` | `router_v6/test_constraint_model.py`, `_constraint_model_builder_py_oracle.py` | **no commit anywhere** |
| `2026-08-08-nlayer-via-astar-spike-terminal-fix.md` | `test_channel_mapping_terminal_validation.py` | **no commit anywhere** |
| `2026-08-09-bundle-analyzer-geos-spike.md` | `packages/temper-geometry/src/bundle_analyzer.rs`, `router_v6/bundle_analyzer.py` | **no commit anywhere** |

**8 of the 13 are recoverable from side branches by the same procedure this PR
used. 5 exist in no commit reachable from anywhere and cannot be recovered —
for those, the citation is the only surviving trace of the reasoning.**

**Two of these deserve to be singled out.**

- **Four of the 13 are cited by `scripts/generate_kicad_dru.py` itself, plus one
  by `packages/temper-placer/configs/netclass_rules.yaml`.** Counting the two
  this PR recovers, the script that emits the fabrication rule file has cited
  **six** documents that a reader on `main` could not open. Four of those six
  are still unreadable after this PR.
- **`scripts/check_evidence_provenance.py` — the gate whose whole purpose is
  making evidence traceable — cites `docs/evidence/2026-07-26-measurement-provenance.md`,
  which exists in no commit in this repository.** The traceability gate is
  itself untraceable.

They are not landed here because this PR is scoped to the two documents that
carry standards primary text and to the determination that depends on them.
**Recommended follow-up: one PR restoring the 8 recoverable paths, and one that
replaces the 5 unrecoverable citations with an honest marker rather than a
pointer to nothing.**

For completeness, the provenance gate is *already* red on `origin/main`: 76
files under `docs/evidence/` fail `scripts/check_evidence_provenance.py` before
this PR. Both files this PR recovers pass it (after the one-line SHA expansion
disclosed in Sec 1), and so does this document. This PR does not change that
count in either direction beyond its own three files.

---

## 9. What this determination does not do

- **It changes no netclass value and adds no creepage constraint.** Per the
  brief: the determination lands first. `HighVoltage` stays at 2.0mm and
  HV↔HV creepage stays unenforced until someone decides what to do about it.
- **It does not re-measure anything.** No board file was opened for writing, no
  DRC was run, no simulation was run. The voltages are carried forward from
  `de7d3a113` with attribution.
- **It does not settle whether the appliance passes clause 19.** It maps the
  test (Sec 5) and names what would decide it. Running it is the next step and
  it is not a documentation task.
- **It does not close IEC 60664-4.** The high-frequency question raised by
  `docs/evidence/2026-08-12-hv-clearance-adequacy.md` Sec 3.3 is exactly as open
  as it was.
- **It does not reconstruct anything from memory.** Every normative sentence
  above is quoted from a file that was fetched, hashed, and cited in the
  provenance header. Where the OCR damaged a character I marked it and said how
  the value was recovered. Where the standard is silent — what "reduced" reduces
  to — I said it is silent instead of filling it in.
