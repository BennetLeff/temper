# Oracle request: controller reference and power-stage insulation basis

## Question to answer

For this 120 V induction cooker, should the controller's isolated low-voltage
return (`SELV_GND`, the current net name) have a direct protective-earth bond,
remain galvanically floating, or use a specified alternative connection?
Recommend an architecture and explain its consequences for touch safety,
faults, EMI, sensing and insulation coordination. Do not choose a bond merely
to reduce a PCB creepage number.

Then identify the working-voltage analysis needed to release the power-stage
barrier placement. In particular, can the proposed isolation packages and
land patterns meet the appliance's PD3 requirements, or must parts or the
environmental protection strategy change? Separate what follows from the
given schematic from what needs a measurement, waveform model, owner
decision or certification-lab ruling.

This is an architecture decision request, not a request to certify the board.
If the evidence is insufficient, give the smallest set of additional inputs
and a conditional recommendation instead of inventing a voltage bound.

## Current circuit, enough to reason without the repository

- Product: mains-powered induction cooker, nominal 120/127 V, 15 A input.
  The front-end brief proposes **108–140 V RMS** for design calculations;
  this is an assumption to confirm. The detailed coil screen currently covers
  114 V and 127 V, not the full proposed range.
- J1 brings in L, N and PE. Line is fused; an EMI filter has X capacitors
  across L/N and two **2.2 nF Y1 capacitors, one L-to-PE and one N-to-PE**.
  There is no source connection from PE to `SELV_GND`.
- A GBJ2510 full-wave bridge feeds a **5 µF film bus**, without a large
  smoothing electrolytic. At 140 V RMS the ideal rectified crest is about
  198 V. `HV_RET` is the bridge negative terminal, not earth. The full-bridge
  MOSFET return `LEG_RET` connects to `HV_RET` through a 1 mΩ current shunt.
- Four 650 V MOSFETs form a full bridge. Tank path:
  `SW_A → coil → COIL_RET → CT primary → RES_A → 0.54 µF → SW_B`.
  The intended nominal coil is 70 µH; actual coil/pan impedance is not yet
  measured. The design screen considers 20–60 kHz, with phase control and
  reduced-power operation. It is a first-harmonic design screen over assumed
  inputs, not an insulation or fault-voltage model.
- PS1, **MEAN WELL IRM-20-15**, runs from filtered L/N and supplies
  `V15_SELV`/`SELV_GND` to the controller, fan and sensor boards through J4.
  The controller returns 3.3 V and control signals through that header.
- PS2, **IRM-05-15**, supplies the HOT gate domain. Its negative output is
  deliberately tied to `LEG_RET`; an off-board thermal-cutoff loop interrupts
  its mains input. It does not supply the controller domain.
- Two **UCC21550BDWKR** dual gate drivers cross from controller 3.3 V/ground
  to the low-side `LEG_RET`/15 V domain and bootstrapped high-side switching
  domains. **AMC1311BDWVR** bus sensing and **ISO7710FDWR** fault signaling
  cross from HOT `LEG_RET`/5 V to controller 3.3 V/ground.
- **CST3015-100ED** CT primary is in the tank path. Its secondary goes to
  `CT_S1`/`CT_S2` on J4; the burden and comparators are on the current-sense
  board. Their common-mode reference must be checked, not inferred solely
  from the power-stage net names.
- The controller's ground-to-PE bond is explicitly undecided. Accessible
  probes must remain appropriately isolated. Controller ports, programming
  connections, sensor shields and any externally grounded equipment need
  an explicit connection inventory; do not assume USB or other ports are
  permanently isolated or permanently connected.
- A shared **PE-bonded heatsink**, with electrically insulated MOSFETs and
  rectifier, is a proposed mechanical default, not an owner-approved design.
  The enclosure, accessible metal and protective-earth arrangement need to
  be considered together.

## Why construction is paused at the barrier

The project currently uses **pollution degree 3** for a forced-air cooking
board. Do not silently substitute PD2. The existing layout plan used
430–560 V **peak** to select bands in a creepage table requiring **RMS working
voltage**. Its 558 V example belongs to an older half-bridge analysis.
The newer full-bridge screen's **650 V peak limit is across the resonant
capacitors** and is itself an assumed screening limit. It does not establish
any HOT-to-controller or HOT-to-PE differential waveform.

The repository's IEC 60335-1 Table 17 lookup gives these conditional values;
they have been checked against its live Rust implementation. Please verify
the applicable standard, edition, clauses, voltage definition, material
group and reinforced-insulation treatment independently before endorsing
them for the product.

| RMS band | PD3 reinforced, group IIIa/IIIb PCB, basic × 2 | PD3 reinforced, group I package material, basic × 2 |
| --- | ---: | ---: |
| >125–250 V | 8.0 mm | 6.4 mm |
| >250–400 V | 12.6 mm | 10.0 mm |
| >400–500 V | 16.0 mm | 12.6 mm |
| >500–800 V | 20.0 mm | 16.0 mm |

