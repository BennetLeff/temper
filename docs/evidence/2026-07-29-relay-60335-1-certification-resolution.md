<!-- provenance: commit=46d4b4c83dbd3f62185af7193efa4ee77bb5469b dirty=false -->

# K2/K3 IEC 60335-1 open question, resolved as far as public evidence goes:
# no orderable relay explicitly carries it on a real certificate, and the
# standards themselves say a bare IEC 61810-1 mark cannot settle this alone

Base commit `46d4b4c8` (`origin/main`, "fix(gates): report a malformed
provenance stamp as malformed, not missing (#456)"). Branch
`docs/relay-60335-1-certification-survey`, worktree created fresh from
`origin/main` per this task's hard rule. **Research and analysis only** --
no design file, constant, footprint, or netclass touched; `git status
--short` clean apart from this document throughout. No part swapped.

This document answers the question left open, in the same words, by two
prior sessions in this repo's history:

- `docs/evidence/2026-07-28-pd3-retarget-relay.md`, "The conflation
  question" section: *"Whether the component's own 8mm internal rating is
  an acceptable substitute for that missing PCB margin is the open
  question... a standards-interpretation question for a safety engineer, not
  something this pass can settle by geometry alone."*
- `docs/evidence/2026-07-29-pd3-part-selection-verification.md` (branch
  `docs/verify-pd3-part-selection`), Claim 1.1: TE's VDE certificate
  40007571 covers EN/IEC 61810-1 only, not IEC 60335-1, for the currently
  orderable `RT114012`; the WG SKU that historically carried the distinct
  claim is discontinued.

## Verdict up front

**Track A: no orderable relay was found this session, from any of the
manufacturers checked (TE's RT1/RT2 and T9A/OEG families, Hongfa, Song
Chuan, Zettler), that carries a genuinely independent third-party
certificate scoped to IEC 60335-1 (as opposed to its own component
standard, IEC 61810-1).** Every manufacturer checked directly uses a
variant of the identical structure: a front-page or ordering-suffix claim
of "product in accordance to IEC 60335-1" / "meets EN 60335-1," backed by
the *same* VDE certificate that also covers the base part and that, read
directly from the certifying body's own database, lists **only** EN/IEC
61810-1. **Five separate VDE certificate numbers were fetched and read
directly across this document (40007571 TE-RT, 116934 Hongfa, 40007630
TE-OEG, 40019600 Song Chuan-T92, plus 40010643 checked as a
likely-mismatched claim) -- all five show the same gap.** The specific
ordering-code suffix that historically gated the 60335-1 claim (TE's `WG`,
Hongfa's `(335)`, Song Chuan's `WG`) turns out, where its actual scope was
checked, to gate either nothing the certificate backs, or (per the earlier
TE-RT finding) a narrower glow-wire/flammability test under clause 30.2 --
not the insulation-coordination requirements (clause 29) this design's
12.6mm PCB question is actually about. A subagent survey of Omron's
appliance lines was also dispatched but **had not returned by the time
this document was finalized** -- see A.3, still an open gap. TE Schrack
`RT114012` remains the best-verified part on **geometry** (13.820mm PCB
spacing, reproduced twice now against the manufacturer's own dimensioned
drawing, and the only candidate across every family checked whose spacing
figure comes from printed dimensions rather than a shortfall) and is this
document's recommendation on the evidence gathered directly, but not on
the strength of its 60335-1 bullet, which this document treats as
unsubstantiated self-declaration, same as the verification doc already
found.

**Track B: this is answered with primary-source text, not just inference.**
IEC 61810-1:2015 itself, in its own Scope clause, says a relay's own
certification does not cover appliance-level requirements and must be
separately assessed against the appliance standard. IEC 60335-1 clause 24.1
says the same thing from the other direction, and clause 29 is what
actually governs -- reproducing this project's own 12.6mm PD3 figure
directly from the standard's Table 17. **A relay's IEC 61810-1 certificate,
however solid, governs only the component's own internal construction. It
cannot stand in for the PCB pad-to-pad path's own appliance-level creepage
requirement, because that path is physically outside the relay -- it exists
on this project's own board, under this project's own control, and the
component manufacturer's certificate says nothing about it.** This closes
the "conflation question" the prior document left open: it is not a
question of whether 61810-1 "counts" as some fraction of 60335-1 -- the two
clauses are about two different physical paths, and both must independently
clear their own bar. The PCB-geometry measurements this project's evidence
chain has already been doing (5.3mm, 3.5mm, 13.820mm) are not a proxy for
the relay's certification status; they are the actually-decisive test for
the question this design needs answered, and remain so regardless of how
the datasheet-bullet question resolves.

---

## Provenance labels

Same convention as the documents this one follows on from:

| Label | Meaning |
|---|---|
| **CITED-PRIMARY** | Standard's own text or a certifying body's own database, read this session. |
| **CITED-SECONDARY** | Manufacturer datasheet or distributor page, fetched and read this session. |
| **MEASURED** | Computed this session from a real file/drawing, method shown. |
| **DERIVED** | Arithmetic on labelled inputs, shown in full. |
| **INFERRED** | A conclusion this session draws from cited text, flagged as interpretation, not a verbatim standard statement. |
| **UNVERIFIED** | Not established; flagged for a human. |

---

# TRACK A -- searching for a relay that explicitly carries IEC 60335-1

### Requirements bar applied to every candidate (per the task, all mandatory)

Coil-to-contact PCB spacing >=12.6mm **as landed**, verified against the
manufacturer's own dimensioned PCB layout drawing; reinforced insulation
with standard+figure stated; an NC contact; 12VDC coil near 360R/400mW;
DC break capability at 21.8mA/170V (design already has RC snubbers across
the contact gaps, so the un-snubbed arc case is not the operating case);
actually orderable and stocked.

## A.1 TE Schrack RT1/RT2 family -- already verified, restated for the record

`RT114012` (SPDT, RM3.5mm): **13.820mm** edge-to-edge, MEASURED against TE's
own dimensioned "PCB LAYOUT / TERMINAL ASSIGNMENT" drawing and cross-checked
against the stock KiCad footprint -- CONFIRMED twice now
(`docs/evidence/2026-07-29-pd3-part-selection-survey.md` Section 5,
`docs/evidence/2026-07-29-pd3-part-selection-verification.md` Claim 1.2).
Reinforced 10/10mm, 5kVrms, material group IIIa (CITED-SECONDARY, TE RT1
datasheet). Coil 12V/360R+/-10%/400mW -- numerically identical to the
incumbent G5LE-1. NC pin ("12") is the same pin that governs creepage. DC
load curve is flat at 300V ceiling down to the plotted floor (0.1A), and
this design's 170-200V requirement needs no extrapolation at all (only the
0.0218A current point does, by <1 decade, in the safe direction). DigiKey
Active, 1,224 units. **All of this stands; nothing in this session changes
it.** What does not stand, per the verification doc and confirmed again
here (Track B), is the front-page "product in accordance to IEC 60335-1"
claim as a certified fact.

## A.2 Hongfa HF115F / HF115FK family -- checked fresh this session, FAILS on PCB geometry

Hongfa markets this exact same claim structure. `HF115F-Q` datasheet
(`source.hongfa.com/Uploads/Product/PDF/HF115F-Q_en.pdf`, fetched and read
directly this session, CITED-SECONDARY): front-page bullets *"Creepage
distance >8mm," "Meeting VDE 0700, 0631 reinforce insulation," "Product in
accordance to IEC 60335-1 available."* Coil, 12V code: **8.40V pick-up /
1.2V drop-out / 18.0V max / 360R+/-10%** -- coil power "Approx. 400mW" --
numerically identical to the incumbent, same as TE's part. Contact
arrangement on this exact SKU is 1A/1B only (no Form C), but the sibling
`HF115FK` datasheet (`source.hongfa.com/Uploads/Product/PDF/HF115FK_en.pdf`,
fetched fresh, CITED-SECONDARY) offers `Z: 1 Form C` with an NC contact and
the same coil table, so the family does offer what's needed electrically.

**PCB geometry, MEASURED this session against Hongfa's own dimensioned "PCB
Layout (Bottom view)" drawing** (HF115FK datasheet p.3/265, "5mm Pinning, 1
Pole, 16A, 1 Form C"): printed dimensions are 2.6mm (courtyard-to-coil-pin
offset), 5.04mm x2 (contact-column sub-pitch, printed twice), 20.16mm
(coil-column to farthest-contact-column span, printed), 7.56mm (row pitch).
The nearest-contact column is not itself printed as a standalone figure but
is DERIVED from the two dimensions that are printed on the same drawing
(20.16mm total span, 5.04mm x2 sub-pitch): `20.16 - 2*5.04 = 10.08mm`
coil-to-nearest-contact center-to-center, same row (the cross-row diagonal,
`sqrt(10.08^2+7.56^2)=12.6mm`, is longer and does not govern). With any
realistic pad on a 1.3mm(+0.1/-0)mm drill hole (1.9-3.0mm pad, 0.3-0.85mm
annular ring):

