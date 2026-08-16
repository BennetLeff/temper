<!-- provenance: commit=607cc7bd662b14eb3e34e65859e9a5d74dedb3dc (origin/main at fork point)
     dirty=false throughout (git status --porcelain clean apart from this document). Own git
     worktree (/tmp/opencode/agent-cert-ocp, branch investigate/cert-lab-and-ocp02-spike), never
     the main checkout. pcb/temper.kicad_pcb sha256=ddb96f9e03abdcbb0aa40523b45c07413bc6943094
     17628907780e3d19527ef2, read-only. No pcb/temper.kicad_pcb, footprint, DRU threshold, or
     enforced safety constant was edited anywhere in this task -- this is a spike/analysis
     deliverable, no board change. All standards figures below are quoted from recovered primary
     text already in this repo (cited by exact document), or from datasheets fetched live this
     session (Allegro ACS712/ACS724, TI AMC1301 -- each figure states its source). No standards
     value is invented or reconstructed. -->

# T1/T2/U6 cert-lab creepage spike (can slots clear the 7 without the lab answer?) + OCP-02 mechanism redesign spike

**Date:** 2026-08-16
**Purpose:** Two external-resolution items, prepped further before the answers arrive:
(A) whether the 7 same-footprint T1/T2/U6 PD3 creepage violations can be cleared by routed slots
WITHOUT waiting for the certification-lab answer (cert-lab package on main, PRs #1209/#1236);
(B) a data-driven recommendation for OCP-02's sensing mechanism given the CST3015 CT's 9.1mm
primary↔secondary separation against the 12.6mm PD3 reinforced bar.

**Headline, both parts:**

- **Part 1: No slot clears any of the 7 violations without the cert-lab answer.** The repo's own
  edge-reaching slot determination (`docs/evidence/2026-08-13-hv-creepage-edge-reaching-slot-determination.md`)
  proves the slots *geometrically* reach 12.6mm for T1 (13.265mm nominal / 12.830mm worst-case)
  and U6 (14.85mm / 14.11mm), but its own verdict is explicit on every row: the governing path
  still detours around the still-closed interior end, and that end's creepage credit is **exactly
  cert-lab Question A** — narrowed from two uncertain ends to one, not eliminated. Implementing
  the slots now would be implementing a compliance-relevant board change whose credit is
  unresolved; the repo's own prior determinations have repeatedly declined exactly this.
- **Part 2: De-scope OCP-02 (keep T2/C37/R65 in staging).** Every alternative mechanism checked
  with verified figures fails the 12.6mm bar: Hall ICs (ACS712/ACS724) at 4.0–4.2mm creepage,
  AMC1301 isolated amplifier at 8.5mm, alternative CT parts at ≤9.1mm. The aperture/donut CT
  (ICE CT07-1000 class, Talema ASM) is the only technically-plausible long-term fix — for T1+T2
  jointly — but remains blocked on a verified third-party reinforced-insulation certificate,
  exactly as the repo's prior work found. OCP-02 is not IEC 60335-1 clause-mandated; de-scoping
  is legitimate with a stated, bounded safety cost (loses the DC_BUS_RTN shoot-through sensing
  path that OCP-01's tank CT does not cover by construction).

---

## Part 1 — the 7 T1/T2/U6 same-footprint creepage violations vs. the cert-lab question

### 1.1 What the "7" is

The DRC-zero action plan (`docs/evidence/2026-08-16-drc-zero-action-plan.md` §3.2, on main)
classifies the routed-board PD3 creepage total (511) by item type: **"21 config same-footprint
(7 of them T1/T2/U6 pad-pad = cert-lab question)"**. The 7 are the same-footprint pad↔pad
intra-part pairs of T1 (Coilcraft CST3015, `ct_sense.ct`), T2 (same part, `safety.ocp2.ct`), and
U6 (TI UCC21550BDWKR gate driver, `hb.gate_hs.driver` — **U6 on main's current board**, the
resync lineage has landed; U7 is now a diode) that fail the 12.6mm PD3 reinforced bar. The
intrinsic (unslotted) governing figures, measured with the repo's canonical
rotation-and-side-aware pad-geometry kernel and reproduced to 4 decimal places across PRs
#1146/#1152/#1160:

| Part | Part number | Intrinsic governing pair | Intrinsic creepage | vs 12.6mm |
|---|---|---:|---:|---|
| T1 | Coilcraft CST3015-100ED | pad1↔pad4 / pad2↔pad3 (primary↔secondary) | 9.100mm | −3.500mm |
| T2 | Coilcraft CST3015-100ED (same part) | identical | 9.100mm | −3.500mm (if placed) |
| U6 | TI UCC21550BDWKR | pin3↔pin14 | 8.100mm | −4.500mm |

Both parts' positions on main's board match the edge-reaching determination's measured geometry
exactly (T1 at `(53.21, 148.91, 90°)`, T2 parked off-board at `(100.0, 300.0)`, U6 at
`(85.91, 142.43, 90°)` — confirmed directly from `pcb/temper.kicad_pcb` this session), so the
determination's figures transfer without re-derivation.

### 1.2 What the edge-reaching slot determination established (PR #1194, merged)

`docs/evidence/2026-08-13-hv-creepage-edge-reaching-slot-determination.md` measured, against the
real board, whether a slot with **one end reaching the true board edge** rescues these parts.
Its verdict table is the load-bearing fact for this spike:

| Part | Edge-reaching geometrically possible? | Governing creepage with slot | vs 12.6mm | Standards question |
|---|---|---:|---|---|
| T1 | YES — south end, toward left edge (x=20), 17.96mm arm | 13.265mm nominal / 12.830mm worst-case | PASS (+0.230mm worst-case) | **Narrowed to 1 end (north), not eliminated** |
| T2 | Contingent — same footprint as T1, transfers if placed | same as T1's | would PASS if placed | same as T1's |
| U6 | YES, but costly — north end, 60.51mm arm, must stay ≥2.0mm clear of T1's slot | 14.85mm nominal / 14.11mm worst-case | PASS (+1.51mm worst-case) | **Narrowed to 1 end (south), not eliminated** |

Its core standards finding (established computationally, §2.3 of that document): **making one end
reach the true edge does not change the governing creepage figure at all** — the edge-open end
offers *zero* available creepage path (there is no board material past the true edge, on any
layer — a physical fact, no clause citation needed), so the governing path is forced onto the
still-closed interior end, which is exactly the already-flagged, uncited "around a closed
interior end" derivation. Opening one end removes a redundant tie; it does not create a new,
shorter path. A topological (Jordan-curve) argument additionally shows both ends can never be
opened for a mid-board component on this simple-rectangle outline without mechanically
disconnecting a board region.

**Consequence, stated plainly: the slots do NOT clear any of the 7 without the cert-lab answer.**
The 12.830mm (T1) / 14.11mm (U6) figures are computed *under the closed-end credit* — the exact
thing cert-lab Question A asks. Without that credit (e.g. if the lab reads the path as running
under the component's moulded body and disregards the slot), the governing figure reverts to the
intrinsic 9.100mm / 8.100mm and all 7 still fail. This is not a margin nuance: the entire
slot benefit (9.1→13.27mm, +4.17mm) IS the contested credit. There is no partial-credit floor
above 12.6mm that survives a "no credit" lab answer.

### 1.3 Per-violation feasibility (the task's item 4 decision tree)

| # | Violation | Routed slot feasible? (per determination) | Clears 12.6mm without cert-lab? | Action |
|---|---|---|---|---|
| T1 pad1↔pad4 | 9.100mm | Yes — south-arm edge-reaching design, 13.265/12.830mm | **No** — pass is conditional on closed-end credit | **Needs cert-lab answer — flag and leave** |
| T1 pad2↔pad3 | 9.100mm | Yes — same design, same figures | **No** — same reason | **Needs cert-lab answer — flag and leave** |
| T2's pairs (if placed) | 9.100mm | Yes, same footprint as T1 — placement now exists (18 courtyard-legal positions at (132-136, 116-120), per `2026-08-16-placement-reconciliation-*.md`) | **No** — same reason; also the 08-16 decision keeps T2/C37/R65 in staging because the intrinsic defect is placement-independent | **Needs cert-lab answer — flag and leave** |
| U6 pin3↔pin14 (and sibling pairs) | 8.100mm | Yes — north-arm design, 14.85/14.11mm, at materially higher reroute/structural cost | **No** — same reason | **Needs cert-lab answer — flag and leave** |

**No board edit is made by this spike.** Three independent grounds: (1) the operating rules for
this task forbid modifying `pcb/temper.kicad_pcb` except when placing alternative components —
cutting slots is not that; (2) the task's own decision tree (4c) says violations that need the
cert-lab answer are flagged and left, and all 7 are in that class; (3) this repo's repeated,
documented position ("a redundant protection channel that is itself a codified creepage
violation is a liability…", "no creepage credit is claimed for the closed end") applies a fortiori
to a slot whose *entire* benefit is the pending credit.

### 1.4 Task item 5 — does the recovered Table 17 (via SafetyValue) provide any slot-credit mechanism that does NOT need Annex L?

**Answer: partially — the groove-width/contour-following mechanism is recovered primary text
(no Annex L needed); only the bounded-slot closed-end cap is the open question.** Chain, all
CITED-PRIMARY in this repo:

1. **IEC 60335-1 cl. 29.2 Note** (recovered, `docs/evidence/2026-07-28-creepage-determination-brainstorm.md` §10):
   *"The way in which creepage distances are measured is specified in IS 15382 (Part 1)"* — i.e.
   IEC 60335-1 **delegates creepage measurement to IEC 60664-1**. The recovered Table 17 (via
   `SafetyValue`, `packages/temper-design-bundle/src/safety_value.rs`) is the *value* table
   (cl. 29.2.1 basic, cl. 29.2.3 reinforced = 2×); it contains no groove clause of its own, and
   does not need one — the measurement rule lives in IEC 60664-1.
2. **IEC 60664-1 cl. 4.2** (recovered verbatim from IS 15382 (Part 1):2003, the identical Indian
   national adoption, `docs/evidence/2026-08-13-hv-creepage-slot-rescue-t1-t2-u6.md` §1 — a live
   re-fetch of the primary source, not a second-hand citation): the groove-width minimum
   **X = 1.5mm at PD3** ("If the associated clearance is less than 3 mm, the minimum dimension X
   may be reduced to one third of this clearance"), and Example 2: *"Condition: Path under
   consideration includes a parallel-sided groove of any depth and equal to or more than X mm.
   Rule: … Creepage path follows the contour of the groove."* This is the **cited, recovered,
   non-Annex-L slot-credit mechanism**: a slot ≥1.5mm wide (PD3) is a legitimate groove whose
   path follows its contour. Every slot this repo has designed (4.0–8.0mm) clears X=1.5mm by
   2.4×–5.3×.
3. **What remains open**: all 11 of cl. 4.2's worked examples are 2D cross-sections of grooves
   implicitly infinite in the third dimension — **none pictures a bounded slot's closed end**
   (the rounded/squared cap a path must detour around). The groove-*body* contour rule is cited;
   the closed-*end* detour is the derived (uncited) extension. That is precisely what cert-lab
   Question A asks, and why Annex L (IEC 60335-1's own guidance on such slots, paywalled) was
   named in the package.

**Net for the cert-lab package**: the package's Question A can be sharpened with a
now-recovered-text-backed sub-premise — the lab need not confirm that a wide groove earns
contour-following credit (that is IEC 60664-1 cl. 4.2 Example 2, recovered); it must confirm
only whether the contour rule extends to a *bounded* slot's closed end. This is a narrowing of
the question, not a closing of it. (No change to the package text is made here — flagging the
possible refinement for the owner.)

---

## Part 2 — OCP-02 mechanism redesign

### 2.1 Current state (verified from `elec/src` this session)

OCP-02 is **Option A — a second current transformer**, not a shunt. `SecondaryOCPComparator`
(`elec/src/modules.ato:2636+`, implemented 2026-08-07) replaces the original shunt+INA240 front
end (superseded: the INA240 would see ~170V common mode against its −4..+80V absolute maximum
in this voltage-doubler topology). Committed design:

| Element | Value | Source |
|---|---|---|
| Sensing element | CST3015-100ED CT (T2, `safety.ocp2.ct`), 1:100, primary spliced IN SERIES in `DC_BUS_RTN` (`hb.dc_bus.hv_minus` → `safety.ocp2_bus_in` → CT primary → `safety.ocp2_bus_out` → `dc_bus_minus`) | `modules.ato:2636-2668`, `main.ato:794-795` |
| Burden | 4.12Ω, Yageo RC1206FR-074R12L (E96, ±1%, ±200ppm/C) | `modules.ato:2705-2713` |
| Reference | REF2025 fixed 2.5V (already on board, `rtd_pan.reference.VREF`) | `modules.ato:2740-2747` |
| Comparator | TLV3201 (same as OCP-01/OVP-01/THM-01/02) | `modules.ato:2768` |
| Trip | 60.68A nominal; worst-case band 59.31–62.10A; window 55–65A | `modules.ato:2753-2763` |
| Timing | ~918ns est. (528ns logic/driver + ~350ns CT front-end + 40ns TLV3201 typ), ~82% margin to 5µs | `modules.ato:2795-2800` |
| Fault path | `ocp2.fault.line ~ fault_or3.B1` (the input `UVL02_DESIGN.md` §7.2 reserved for OCP-02 — OCCUPIED) | `docs/hardware/UVL02_DESIGN.md:15-19` |

**T2/C37/R65 are UNPLACED** — staged off-board at `(100.0, 300.0)` / `(20.0, 272.12)` /
`(44.0, 272.12)`. Placement is now *feasible* (18 courtyard-legal positions for T2 alone at
(132-136, 116-120) per the 2026-08-16 placement reconciliation — the #1173 board changes freed
the mid-right region), but the 08-16 owner decision keeps the subsystem in staging because
**the 9.1mm-vs-12.6mm defect is intra-footprint and placement-independent**.

### 2.2 The problem restated

T2's CST3015 has 9.100mm intrinsic primary↔secondary pad separation (verified three ways: PR
#1146's canonical kernel, PR #1152's reproduction, and the 08-16 doc's direct pad-table
recomputation). PD3 reinforced requires 12.6mm. The part cannot reach it in any placement, and
the repo's exhaustive prior search (`docs/evidence/2026-07-30-pd3-part-selection-k1-c6-t1.md`)
found no drop-in CT at the same 1:100, ≥50A class with better creepage. **The same defect
already sits on the board today in T1** — OCP-02's problem is T1's problem, not a new one.

### 2.3 Options assessment (task items a–e)

#### (a) Aperture / donut-primary CT — the only technically-plausible long-term fix; still blocked on certification

Mechanism: the primary is not a PCB pad at all — an insulated wire or bus-bar tab threads through
the core's bore (ICE CT07-1000: 9.20mm bore, secondary pins clustered 7.62×7.62mm; Talema ASM
family). Because there is no primary PCB copper, **primary↔secondary creepage becomes a
board-layout choice**, buildable to ≥12.6mm by construction. Footprint ~16× smaller than
CST3015's 24.86×30.6mm courtyard — which also dissolves the (now-resolved) placement issue for
C37/R65. Burden conversion is verified: 1:1000 ratio at the same trip point → 4.99Ω→49.85Ω for
OCP-01's 50A trip (and it *reduces* burden dissipation).

**Not established — and this is the blocker**: no third-party reinforced-insulation certificate
(VDE/ENEC/CB/UL covering IEC 60335-1/60664-1 insulation coordination) was found for any
aperture/donut part checked — ICE (only a manufacturer hipot test), Talema AS (approvals page
lists power-converter certs only; "no certificate number, no reinforced-insulation claim, no
creepage figure in mm"), LEM CDSR 0.07-TPDT (12.2mm — closest of anything found — but wrong
function: residual/leakage current RCD, not overcurrent; certificate "Ongoing submission").
Requires an `elec/`+mechanical redesign (discrete conductor through bore, strain relief, ≥12.6mm
layout distance measured along the actual physical path). **Verdict: mechanism sound, part
unverified; do not field OCP-02 on it until a certified part exists. Revisit for T1+T2 jointly
when it does.**

#### (b) Alternative CT part — closed (no better part exists)

Exhaustive search across Coilcraft (CST1211/CS4xxx/SCS), TDK (B78419A), and others: every
1:100-ratio, ≥50A-sensed transformer has equal-or-worse PCB creepage than CST3015's 9.1mm. LEM
LPSR (closest *functional* match, built-in overcurrent detector) measures 8.26mm — *worse*. No
drop-in swap exists. **Verdict: closed.**

#### (c) Hall-effect sensor (ACS712/ACS724 class) — closed, verified this session

Fetched live from Allegro's own datasheets this session:

| Part | Package | Clearance | **Creepage** | Isolation rating | Working voltage | Source |
|---|---|---|---|---:|---|---|
| ACS712 | SOIC-8 (LC) | 4.0mm | **4.0mm** | 2400Vrms withstand (UL 62368-1 Ed.3), **basic isolation** (V_WVBI) | 420Vpk | Allegro ACS712-DS Rev.22, Isolation Characteristics |
| ACS724 | SOIC-8 (LC) | 4.2mm | **4.2mm** | 297Vrms working; DTI 63µm (implied), CB cert US-32848… | 297Vrms | Allegro ACS724-DS Rev.25, Isolation Characteristics |

**Both fail the 12.6mm PD3 bar by ~3×.** The ACS724 datasheet's own layout note ("Slot in PCB to
maintain 4.2 mm creepage once part is on PCB") shows the manufacturer's own ceiling for this
package is ~4.2mm even with a slot — an order of magnitude short of 12.6mm, and (per Part 1) a
slot's credit is itself the pending cert-lab question. LEM's closed-loop Hall family (checked by
the prior CT-replacement search) is the same story: LES ~8mm, LKSR/LPSR 8.26mm, HO-S >8mm, CDSR
12.2mm but wrong function + unissued cert. Firmware compatibility is **not** the binding
constraint: OCP-02's trip is a hardware comparator path (TLV3201 → `fault_or3.B1`), not a
firmware read — the ESP32 only sees `I_SENSE` (OCP-01's CT path). Even a Hall IC with an analog
output feeding the comparator cannot get past the isolation bar. **Verdict: closed.**

#### (d) Shunt + isolated amplifier (AMC1301 class) — closed, verified this session

Fetched live from TI's AMC1301 datasheet (Rev. G) this session:

| Parameter | AMC1301 (DWV-8) |
|---|---|
| External clearance (CLR) | ≥8.5mm |
| **External creepage (CPG)** | **≥8.5mm** |
| DTI | ≥0.021mm |
| CTI / material group | ≥600V / group I |
| Withstand (UL1577) | 5000Vrms, 60s |
| Reinforced (VDE 0884-17) | 7070Vpk |
| Working voltage | 1kVRMS |

**8.5mm creepage < 12.6mm — fails by 4.1mm**, the same defect class as the CT and as AMC1300
(8.5mm, already ruled out by the 2026-08-13 options doc). TI's own datasheet footnote states the
obvious escape: "Techniques such as inserting grooves, ribs, or both on a PCB are used to help
increase these specifications" — i.e. the *only* way to reach 12.6mm with this package is a slot,
which re-enters the Part 1 cert-lab question. On top of the isolation shortfall: needs a second
isolated bias supply (UCC14141-Q1 was out of stock at last check, and cannot directly produce
AMC1300/1301's required 4.5–5.5V — an added LDO), and has the tightest timing margin of any
candidate (20.6% guaranteed-worst-case, intrinsic to the part). **Verdict: closed — same
8.5mm-class shortfall, largest cost, no timing headroom.**

#### (e) De-scope OCP-02 — recommended (consistent with prior ranked #1 and the 08-16 decision)

**Not IEC 60335-1 clause-mandated.** The repo-wide search of every IEC 60335-1 clause citation
(3.4.2/3.4.4 SELV, 19, 29.1/29.2/29.2.3/29.2.4, 27.1/27.5) finds nothing requiring redundant
overcurrent sensing; `OCP02_DECISION_BRIEF.md` §6 — which asked exactly this question — never
cites a clause; its case is "it's buildable" and "it's a numbered acceptance-test line item."
`docs/FUNCTIONAL_TEST_CRITERIA.md:48-49`'s "Secondary OCP 60A Peak / 55–65A / <5µs" is an
internal acceptance bar with no external standard cited. BOM §5.4's accepted-residual-risk table
already frames OCP-01+OCP-02 as covering "most of the same fault space," with both jointly still
missing shoot-through, gate-drive degradation, device-local shorts, and speed-vs-fastest-short —
i.e. OCP-02 narrows a margin, it does not close a uniquely-open compliance gap.

**Stated, bounded cost of de-scope**: fails the internal "Secondary OCP" acceptance line, and
removes the one sensing path that specifically covers a shoot-through fault crossing
`DC_BUS_RTN` — a conductor OCP-01's tank-return CT does not sense by construction. This is a
real redundancy loss, but within the residual-risk class BOM §5.4 already accepts, and the
primary protection is intact: OCP-01 hardware comparator (50.1A peak nominal, 45–55A acceptance,
<1µs, latched) plus the firmware software-OCP layer (40A peak per the 2026-08-15 OCP threshold
decision).

**This is exactly the repo's own prior ranked #1** (`2026-08-13-ocp02-unplaced-subsystem-options.md`
§8: "5 — do not populate OCP-02") and the 2026-08-16 owner decision ("keep T2/C37/R65 in
staging… placing them would ADD a known, unfixable 9.1mm-vs-12.6mm PD3 violation"). This spike
confirms it with the added Hall/AMC1301 isolation figures (2.3c/2.3d), which close the last two
mechanism alternatives with datasheet-verified numbers.

### 2.4 Recommendation, with the trigger conditions that would change it

**Recommendation: de-scope OCP-02 now — keep T2/C37/R65 in staging, do not populate, do not
place.** No board edit, no BOM addition, no `elec/` change is made here; this is the
recommendation the owner's decision can rest on.

| Would change the recommendation | Condition |
|---|---|
| Aperture CT becomes fieldable | A verified third-party reinforced-insulation certificate (VDE/ENEC/CB/UL, IEC 60335-1/60664-1-scoped) for an ICE CT07/08/10-class or Talema ASM part — then build OCP-02 with it, for T1+T2 jointly (a scoped sourcing task, distinct from this spike) |
| Slot credit confirmed | If cert-lab Question A answers "yes, the closed end earns credit": T2 can be placed at one of its 18 legal positions with the T1-identical 28×8mm slot design (15.53mm nominal / 14.83mm worst-case) — OCP-02 becomes fieldable with the existing part, subject to the reroute/structural caveats the slot docs carry |
| PD2 compartment lands | A real, inspected sealed compartment closes `check_pd2_compartment_evidence.py` → 8.0mm governs → CST3015's 9.1mm clears unslotted with +1.1mm, and the entire Part 1 + Part 2 question set dissolves for these parts |

### 2.5 Risk analysis of the recommendation (de-scope)

1. **Shoot-through on DC_BUS_RTN becomes sensed only indirectly.** OCP-01's tank CT sees the
   resonant loop current, not the bus-return conductor; a shoot-through fault's bus current is
   the one path OCP-02 uniquely covered. Mitigation: the hardware OCP-01 comparator trips on the
   same fault's tank-side signature within <1µs at 50.1A; the firmware layer adds 40A-peak
   software-first response; BOM §5.4 already accepts the residual class. This is a documented,
   bounded redundancy reduction, not a new uncovered fault category.
2. **Internal acceptance-test line remains unmet.** `FUNCTIONAL_TEST_CRITERIA.md` "Secondary
   OCP" stays red. That is a project-standards item (owner can re-scope the criterion or leave
   it documented as deferred); it is not a certification blocker.
3. **Staging rot.** T2/C37/R65 parked off-board could drift from the schematic if someone
   edits `safety.ocp2.*` without noticing the staging row. Mitigation: the 08-16 doc and this
   one both name the staging explicitly; the schematic (`modules.ato:2636+`) already documents
   its own unplaced status in the BOARD FOLLOW-ON note.
4. **No regression risk to the live board**: OCP-02 has no placed copper, no BOM row, no
   firmware path — de-scoping changes nothing physically; it only makes the *decision* explicit
   instead of accidental.

---

## 3. What this spike changes and does not change

- **Does not change**: `pcb/temper.kicad_pcb` (sha256 unchanged), any footprint, any DRU
  threshold, any enforced safety constant, `elec/src/**`, `firmware/**`, any ratchet ceiling.
  No slot was cut; no part was placed or removed; no BOM row was added.
- **Does add**: (1) the Part 1 determination that all 7 T1/T2/U6 violations remain
  cert-lab-dependent — the edge-reaching slot is the *contingent* fix, ready to implement the
  moment the lab answers, not a cert-lab-free clearing; (2) the recovered-text narrowing for the
  cert-lab package (groove-body contour credit is already cited in IEC 60664-1 cl. 4.2 Example 2
  via IS 15382:2003 — only the bounded-slot closed end needs the lab); (3) the OCP-02
  mechanism options closed with datasheet-verified figures this session (ACS712/724 at
  4.0–4.2mm, AMC1301 at 8.5mm) that prior docs did not carry; (4) the de-scope recommendation
  restated with its trigger conditions.

## 4. What is NOT established here (explicit)

- **No certification-lab answer is in hand** — this spike does not resolve cert-lab Question A
  or Question B (IEC 60664-4); it sharpens Question A's premises. The package is on main
  (#1209) with its cover letter (#1236).
- **No aperture-CT part with a verified reinforced-insulation certificate is named** — closing
  that sourcing gap is a distinct, scoped task (prior docs' conclusion, unchanged).
- **The T1/T2 slot structural questions are open** (solder-joint fatigue under the 23×30mm CT
  body; U6's 60.51mm arm warpage) — unchanged from the slot documents; this spike adds no FEA.
- **The Hall/AMC1301 figures are datasheet-quoted, not lab-tested on this board** — they close
  the mechanism options on the isolation axis, which is the axis that matters here.

## Files

- This document: `docs/evidence/2026-08-16-cert-lab-and-ocp02-spike.md`
- Cites: `docs/evidence/2026-08-13-hv-creepage-edge-reaching-slot-determination.md` (PR #1194);
  `docs/evidence/2026-08-13-hv-creepage-slot-rescue-t1-t2-u6.md` (PR #1155);
  `docs/evidence/2026-08-14-certification-lab-package-pd3-and-60664-4.md` (PR #1209, on main);
  `docs/cert-lab-cover-letter-2026-08-15.md` (PR #1236, on main);
  `docs/evidence/2026-08-13-ocp02-unplaced-subsystem-options.md` (PR #1151);
  `docs/evidence/2026-08-13-t2-ct-replacement-creepage-and-placement-search.md`;
  `docs/evidence/2026-08-15-ocp-threshold-decision.md`;
  `docs/evidence/2026-08-16-placement-reconciliation-k1-cluster-c7-and-creepage-ranking.md` (#1248);
  `docs/evidence/2026-08-16-drc-zero-action-plan.md`;
  `docs/evidence/2026-07-28-creepage-determination-brainstorm.md` (recovered Table 17/clauses);
  `docs/hardware/OCP02_DESIGN.md`, `docs/hardware/UVL02_DESIGN.md`,
  `docs/hardware/OCP02_DECISION_BRIEF.md`, `docs/FUNCTIONAL_TEST_CRITERIA.md`;
  `elec/src/modules.ato` (SecondaryOCPComparator), `elec/src/main.ato`;
  `packages/temper-design-bundle/src/safety_value.rs` (recovered Table 17 via SafetyValue);
  `pcb/temper.kicad_pcb` (read-only).
- Datasheets fetched live this session (primary sources, quoted not reconstructed): Allegro
  ACS712-DS Rev.22; Allegro ACS724-DS Rev.25; TI AMC1301 datasheet Rev. G (all via the session's
  web fetch of the manufacturers' own documents).
- Recovered primary standards text relied on (already in repo, cited above): IS 302-1:2008 =
  IEC 60335-1 (Table 17, cl. 29.2/29.2.1/29.2.3/29.2 Note); IS 15382 (Part 1):2003 = IEC
  60664-1:2002 (cl. 4.2, all 11 worked examples, X=1.5mm at PD3).