Package and PCB surface paths are separate. Existing evidence:

| Crossing | Package evidence | Current PCB land-pattern gap |
| --- | --- | --- |
| U1/U2 UCC21550BDWKR | >8 mm external creepage/clearance; group I; datasheet insulation table states PD2 | 8.1 mm custom land option |
| U7 ISO7710FDWR | 8 mm; group I; datasheet table states PD2 | Stock footprint 7.25 mm; TI high-voltage option 8.1 mm |
| U4 AMC1311BDWVR | ≥8.5 mm; group I; datasheet table states PD2 | Stock footprint 8.85 mm |
| T1 CST3015-100ED | ≥8 mm creepage/clearance; material group not established | Requires its own surface-path evaluation |
| PS1 IRM-20-15 | 45 mm opposing input/output pin-center span; no external creepage figure identified | Pin-center distance and hipot rating are not a complete creepage assessment |

Slots can increase a PCB surface path but do not lengthen the package surface.
Coating or enclosure credit needs a defined protection process and acceptance
basis. A dielectric withstand rating alone does not answer this question.

## Requested answer format

1. **Architecture recommendation:** direct single-point PE bond, floating,
   or a precisely described alternative. State assumptions about protective
   class, accessible parts and external connections. If earthing changes the
   applicable SELV/PELV classification, explain that; the existing net name
   is not a classification claim.
2. **Tradeoffs and faults:** explain common-mode current paths, EMI effects,
   sensing implications, and the normal/fault cases that govern. Distinguish
   protective earth from neutral; do not assume PE is intact in every case.
3. **Per-boundary voltage table:** U1/U2 low-side and high-side barriers,
   U4/U7, T1, PS1, and HOT-to-PE. State differential RMS for creepage and the
   relevant peak/impulse basis for clearance, or explicitly mark each value
   unestablished and name the calculation or measurement required. State the
   averaging convention and treatment of switching frequency. Do not use
   capacitor voltage as a substitute for an isolation-boundary waveform.
4. **Package and PCB disposition:** separately evaluate package material and
   board material. Say which parts/lands can remain, which need changes, and
   which conclusions need certification-lab confirmation. Cite primary
   sources and exact standard editions/clauses where available.
5. **Next actionable decision:** what can the owner approve now, and exactly
   what evidence is still needed before barrier placement? Keep pending
   physical verification explicit.

## Files to give the oracle

Canonical working checkout for this implementation:
`/Users/bennet/Desktop/temper/worktrees/ps-build`.
Paths below are relative to that checkout. The new preflight and decision
documents are local implementation files; do not assume they are on GitHub.

**Minimum Markdown reading packet:**

- `zapote/power-stage-120v/RULES-PREFLIGHT.md` — findings, package sources,
  material-group distinction and the missing voltage basis.
- `zapote/power-stage-120v/README.md` — circuit domains, J4 pinout, safety
  chain and the explicitly open controller bond.
- `docs/hardware/power-section-120v/POWER-SECTION.md` — source topology and
  current BOM; treat its unverified voltage shorthand as provisional.
- `docs/hardware/power-section-120v/COIL-MC.md` — full-bridge selection,
  waveform-model scope and assumed coil/pan inputs.
- `docs/adr/2026-09-25-front-end-architecture-brief.md` — proposed line range
  and product/front-end assumptions.
- `docs/plans/power-stage-120v-board/04-placement.md` — intended D5 hold point;
  its peak-to-RMS band selection is the defect being resolved.

**For checking circuit facts and calculations:**

- `zapote/power-stage-120v/elec/src/power_stage_120v.ato` and `parts.ato` —
  authoritative connections and part declarations.
- `zapote/power-stage-120v/audit.rs` — checked barrier pin membership; it
  validates connectivity, not isolation ratings or working voltages.
- `docs/hardware/power-section-120v/coil_mc.rs` — actual full-bridge screen.
- `packages/temper-design-bundle/src/safety_value.rs` — repository table
  lookup, to be checked against the applicable standard.
- `zapote/power-stage-120v/DECISIONS.md` — current pending decisions.

**Manufacturer primary sources:**

- [TI UCC21550](https://www.ti.com/lit/ds/symlink/ucc21550.pdf)
- [TI ISO7710](https://www.ti.com/lit/ds/symlink/iso7710.pdf)
- [TI AMC1311](https://www.ti.com/lit/ds/symlink/amc1311.pdf)
- [Coilcraft CST3015](https://www.coilcraft.com/getmedia/df31d5fe-b3af-4586-82a7-7b773ac9f838/cst3015.pdf)
- [MEAN WELL IRM-20](https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF)

Source baseline: `ad51823308f3a65d7bfe86351a128af5f237b31e`, with the corrected
TDK choke winding map 1–4 and 2–3. No electrical source change has been made
by this native-board implementation. Physical tests and certification have
not been performed.