```
edge-to-edge = 10.08mm - pad_radius - pad_radius
   1.9mm pad -> 8.180mm   (-4.420mm vs 12.6mm)
   2.2mm pad -> 7.880mm   (-4.720mm vs 12.6mm)
   3.0mm pad -> 7.080mm   (-5.520mm vs 12.6mm)
```

**FAILS by 4.4-5.5mm regardless of pad choice** -- this margin is wide
enough that the qualitative conclusion does not depend on precisely which
contact column is electrically NC (COM sits at this same nearest column
per the wiring-diagram schematic read alongside the layout, INFERRED from
the symbol's wiper-arm convention, not a printed pin number the way TE
labels "11/12/14" -- flagged as a softer read than TE's, but irrelevant
here since the failure margin swamps that uncertainty). The 3.5mm-pinning
and 5mm/12A siblings in the same datasheet print the identical 20.16mm
total span with a smaller 3.5mm sub-pitch, which would put the
coil-to-nearest-contact figure even closer, not farther -- not separately
re-measured because the 16A/5mm case already fails by such a wide margin
that no sibling in the same case family is a plausible pass.

**Certificate scope, CITED-PRIMARY (VDE's own database, fetched this
session):** File No. 116934, appearing on both HF115F and HF115FK
datasheets, resolves at
`vde.com/tic-en/marks-and-certificates/vde-approved-products/certificate?id=116934` to: manufacturer Xiamen Hongfa Electroacoustic; standards applied
**DIN EN 61810-1 (VDE 0435-201):2015-10 / IEC 61810-1:2015(+AMD1:2019)** --
covering, by name, 22 HF115F/JQX-115F-series type variants including
HF115FK. **No mention of IEC 60335-1 anywhere in the certificate.** The
ordering-table note explaining the "(335)" special code reads, verbatim:
*"(335): stands for product in accordance to IEC 60335-1 (GWT)"* -- GWT is
the Glow Wire Test, clause 30.2's flammability-of-plastics requirement, not
a claim about clause 29 insulation coordination. **This is the identical
structure to TE's WG gating**, independently confirmed at a second
manufacturer.

