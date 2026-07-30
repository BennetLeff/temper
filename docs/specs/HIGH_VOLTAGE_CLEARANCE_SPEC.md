# High-Voltage Clearance and Creepage Specification

**Document ID:** REQ-ELEC-04  
**Version:** 1.0  
**Date:** 2025-12-16  
**Status:** Implemented  
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

### 3.2 Environmental Parameters

| Parameter | Value | Justification |
|-----------|-------|---------------|
| **Pollution Degree** | **3** (corrected 2026-07-30, was 2) | See 3.2.1 -- IEC 60335-2-6 cl. 29.2 Addition makes PD3 the default for this appliance class; no enclosure/sealing argument earns the PD2 exception on this design's own mechanical documents. |
| **Overvoltage Category** | III | Equipment connected to mains distribution |
| **Material Group** | IIIb | FR4 CTI 175-249V |
| **Altitude** | ≤2000m | Standard household use |
| **Working Temperature** | 60°C max ambient | Kitchen environment near cooking |

### 3.2.1 Pollution degree -- corrected, with citation

**This row previously read "2 -- Normal indoor environment, condensation
possible," with no clause citation.** IEC 60335-1 clause 29.2 (CITED-PRIMARY,
IS 302-1:2008 Sec 29, identical adoption, re-read directly) states the
general default: *"Pollution degree 2 applies unless: a) precautions have
been taken to protect the insulation, in which case pollution degree 1
applies; and b) the insulation is subjected to conductive pollution, in
which case pollution degree 3 applies."* IEC 60335-2-6, the particular
standard for cooking ranges/hobs/ovens -- this appliance's own category, not
a generic household appliance -- overrides that default. Clause 29.2
Addition (CITED-PRIMARY, IS 302-2-6:2009 Sec 29, identical adoption,
re-read directly):

> "The microenvironment is pollution degree 3 unless the insulation is
> enclosed or located so that it is unlikely to be exposed to pollution
> during normal use of the appliance."

**PD3 is therefore the default for this appliance class. PD2 is an
exception that must be earned**, by showing the insulation is enclosed or
located away from pollution exposure. Checked directly against this
project's own mechanical documents, and the exception is not earned:

- `docs/CHASSIS_AIRFLOW_DESIGN.md` describes forced convection cooling that
  draws air from the chassis's own bottom intake vents, through an intake
  plenum, an 80mm PWM fan, a transition duct, across the IGBT heatsink, and
  out a rear exhaust vent -- an actively vented path pulling unfiltered
  kitchen air (grease, steam, cooking aerosols) through the same chassis
  cavity the PCB occupies, not an enclosure that excludes it.
- `docs/COIL_BRACKET_DESIGN.md` describes "large triangular cutouts around
  the central coil ring [that] allow air from the bottom intake to flow
  directly through the Litz wire strands" -- an air-permeable baffle, not a
  seal.
- `docs/ASSEMBLY_GUIDE.md` mounts the main PCB via M3 standoffs directly
  into that same vented chassis cavity -- no separate box, partition wall,
  or gasket is described anywhere for the PCB itself. The assembly's only
  gasket ("high-temp silicone gasket to the chassis lip," Phase 3) seals
  the glass-ceramic cooktop to the chassis, a different joint entirely.
- This table's own **IP20** rating states "No liquid ingress protection
  guaranteed" -- an argument against, not for, an enclosure claim, and
  neither IP20 digit addresses airborne grease/steam/cooking aerosol, which
  is exactly what the forced-air duct is designed to pull across the
  compartment.

**PD2 (and the 10.0mm reinforced creepage figure that came with it) remains
available**, but only if a future mechanical revision documents an actual
sealed, gasketed PCB compartment -- separate from the coil/heatsink airflow
path -- that the forced-air duct demonstrably does not cross. That document
does not exist today. See
`docs/evidence/2026-07-30-pollution-degree-determination.md` for the full
determination, including why a conformal coating does not change this
answer for the boundaries that currently fail.

