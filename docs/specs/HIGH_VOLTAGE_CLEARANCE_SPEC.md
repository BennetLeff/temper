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

**AC Mains corrected 2026-08-14** (was "120-240V RMS", contradicting
REQ-SYS-01's authoritative 120V RMS ±10% -- see the revision-history entry
below for what was checked before making this a documentation-only change).

| Domain | ID | Reference | Working Voltage | Peak/Transient | Classification |
|--------|-----|-----------|-----------------|----------------|----------------|
| AC Mains | A | Earth/Neutral | 120V RMS ±10% | 340V | Hazardous |
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
│  │  • ADC sensing   │(removed│                                  │   │
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
| **Pollution Degree** | **2, conditional** | The production architecture selects the IEC 60335-2-6 cl. 29.2 enclosure exception. A gasketed PCB compartment separate from the coil/heatsink airflow path is a release prerequisite; otherwise PD3 applies. |
| **Overvoltage Category** | **II** (corrected 2026-08-14, was III) | IEC 60335-1 clause 29.1 (CITED-PRIMARY, `docs/evidence/2026-07-28-creepage-determination-brainstorm.md:221-223`): **"Appliances are in overvoltage category II."** Unconditional -- the clause does not distinguish by appliance class. The prior "Equipment connected to mains distribution" justification described OVC III's own use case (equipment *at* the distribution level), not this design's: a detachable-cord, plug-in countertop appliance (IEC C20 inlet/C19 cord, `docs/CONNECTORS_AND_WIRING.md:13`) downstream of the distribution level, at 120V RMS ±10% into a standard 15A US outlet (`REQUIREMENTS.md` REQ-SYS-01). `scripts/generate_kicad_dru.py:56-63` already derives `HV_INTERNAL_CLEARANCE_MM` from OVC II and cites clause 29.1 correctly -- this correction changes no enforced clearance/creepage value, it aligns this document with what is already enforced and independently re-verified in `docs/evidence/2026-08-12-hv-clearance-adequacy.md` Sec 3.1/6.2. |
| **Material Group** | IIIa (corrected 2026-08-15, was IIIb) | FR4 CTI 175-249V. Per IEC 60335-1 cl. 29.2 material groups (CITED-PRIMARY, `docs/evidence/2026-07-28-creepage-determination-brainstorm.md:299`): IIIa is 175 < CTI < 400, IIIb is 100 < CTI < 175. CTI 175-249 therefore falls in **IIIa**, not IIIb. Non-operational in practice: IEC 60335-1 Table 17 merges IIIa and IIIb into a single column, so the creepage figures in §5.1 are unchanged. |
| **Altitude** | ≤2000m | Standard household use |
| **Working Temperature** | 60°C max ambient | Kitchen environment near cooking |

### 3.2.1 Pollution degree -- selected architecture and release gate

IEC 60335-2-6 clause 29.2 Addition makes PD3 the default for cooking
appliances unless the insulation is enclosed or located so that it is
unlikely to be exposed to pollution during normal use. The project owner
selected the PD2 exception as the production architecture on 2026-07-30,
with a concrete mechanical prerequisite rather than an assumption:

- the PCB is inside a covered, gasketed compartment;
- the compartment is separate from the coil/heatsink forced-air path;
- grease, steam, and cooking aerosols cannot reach exposed PCB insulation
  through the cooling duct, service openings, or cable penetrations;
- the assembly drawing identifies the cover, gasket interface, partition,
  and inspection points; and
- production inspection verifies that the barrier is installed and intact.

**That compartment was never built, and the 2026-08-15 data-driven
decision (docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md)
supersedes the PD2 adoption: the as-built board is forced-air vented with
no cover/gasket/partition, so PD3 and its 12.6mm reinforced-creepage
requirement govern.** `docs/CHASSIS_AIRFLOW_DESIGN.md`,
`docs/ASSEMBLY_GUIDE.md`, and `docs/ENVIRONMENTAL_SPEC.md` record the
(now-superseded) compartment as a release requirement; the airflow/thermal
design is unchanged. The PD2 column remains the documented fallback should
the sealed compartment ever be built and verified.

### 3.3 Insulation Types

| Type | Description | Test Voltage | Application |
|------|-------------|--------------|-------------|
| **Functional** | Minimum for operation | None required | Within same voltage domain |
| **Basic** | Single fault protection | 1500V AC 1 min | Mains to accessible parts |
| **Supplementary** | Second layer over basic | 1500V AC 1 min | Double insulation systems |
| **Reinforced** | Equivalent to double | 3000V AC 1 min | HV to SELV isolation |

## 4. Clearance Requirements

### 4.1 Clearance Table (Through Air)

**Flagged, not corrected in this pass (consistent with the outstanding-item
convention in §6.4 below):** this table's own header still says "Overvoltage
Category III", the same error §3.2 corrects to OVC II above, and its rows use
invented round-number working voltages rather than IEC 60335-1 Table 16's own
rated-impulse-voltage steps -- the same defect class §5.1's creepage table
had before its 2026-07-30 correction. §7-9's component-specific rows carry
the same unreconciled figures. None of this table's numbers are read by any
enforcement gate (`packages/temper-placer/src/temper_placer/requirements/validators/clearance.py`
and `scripts/generate_kicad_dru.py` are; see §5.1's own note), so leaving it
uncorrected changes no enforced value -- but a reader should not treat this
table as current. See `docs/evidence/2026-08-12-hv-clearance-adequacy.md`
for the real, clause-29.1.5-derived clearance requirement at this board's
actual worst-case working voltages,
including the resonant-tank node.

Based on IEC 60664-1 Table F.2 for Overvoltage Category III, Pollution Degree 2:

> **FLAGGED 2026-08-15 (safety-assertion audit):** two problems with this
> table's basis. (1) **OVC III vs OVC II**: IEC 60335-1 cl. 29.1 places
> appliances in overvoltage category **II**, not III
> (docs/evidence/2026-08-12-hv-clearance-adequacy.md; handoff 2026-08-15
> §9) -- an OVC III-based table is the wrong column for this appliance. The
> repo's OVC II-cited clearance derivation is
> `scripts/generate_kicad_dru.py`'s `HV_INTERNAL_CLEARANCE_MM` (Table 16
> 0.5mm at 1500V rated impulse -> cl. 29.1.3 next higher step 1.5mm + cl.
> 29.1 soldered-construction adder 0.5mm = **2.0mm**). (2) The "Design
> Value" column's 6.0mm at 400V is **UNSOURCED** -- IEC 60335-1 Table 16
> (the clearance table the repo actually recovered) has no 400V row and no
> 6.0mm value; 6.0mm appears in no recovered table. This table is retained
> as-is (values unchanged) with the flag; re-deriving it is a separate
> attributed task.

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

**PD3 governs (2026-08-15 data-driven decision)**: the sealed compartment
that would earn the PD2 exception is not built and is thermally
counterproductive, and the as-built board is forced-air vented with no
cover/gasket/partition (docs/evidence/2026-08-15-pd2-pd3-data-driven-
decision.md). MAINS (340V pk), DC_BUS (400V pk/transient), and Gate Drive
Isolated (355V peak-to-earth) satisfy ">250, ≤400" literally (400 ≤ 400),
which is row iv of Table 17 and gives **6.3mm basic / 12.6mm reinforced**
at PD3, Material Group IIIa/IIIb. The PD2 column (4.0mm basic / 8.0mm
reinforced) remains the documented fallback should the sealed compartment
ever be built and verified at the §3.2.1 release gate.

The prior PD2 baseline's 10.0mm value was the next voltage row's reinforced
figure. For the selected 400V boundary, this specification uses the literal
row-iv PD2 value of 8.0mm; the PD3 fallback remains 12.6mm. The historical
determination and its derivation are retained in
`docs/evidence/2026-07-30-pollution-degree-determination.md`.

**No interpolation between rows.** IEC 60664-1/60335-1 clearance and
creepage tables are not interpolated: a working voltage that falls within a
row's own stated bracket uses that row directly; a voltage that falls
*between* two rows' brackets (which does not arise for any boundary on this
board) would take the next row up.