**Verdict: Hongfa HF115F/HF115FK family FAILS the PCB-geometry bar badly
and shows the same self-declaration/GWT-gating pattern as TE on the
certification claim. Not a viable Track A candidate.**

## A.3 Omron appliance-line relays -- DELEGATED, NOT YET RETURNED

A subagent was dispatched this session to survey Omron's appliance-oriented
relay lines (G5NB-HA, G5Q-HA, G2RL-1-HA and others) against the same bar
as A.1/A.2/A.4. **Its results had not returned by the time this document
was finalized.** Per this session's own working rule (never fabricate or
predict a dispatched agent's findings, learned the hard way earlier in this
same session -- an earlier draft of this document briefly, wrongly,
attributed specific Omron figures to a different agent's report before that
mistake was caught and corrected), **no claim about Omron appears anywhere
in this document** -- not a part number, not a certificate number, not a
spacing figure. This is a real gap in Track A's coverage, not a stylistic
choice. If the subagent's results exist by the time a human reads this,
they were not available to the author at write time and should be sought
as a separate, later addendum or a fresh evidence file.

## A.4 TE's other families, Song Chuan, and Zettler -- returned, findings below

A second (re-dispatched, after the mix-up noted in A.3) subagent surveyed
TE's non-RT1/RT2 PCB power relay families plus Song Chuan and Zettler,
against the identical A.1/A.2 evidence bar, fetching and reading real
datasheets and VDE certificates this session. Reported CITED-SECONDARY
(datasheets) / CITED-PRIMARY (VDE certificate scopes, fetched directly)
below, as relayed by that subagent.

**TE T9A** (P&B legacy, 30A, 1NO/1CO): datasheet states only "Product
specification according to IEC 61810-1" -- no 60335-1 claim at all.
Insulation is explicitly basic, not reinforced: clearance/creepage
coil-to-contact only >=2.5/4mm (>=3.1/6.3mm per UL508). Far below 12.6mm.
12VDC coil: 144R+/-10%, 1000mW -- not a coil match. **Ruled out cleanly;
no certification claim to even chase.**