### 3.3 Insulation Types

| Type | Description | Test Voltage | Application |
|------|-------------|--------------|-------------|
| **Functional** | Minimum for operation | None required | Within same voltage domain |
| **Basic** | Single fault protection | 1500V AC 1 min | Mains to accessible parts |
| **Supplementary** | Second layer over basic | 1500V AC 1 min | Double insulation systems |
| **Reinforced** | Equivalent to double | 3000V AC 1 min | HV to SELV isolation |

## 4. Clearance Requirements

### 4.1 Clearance Table (Through Air)

Based on IEC 60664-1 Table F.2 for Overvoltage Category III, Pollution Degree 2:

| Working Voltage (V) | Basic (mm) | Reinforced (mm) | Design Value (mm) |
|--------------------|------------|-----------------|-------------------|
| 50 | 0.5 | 1.0 | 1.5 |
| 100 | 0.7 | 1.4 | 2.0 |
| 150 | 1.0 | 2.0 | 2.5 |
| 200 | 1.3 | 2.6 | 3.0 |
| 300 | 2.0 | 4.0 | 5.0 |
| 400 | 2.5 | 5.0 | 6.0 |
| 600 | 4.0 | 8.0 | 10.0 |

### 4.2 Design Clearances

| Boundary | Insulation | Working V | Min Required | Design Value |
|----------|------------|-----------|--------------|--------------|
| AC Mains (L/N) to PE | Basic | 340V pk | 2.5mm | 4.0mm |
| AC Mains to SELV (Domain D) | Reinforced | 340V pk | 5.0mm | 8.0mm |
| DC Bus to SELV (Domain D) | Reinforced | 400V pk | 5.0mm | 8.0mm |
| DC Bus to Gate Iso (Domain C) | Functional | 15V | 0.5mm | 1.0mm |
| Gate Iso to SELV (Domain D) | Reinforced | 355V | 5.0mm | 8.0mm |
| Within SELV (Domain D) | Functional | 15V | 0.2mm | 0.5mm |
| Any HV to Exposed Metal | Basic | 400V | 2.5mm | 4.0mm |

## 5. Creepage Requirements

### 5.1 Creepage Table (Along Surface)

**Table number, row boundaries, and pollution degree corrected 2026-07-30.**
This table is IEC 60335-1's **Table 17** ("Minimum Creepage Distances for
Basic Insulation," clauses 29.2.1-29.2.3), not Table 16 (Table 16 is the
*clearance* table, §4.1's basis) -- a pre-existing mislabel corrected here.
The row boundaries below are the standard's own (previously this table used
invented round-number rows -- 50/100/150/200/300/400/600V -- that do not
match Table 17's actual breakpoints at every row; replaced here with the
real breakpoints so every figure traces exactly). Based on IEC 60335-1
Table 17, Material Group IIIa/IIIb (CITED-PRIMARY, IS 302-1:2008 Table 17,
re-read directly this session), both pollution-degree columns shown for
comparison:

| Working Voltage (V) | PD2 Basic (mm) | PD2 Reinforced (mm) | PD3 Basic (mm) | **PD3 Reinforced (mm)** |
|---|---:|---:|---:|---:|
| ≤50 | 1.2 | 2.4 | 1.9 | 3.8 |
| >50, ≤125 | 1.5 | 3.0 | 2.4 | 4.8 |
| >125, ≤250 | 2.5 | 5.0 | 4.0 | 8.0 |
| >250, ≤400 | 4.0 | 8.0 | 6.3 | **12.6** |
| >400, ≤500 | 5.0 | 10.0 | 8.0 | 16.0 |

**Pollution Degree 3 governs** (corrected from PD2 -- see §3.2.1). MAINS
(340V pk), DC_BUS (400V pk/transient), and Gate Drive Isolated (355V
peak-to-earth) all satisfy ">250, ≤400" literally (400 ≤ 400) -- this is
row iv of Table 17, not an interpolated or rounded-up value -- giving
**6.3mm basic / 12.6mm reinforced** at PD3, Material Group IIIa/IIIb.