### 5.2 Design Creepage

| Boundary | Insulation | Working V | Min Required | Design Value |
|----------|------------|-----------|--------------|--------------|
| AC Mains to SELV | Reinforced | 340V pk | 12.6mm PD3 / 8.0mm PD2 fallback | 14.6mm |
| DC Bus to SELV | Reinforced | 400V pk | 12.6mm PD3 / 8.0mm PD2 fallback | 14.6mm |
| Across UCC21550 | Reinforced | 400V | Per device spec, not less than selected system target | Per device spec |
| IGBT tab to LV trace | Reinforced | 400V | 12.6mm PD3 / 8.0mm PD2 fallback | 14.6mm |
| Within SELV | Functional | 15V | 0.5mm | 1.0mm |

**Within SELV (functional) row corrected 2026-08-15.** `Min Required`
0.5mm here is the clearance floor (Table 16, <=1500V rated impulse); the
creepage figure enforced by the requirement matrix's
LV_CONTROL<->LV_CONTROL FUNCTIONAL row is **1.8mm** -- IEC 60335-1 Table 18
row i (<=50V), Material Group IIIa/IIIb, PD3 (CITED-PRIMARY,
`docs/evidence/2026-08-12-hv-hv-creepage-determination.md`), the as-built
governing pollution degree (handoff 2026-08-15 §7.C). The prior 1.0mm
figure was a known-low pin the code itself conceded sat under even Table
18's PD2 value of 1.1. This row is a same-domain SELV-to-SELV functional
boundary, not a mains/DC-bus-to-SELV safety barrier; no clause 29.2.4
short-circuit-test exemption is claimed here. The matrix
(`validators/clearance.py` `IEC60335_REQUIREMENTS`, mirrored in
`temper-drc-rs/src/req_safe_01.rs` `MATRIX_ROWS`) is authoritative; this
spec row mirrors it for documentation.

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

