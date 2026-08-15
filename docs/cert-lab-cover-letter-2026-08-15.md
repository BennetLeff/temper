<!-- provenance: commit=7f6a6bd5c3cf9ce8adc1cd9ab67b677239d34792 dirty=false (branch
     chore/close-1198-and-certlab-prep, based on origin/main at HEAD. Companion to
     docs/evidence/2026-08-14-certification-lab-package-pd3-and-60664-4.md (on main, PR #1209),
     which carries the full evidence, figures, and board-state disambiguation. No
     pcb/temper.kicad_pcb or enforced safety constant was touched. No standards value is invented
     or reconstructed in this letter: every figure cites its source in the companion package. -->

# Cover letter — certification-lab inquiry: Temper induction cooktop (IEC 60335-1)

**Date:** 2026-08-15
**To:** Certification test house / IEC 60335-1 reviewing body
**From:** Temper induction-cooktop development project
**Subject:** Two standards-interpretation questions requiring primary standards text or a
certification determination (PD3 island-slot creepage credit; IEC 60664-4 applicability at
44–50 kHz)

## 1. Project overview

We are developing an induction cooktop for US residential use. The appliance is a
series-resonant half-bridge induction cooker controlled by an ESP32-S3 microcontroller,
targeting IEC 60335-1 compliance (as read through IEC 60335-2-6 for cooking appliances).
This letter accompanies a complete evidence package
(`docs/evidence/2026-08-14-certification-lab-package-pd3-and-60664-4.md`) and asks two
specific questions the project cannot close in-house because the governing standards text
is paywalled. We ask for your interpretation of the two questions below, with citations,
and for the specific normative text listed in §5.

## 2. Board and operating conditions

| Item | Value |
|---|---|
| Board | 6-layer FR4 PCB (declared production stackup; the stackup declaration is in the design lineage under review — see the companion package §0 for board-state details) |
| Construction | Forced-air vented (bottom-intake airflow through the PCB cavity by design); **no cover, gasket, or sealed compartment** → **pollution degree 3 (PD3) governs the as-built board** |
| Mains input | 120 V RMS ±10%, 60 Hz (US 15 A outlet; max 15 A continuous; input ≤1900 W) — no 240 V variant is designed |
| Max output power | 1.8 kW |
| Tank operating frequency | 44–50 kHz (PLL-controlled series-resonant tank) |
| Overvoltage category | OVC II (IEC 60335-1 cl. 29.1) |
| Key components | IKW40N120H3 IGBTs (1200 V / 40 A) ×2, UCC21550 isolated gate driver, Coilcraft CST3015 current-sense transformers (T1/T2), galvanic isolation across T1/T2/U6 (see §4 for the U6/U7 designator note) |
| Governing creepage figures | PD3 reinforced **12.6 mm** (>250–400 V, Table 17 row iv, material group IIIa/IIIb); tank functional **10.0 mm** (Table 18 row vi, >500–800 V) |

## 3. Findings from this week's safety audit (context for the questions)

Three findings from a recent internal audit of our safety-distance implementation are
directly relevant to the questions below:

1. **PD3 is the applicable pollution degree.** Our PD2 production target (8.0 mm
   reinforced creepage) was conditional on a sealed, gasketed PCB compartment separate
   from the forced-air path. That compartment is not built and is not committed anywhere
   in the design. Per IEC 60335-2-6 cl. 29.2's Addition, PD2 is earned only when the
   insulation is enclosed; our as-built, forced-air-vented construction therefore
   **governs at PD3 — raising the reinforced-creepage bar from 8.0 mm to 12.6 mm**.
2. **A 14.0 mm creepage base in our clearance implementation was verified as fabricated.**
   An audit traced it to an unsourced constant (no clause, no table row, no derivation);
   it is not traceable to any recovered standard at any applicable row, pollution degree,
   or material group, and the "Table 17" citation attached to it does not support it. It
   has since been removed from the codebase in favor of recovered-table lookups. This
   finding is noted here only to be transparent that we found and corrected an
   unsupported internal value; it does not affect the questions below, which concern
   genuine gaps in the recoverable text.
3. **OVC II governs** (IEC 60335-1 cl. 29.1: "Appliances are in overvoltage category II"),
   which we have aligned our clearance derivation to.

## 4. Question A — PD3 island-slot creepage credit for the isolation barrier components (T1, T2, U6)

**The problem.** At PD3's 12.6 mm reinforced-creepage requirement, three of our declared
galvanic isolators cannot reach 12.6 mm from their intrinsic package geometry alone
(T1/T2: 9.100 mm intrinsic; U6: 8.100 mm intrinsic — a property of each part's
package/pin geometry, not a layout defect). No replacement part clears the requirement.
A routed, non-plated, full-board-thickness PCB slot under the component is the one
mechanism that reaches 12.6 mm without a part change or redesign — *if it earns the
creepage credit the standard's text does not clearly grant*.

**The question.** For a fully-through, non-plated PCB slot that terminates *inside* the
board (one or both ends solid FR4, not reaching the board outline), entirely underneath a
surface-mount component's body but clear of all pads: is the governing creepage path from
a pad on one side to a pad on the other (a) the straight-line distance ignoring the slot,
(b) a path detouring around the slot's nearest closed end on the accessible top surface,
or (c) something else — e.g., is the slot disregarded because the moulded package body
itself defines the creepage surface? We ask this specifically under **IEC 60664-1
(clause 4.2 in the 2002-era text / clause 6.8 in the current editions, and Annex L of
IEC 60335-1)**. Neither edition's 11 worked groove/rib/joint examples pictures a slot
with real, board-surrounded *ends* — the exact geometry we need.

A secondary sub-question (only if the slot earns credit at its closed end): does an
edge-reaching redesign — the same slot with one end extended to the board's true outline,
the other end still closed — change the answer for the remaining closed end? Our own
topological analysis says it cannot (a slot cannot reach the true edge at both ends
without disconnecting the board; past a true edge there is no FR4 on any layer, so no
path exists there). We ask you to confirm or correct this reasoning.

Our in-house analysis (full derivation, figures, and worst-case fab-tolerance model in
the companion package §1) concludes the governing path detours around the closed end,
yielding **13.27 mm nominal / 12.83 mm worst-case for T1** — a marginal +0.23 mm pass
over 12.6 mm — but this is explicitly **not validated by any specific worked example**,
and we do not conflate our physical reasoning with a standards determination.

## 5. Question B — does IEC 60664-4 apply at our 44–50 kHz tank frequency?

**The problem.** Our resonant tank operates at **44,000–50,000 Hz** across its entire
legal range. IEC 60664-4 (*Insulation coordination for equipment within low-voltage
systems — Part 4: Consideration of high-frequency voltage stress*) states in its scope
(publicly readable) that it applies to "periodic voltages with a fundamental frequency
above 30 kHz and up to 10 MHz" — our operating range sits above that threshold. But the
standard's normative dimensioning clauses and tables are paywalled, so we cannot
determine what it would require. Separately, the governing high-frequency node measures
**923.7 V peak**, above the 700 V-peak threshold IEC 60335-1 Annex J itself flags as
partial-discharge-relevant (a note written for coating qualification, not bare-board air
gaps — we ask whether the same threshold applies to our uncoated gap at this frequency).

**The questions.**

1. Does IEC 60664-4 apply to a PCB-internal functional-insulation clearance/creepage
   boundary carrying a periodic 44–50 kHz voltage? If so, what frequency-dependent factor
   applies to (a) our clearance figure (2.0 mm required per IEC 60335-1 cl. 29.1.5 /
   Table 16 at a 923.7 V-peak determining voltage of 2254 V) and (b) our creepage figure
   (6.3 mm PD2 / 10.0 mm PD3 at 570.5 V rms, Table 17/18 row vi)? Please cite the
   specific clause/table.
2. Is partial-discharge inception testing warranted for a recurring 923.7 V-peak across a
   ~2.0 mm air gap at 44–50 kHz, given the 700 V-peak note in IEC 60335-1 Annex J?
3. Does IEC 60664-4 (or IEC 60335-1 itself) impose anything beyond what cl. 29.1.5's
   determining-voltage arithmetic already computes for a resonant/higher-than-rated
   working voltage (Table 15 Note 2)? Our reading is that cl. 29.1.5 is the mechanism
   Note 2 points at; we ask for confirmation or correction.

This pair already carries our two largest simultaneous risk factors: it is the pair with
the least existing clearance margin (2.0 mm required / 2.0 mm provided — an exact Table 16
step-boundary coincidence, not a design margin), and its margin is held by a protection
function (our over-current trip), not by copper geometry. A frequency-derating factor of
even 1.0×+ would move this pair from "exactly adequate" to "inadequate" with zero present
margin. Creepage for this pair is a known, currently-unenforced 3.2–5.0× shortfall at
power-frequency figures alone.

## 6. What we need from you

To answer the two questions above, we need:

1. **The normative text of IEC 60664-1 Annex L** (slot / creepage-credit provisions in
   the context of IEC 60335-1) — paywalled; content beyond its table of contents was not
   accessible to us.
2. **The normative dimensioning clauses and tables of IEC 60664-4** (clauses 4/5/6 —
   high-frequency clearance, creepage, and solid-insulation dimensioning) — paywalled;
   only the scope paragraph is publicly readable. No figure from this standard is used
   anywhere in our package.
3. **Your determination on each question**, citing the specific clauses/tables relied on.

## 7. Board-state note (important for cross-referencing)

Reference designator **U6** names the UCC21550 gate driver in the branch lineage our
Question A geometry was measured on, but **U6 is a different, unrelated IGBT on `main`
today, where the gate driver is U7**. The companion package §0 carries the full
board-state map (branch, commit hashes, sha256). When referring to the isolation barrier
components, the parts are: Coilcraft CST3015-100ED current-sense transformers (T1, T2)
and the TI UCC21550BDWKR gate driver (U6 on the measurement branch / **U7 on main**). We
will supply the exact board file version matching any geometry we ask you to review.

The full evidence package — including every figure's measurement method, the board-state
disambiguation, and the complete derivation chains — is
`docs/evidence/2026-08-14-certification-lab-package-pd3-and-60664-4.md`. We are happy to
supply the committed simulation deck, component datasheets, and a physical sample or 3D
render of the slotted geometry on request.

Thank you for your time.