**TE OEG OJ/OJE** (miniature PCB power relay, 3-10A, marketed for "major/
small home appliances"): approvals include VDE 40007630; an ordering
suffix "WG = IEC 60335-1 compliant" exists on specific SKUs. Printed
insulation table: clearance/creepage coil-to-contact = OJ >7.7mm/9.4mm
(3.2mm short of 12.6mm); OJE >3.2mm/3.6mm (far short). **Contact
arrangement is 1 Form A (NO) only across the whole family -- no NC/Form C
variant exists**, disqualifying it on topology alone regardless of
spacing. Coil: 12VDC, 720R/200mW or 320R/450mW depending on sub-type --
not the 360R/400mW match. Max switching voltage only 30VDC; no DC-break
data anywhere near 170-200VDC. **VDE certificate 40007630, fetched
directly: covers OJ/OJE/OJT and lists only EN 61810-1:2015/A1:2020 and
IEC 61810-1:2015 -- the WG/60335-1 ordering-suffix claim is not backed by
this certificate.** Same pattern as TE's WG on RT1 and Hongfa's "(335)".

**Song Chuan T92/T92H** (2-pole, 30/40/50A, sold via TE): front-page
bullet states "WG version available (Meets EN 60335-1)" as a distinct SKU.
**2 Form C is available, satisfying the NC requirement.** Printed
insulation table: clearance/creepage coil-to-contact = 8mm/9.5mm -- 3.1mm
short of 12.6mm. 12VDC coil: 86R, 1.7W nominal/0.41W hold -- not a coil
match (much higher power than the incumbent). No DC-break curve published
(only AC and resistive-DC current tables at higher voltages, e.g. 20A at
28VDC); 170-200VDC/20mA would need extrapolation with no plotted curve to
extrapolate from at all (worse-founded than TE RT1's case, which at least
has a curve). **VDE certificate 40019600, fetched directly: covers
T92/T92H and lists only EN 61810-1:2015/A1:2020 and IEC 61810-1:2015 --
the datasheet's own "Meets EN 60335-1" claim is not reflected in its
certificate.** A third independent confirmation of the same self-declared/
certificate-mismatch pattern.

**Zettler AZSR143/165/190** (50-100A): no IEC/EN 60335-1 claim anywhere on
any of the three datasheets -- compliance line lists only UL 508, IEC
61810-1, RoHS, REACH. **All are 1 Form A (SPST-NO) only -- no NC option**,
disqualifying the family on topology regardless of spacing. Printed
clearance/creepage coil-to-contact: AZSR165/190 >=10.0mm/>=10.0mm (2.6mm
short of 12.6mm, the closest of any part checked across this whole
document); AZSR143 6.4mm/7.6mm. No DC-break curves. A search-engine
summary the subagent initially found claimed a VDE certificate plus an
EN60335-1/EN60730-1 "reinforced insulation" claim for AZSR; the subagent
fetched the actual source article directly and found **no such claim
present in it** -- flagged and discarded by the subagent itself as a
likely search-summarization artifact, not carried into this document as a
finding. (Reported here as a caution about how this kind of research can
go wrong, not as a data point about AZSR.)

**Song Chuan 899/833H** (small signal relays): primary datasheets could
not be retrieved (blocked by distributor hosts). A search snippet claimed
899 carries VDE 40010643 for 60335-1; the subagent fetched that
certificate directly and found it is actually registered to Song Chuan's
**835 series**, scoped only to EN/IEC 61810-1 -- not 60335-1, and not even
the right part family. **Flagged low-confidence/unverified by the
subagent, not treated as a finding.**

**A.4 verdict: nothing in either thread qualifies.** The closest candidate
on geometry is Zettler AZSR165/190 (>=10.0mm, still 2.6mm short, and
1-Form-A-only regardless); the closest on a stated 60335-1 claim is Song
Chuan T92 WG (Form C available, 9.5mm, 3.1mm short, and its VDE
certificate is 61810-1-only exactly like every other candidate checked
across this document). **This is the fourth and fifth manufacturer
(TE-OEG, Song Chuan) whose "meets 60335-1" ordering-suffix claim was
checked directly against its own cited VDE certificate and found
unsubstantiated by that certificate -- the pattern from A.1/A.2 (TE RT1,
Hongfa) is not an anomaly; it is what this industry's labeling looks like
everywhere this document's evidence chain checked.**

---

# TRACK B -- the standards mapping, resolved with primary text

## B.1 The full scope of VDE certificate 40007571, read directly from VDE's own database

**CITED-PRIMARY**, fetched this session from
`vde.com/tic-en/marks-and-certificates/vde-approved-products/certificate?id=40007571&type=zertreg|certificate`
(same URL the verification doc used; re-confirmed, not re-derived):

- Manufacturer: TE Connectivity Austria GmbH, Schrackstrasse 1, 3830
  Waidhofen/Thaya, Austria.
- Product type: "Electromechanical elementary relay," product group
  Relays, scope "RT Serie(s)."
- **Standards applied: DIN EN 61810-1 (VDE 0435-201):2015-10; EN
  61810-1:2015; DIN EN 61810-1/A1 (VDE 0435-201/A1):2020-08; EN
  61810-1:2015/A1:2020; IEC 61810-1:2015; IEC 61810-1:2015/AMD1:2019.**
  **No IEC/EN 60335-1 anywhere.**
- Status: Active. Test procedure: A (3 samples; group mounting).
- A downloadable appendix exists ("Appendix 100A: Type Code," referenced
  alongside appendices 200A-1000) but the database's own summary page --
  the only part fetched this session, consistent with the verification
  doc's own UNVERIFIED flag on this exact point -- does not expose a
  separate pollution-degree/working-voltage field distinct from the
  standards list itself. **The pollution degree and working voltage
  the 61810-1 certificate was qualified at were not found on the public
  database page; the appendix PDF, which might carry a type-by-type
  ratings annex, was not fetched this session** (flagged in UNVERIFIED
  below, same open item the verification doc already flagged, not closed
  here either).

**This is not new information relative to the verification doc** -- it is
confirmed, not re-derived, and the pollution-degree/working-voltage gap in
the public record stands exactly as that document left it.

## B.2 What IEC 60335-1 itself says about accepting a component's own certification -- clause 24.1, read from the standard's own text

**CITED-PRIMARY.** A full copy of IEC 60335-1 (edition 4.1, "IEC:2001+A1:2004") was fetched and read directly this session. This is an
**older edition** than the 2020 (Ed 6.0) edition current at the time of
writing -- only a paywalled preview of Ed 6.0 was available (front matter
only, no clause text) -- so this citation is flagged as edition-specific.
The structural principle quoted below (component certification is
necessary but not sufficient; clause 29 applies at the appliance level
regardless) is corroborated by multiple secondary sources this session
found describing later editions in the same terms, but the *exact section
numbering* (24.1.1-24.1.6 in this edition vs. a reportedly longer
24.1.1-24.1.9-ish list in later editions per a search snippet not
independently verified) may have shifted. Quoted verbatim, clause 24:

> "24.1 Components shall comply with the safety requirements specified in
> the relevant IEC standards as far as they reasonably apply.
>
> NOTE 1 Compliance with the IEC standard for the relevant component does
> not necessarily ensure compliance with the requirements of this
> standard.
>
> Unless otherwise specified, the requirements of clause 29 of this
> standard apply between live parts of components and accessible parts of
> the appliance."

Sub-clauses 24.1.1 through 24.1.6 enumerate the specific "relevant IEC
standard" for six component categories: capacitors (IEC 60384-14), safety
isolating transformers (IEC 61558-2-6), switches (IEC 61058-1), automatic
controls (IEC 60730-1), appliance couplers (IEC 60320-1), small
lampholders (IEC 60238). **Relays are not one of the six.** The closest
applicable text is inside 24.1.3 (switches): *"If the switch operates a
relay or contactor, the complete switching system is subjected to the
test"* -- i.e., when a relay is part of a switching path, the assembly is
tested together, not accepted on the relay's certificate alone. Relays used
as *controls* (e.g., a thermostat-type protective function) would instead
fall under 24.1.4's IEC 60730-1 route -- a real, standards-recognized path
this project has not previously used, noted here as a fact, not a
recommendation to switch topology.

## B.3 What IEC 61810-1 itself says about its own scope, relative to appliance standards

**CITED-PRIMARY**, and this is the single most direct primary-source
answer to the task's question. IEC 61810-1:2015 (the exact edition VDE
40007571 certifies against), clause 1 (Scope), fetched from the IEC's own
preview copy
(`cdn.standards.iteh.ai/samples/19875/298f06bd393348f7a7c06fa9aea7d63c/IEC-61810-1-2015.pdf`), quoted verbatim:

> "This part of IEC 61810 applies to electromechanical elementary relays...
> for applications in all areas of electrical engineering or electronics,
> such as: ... electrical appliances for household and similar use...
>
> Compliance with the requirements of this standard is verified by the
> type tests indicated.
>
> **In case the application of a relay determines additional requirements
> exceeding those specified in this standard, the relay should be assessed
> in line with this application in accordance with the relevant IEC
> standard(s) (e.g. IEC 60730-1, IEC 60335-1, IEC 60950-1).**"

IEC 61810-1's own scope clause names IEC 60335-1 by number as one of the
standards a relay "should be assessed in line with" when its application --
exactly this one -- determines requirements beyond what 61810-1 itself
tests. This is not this document's inference; it is the relay standard
saying, of itself, that it is not sufficient on its own for appliance use.

## B.4 Table 17 -- where this project's 12.6mm figure actually comes from, confirmed against the standard's own table

**CITED-PRIMARY / DERIVED**, same IEC 60335-1 copy as B.2. Clause 29.2
(creepage distances): *"Appliances shall be constructed so that creepage
distances are not less than those appropriate for the working voltage,
taking into account the material group and the pollution degree... Pollution
degree 2 applies unless... the insulation is subjected to conductive
pollution, in which case pollution degree 3 applies."* Clause 29.2.3:
*"Creepage distances of reinforced insulation shall be at least double
those specified for basic insulation in table 17."* Table 17, working
voltage bracket **>250V and <=400V**, pollution degree **3**, material
group **IIIa/IIIb** (both TE's and Hongfa's stated coil-contact material
group): **basic creepage 6.3mm**. Reinforced (clause 29.2.3, double basic):