**ADUM1250 I2C Isolator — REMOVED from the design (2026-07-30, `elec/src/components.ato:51-54`); this bullet and the §8.1 checklist row are stale artifacts, retained only as the historical record, superseded by `docs/hardware/BOM.md:238` ("Isolation is provided by the AuxSupply transformer, not an I2C isolator").**

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
whatever pollution degree actually governs (PD3 for the enforced
classification since the 2026-08-15 data-driven decision, with PD2 as the
documented fallback should the sealed compartment ever be built).
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

**Some component-specific rows in §§7-9 still show pre-2026-07-30 figures
(8.0/10.0/12.0mm reinforced creepage) and have not yet been reconciled to
the enforced PD3 target and its 8.0mm PD2 fallback -- flagged here so a
reader does not mistake them for current. The system-level checklist and
KiCad example below use the enforced 12.6mm PD3 target; remaining component
rows are a separate reconciliation task. Only §3.2, §5.1, §5.2, and §6.4
were in scope for the pollution-degree decision;
the validator matrix (`packages/temper-placer/src/temper_placer/requirements/validators/clearance.py`),
not this document's §7-9, is what actually gates REQ-SAFE-01.** See
`docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md`.

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
| AC_L to CGND | 12.6mm | ___mm | ☐ Pass |
| AC_N to CGND | 12.6mm | ___mm | ☐ Pass |
| DC_BUS+ to CGND | 12.6mm | ___mm | ☐ Pass |
| DC_BUS- to CGND | 12.6mm | ___mm | ☐ Pass |
| SWITCH_NODE to CGND | 12.6mm | ___mm | ☐ Pass |
| IGBT Q1 tab to LV | 12.6mm | ___mm | ☐ Pass |
| IGBT Q2 tab to LV | 12.6mm | ___mm | ☐ Pass |
| UCC21550 Pin 1-8 to 9-16 | 1.0mm | ___mm | ☐ Pass |
| ADUM1250 Side1 to Side2 | N/A — part removed (see §6.3) | — | ☐ N/A |
| Isolation slot width | 2.0mm | ___mm | ☐ Pass |

### 8.2 Creepage Verification Checklist

