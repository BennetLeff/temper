# Insulation preflight — D5 remains open

Reviewed against source baseline `ad51823308f3a65d7bfe86351a128af5f237b31e`
on 2026-09-25. This is a requirements and package review, not an approved
rule set or a compliance verdict. No final barrier placement is authorized by
this record.

## Working-voltage gap

Part 4 uses 430–560 V **peak** to select creepage bands that require **RMS
working voltage**. The 558 V case in
`docs/hardware/power-section-120v/power-section-output.txt` is explicitly from
the superseded half-bridge screen. `COIL-MC.md` selects the full bridge and
uses a 650 V peak resonant-capacitor screen; that is not the differential RMS
voltage from each HOT boundary to SELV.

The boundary analysis must cover the operating/fault envelope and state the
SELV/PE reference assumption. U1/U2 cross SW_A/SW_B and LEG_RET to SELV;
U4/U7 cross LEG_RET to SELV; T1 crosses its tank primary to its SELV
secondary; PS1 crosses mains to SELV. A voltage quoted relative to HV_RET
does not by itself bound voltage relative to floating SELV.

A verified bound on the absolute differential peak can conservatively bound
RMS, since RMS cannot exceed that bound. It does not establish the actual
RMS value. The historical 560 V number has not been established as such a
bound for this design.

The unit README explicitly lists the controller-side `SELV_GND` to PE bond
as undecided. The two Y capacitors connect mains to PE; they do not establish
a SELV-to-PE bond. `POWER-SECTION.md` also marks voltage verification and
coil/pan measurement open. The full-bridge screen runs detailed cases at
114 V and 127 V and limits resonant-capacitor peak to 650 V; neither supplies
the missing boundary waveforms at high line and under the relevant faults.

| Crossing | Source nets on the HOT side | Established differential RMS / peak to SELV |
| --- | --- | --- |
| U1/U2 | SW_A/SW_B and bootstrap supply; LEG_RET/V15_LS | Not established |
| U4/U7 | HOT5/LEG_RET | Not established |
| T1 | COIL_RET/RES_A | Not established |
| PS1 | L_FILT/N_FILT | Not established; 140 V line-to-neutral is not automatically the voltage to floating SELV |

The first missing decision is the controller-side SELV/PE reference
architecture. Fix that before defining and calculating each crossing's
operating and fault envelope. A bond decision alone is not an insulation
approval.

## Repository table values

Inspected `packages/temper-design-bundle/src/safety_value.rs`, Table 17
rows at lines 530–575, then independently executed every lookup below with
the fresh `temper_design_bundle_python` extension in the isolated toolchain
venv. The source readings and live results agree. The plan's `>130-250`
argument raises `ValueError: unknown voltage range '>130-250'`; the API
accepts `>125-250`.

| RMS band | PD3 basic, PCB group IIIa/IIIb | Reinforced, PCB group IIIa/IIIb | PD3 basic, group I | Reinforced, group I |
| --- | ---: | ---: | ---: | ---: |
| >125–250 V | 4.0 mm | 8.0 mm | 3.2 mm | 6.4 mm |
| >250–400 V | 6.3 mm | 12.6 mm | 5.0 mm | 10.0 mm |
| >400–500 V | 8.0 mm | 16.0 mm | 6.3 mm | 12.6 mm |
| >500–800 V | 10.0 mm | 20.0 mm | 8.0 mm | 16.0 mm |

Reinforced entries apply the plan's basic × 2 convention. **Package and PCB
surface paths must be evaluated separately.** The TI package materials below
are group I; applying the PCB's group IIIa/IIIb number to every package is a
conservative construction target, not a demonstrated package requirement.
Package ratings and their stated pollution-degree conditions still require
evaluation for this appliance.