```
6.3mm x 2 = 12.6mm
```

**This independently reproduces this project's already-established PD3
target (`docs/evidence/2026-07-30-creepage-requirement-reconciliation.md`,
which derives the same 400V-row reasoning for clearance/Table 16) directly
from clause 29/Table 17's own text, for the creepage side specifically.**
This was not previously shown against the standard's primary creepage
table in this project's evidence chain (the reconciliation document works
the clearance/Table 16 side); it is shown here as independent confirmation,
not a new number.

## B.5 The conflation question, resolved

`docs/evidence/2026-07-28-pd3-retarget-relay.md` left open whether a
component's own internal EN 61810-1 rating (there, 8mm on the Finder
40.52; here, 10mm on the RT114012) could be an "acceptable substitute" for
the PCB's own coil-to-contact pad spacing. **INFERRED, from B.2-B.4 above,
not a verbatim standard statement, but a direct application of what those
clauses say:**

The relay's internal coil-to-contact path (rated and certified under IEC
61810-1, inside the sealed/vented case, between the coil bobbin and the
contact set) and the PCB's external coil-pin-to-contact-pin path (along the
board surface, outside the relay's own body, between the same two circuits
as they are brought out to solderable pins) are **two independent,
physically separate creepage paths between the same two circuits.**
Clause 24.1's own text scopes clause 29's appliance-level creepage rule to
apply "between live parts of components and accessible parts of the
appliance" -- language that, read plainly, covers exactly a board-level,
appliance-designer-controlled path like this one, as a matter for the
appliance standard, independent of what the component's own certificate
says about its internal path. Ordinary insulation-coordination practice
(and this project's own already-committed reasoning in
`isolator-creepage-slots.md` and `pd3-retarget-relay.md`) treats parallel
creepage paths as independently governing: **the overall protection is
only as good as the shorter of the two paths**, because a pollution bridge
across either one alone defeats the isolation. A relay's own reinforced
certificate cannot be spent twice -- it answers for the internal path only.

**Verdict: the RT114012 (or any candidate) cannot rely on its VDE
40007571/IEC 61810-1 certificate, however solid, to satisfy the PCB
pad-to-pad creepage requirement.** That requirement is answered
independently by measuring the real PCB layout against Table 17 --
which is exactly the geometric verification this project's evidence chain
has already been doing (13.820mm for RT114012, CONFIRMED against TE's own
dimensioned drawing, clearing 12.6mm with 1.220mm margin). **The
"is-it-60335-1-certified" datasheet-bullet question this document spent
most of its effort on turns out not to be load-bearing for whether
RT114012 satisfies this board's construction requirement** -- the PCB
geometry measurement already answers that directly, on its own terms, per
clause 29. What the bullet question *is* relevant to is a narrower, still
real thing: whether TE's own front-page marketing claim ("product in
accordance to IEC 60335-1") is a claim a human can cite in a compliance
file. On the evidence gathered here, it is not -- it is an unsubstantiated
self-declaration, the same finding the verification doc already reached,
now corroborated at two more manufacturers.

## B.6 Precedent and secondary authority

- **ENEC**: searched this session; could not confirm whether ENEC issues
  certificates for bare elementary relays at all in current practice (the
  scheme's own public materials describe its historical component
  categories as lamp holders, IT equipment, safety isolating transformers,
  and switches -- relays were not confirmed as a listed category this
  session). Where ENEC does cover relays, the standard cited would itself
  be EN 61810-1 (the same component standard TE and Hongfa already cite)
  -- so an ENEC mark on a relay, if one exists, is **not obviously a
  stronger signal for this specific question** than the VDE marks already
  examined; it would most likely be a different notified body attesting
  the same underlying thing. **Flagged as genuinely unresolved, not
  resolved in ENEC's favor as the task's framing anticipated it might be.**
- **CQC (China)**: Hongfa's HF115FK datasheet cites CQC13002103948. CQC's
  public certificate-number query tool requires an interactive form this
  session could not drive (fetch attempts 404'd or require JS/POST); the
  certificate's exact standard scope was **not independently confirmed**.
  Secondary-source research this session found that relays used in Chinese
  household appliances are "typically certified under specific component
  certification categories... rather than directly under the complete
  appliance standard GB 4706.1" (GB 4706.1 being China's national adoption
  of IEC 60335-1) -- consistent with, but not proof of, the same
  component-only pattern found at VDE. **UNVERIFIED for this specific
  certificate number.**
- **Real-world practice, noted for context, not as a citation**: in
  practice, an assembled appliance's IEC 60335-1 conformity is established
  by testing the finished product (or a representative sub-assembly) at a
  notified body/test lab, which independently measures clearances and
  creepages on the actual board as built -- exactly what this project's
  own evidence chain has been doing part-by-part. A relay's own component
  certificate is one input to that process, not a substitute for it,
  regardless of which standard the datasheet's front page names.