| Location | Required | Actual | Status |
|----------|----------|--------|--------|
| AC Mains to SELV | 12.6mm PD3 / 8.0mm PD2 fallback | ___mm | ☐ Pass |
| DC Bus to SELV | 12.6mm PD3 / 8.0mm PD2 fallback | ___mm | ☐ Pass |
| IGBT tab to nearest trace | 12.6mm PD3 / 8.0mm PD2 fallback | ___mm | ☐ Pass |
| Across isolation barrier | 12.6mm | ___mm | ☐ Pass |

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
  (constraint creepage (min 8.0mm)))

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
| 1.2 | 2026-07-30 | AI Agent | Owner selected the PD2 enclosure exception for production, conditional on a gasketed PCB compartment outside the coil/heatsink airflow path; restored the literal 8.0mm PD2 row-iv target while retaining 12.6mm as the fallback. |
| 1.3 | 2026-07-30 | AI Agent | Aligned the third enforcement point this document's Sec 6.4 note flagged as outstanding: the REQ-SAFE-01 requirements validator (`packages/temper-placer/src/temper_placer/requirements/validators/clearance.py`) moved from the PD3 fallback (12.6mm reinforced / 6.3mm basic) to the PD2 target (8.0mm reinforced / 4.0mm basic) this document already declared operative in v1.2, closing the inconsistency between the validator and the already-aligned KiCad DRU generator / physical isolation keepout. See `docs/evidence/2026-07-30-pd2-enclosure-decision.md`. |
| 1.4 | 2026-08-14 | AI Agent | **Two documentation-only corrections; no enforced clearance/creepage/voltage value changed.** (1) §3.2 Overvoltage Category corrected III -> II, citing IEC 60335-1 clause 29.1 (CITED-PRIMARY, unconditional: "Appliances are in overvoltage category II") -- the prior "Equipment connected to mains distribution" justification actually describes OVC III's own use case, not this cord-and-plug countertop appliance's; `scripts/generate_kicad_dru.py` already assumed and cited OVC II correctly, so this aligns the document with the value already enforced. Also corrected the identical uncited OVC III claim at `docs/evidence/2026-08-07-creepage-authority-and-pullback-analysis.md:133-137`. §4.1's table header still says OVC III and is flagged, not corrected, consistent with §6.4's existing convention for unreconciled sections. (2) §2.1's AC Mains "120-240V RMS" row corrected to "120V RMS ±10%", matching REQ-SYS-01 (`REQUIREMENTS.md`) exactly -- confirmed, not assumed: the design's voltage doubler exists specifically so the appliance needs no 240V input (`docs/hardware/VOLTAGE_DOUBLER_DESIGN.md`: "Compatible with 120V/15A outlet (no 240V required)"), `elec/src/main.ato:52` asserts `v_ac_nominal` within 100-130V, and no 120/240V dual-input or export variant is declared as a design target anywhere in `REQUIREMENTS.md`/`docs/CONNECTORS_AND_WIRING.md`. **No 240V variant is intended for this design.** Two stale artifacts from what appears to be an earlier generic/EU-oriented template were found and are reported, not fixed, here (out of this correction's scope, and neither gates enforced clearance/creepage): `packages/temper-placer/src/temper_placer/core/design_rules.py`'s `ACMains` netclass carries `voltage_v=240.0` (metadata only -- confirmed unconsumed by `scripts/generate_kicad_dru.py`'s per-class trace-width/clearance emission, which reads `.trace_width`/`.clearance`/`.creepage_mm`, not `.voltage_v`), and `packages/temper-placer/configs/pcb_spec.yaml`'s `safety.mains_voltage_v: 230.0` feeds a *separate* derivation path (`packages/temper-placer/src/temper_placer/pipeline/derivation.py` -> `hv_lv_isolation_mm` -> `temper-quality-oracle`/`physics_oracle.py`, a regression/scoring tool, not the board's DRC gate) that should be reconciled to 120V by whoever owns that config, since a reader could otherwise mistake it for a second live voltage target. **If a 240V (or 120/240V dual-input) variant is ever built, this correction and the entire clearance/creepage derivation chain built on it (`scripts/generate_kicad_dru.py`'s `HV_INTERNAL_CLEARANCE_MM`, this document's §3.2/§4/§5) do NOT cover it and must be re-derived**: IEC 60335-1 Table 15's rated-voltage row shifts at 150V, so a genuine 240V rated voltage falls in the >150-300V row, requiring 2500V rated impulse voltage even under OVC II -- the same figure OVC III would have given at 120V, i.e. exactly the discrepancy this correction just removed would reappear on different grounds. See the certification-lab package, `docs/evidence/2026-08-14-certification-lab-package-pd3-and-60664-4.md`, for the related open questions this session also documented. |
| 1.5 | 2026-08-15 | AI Agent | §3.2 Material Group row corrected **IIIb -> IIIa**: FR4 CTI 175-249V falls in cl. 29.2's **IIIa** band (175 < CTI < 400); IIIb is 100 < CTI < 175 (CITED-PRIMARY, `docs/evidence/2026-07-28-creepage-determination-brainstorm.md:299`). **Non-operational, not merely cosmetic**: IEC 60335-1 Table 17 merges IIIa and IIIb into a single column, so every creepage figure in §5.1 (already labeled "Material Group IIIa/IIIb") is unchanged -- no enforced value moves. The prior IIIb label was a misclassification of the same CTI range, not a different material. |
