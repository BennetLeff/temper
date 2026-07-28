# High-Voltage Clearance and Creepage Specification

**Document ID:** REQ-ELEC-04  
**Version:** 1.2 (see §11 Revision History — v1.0's original clearance/creepage tables and v1.1's coating scheme both carried errors, corrected in place, not deleted)  
**Date:** 2025-12-16 (original); last corrected 2026-07-28  
**Status:** Implemented, with UNRESOLVED items flagged inline (Pollution Degree PD2 vs PD3 — see §3.2, §5)  
**Standard:** IEC 60335-1, IEC 60335-2-6, IEC 61010-1

## 1. Overview

This document defines clearance (through air) and creepage (along surface) requirements for the Temper induction cooker PCB to ensure safety compliance with household appliance standards.

## 2. Voltage Domains

### 2.1 Domain Definitions

| Domain | ID | Reference | Working Voltage | Peak/Transient | Classification |
|--------|-----|-----------|-----------------|----------------|----------------|
| AC Mains | A | Earth/Neutral | 120-240V RMS | 340V | Hazardous |
| DC Bus | B | DC_BUS- | 170-340V DC | 400V (transient) | Hazardous |
| Gate Drive Isolated | C | IGBT Source | 15V (floating at 340V) | 355V to earth | Hazardous |
| Low Voltage Control | D | CGND | 3.3-15V | 20V | SELV |
| Protective Earth | PE | Earth | 0V | Fault current | Safety |

### 2.2 Domain Locations on PCB