**Flagged, not corrected here: an apparent inconsistency in the currently-
committed PD2 baseline.** `docs/evidence/2026-07-30-creepage-requirement-
reconciliation.md` (PR #442, already merged) states the PD2 figure at this
boundary is **10.0mm reinforced**, matching Table 17's *next* row (">400,
≤500": 5.0mm basic / 10.0mm reinforced), not the ">250, ≤400" row this
session's direct read of the primary text puts 400V in. Re-deriving that
axis is **out of scope for this pass** (a distinct, previously-settled
voltage-row question, not the pollution-degree question this document
addresses), so the PD3 figure above is derived directly from Table 17 row
iv rather than by scaling PR #442's 10.0mm -- consistent with every prior
PD3 investigation in this repository's history
(`docs/evidence/2026-07-28-pd3-retarget-relay.md` and siblings, all of
which independently derive 12.6mm the same way). A human should reconcile
whether PR #442's 10.0mm was itself an off-by-one-row (more conservative
than the letter of the standard, not less -- not a safety defect, but not
literally what row iv requires either) as a separate follow-up; see
`docs/evidence/2026-07-30-pollution-degree-determination.md`.

**No interpolation between rows.** IEC 60664-1/60335-1 clearance and
creepage tables are not interpolated: a working voltage that falls within a
row's own stated bracket uses that row directly; a voltage that falls
*between* two rows' brackets (which does not arise for any boundary on this
board) would take the next row up.

### 5.2 Design Creepage

| Boundary | Insulation | Working V | Min Required | Design Value |
|----------|------------|-----------|--------------|--------------|
| AC Mains to SELV | Reinforced | 340V pk | 12.6mm | 14.6mm |
| DC Bus to SELV | Reinforced | 400V pk | 12.6mm | 14.6mm |
| Across UCC21550 | Reinforced | 400V | 12.6mm | Per device spec |
| IGBT tab to LV trace | Reinforced | 400V | 12.6mm | 14.6mm |
| Within SELV | Functional | 15V | 0.5mm | 1.0mm |