Table 18 PD3/IIIa/IIIb functional values for the same four bands are 3.2,
5.0, 6.3 and 10.0 mm. Table 16's raw 2500 V impulse clearance cell is 1.5 mm.
Impulse category, reinforced-insulation step, soldered construction and
resonant peak-voltage effects must be resolved before treating that raw cell
as a final clearance rule. See the repository's
`docs/evidence/2026-07-28-creepage-determination-brainstorm.md`.

## Manufacturer and land-pattern evidence

| Part | Manufacturer evidence | Existing land pattern / limitation |
| --- | --- | --- |
| U1/U2 UCC21550BDWKR | [TI UCC21550](https://www.ti.com/lit/ds/symlink/ucc21550.pdf), §5.6 p7: external creepage/clearance >8 mm, CTI >600, group I, table states PD2. Figure 4-2 p3 confirms DWK numbering 1–11, 14–16; pins 12/13 absent. | TI high-voltage land option p50 gives 8.1 mm. The copied custom footprint uses this gap. A published lower bound >8 mm does not establish ≥10 or ≥12.6 mm. |
| U7 ISO7710FDWR | [TI ISO7710](https://www.ti.com/lit/ds/symlink/iso7710.pdf), §5.6 p8: 8 mm external creepage/clearance, CTI >600, group I, PD2. | Current stock pad rows at ±4.65 mm with 2.05 mm pad length give 7.25 mm PCB pad gap. TI's high-voltage land option p33 provides 8.1 mm. Even an 8 mm PCB rule needs a land-pattern change or another justified board-path treatment. |
| U4 AMC1311BDWVR | [TI AMC1311](https://www.ti.com/lit/ds/symlink/amc1311.pdf), §7.6 p8: ≥8.5 mm external creepage/clearance, CTI ≥600, group I, PD2. HOT pins 1–4, SELV 5–8. | Current stock pad rows ±5.325 mm, pad length 1.8 mm: 8.85 mm pad gap. TI's p36 nominal land option gives 9.1 mm. |
| T1 CST3015-100ED | [Coilcraft CST3015](https://www.coilcraft.com/getmedia/df31d5fe-b3af-4586-82a7-7b773ac9f838/cst3015.pdf), p1: ≥8 mm creepage/clearance, 5 kVrms for one minute; primary pins 1–2, secondary 3–4. | The lower-bound guarantee does not establish ≥12.6 mm. Do not invent the actual surface distance or its material group. |
| PS1 IRM-20-15 | [MEAN WELL IRM-20](https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF), p3 bottom view: pin1 AC/L, pin2 AC/N, pin3 −V, pin4 +V; 45 mm opposing input/output pin-center span, 1 mm pins. | No external creepage figure identified. The p2 4.2 kVac input/output withstand rating is not a creepage dimension. |

Manufacturer sources were inspected by the read-only Sol preflight agent.
Dimensions quoted from existing KiCad footprints are geometric checks;
package surface paths cannot be measured by PCB DRC alone.

The external answer and its rectifier-clamp counterexample are reviewed in
[ORACLE-REVIEW.md](ORACLE-REVIEW.md). The corrected CST3015 land pattern has
18.5 mm PCB copper edge gap; package guarantee remains ≥8 mm.

## Required resolution before barrier placement

1. Establish each boundary's differential RMS and clearance-determining peak
   voltage for this full-bridge design, with SELV/PE assumptions.
2. Derive PCB and package requirements using their respective materials and
   justified environment. PD3 remains the project basis.
3. Resolve any shortfall through reviewed source/package/land-pattern changes,
   or a separately justified environmental protection strategy. Coating or
   sealed-compartment credit requires the certification basis; it is not
   assumed here. Slots increase board creepage, not package-surface creepage.
4. Record D5 and run rules against the generated board, including a deliberate
   barrier-violation test before accepting routing.

Pure-HOT placement may proceed under Part 4 once the mechanical decisions
are available. Final placement approval, routing and final fabrication
exports remain gated. Physical insulation and certification: **NOT RUN**.