```
┌─────────────────────────────────────────────────────────────────────┐
│                         TEMPER PCB (100mm × 150mm)                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────┐        ┌──────────────────────────────────┐   │
│  │                  │        │                                  │   │
│  │   DOMAIN A       │        │         DOMAIN B                 │   │
│  │   AC MAINS       │        │         DC BUS                   │   │
│  │                  │        │                                  │   │
│  │  • AC input      │        │  • Bridge rectifier              │   │
│  │  • EMI filter    │        │  • Bus capacitors                │   │
│  │  • Fuse          │        │  • IGBTs (collector)             │   │
│  │                  │        │  • Switch node                   │   │
│  └────────┬─────────┘        └──────────────┬───────────────────┘   │
│           │                                  │                       │
│           │ 6mm clearance                    │ 8mm clearance         │
│           │ (basic insulation)               │ (reinforced)          │
│           ▼                                  ▼                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                                                              │   │
│  │                    ISOLATION BARRIER                         │   │
│  │              (2mm routed slot in PCB)                        │   │
│  │                                                              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│           │                                  │                       │
│           │                                  │                       │
│           ▼                                  ▼                       │
│  ┌──────────────────┐        ┌──────────────────────────────────┐   │
│  │                  │        │                                  │   │
│  │   DOMAIN D       │        │         DOMAIN C                 │   │
│  │   LOW VOLTAGE    │        │         GATE DRIVE ISOLATED      │   │
│  │                  │        │                                  │   │
│  │  • ESP32-S3      │        │  • UCC21550 output side          │   │
│  │  • MAX31865      │◄──────►│  • Bootstrap supply              │   │
│  │  • UI circuits   │ I2C    │  • IGBT gates/sources            │   │
│  │  • ADC sensing   │(ADUM)  │                                  │   │
│  │                  │        │                                  │   │
│  └──────────────────┘        └──────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## 3. IEC 60335 Requirements

### 3.1 Applicable Standards

| Standard | Title | Application |
|----------|-------|-------------|
| IEC 60335-1 | Safety of household appliances - General | General safety requirements |
| IEC 60335-2-6 | Particular requirements for cooking ranges | Induction hob specific |
| IEC 61010-1 | Safety for measurement equipment | Control/sensing circuits |
| IEC 60664-1 | Insulation coordination | Clearance/creepage basis |

### 3.2 Environmental Parameters — corrected 2026-07-28, reasoning recorded

**This table previously asserted Pollution Degree 2, Overvoltage Category III,
and Material Group IIIb, each with no clause citation.** Independently
re-derived from primary text in
`docs/evidence/2026-07-28-creepage-determination-brainstorm.md` (§3.1, §5) and
`docs/evidence/2026-07-28-coating-supplemental-scope.md` (§4); corrected here,
not deleted, so the mistake and its fix are both visible:

| Parameter | Old value (uncited) | **Corrected value** | Justification |
|-----------|---------------------|----------------------|----------------|
| **Pollution Degree** | 2 | **3** | IEC 60335-2-6 clause 29.2 Addition (the particular standard for cooking ranges/hobs, overriding Part 1's PD2 default): "The microenvironment is pollution degree 3 unless the insulation is enclosed or located so that it is unlikely to be exposed to pollution during normal use of the appliance." No document in this repo establishes an enclosure/location argument earning PD2 — `docs/ENVIRONMENTAL_SPEC.md`'s own IP20 rating and `docs/CHASSIS_AIRFLOW_DESIGN.md`'s forced-airflow duct both argue the opposite way. **This is flagged, not finally resolved** — see the "Pollution degree" row below. |
| **Overvoltage Category** | III | **II** | IEC 60335-1 clause 29.1: "Appliances are in overvoltage category II" — stated directly by the standard for this appliance class, not III. `elec/src/main.ato:52` sets `v_ac_nominal = 120V` (100-130V asserted range); at OVC II this gives rated impulse voltage **1500V** (Table 15), not the higher figures OVC III would imply. |
| **Material Group** | IIIb ("FR4 CTI 175-249V") | **IIIa/IIIb (unified default; laminate unspecified)** | No document in this repo specifies a laminate CTI, IPC-4101 slash sheet, or stackup — re-confirmed by grep, still true today. IEC 60335-1 Table 17 gives IIIa and IIIb an *identical* value at every row (175 < CTI < 400 covers both), so the IIIa-vs-IIIb distinction this row previously implied buys nothing; the real open question is whether a CTI≥400 (Group II) laminate could be specified to relax the figure, which nobody has checked against a real datasheet. |
| **Altitude** | ≤2000m | (unchanged) | Standard household use — not re-derived this pass, no primary-text citation found either way. |
| **Working Temperature** | 60°C max ambient | (unchanged, but see caveat) | Ambient figure, not the *board surface* figure IEC 60664-3's coating-qualification Table 2 keys on — `docs/evidence/2026-07-28-coating-supplemental-scope.md` §2 found no PCB working-surface-temperature declaration anywhere in this repo and derived a placeholder 100°C for that separate purpose. Not the same quantity as this row; not changed here. |

**Pollution degree — the same unresolved question this document's §6.4 and
`scripts/generate_kicad_dru.py` both already flag, restated here so this
table stops silently disagreeing with them:** PD3 is the appliance class's
governing default per the clause above, and no enclosure argument exists in
this repo to earn PD2 back. `docs/ENVIRONMENTAL_SPEC.md` has already been
corrected to state PD3 as its cited default
(`docs/evidence/2026-07-28-coating-supplemental-scope.md` §4). **This
document is not the owner of that determination and does not re-resolve it**
— it adopts PD3 above for consistency with the rest of the repo's now-cited
position, while leaving the final human sign-off exactly where
`scripts/generate_kicad_dru.py`'s `HV_CREEPAGE_ENFORCED_MM` comment and
`scripts/check_isolation_keepout.py`'s module docstring already leave it.

### 3.3 Insulation Types

| Type | Description | Test Voltage | Application |
|------|-------------|--------------|-------------|
| **Functional** | Minimum for operation | None required | Within same voltage domain |
| **Basic** | Single fault protection | 1500V AC 1 min | Mains to accessible parts |
| **Supplementary** | Second layer over basic | 1500V AC 1 min | Double insulation systems |
| **Reinforced** | Equivalent to double | 3000V AC 1 min | HV to SELV isolation |

## 4. Clearance Requirements

### 4.1 Clearance Table (Through Air) — corrected 2026-07-28, reasoning recorded

**This section previously gave a clearance table with a "Design Value"
column running 1.5mm–10.0mm and a §4.2 design-clearance table asserting
5.0mm–8.0mm at the mains↔SELV boundary. Those figures were wrong, and wrong
in a specific, now-understood way: they are IEC 60335-1 Table 17 *creepage*
values (or values close to them) copied into a *clearance* section.**
`docs/evidence/2026-07-28-creepage-determination-brainstorm.md` §1 traced
this exact failure mode across every clearance/creepage figure in this
repo ("every wrong number in this repo is a creepage value that has been
relabelled as a clearance value") — this document's own old §4 table was
one more instance of it, not caught until this pass. Recorded here, not
deleted, so the mistake is not repeated a third time (its §6.4 already
records the same lesson for the coating multiplier).

**The real clearance derivation, from primary text
(`docs/evidence/2026-07-28-creepage-determination-brainstorm.md` §3.1–§4,
CITED-PRIMARY throughout):**

- IEC 60335-1 clause 29.1: this appliance is **overvoltage category II**
  (stated directly by the standard, not III as the old §3.2 asserted).
- `elec/src/main.ato:52`: `v_ac_nominal = 120V` (100–130V asserted range) →
  Table 15 rated impulse voltage **1500V** at OVC II.
- Table 16 basic clearance at 1500V: **0.5mm**. Clause 29.1.3: reinforced =
  next-higher Table 16 step = **1.5mm**. Clause 29.1's own
  soldered-construction adder (+0.5mm at rated impulse ≥1500V, naming
  soldering as one of its own examples, and this is a soldered PCB):
  **2.0mm**.
- Clause 29.1.5's resonant/higher-working-voltage provision, applied at this
  board's tank-node peak voltages, can push the determining voltage to the
  4000V step under a stricter reading, giving **3.0mm** (3.5mm total with
  the adder) as an upper bound — see the evidence doc §4 for the full
  per-node table.

**Corrected clearance table** (basic / reinforced, Table 16, OVC II — this
table is a straight Table 16 reproduction, unlike the old one, which
reproduced no real table):

| Rated impulse voltage (V) | Basic clearance (mm) | Reinforced (next step, cl. 29.1.3) |
|---:|---:|---:|
| 500 | 0.5 | 0.5 (330 step) |
| 1500 | 0.5 (+0.5 soldered adder = **1.0mm** *per-step*, board's actual reinforced figure is derived below, not read off this row directly) | 1.5 (2500 step) |
| 2500 | 1.5 | 3.0 (4000 step) |
| 4000 | 3.0 | 5.5 (6000 step) |

**This board's design clearance requirement: reinforced 1.5mm nominal, 2.0mm
with the clause-29.1 soldered-construction adder, up to 3.0–3.5mm under the
strictest available reading. Not 5.0mm, not 8.0mm, and not any value the old
table asserted.** Clearance is **not the binding constraint anywhere on this
board** — every measured isolator pad gap clears 2.0mm; see the evidence
doc §4 and §6 for the full measurement. `scripts/generate_kicad_dru.py`'s
`HV_INTERNAL_CLEARANCE_MM = 2.0` constant is the one place this figure is
actually enforced today.

### 4.2 Design Clearances — corrected 2026-07-28

| Boundary | Insulation | Working V | Old (wrong) value | **Corrected value** |
|----------|------------|-----------|--------------------|----------------------|
| AC Mains (L/N) to PE | Basic | 340V pk | 4.0mm | Not re-derived this pass — PE bonding is a separate clause-27.5 question (`docs/evidence/2026-07-28-creepage-determination-brainstorm.md` §2.1); flagged, not corrected here. |
| AC Mains to SELV/PELV | Reinforced | 340V pk | 8.0mm clearance | **2.0mm clearance** (1.5mm nominal + 0.5mm soldered adder) |
| DC Bus to SELV/PELV | Reinforced | 400V pk | 8.0mm clearance | **2.0mm clearance** (same derivation; §4.1) |
| DC Bus to Gate Iso (Domain C) | Functional | 15V | 1.0mm | Not re-derived this pass — functional/working insulation between two hazardous-side circuits, out of this pass's scope. |
| Gate Iso to SELV/PELV | Reinforced | 355V | 8.0mm clearance | **2.0mm clearance** (same derivation) |
| Within SELV/PELV | Functional | 15V | 0.5mm | Not re-derived this pass. |
| Any HV to Exposed Metal | Basic | 400V | 4.0mm | Not re-derived this pass. |

**"SELV" renamed "SELV/PELV" in this table only as a pointer, not a fix**:
`docs/evidence/2026-07-28-creepage-determination-brainstorm.md` §2.2
establishes from IEC 60335-1 clause 27.1/3.4.4 that `elec/src/main.ato:475`'s
`gnd ~ pe` hard bond makes this domain a **PELV** circuit under the
standard's own definitions, not SELV as `elec/domain_manifest.yaml` and
every other document in this repo (including this one) name it. Naming
only — does not itself change any distance in this document — flagged here
so the inconsistency is visible; renaming the domain everywhere is out of
this document's scope.

## 5. Creepage Requirements

### 5.1 Creepage Table (Along Surface) — corrected 2026-07-28, reasoning recorded

**This table previously cited "IEC 60335-1 Table 16" for creepage — Table 16
is the *clearance* table; Table 17 is the creepage table. The Design Value
column (3.0mm–12.0mm) does not reproduce Table 17 at any pollution
degree/material-group combination cleanly either.** Corrected below,
old values recorded rather than deleted.

**Real derivation (IEC 60335-1 Table 17, CITED-PRIMARY, working voltage
>250V and ≤400V — this barrier's 340V/400V-class bus falls in this row;
clause 29.2.3: reinforced = 2× basic):**

| Pollution degree | Material group | Basic creepage (mm) | **Reinforced creepage (mm)** |
|---|---|---:|---:|
| PD1 (qualified Annex J Type A coating only — not qualified on this board, §6.4) | any | 1.0 | 2.0 |
| **PD2** | IIIa/IIIb | 4.0 | **8.0** |
| **PD3** (appliance-class default per IEC 60335-2-6 cl. 29.2 Addition — §3.2 above) | IIIa/IIIb | 6.3 | **12.6** |

**Design creepage requirement: 8.0mm if Pollution Degree 2 can be earned by
an enclosure/location argument (none exists in this repo today); 12.6mm
under Pollution Degree 3, this appliance class's standard default. THIS
QUESTION IS FLAGGED, NOT RESOLVED** — same status as
`scripts/generate_kicad_dru.py`'s `HV_CREEPAGE_PD2_MM`/`HV_CREEPAGE_PD3_MM`
constants and `scripts/check_isolation_keepout.py`'s
`MIN_BARRIER_WIDTH_MM` (currently pinned to the PD3/12.6mm figure — see
that script's module docstring and `generate_kicad_dru.py`'s
`HV_CREEPAGE_ENFORCED_MM` comment for why). **Not 3.0–12.0mm as the old
table asserted, and not derived from "Table 16" as the old table claimed.**

### 5.2 Design Creepage — corrected 2026-07-28

| Boundary | Insulation | Working V | Old (wrong) value | **Corrected value** |
|----------|------------|-----------|--------------------|----------------------|
| AC Mains to SELV/PELV | Reinforced | 340V pk | 10.0mm | **8.0mm (PD2) / 12.6mm (PD3, unresolved default)** |
| DC Bus to SELV/PELV | Reinforced | 400V pk | 10.0mm | **8.0mm (PD2) / 12.6mm (PD3, unresolved default)** — same derivation, this is the same reinforced mains↔PELV barrier, not a separate figure |
| Across UCC21550 | Reinforced | 400V | 10.0mm | Per device spec (unchanged — component-level rating, not this document's derivation) |
| IGBT tab to LV trace | Reinforced | 400V | 10.0mm | **8.0mm (PD2) / 12.6mm (PD3, unresolved default)** — same barrier, same derivation |
| Within SELV/PELV | Functional | 15V | 0.5mm | Not re-derived this pass — functional insulation within one domain, out of this pass's scope. |

## 6. Isolation Barrier Design

**§6.1–§6.3 below predate the 2026-07-28 clearance/creepage correction
(§3.2, §4, §5 above) and have not been individually re-derived this pass —
flagged, not corrected, so this section is not silently trusted as
authoritative.** Two things are known to be wrong in §6.1 specifically
(corrected in place immediately below); §6.2's "6mm min" callouts and
§6.3's per-device figures are old, uncited design values in the same
family as the ones §4/§5 corrected, and should be treated as UNVERIFIED
until someone repeats the same derivation exercise for them specifically.
**The actual enforcement for this barrier today is
`scripts/check_isolation_keepout.py`'s `MIN_BARRIER_WIDTH_MM` (currently
12.6mm, a physical zero-copper-corridor construction check) and
`scripts/generate_kicad_dru.py`'s emitted `clearance`/`creepage` KiCad DRC
rules (2.0mm / 12.6mm) — not this document's §6 diagrams.**

### 6.1 PCB Slot Specification

A routed slot in the PCB creates a physical barrier between high-voltage and low-voltage domains.

**Slot Parameters:**
- **Width:** 2.0mm minimum
- **Depth:** Full board thickness (1.6mm)
- **Location:** Between Domain B/C and Domain D
- **Length:** Full board width where domains meet

**Creepage Enhancement — corrected 2026-07-28, formula was wrong:**
```
Without slot:  Creepage = surface distance only
With slot:     Creepage = 2 × slot width + surface across slot
               Effective creepage = 2 × 2.0mm + 4.0mm = 8.0mm minimum   [OLD, WRONG -- see below]
