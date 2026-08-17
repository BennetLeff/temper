<!-- provenance: commit=7b424488fc70f86b3be0630b9b213e38313df4a2 (origin/main at fork point),
     dirty=false. Own git worktree (/tmp/opencode/agent-ocp-certlab, branch
     chore/ocp02-descope-and-certlab-send). This is the consolidated, sendable inquiry —
     it merges the cover letter (docs/cert-lab-cover-letter-2026-08-15.md, PR #1236) with the
     evidence package (docs/evidence/2026-08-14-certification-lab-package-pd3-and-60664-4.md,
     PR #1209) and incorporates the Question A sharpening from
     docs/evidence/2026-08-16-cert-lab-and-ocp02-spike.md (PR #1262). No standards value is
     invented or reconstructed: every figure cites its source. No pcb/temper.kicad_pcb or
     enforced safety constant was touched (board hash ddb96f9e… unchanged).
     UPDATED 2026-08-16 (investigate/board-redesign-evaluation): §6 corrected to the current
     board's actual designator state (U6 = UCC21550 gate driver, U7 = SMA bootstrap diode;
     verified against the board file by footprint/nets), board hash line refreshed, and
     T1/T2/U7 -> T1/T2/U6 re-labelled throughout. No Question A/B figure changed. -->

# Certification-lab inquiry — Temper induction cooktop (IEC 60335-1): two standards-interpretation questions

**Date:** 2026-08-16
**To:** Certification test house / IEC 60335-1 (as read through IEC 60335-2-6) reviewing body
**From:** Temper induction-cooktop development project
**Subject:** (1) PD3 island-slot creepage credit for the isolation-barrier components T1/T2/U6;
(2) IEC 60664-4 applicability at the 44–50 kHz tank frequency

---

## 1. Project overview

We are developing an induction cooktop for US residential use — a series-resonant half-bridge
induction cooker controlled by an ESP32-S3, targeting IEC 60335-1 compliance (read through IEC
60335-2-6 for cooking appliances). We are requesting your determination on two standards-
interpretation questions the project cannot close in-house because the governing standards text is
paywalled. Both questions carry full in-house analysis with measured figures; what we lack is the
specific normative text and a certification determination applying it.

## 2. Board and operating conditions (the facts the questions rest on)

| Item | Value |
|---|---|
| Board | 6-layer FR4 PCB (current board file declares F.Cu/In1–In4/B.Cu; board revision hash `ddb96f9e…` — supply the exact board file revision with any geometry review) |
| Construction | Forced-air vented (bottom-intake airflow through the PCB cavity by design); **no cover, gasket, or sealed compartment** → **pollution degree 3 (PD3) governs the as-built board** (IEC 60335-2-6 cl. 29.2 Addition; PD2 is earned only when the insulation is enclosed — our PD2 compartment is not built and is not committed anywhere) |
| Mains input | **120 V RMS ±10%, 60 Hz only** (US 15 A outlet; max 15 A continuous; input ≤1900 W). **No 240 V variant is designed** — the voltage-doubler exists specifically so no 240 V input is needed; the schematic asserts `v_ac_nominal` within 100–130 V |
| Max output power | 1.8 kW |
| Tank operating frequency | 44–50 kHz (PLL-controlled series-resonant tank; `PLL_MIN_FREQ_HZ 44000` / `PLL_MAX_FREQ_HZ 50000` in firmware, mirrored in the schematic) |
| Overvoltage category | **OVC II** (IEC 60335-1 cl. 29.1: "Appliances are in overvoltage category II") |
| Key components | IKW40N120H3 IGBTs (1200 V / 40 A) ×2; UCC21550 isolated gate driver (see §6 for the U6/U7 designator note); Coilcraft CST3015 current-sense transformers (T1, T2); galvanic isolation across T1/T2/U6 |
| Governing creepage figures | **PD3 reinforced 12.6 mm** (>250–400 V, Table 17 row iv, material group IIIa/IIIb); tank functional **10.0 mm** (Table 18 row vi, >500–800 V) |

## 3. What we need from you

1. **The normative text of IEC 60335-1 Annex L** (slot / creepage-credit provisions) — paywalled;
   content beyond its table of contents was not accessible to us.
2. **The normative dimensioning clauses and tables of IEC 60664-4** (clauses 4/5/6 — high-frequency
   clearance, creepage, and solid-insulation dimensioning) — paywalled; only the scope paragraph is
   publicly readable. No figure from this standard is used anywhere in our package.
3. **Your determination on each question below, citing the specific clauses/tables relied on.**

---

## 4. Question A — does a PCB slot earn creepage credit at its closed end, for the isolation-barrier components?

**The problem.** At PD3's 12.6 mm reinforced-creepage requirement, three of our declared galvanic
isolators cannot reach 12.6 mm from their intrinsic package geometry alone — a property of each
part's package/pin geometry, not a layout defect:

| Part | Part number | Intrinsic (unslotted) primary↔secondary creepage | Shortfall vs 12.6 mm |
|---|---:|---:|
| T1 | Coilcraft CST3015-100ED current-sense transformer | 9.100 mm | −3.500 mm |
| T2 | Coilcraft CST3015-100ED (same part; OCP-02 CT — see note in §6) | 9.100 mm | −3.500 mm |
| U6* | TI UCC21550BDWKR isolated gate driver | 8.100 mm | −4.500 mm |

\* *Designator per §6 — this is the UCC21550, named U6 on the measurement branch and on the
current board (an earlier board lineage and the older documents in this package call it U7).*

No replacement part clears the requirement: an exhaustive search across Coilcraft, TDK, and other
manufacturers for a 1:100, ≥50 A-sensed current-sense transformer with better PCB creepage found
none, and every reinforced gate-driver IC and optocoupler surveyed plateaus at 7–8.5 mm. A routed,
non-plated, full-board-thickness PCB slot under the component is the one mechanism that reaches
12.6 mm without a part change or redesign — *if it earns the creepage credit the standard's text
does not clearly grant*.

**What we have already established in-house (recovered primary text):** IEC 60335-1 cl. 29.2's
Note delegates creepage measurement to IEC 60664-1, and IEC 60664-1 cl. 4.2 (quoted verbatim from
IS 15382 (Part 1):2003, the identical national adoption) already covers the groove-*body*:
a parallel-sided groove of width ≥ **X = 1.5 mm at PD3** ("If the associated clearance is less than
3 mm, the minimum dimension X may be reduced to one third of this clearance") earns
contour-following credit (Example 2: "Creepage path follows the contour of the groove"). All our
slot designs (4.0–8.0 mm wide) clear X by 2.4–5.3×. **We do not need you to confirm that a wide
groove earns contour credit — that is cited text.** What we need you to confirm is the one thing no
recovered worked example pictures:

**The question.** For a fully-through, full-board-thickness, non-plated PCB slot that terminates
*inside* the board on at least one end (both walls solid FR4 at that end — not reaching the board's
true outline), entirely underneath a surface-mount component's own body but clear of all pads: is
the governing creepage path from a pad on one side of the slot to a pad on the other
(a) the straight-line distance ignoring the slot (the slot does not count because the path is
considered to run under/through the component regardless of the cutout); (b) a path that detours
around the slot's nearest closed end and stays on the accessible top surface; or (c) something else
— e.g., is the slot disregarded because the moulded package body itself, not just the missing PCB
material, defines the creepage surface? **Please cite the specific clause/worked example
(IEC 60664-1 cl. 4.2 in the 2002-era text / cl. 6.8 in the current 3.0:2020 and 3.1:2025 editions,
or IEC 60335-1 Annex L) that the answer relies on** — none of cl. 4.2/6.8's 11 worked
groove/rib/joint examples, in either edition, pictures a slot with real, board-surrounded *ends*:
all are 2D cross-sections of features implicitly infinite in the third dimension.

A **secondary sub-question, only if the slot earns credit at its closed end**: does an
edge-reaching redesign — the same slot with one end extended to the board's true outline, the other
end still closed — change the answer for the remaining closed end? Our topological analysis says it
cannot: past a true board edge there is no FR4 on any layer, so no path can exist there, and a
single connected slot cannot reach the true edge at *both* ends without disconnecting a region of
the board (Jordan-curve argument on our simple-rectangle outline). Please confirm or correct this
reasoning.

**Our in-house figure for context** (full derivation in the evidence package §1): with the closed-
end credit assumed, the governing path for T1 detours around the closed end, giving **13.27 mm
nominal / 12.83 mm worst-case** — a marginal +0.23 mm pass over 12.6 mm. We explicitly do not
conflate this physical reasoning with a standards determination.

## 5. Question B — does IEC 60664-4 apply at our 44–50 kHz tank frequency, and if so, what does it require?

**The problem.** Our resonant tank operates at **44,000–50,000 Hz** across its entire legal range.
IEC 60664-4 (*Insulation coordination for equipment within low-voltage systems — Part 4:
Consideration of high-frequency voltage stress*) states in its scope (publicly readable, quoted
from IEC's own catalogue entry and free preview PDF): *"applicable for the dimensioning of
clearances, creepage distances and solid insulation stressed by any type of periodic voltages with
a fundamental frequency above 30 kHz and up to 10 MHz."* Our operating range sits above that
threshold. The standard's normative dimensioning clauses (4/5/6) are paywalled, so we cannot
determine what it would require.

Separately, the governing high-frequency node measures **923.7 V peak** (live simulation, full
44–50 kHz envelope, all L/C tolerance corners) — above the **700 V-peak** threshold IEC 60335-1
Annex J itself flags as partial-discharge-relevant (a note written for coating qualification, not
bare-board air gaps — we ask whether the same threshold applies to our uncoated gap at this
frequency).

**The questions.**

1. Does IEC 60664-4 apply to a PCB-internal functional-insulation clearance/creepage boundary
   carrying a periodic 44–50 kHz voltage? If so, what frequency-dependent factor applies to
   (a) our clearance figure — **2.0 mm required** per IEC 60335-1 cl. 29.1.5 / Table 16 at a
   923.7 V-peak determining voltage of 2254 V (1500 V rated impulse + (923.7 − 169.7) V) — and
   (b) our creepage figure — **6.3 mm PD2 / 10.0 mm PD3** at 570.5 V rms, Table 17/18 row vi?
   Please cite the specific clause/table.
2. Is partial-discharge inception testing warranted for a recurring 923.7 V-peak across a ~2.0 mm
   air gap at 44–50 kHz, given the 700 V-peak note in IEC 60335-1 Annex J?
3. Does IEC 60664-4 (or IEC 60335-1 itself) impose anything beyond what cl. 29.1.5's
   determining-voltage arithmetic already computes for a resonant/higher-than-rated working voltage
   (Table 15 Note 2)? Our reading is that cl. 29.1.5 is the mechanism Note 2 points at; we ask for
   confirmation or correction.
4. The UCC21550 gate driver's secondary side floats on the 44–50 kHz switching node. Does its
   galvanic barrier's own pad-gap creepage/clearance rating (datasheet-specified against
   DC/mains-frequency withstand) need re-examination for the same high-frequency periodic stress, or
   is a galvanically isolated barrier's stress profile categorically different from the
   same-domain functional-insulation gap asked about above?

**Why this is urgent, not theoretical.** This pair carries our two largest simultaneous risk
factors: it is the pair with the least existing clearance margin (2.0 mm required / 2.0 mm
provided — an exact Table 16 step-boundary coincidence, not a design margin), and its margin is
held by a protection function (our over-current trip), not by copper geometry. A
frequency-derating factor of even 1.0×+ would move this pair from "exactly adequate" to
"inadequate" with zero present margin. Its creepage is a known, currently-unenforced 3.2–5.0×
shortfall at power-frequency figures alone.

---

## 6. Board-state note — read before cross-referencing (designator collision)

Reference designator **U6** names the UCC21550 gate driver in the branch lineage our Question A
geometry was measured on, and **on the current board U6 is still the UCC21550 gate driver**
(verified against the shipped board file by footprint and nets — `GATE_HS`, `SHUTDOWN`,
`hb.gate_hs.driver-p1-1`, `+15V_LS`, SOIC-16 DWK land pattern). **U7 on the current board is a
different part: the SMA bootstrap diode** (`hb.gate_hs.driver-p1-1`/`+15V_LS`, `Diode_SMD:D_SMA`),
not the gate driver — an earlier board lineage carried an IGBT as U6 and the gate driver as U7,
and that older assignment is what some documents in this package were written against. Every "U6"
in older documents means the gate driver per the branch its figures were measured on — never an
IGBT. The parts Question A refers to are, unambiguously, identified by part number: **Coilcraft
CST3015-100ED current-sense transformers (T1, T2)** and the **TI UCC21550BDWKR gate driver
(U6 on the measurement branch and on the current board)**.

Additional state notes, so nothing in this letter is misread:

- **T2 is staged off-board** (not placed on the board; it is the de-scoped OCP-02 CT). Its
  intrinsic figure transfers directly from T1 (identical part, identical footprint); its slot
  design transfers identically if it is ever placed.
- **Question B's figures were measured against board sha256 `6928b7c8…`; Question A's against
  `b7d865b7…`** (a resync/renumber lineage). The two board states are not interchangeable. We will
  supply the exact board file revision matching any geometry we ask you to review.
- Board revision shipped with this inquiry: sha256 `9c1f4a37…` (this PR's board — `main` at
  `593d9ab2` plus the left-edge outline enlargement + R5/U7/C23 placement moves of
  `docs/evidence/2026-08-16-board-enlargement-left-column-redesign.md`; the immediately prior
  `main` board was `72e14ab4…`, and the ZCD-removal lineage was `ddb96f9e…`). None of these
  changes touch T1, T2, or the U6 gate driver — the Question A geometry is positionally
  unchanged on the shipped board.

## 7. Attachments and where the full detail lives

The complete evidence package — every figure's measurement method, derivation chains, worst-case
fab-tolerance model, the board-state map, and the full Question A slot geometries — is
**`docs/evidence/2026-08-14-certification-lab-package-pd3-and-60664-4.md`**. Supporting
documents:

- `docs/evidence/2026-08-12-hv-clearance-adequacy.md` — Question B clearance derivation, 923.7 V
  peak figure, OCP-01 margin analysis (on `main`)
- `docs/evidence/2026-08-12-hv-hv-creepage-determination.md` — cl. 29.2.4 functional-insulation
  analysis, Table 18 comparison (on `main`)
- `docs/evidence/2026-07-28-creepage-determination-brainstorm.md` — recovered IEC 60335-1 Tables
  15/16/17, cl. 29.1/29.1.5 (on `main`)
- `docs/evidence/2026-08-11-pd2-decision-record.md`, `docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md`
  — the PD3-governs-as-built finding (on `main`)
- `docs/evidence/2026-08-13-hv-creepage-pd3-gap-measurement-and-plan.md`,
  `docs/evidence/2026-08-13-hv-creepage-slot-rescue-t1-t2-u6.md`,
  `docs/evidence/2026-08-13-hv-creepage-edge-reaching-slot-determination.md` — Question A intrinsic
  figures and slot designs (branch-specific; figures reproduced in the package §1)
- `docs/evidence/2026-08-16-cert-lab-and-ocp02-spike.md` — the recovered-text narrowing of
  Question A's premise (groove-body credit is cited text; only the bounded-slot closed end needs
  your determination) and the de-scope of T2's OCP-02 subsystem (on `main`)
- Component drawings available on request: Coilcraft CST3015 Recommended Land Pattern (Document
  1608-2); TI UCC21550BDWKR datasheet (SLUSE89C); physical sample or 3D render of the slotted
  geometry; the committed simulation deck (`zvs_margin_sweep.cir`) behind Question B's figures.

We are happy to supply anything above in full, or to walk through the geometry on a call.

Thank you for your time.

---

*This inquiry supersedes `docs/cert-lab-cover-letter-2026-08-15.md` as the sendable document. It
adds: the recovered-text Question A sharpening (§4 — groove-body credit is now cited primary text;
only the bounded closed end remains open), the consolidated board-state note (§6), and explicit
verification that the package's operating conditions are current: 120 V only, PD3 governs, OVC II.*