---

## Bottom line for a human

**Track A**: no orderable relay found this session, across every family
checked (TE RT1/RT2, TE T9A/OEG, Hongfa HF115F/HF115FK, Song Chuan T92,
Zettler AZSR), carries an independently-issued certificate scoped to IEC
60335-1. All show the identical pattern: a front-page or ordering-suffix
compliance claim backed only by a component-standard (IEC 61810-1)
certificate -- checked directly against five separate VDE certificate
numbers, all five EN/IEC 61810-1-only. Most candidates also fail outright
on PCB geometry (TE T9A, Hongfa, Song Chuan T92 all fall 3-5mm short) or on
topology (TE OEG and Zettler AZSR are Form-A-only, no NC available, ruling
them out regardless of spacing). **TE Schrack RT114012 remains this
document's recommendation** -- not because its 60335-1 bullet is any
better-founded than the others (it is not, and should not be cited as
certified), but because it is the only part checked, across every family
in both A.1/A.2 and A.4, with a manufacturer-**printed** (not
pixel-derived, not merely "closest") PCB dimension clearing 12.6mm with
real margin (13.820mm, +1.220mm), a solidly VDE-certified 10mm/5kV internal
reinforced rating, an exact coil match, and confirmed stock. **This
recommendation is explicitly partial in one respect**: Omron's appliance
lines were dispatched to a subagent whose results had not returned when
this document was finalized (A.3) -- that finding is not reflected here in
any form. A human should treat Track A as covering everything except
Omron, and should look for a follow-on addendum (or re-run that one
survey) before treating it as fully exhausted -- though given the
five-for-five pattern already found, a genuinely different outcome from
Omron specifically would be the surprise, not the expectation.

**Track B**: settled with primary text, not just inference. IEC 61810-1's
own scope clause (quoted in full, B.3) says a relay needs separate
appliance-standard assessment when its application demands more than
61810-1 tests. IEC 60335-1 clause 24.1 (quoted in full, B.2) says component
certification "does not necessarily ensure compliance," and scopes its own
clause 29 creepage rule to the appliance level regardless. Table 17 (B.4)
reproduces this project's 12.6mm figure directly from the standard's own
creepage table. **The RT114012 cannot stand on its 61810-1 certification
for the PCB pad-to-pad question -- that was never the right test to ask of
it.** The right test is the one already being applied throughout this
project's evidence chain: does the real, manufacturer-drawn PCB geometry
clear Table 17's reinforced figure. For RT114012, it does (13.820mm,
independently confirmed twice). Whether TE's or Hongfa's datasheet bullet
can be cited as a genuine IEC 60335-1 certification claim in a compliance
file is a separate question this document answers "no" to, on the evidence
gathered -- but it is not the question that actually gates this board's
construction requirement. This standards-mapping conclusion (B.1-B.5) does
not depend on Track A's outcome and holds regardless of what the two
pending subagent surveys eventually find.

## UNVERIFIED (explicit list)

- **VDE 40007571's full appendix** (pollution degree / working voltage the
  61810-1 rating was qualified at) was not fetched -- only the database
  summary page, same limitation the verification doc already flagged.
- **IEC 60335-1's current edition (Ed 6.0, 2020) clause 24 text** was not
  read directly -- only an older edition (2001+A1:2004) was available
  unpaywalled. The structural principle quoted is corroborated by
  secondary sources describing later editions in the same terms, but exact
  sub-clause numbering in the current edition was not independently
  confirmed.
- **CQC13002103948's exact standard scope** (Hongfa) was not confirmed;
  CQC's query tool could not be driven this session.
- **Whether ENEC issues certificates for bare elementary relays at all**,
  and if so under what standard, was not confirmed either way.