```

**Why this formula was wrong, recorded rather than deleted:** IEC 60664-1's
groove-measurement rule (delegated to by IEC 60335-1 clause 29.2's
measurement note) is not "2× slot width + surface across slot" — that
arithmetic does not appear in either standard and was never
independently derived here (`docs/evidence/2026-07-28-creepage-
determination-brainstorm.md` §10 flags the actual groove-width rule as
**not read** in any session to date; `docs/PCB_SAFETY_DESIGN_RULES.md`
§3.2's "1.0mm slot width minimum" is separately flagged UNVERIFIED there
too). What primary text **does** establish and this formula did not
capture: a slot/groove increases **creepage only** — clearance is a
straight-line, through-air quantity that removing substrate does not
change (same evidence doc §10, citing TI SLUSE89C §5.6 fn. 1). Treat the
"8.0mm minimum" conclusion above as coincidental, not derived; the real
minimum creepage requirement for this barrier is the §5 figure (8.0mm PD2
/ 12.6mm PD3, unresolved), not a slot-geometry formula.

### 6.2 Slot Routing Rules

```
                    SLOT CROSS-SECTION
                    
     HV Side                          LV Side
    (Domain B)                       (Domain D)
        │                                │
        │◄──── 6mm min ────►│◄── 6mm min ──►│
        │                    │              │
   ─────┴────────────────────┴──────────────┴─────  L1 (Top)
                    ║        ║
                    ║ 2.0mm  ║                      Slot (routed)
                    ║  slot  ║
   ─────────────────╨────────╨────────────────────  L4 (Bottom)
        │                    │              │
        │                    │              │
    No copper            No copper      No copper
    within 2mm          in slot        within 2mm