**Within SELV (functional) row not corrected in this pass.** The same PD3
finding applies in principle (Table 18 row i, ≤50V, PD3, Material Group
IIIa/IIIb = 1.8mm, vs. this row's 1.0mm, which was already slightly under
Table 18's own PD2 figure of 1.1mm at this row) but this is a same-domain
SELV-to-SELV functional boundary, not a mains/DC-bus-to-SELV safety barrier,
and needs its own check of whether clause 29.2.4's short-circuit-test
exemption already applies before being changed. Flagged, not corrected
here -- see `docs/evidence/2026-07-30-pollution-degree-determination.md`.

## 6. Isolation Barrier Design

### 6.1 PCB Slot Specification

A routed slot in the PCB creates a physical barrier between high-voltage and low-voltage domains.

**Slot Parameters:**
- **Width:** 2.0mm minimum
- **Depth:** Full board thickness (1.6mm)
- **Location:** Between Domain B/C and Domain D
- **Length:** Full board width where domains meet

**Creepage Enhancement:**
```
Without slot:  Creepage = surface distance only
With slot:     Creepage = 2 × slot width + surface across slot
               Effective creepage = 2 × 2.0mm + 4.0mm = 8.0mm minimum
```

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

### 6.4 Conformal Coating -- NOT a live relaxation on this design (corrected 2026-07-30)

**This section previously specified a "Creepage Multiplier: x1.5 for coated
surfaces." No such provision exists in IEC 60335-1 or IEC 60664-3** (both
read directly this session -- see
`docs/evidence/2026-07-28-conformal-coating-pd1.md`, `docs/evidence/2026-07-30-pollution-degree-determination.md`).
The real mechanism (IEC 60335-1 clause 29 preamble + Annex J, delegating to
IEC 60664-3) is not a scaling factor: a qualified Type A ("type 1
protection") coating changes the *pollution degree* of the protected
microenvironment to **PD1**, per-creepage-path, binary -- either a path is
fully covered and gets the PD1 figure, or it is not covered at all and gets
whatever pollution degree actually governs (PD3 on this design, per §3.2.1).
A x1.5 multiplier is not equivalent to that in either direction and has no
textual basis.

**This design has no qualified coating today, and could not earn PD1 on its
current failing paths even if one were added:**

1. **No coating process exists in this project's BOM or assembly
   documents.** Checked directly (`docs/hardware/BOM.md`,
   `docs/ASSEMBLY_GUIDE.md`) -- neither mentions a coating step, material,
   or process. §6.4's "Coating Type/Thickness" above was never connected to
   an actual manufacturing step.
2. **IEC 60664-3 clause 4.3 requires the entire creepage path -- both
   conductive parts and every span between them -- to be covered** for PD1
   credit on that path; there is no partial credit. Measured directly
   against every declared isolator's real footprint geometry
   (`docs/evidence/2026-07-28-conformal-coating-pd1.md` §4): **100.0% of
   the shortest HV<->SELV surface path lies underneath the component body**
   for every one of the seven isolators with a body outline (C6, K1, K2,
   K3, T1, U3, U7). A coating applied after reflow/wave does not reach the
   board surface beneath an already-seated component body -- the credit
   cannot be earned on these paths by adding a coating step alone, only by
   also changing the footprint/placement so the path is not hidden under a
   body, which is a layout change, not a coating spec.
3. **Even a hypothetically perfect, fully-covering Type A coating does not
   make this board compliant.** At PD1, reinforced creepage at this board's
   400V row (Table 17 row iv, Material Group IIIa/IIIb) is 2.0mm, not
   0mm -- several cross-domain pad pairs on this board measure below 2.0mm
   even under that best case (see the cited evidence doc §"Verdict up
   front," item 3).

**Conclusion: conformal coating is not a live option for closing this
board's current creepage shortfalls**, either because the specific failing
paths are structurally uncoatable (under a component body) or because no
coating process is specified in the first place. `scripts/generate_kicad_dru.py`
already encodes this fail-closed (`COATING_QUALIFIED = False`, with the
same citation chain) and is unchanged by this pass. If a future design adds
a genuine coating step **and** relocates the affected footprints so their
governing creepage paths are not hidden under a body, PD1 credit becomes
available for those specific paths at that time -- not before.

**Sections 7-9 below still show pre-2026-07-30 figures (8.0/10.0/12.0mm
reinforced creepage) and have not yet been reconciled to the corrected
12.6mm PD3 figure (§5.1/§5.2) or to PR #442's own 400V-row figures --
flagged here so a reader does not mistake them for current. Only §3.2,
§5.1, §5.2, and §6.4 were in scope for the pollution-degree correction;
the validator matrix (`packages/temper-placer/src/temper_placer/requirements/validators/clearance.py`),
not this document's §7-9, is what actually gates REQ-SAFE-01.** See
`docs/evidence/2026-07-30-pollution-degree-determination.md`.

## 7. Component-Specific Clearances

### 7.1 IGBT (IKW40N120H3) TO-247

**Hazard:** Collector tab at DC bus potential (340V)

| Clearance Path | Requirement | Design |
|----------------|-------------|--------|
| Tab to nearest LV trace | 8mm clearance, 12mm creepage | 12mm |
| Tab to mounting hole | 4mm (to chassis ground) | 5mm |
| Gate pin to collector tab | Per package (internal) | N/A |
| Emitter to collector tab | Per package (internal) | N/A |

**PCB Layout:**
- No LV traces within 12mm radius of collector tab
- Dedicated copper pour for collector (DC bus)
- Thermal pad connected via thermal vias to internal plane

### 7.2 Rectifier Bridge

**Hazard:** AC pins at mains potential, DC pins at bus potential

| Clearance Path | Requirement | Design |
|----------------|-------------|--------|
| AC pins to SELV | 8mm clearance | 10mm |
| DC+ to PE connection | 4mm clearance | 5mm |
| Between AC pins | Per device | Functional |

### 7.3 Bus Capacitors

**Hazard:** Terminals at 340V DC, stored energy hazard

| Clearance Path | Requirement | Design |
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

### 8.1 Clearance Verification Checklist

| Location | Required | Actual | Status |
|----------|----------|--------|--------|
| AC_L to CGND | 8.0mm | ___mm | ☐ Pass |
| AC_N to CGND | 8.0mm | ___mm | ☐ Pass |
| DC_BUS+ to CGND | 8.0mm | ___mm | ☐ Pass |
| DC_BUS- to CGND | 8.0mm | ___mm | ☐ Pass |
| SWITCH_NODE to CGND | 8.0mm | ___mm | ☐ Pass |
| IGBT Q1 tab to LV | 8.0mm | ___mm | ☐ Pass |
| IGBT Q2 tab to LV | 8.0mm | ___mm | ☐ Pass |
| UCC21550 Pin 1-8 to 9-16 | 1.0mm | ___mm | ☐ Pass |
| ADUM1250 Side1 to Side2 | 4.0mm | ___mm | ☐ Pass |
| Isolation slot width | 2.0mm | ___mm | ☐ Pass |

### 8.2 Creepage Verification Checklist

| Location | Required | Actual | Status |
|----------|----------|--------|--------|
| AC Mains to SELV | 10.0mm | ___mm | ☐ Pass |
| DC Bus to SELV | 12.0mm | ___mm | ☐ Pass |
| IGBT tab to nearest trace | 12.0mm | ___mm | ☐ Pass |
| Across isolation barrier | 8.0mm | ___mm | ☐ Pass |

### 8.3 Hi-Pot Test Requirements

| Test | Voltage | Duration | Leakage Limit |
|------|---------|----------|---------------|
| Mains to SELV | 3000V AC | 1 minute | <5mA |
| Mains to PE | 1500V AC | 1 minute | <5mA |
| DC Bus to SELV | 3000V AC | 1 minute | <5mA |
| Isolation barrier | 5700V RMS | 1 minute | Per UCC21550 |

## 9. KiCad Design Rules

### 9.1 Custom DRC Rules

Add to project design rules (`.kicad_dru` or inline):

```
# High-voltage clearance rules for IEC 60335 compliance

# AC Mains to SELV (reinforced insulation)
(rule "HV_AC_to_SELV"
  (condition "A.NetClass == 'ACMains' && B.NetClass == 'Default'")
  (constraint clearance (min 8.0mm)))

(rule "HV_AC_to_SELV_creepage"
  (condition "A.NetClass == 'ACMains' && B.NetClass == 'Default'")
  (constraint creepage (min 10.0mm)))

# DC Bus to SELV (reinforced insulation)
(rule "HV_DC_to_SELV"
  (condition "A.NetClass == 'HighVoltage' && B.NetClass == 'Default'")
  (constraint clearance (min 8.0mm)))

# Isolation barrier - HV-Isolated to SELV
(rule "Isolation_barrier"
  (condition "A.NetClass == 'HighVoltageIsolated' && B.NetClass == 'Default'")
  (constraint clearance (min 6.0mm)))
```

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
| 1.1 | 2026-07-30 | AI Agent | Pollution degree corrected PD2 -> PD3 with citation (§3.2/3.2.1); creepage table mislabel and pollution-degree column corrected, real Table 17 row boundaries substituted for invented round numbers (§5.1/5.2); fabricated conformal-coating creepage multiplier removed and replaced with the real, non-multiplicative mechanism (§6.4). See `docs/evidence/2026-07-30-pollution-degree-determination.md`. §7-9 not yet reconciled -- flagged, not corrected, in this pass. |