- **`docs/ENVIRONMENTAL_SPEC.md`**, checked this session on this base
  commit, still declares Pollution Degree PD2 at line 45, and has no
  numbered "3.1" subsection at all (the file's sections are `##`-level,
  unnumbered below that) -- the "§3.1 PD3 determination" this task's
  background referenced does not exist on `origin/main` at this commit.
  This matches the already-committed finding in
  `docs/evidence/2026-07-29-pd3-part-selection-survey.md` Section 0 (PD3
  is real, in this repo's history, but not yet landed on `main`). This
  document evaluates 12.6mm throughout per the task's explicit instruction
  and flags the same gap rather than re-deriving or disputing it.
- **Track A.3** (Omron's appliance lines) was delegated to a subagent whose
  results were not yet returned when this document's text was finalized --
  see the note in A.3 and the Bottom Line section above. This is the one
  remaining manufacturer thread this document does not cover.
- **A.4's findings (TE T9A/OEG, Song Chuan, Zettler) were relayed by a
  delegated subagent.** The two load-bearing VDE certificate numbers it
  reported were independently re-fetched by this document's author this
  session as a spot-check: **VDE 40007630 (TE OEG OJ/OJE/OJT) and VDE
  40019600 (Song Chuan T92/T92H) both re-confirmed, fetched directly from
  `vde.com`'s own database -- standards applied are EN/IEC 61810-1 only in
  both cases, no 60335-1 mention either time.** The remaining figures in
  A.4 (datasheet dimensions, coil specs, the discarded Zettler AZSR search
  artifact, the Song Chuan 899 certificate mismatch) were not independently
  re-fetched by the author a second time -- the subagent's own report shows
  internal self-checking on those points (it caught and discarded a
  likely-fabricated search-summary claim about AZSR before reporting, and
  flagged the 899/835 mismatch as low-confidence rather than asserting it),
  which is a good sign but is not the same as a second independent read.

## Hard-constraint compliance

- **No design file, constant, footprint, or netclass modified.** Only this
  document written this session; `git status --short` clean apart from it.
- **Own git worktree**, branched fresh from `origin/main` at `46d4b4c8`,
  not a shared/pre-existing worktree.
- **No `git stash`** used anywhere this session.
- **No part swapped, no unverified MPN proposed.** RT114012 (already
  proposed on a sibling branch, not landed here) is the only candidate part
  number this document recommends; HF115FK, T9A, OJ/OJE, T92/T92H, and
  AZSR143/165/190 are all named as rejected candidates with numbers shown,
  per A.2/A.4. No claim is made about any part number this document did
  not itself (A.1/A.2/spot-checks) or a delegated subagent whose report was
  read and relayed (A.4) fetch a primary source for -- see A.3 for the one
  survey (Omron) whose results are deliberately not represented here at
  all.
- Not pushed, no PR opened.

## Sources (fetched this session)

- VDE certificate 40007571 --
  `vde.com/tic-en/marks-and-certificates/vde-approved-products/certificate?id=40007571&type=zertreg|certificate`
- VDE certificate 116934 (Hongfa) --
  `vde.com/tic-en/marks-and-certificates/vde-approved-products/certificate?id=116934&type=zertreg|certificate`
- VDE certificate 40007630 (TE OEG OJ/OJE/OJT), independently re-fetched by
  this document's author as a spot-check on the A.4 subagent's report --
  `vde.com/tic-en/marks-and-certificates/vde-approved-products/certificate?id=40007630&type=zertreg|certificate`
- VDE certificate 40019600 (Song Chuan T92/T92H), independently re-fetched
  as the same spot-check --
  `vde.com/tic-en/marks-and-certificates/vde-approved-products/certificate?id=40019600&type=zertreg|certificate`
- Hongfa HF115F-Q datasheet --
  `source.hongfa.com/Uploads/Product/PDF/HF115F-Q_en.pdf`
- Hongfa HF115FK datasheet --
  `source.hongfa.com/Uploads/Product/PDF/HF115FK_en.pdf`
  (PCB layout page rendered at 300dpi this session for the dimension read)
- IEC 61810-1:2015 (preview copy, Scope clause) --
  `cdn.standards.iteh.ai/samples/19875/298f06bd393348f7a7c06fa9aea7d63c/IEC-61810-1-2015.pdf`
- IEC 60335-1 (edition 2001+A1:2004, full text) --
  `u.dianyuan.com/bbs/u/35/1131687973.pdf`
- IEC 60335-1 Ed. 6.0 (2020) preview -- front matter only, no clause text
  accessible -- `cdn.standards.iteh.ai/samples/101518/78945351a99747cd8a166a9ac8688b50/IEC-60335-1-2020.pdf`
- SCHURTER white paper, "Components and IEC 60335-1" (GWT/GWFI/clause 30.2
  background) -- fetched via DigiKey-hosted PDF link, used for context on
  what the "(335)"/"WG" gating actually tests.
- TE T9A, TE OEG OJ/OJE, Song Chuan T92/T92H, and Zettler AZSR143/165/190
  datasheets -- fetched and read by the delegated A.4 subagent, not
  re-fetched independently by this document's author (see UNVERIFIED);
  exact URLs were not relayed back and are not reproduced here.
- In-repo: `docs/evidence/2026-07-28-pd3-retarget-relay.md`,
  `docs/evidence/2026-07-29-pd3-part-selection-survey.md`,
  `docs/evidence/2026-07-29-pd3-part-selection-verification.md`,
  `docs/evidence/2026-07-30-creepage-requirement-reconciliation.md`,
  `docs/ENVIRONMENTAL_SPEC.md`, `elec/src/modules.ato` (`BusDischarge`).