```

### 6.3 Under-Component Clearances

**UCC21550 Isolated Gate Driver:**
- Minimum 1.0mm clearance between primary and secondary pins
- No traces on any layer under the isolation barrier
- Ground plane cutout under transformer region (center of package)
- Per UCC21550 datasheet Figure 34 layout recommendation

**ADUM1250 I2C Isolator:**
- 4.0mm minimum between Side 1 and Side 2 pins
- No ground plane under center of package
- Place isolation slot under device if possible

### 6.4 Conformal Coating — NOT IMPLEMENTED; corrected 2026-07-28

**No coating exists on this board.** There is no coating process in the
BOM or the assembly, notwithstanding this document's header claiming
"Status: Implemented" for the specification as a whole. This section
previously specified a coating scheme with a "Creepage Multiplier: ×1.5
for coated surfaces" citing IPC-CC-830. That scheme was wrong on multiple
independent grounds and is recorded here, not deleted, so the mistake is
not repeated. Full primary-text determination:
`docs/evidence/2026-07-28-conformal-coating-pd1.md`.

**What was wrong, specifically:**

1. **No such multiplier exists in IEC 60335-1 or IEC 60664-3.** A qualified
   Type A coating (IEC 60335-1 Annex J, which delegates to IEC 60664-3
   cl. 4.3) grants Pollution Degree 1 under the coating — a change of
   *pollution-degree column* in Table 17, not a ×1.5 scaling factor on a
   distance. A ×1.5 multiplier is simultaneously **less generous** than the
   real PD2→PD1 provision (8.0mm → 2.0mm, not 8.0mm → 5.3mm) and, on any
   path the coating does not actually cover, **dangerously more generous**
   than the true requirement (which gives zero credit there, not ×1.5).
2. **IPC-CC-830 is the wrong standard to cite for this credit.** It
   qualifies a coating *material*. The standard governing creepage credit
   for a coated *assembly* is IEC 60664-3 (via IEC 60335-1 Annex J), and
   neither vendor coating datasheet reviewed this session (MG Chemicals,
   Electrolube) even mentions IEC 60664-3. Citing IPC-CC-830 here does not
   discharge the Annex J requirement.
3. **PD1 is earned per-path, all-or-nothing, and this board fails that
   test everywhere it matters.** IEC 60664-3 cl. 4.3: one or both
   conductive parts *and every spacing between them* must be covered by
   the protection — there is no partial credit. Measured: for every
   declared isolator on this board with a body outline, **100.0% of the
   shortest HV↔PELV surface path lies under the seated component body**
   (relay base, SOIC/DIP package, module case). A post-assembly liquid
   coating does not reach under a seated body and, decisively, coverage
   there **cannot be inspected** in production (the standard production QA
   method, UV-tracer inspection, only sees the surface).
4. **All four of the previously-listed "Coating Zones" are exactly the
   zones this fails on.** IGBT TO-247 mounting pads and the UCC21550
   package perimeter are both under-body paths by the argument above
   (verified for the TO-247 and SOIC-16W package classes in
   `docs/evidence/2026-07-28-conformal-coating-pd1.md` sec 4). The
   high-voltage connector area is the one candidate that might genuinely be
   an open-surface, coatable, inspectable path — but nothing in this repo
   has qualified it, and no coating exists in the BOM regardless.
5. **The `0.8mm at PD1` figure that leaked into the generated DRC rules
   from this same reasoning matched no cell of Table 17** (the PD1 column
   at the applicable row, >250–400V, is 1.0mm, not 0.8mm).

**Where this showed up as a live defect, not just a documentation error:**
`scripts/generate_kicad_dru.py` had already encoded this same broken
justification into the *generated DRC rules themselves* — relaxing the "HV
internal same footprint" clearance rule to 1.5mm with a comment citing
"Conformal coating to achieve PD1 (needs 0.8mm for 400V)". That generator
now enforces a fail-closed, uncoated **2.0mm** figure (IEC 60335-1 cl. 29.1:
1.5mm reinforced clearance step + the clause's own +0.5mm
soldered-construction adder), and gates any future coating-based relaxation
behind an explicit `COATING_QUALIFIED` flag that defaults to `False` and
raises loudly if flipped without a real qualification record. See
`docs/evidence/2026-07-28-drc-coating-failopen-fix.md`.

**Corrected creepage figures for the mains↔PELV barrier this coating was
meant to help with** (uncoated, per the prior primary-text determination in
`docs/evidence/2026-07-28-creepage-determination-brainstorm.md`):
reinforced creepage at Pollution Degree 2 is **8.0mm** (IEC 60335-1
cl. 29.2.3 × Table 17 row iv, working voltage >250–400V, material group
IIIa/IIIb). **This is flagged, not resolved:** IEC 60335-2-6 cl. 29.2 makes
Pollution Degree 3 the *default* for this appliance class (cooking
ranges/hobs), which would instead require **12.6mm**; PD2 must be earned by
showing the insulation is enclosed or unlikely to be exposed to pollution,
which no document in this repo establishes today. A human must settle this
before either number is asserted as final.

**If a real coating programme is adopted in the future**, it must: (a)
exist in the BOM and assembly process; (b) pass the IEC 60664-3 clause 5
Annex J qualification test regime (six specimens, or three if production
samples are used, with no failures permitted) on production-representative
coupons; and (c) carry a per-path clause-4.3 coverage argument scoped to
paths that are actually open-surface and inspectable — which excludes
every declared isolator on this board today. It changes the *pollution
degree* of the paths it covers; it is not a multiplier on any distance.

## 7. Component-Specific Clearances

**Same status as §6 above: not individually re-derived this pass, and the
same clearance/creepage relabelling bug §4/§5 corrected is visible again
below (e.g. "8mm clearance, 12mm creepage" in one cell in §7.1 — 8mm and
12mm are both in the creepage family per §5, not a clearance figure at
all). Flagged, not corrected row-by-row; treat every value below as
UNVERIFIED against the §4/§5-corrected derivation until it is individually
redone. The one thing corrected here is the "Tab to nearest LV trace" row's
requirement column, since leaving "8mm clearance" standing beside the
corrected §4 clearance figure (2.0mm) would recreate the exact
three-inconsistent-figure-sets problem this reconciliation pass exists to
close.**

### 7.1 IGBT (IKW40N120H3) TO-247

**Hazard:** Collector tab at DC bus potential (340V)

| Clearance Path | Old Requirement | **Corrected Requirement** | Design |
|----------------|-------------------|------------------------------|--------|
| Tab to nearest LV trace | "8mm clearance, 12mm creepage" (conflated) | **2.0mm clearance (§4.2); 8.0mm PD2 / 12.6mm PD3 creepage, unresolved (§5.2)** | 12mm |
| Tab to mounting hole | 4mm (to chassis ground) | Not re-derived this pass | 5mm |
| Gate pin to collector tab | Per package (internal) | Not re-derived this pass | N/A |
| Emitter to collector tab | Per package (internal) | Not re-derived this pass | N/A |

**PCB Layout:**
- No LV traces within 12mm radius of collector tab
- Dedicated copper pour for collector (DC bus)
- Thermal pad connected via thermal vias to internal plane

### 7.2 Rectifier Bridge

**Hazard:** AC pins at mains potential, DC pins at bus potential

| Clearance Path | Requirement (UNVERIFIED, not re-derived this pass) | Design |
|----------------|-------------|--------|
| AC pins to SELV | 8mm clearance | 10mm |
| DC+ to PE connection | 4mm clearance | 5mm |
| Between AC pins | Per device | Functional |

### 7.3 Bus Capacitors

**Hazard:** Terminals at 340V DC, stored energy hazard

| Clearance Path | Requirement (UNVERIFIED, not re-derived this pass) | Design |
|----------------|-------------|--------|
| Terminals to SELV | 8mm clearance | 10mm |
| Terminals to chassis | 4mm clearance | 5mm |
| Between terminals | 2mm clearance | 3mm |

### 7.4 Current Transformer (CT)

**Hazard:** Primary at DC bus current, secondary isolated

| Clearance Path | Requirement | Design |
|----------------|-------------|--------|
| Primary to secondary | Per device isolation | Verify spec |
| Secondary to SELV | Functional (galvanically isolated) | 2mm |

## 8. Verification Matrix

**§8.1/§8.2's "Required" columns below carry the same old, uncorrected
figures §4/§5 fixed at the top of this document — flagged, not corrected
cell-by-cell, since this is a fill-in-the-blank field checklist rather
than a derivation. Before using this checklist to sign off a board, replace
every "Required" figure below with §4.2's corrected 2.0mm clearance and
§5.2's 8.0mm(PD2)/12.6mm(PD3, unresolved) creepage figures for the
mains/DC-bus↔SELV-PELV rows.**

### 8.1 Clearance Verification Checklist

| Location | Old "Required" | **Corrected Required** | Actual | Status |
|----------|----------|----------|--------|--------|
| AC_L to CGND | 8.0mm | **2.0mm** | ___mm | ☐ Pass |
| AC_N to CGND | 8.0mm | **2.0mm** | ___mm | ☐ Pass |
| DC_BUS+ to CGND | 8.0mm | **2.0mm** | ___mm | ☐ Pass |
| DC_BUS- to CGND | 8.0mm | **2.0mm** | ___mm | ☐ Pass |
| SWITCH_NODE to CGND | 8.0mm | **2.0mm** | ___mm | ☐ Pass |
| IGBT Q1 tab to LV | 8.0mm | **2.0mm** | ___mm | ☐ Pass |
| IGBT Q2 tab to LV | 8.0mm | **2.0mm** | ___mm | ☐ Pass |
| UCC21550 Pin 1-8 to 9-16 | 1.0mm | Not re-derived this pass | ___mm | ☐ Pass |
| ADUM1250 Side1 to Side2 | 4.0mm | Not re-derived this pass | ___mm | ☐ Pass |
| Isolation slot width | 2.0mm | Not re-derived this pass | ___mm | ☐ Pass |

### 8.2 Creepage Verification Checklist

| Location | Old "Required" | **Corrected Required** | Actual | Status |
|----------|----------|----------|--------|--------|
| AC Mains to SELV/PELV | 10.0mm | **8.0mm (PD2) / 12.6mm (PD3, unresolved)** | ___mm | ☐ Pass |
| DC Bus to SELV/PELV | 12.0mm | **8.0mm (PD2) / 12.6mm (PD3, unresolved)** | ___mm | ☐ Pass |
| IGBT tab to nearest trace | 12.0mm | **8.0mm (PD2) / 12.6mm (PD3, unresolved)** | ___mm | ☐ Pass |
| Across isolation barrier | 8.0mm | **8.0mm (PD2) / 12.6mm (PD3, unresolved)** | ___mm | ☐ Pass |

### 8.3 Hi-Pot Test Requirements

| Test | Voltage | Duration | Leakage Limit |
|------|---------|----------|---------------|
| Mains to SELV | 3000V AC | 1 minute | <5mA |
| Mains to PE | 1500V AC | 1 minute | <5mA |
| DC Bus to SELV | 3000V AC | 1 minute | <5mA |
| Isolation barrier | 5700V RMS | 1 minute | Per UCC21550 |

## 9. KiCad Design Rules

### 9.1 Custom DRC Rules — corrected 2026-07-28; this section is illustrative only, not the real generator

**This snippet is hand-written prose, not the actual generated file** — the
real, fab-authoritative `.kicad_dru` is produced by
`scripts/generate_kicad_dru.py` and must never be hand-edited (its own
header says so). This snippet previously carried two independent problems,
both corrected below rather than deleted:

1. **Wrong values** — 8.0mm clearance (should be 2.0mm, §4.2) and 10.0mm
   creepage (should be 8.0mm PD2 / 12.6mm PD3, unresolved, §5.2), the same
   creepage-relabelled-as-clearance defect §4/§5 corrected elsewhere in
   this document.
2. **`B.NetClass == 'Default'` does not mean "SELV" on this board.** The
   real project's net classes (`pcb/temper.kicad_pro`) are `ACMains`,
   `HighVoltage`, `HighVoltageIsolated`, `GateDrive`, `Power`, `Ground`,
   `FinePitch`, and `Default` — `Default` is "unclassified," not "the SELV
   domain." The real generator instead writes the condition the other way
   round (everything that is *not* `ACMains`/`HighVoltage`), which does not
   depend on a specific LV class existing or being named `Default`.

**As of 2026-07-28, `scripts/generate_kicad_dru.py` DOES emit real
`creepage` constraints** (confirmed kicad-cli 10.0.4 supports this
constraint type against `kicad-source-mirror` @ the 10.0.4 tag and
empirically — see `docs/evidence/2026-07-28-drc-creepage-constraint.md`).
The corrected, illustrative form of this snippet, matching what the real
generator actually emits today (RULE 2 "AC Mains to LV" / RULE 4 "HV to
LV"):

```
# High-voltage clearance + creepage rules for IEC 60335 compliance
# (illustrative -- the real file is generated by scripts/generate_kicad_dru.py;
# do not hand-edit pcb/temper.kicad_dru)

# AC Mains to everything else (reinforced insulation)
(rule "AC Mains to LV"
  (condition "A.NetClass == 'ACMains' && B.NetClass != 'ACMains' && B.NetClass != 'HighVoltage'")
  (constraint clearance (min 6.0mm))
  (constraint creepage (min 12.6mm)))

# DC Bus / High Voltage to everything else (reinforced insulation)
(rule "HV to LV"
  (condition "A.NetClass == 'HighVoltage' && B.NetClass != 'HighVoltage' && B.NetClass != 'ACMains'")
  (constraint clearance (min 2.0mm))
  (constraint creepage (min 12.6mm)))
```

**The 12.6mm creepage figure above is the PD3 pin, not a resolution of the
PD2/PD3 question** — see `scripts/generate_kicad_dru.py`'s
`HV_CREEPAGE_ENFORCED_MM` constant, which is the single site to change if a
human later confirms PD2. The 6.0mm/2.0mm clearance figures shown are the
existing net-class-pair clearances already in the generator (basic mains
isolation and the DC-bus/LV pair respectively) — not this document's §4.2
reinforced-barrier figure, which the generator enforces separately via
`HV_INTERNAL_CLEARANCE_MM` on same-footprint HV pairs. The
`HighVoltageIsolated` net class (gate-drive isolated supply) has no
creepage/clearance rule in the generator today — a real, separate,
narrower gap, out of this pass's scope, flagged here rather than silently
implied to be covered by the snippet above.

### 9.2 Zone Definitions

Create keep-out zones in KiCad:
1. **HV Zone** - Contains AC mains, DC bus, switch node
2. **LV Zone** - Contains ESP32, MAX31865, user interface
3. **Isolation Zone** - 2mm slot + 6mm keep-out on each side

## 10. References

- IEC 60335-1:2020 - Safety of household appliances - General
- IEC 60335-2-6:2020 - Particular requirements for cooking ranges
- IEC 60664-1:2020 - Insulation coordination
- IEC 61010-1:2010 - Safety for measurement equipment
- UCC21550 Datasheet - Layout guidelines (Section 11)
- GROUNDING_EMI_STRATEGY.md - Ground domain definitions
- NET_CLASS_SPECIFICATION.md - Net class clearances

## 11. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-16 | AI Agent | Initial specification |
| 1.1 | 2026-07-28 | AI Agent | §6.4 corrected: the coating scheme (×1.5 "Creepage Multiplier", IPC-CC-830) was unqualified, cited the wrong standard, and could not have delivered PD1 on this board's isolators even if built (100.0% of every declared isolator's shortest HV↔PELV path runs under its own component body — measured, `docs/evidence/2026-07-28-conformal-coating-pd1.md`). The same broken justification had already leaked into `scripts/generate_kicad_dru.py`'s generated DRC rules as a live fail-open; that generator now enforces a fail-closed 2.0mm figure gated behind an explicit, currently-`False` `COATING_QUALIFIED` flag. See `docs/evidence/2026-07-28-drc-coating-failopen-fix.md`. |
| 1.2 | 2026-07-28 | AI Agent | **Reconciled a third, independent inconsistent figure set** (§3.2, §4, §5, and downstream §6–§9): this document's own clearance/creepage tables asserted "5.0mm clearance / 8.0mm creepage" (and similar) at the mains↔SELV/PELV boundary, disagreeing with both v1.1's coating-section correction and the primary-text determination in `docs/evidence/2026-07-28-creepage-determination-brainstorm.md`. Root cause was the same bug class v1.1 already found once: creepage-table values (IEC 60335-1 Table 17) relabelled as clearance values, and "Table 16" (clearance) miscited for creepage. Corrected in place, old values recorded rather than deleted: real clearance requirement is **1.5mm nominal / 2.0mm with the clause-29.1 soldered-construction adder** (not 5–10mm); real creepage requirement is **8.0mm at Pollution Degree 2 / 12.6mm at Pollution Degree 3**, with the PD2-vs-PD3 question explicitly flagged UNRESOLVED, matching `scripts/generate_kicad_dru.py`'s `HV_CREEPAGE_PD2_MM`/`HV_CREEPAGE_PD3_MM`/`HV_CREEPAGE_ENFORCED_MM` constants and `scripts/check_isolation_keepout.py`'s `MIN_BARRIER_WIDTH_MM` (both already pinned to the PD3/12.6mm figure). §3.2's Overvoltage Category (III→II) and Pollution Degree (2→3, cited) were also corrected. Also recorded: as of this revision, `scripts/generate_kicad_dru.py` emits a real KiCad `creepage` DRC constraint (kicad-cli 10.0.4 confirmed to support one, both against `kicad-source-mirror` @ 10.0.4 and empirically) — closing the enforcement gap that generator's own header used to document ("this generator has no creepage constraint type"). §9.1's illustrative rule snippet is corrected to match. See `docs/evidence/2026-07-28-drc-creepage-constraint.md`. |
