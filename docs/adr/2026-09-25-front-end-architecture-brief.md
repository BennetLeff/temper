---
title: Cooker front-end architecture — unfiltered-bus half bridge vs PFC + 400 V bank
type: decision-brief
date: 2026-09-25
status: accepted 2026-09-25 (amended: full bridge, see below)
supersedes-if-accepted: Rev38 PFC/bank as the product front end (docs/plans/2026-09-23-001-feat-power-entry-hot-receiver-plan.md, docs/superpowers/specs/2026-09-24-rev38-single-bank-cooker-design.md)
---

# Cooker front-end architecture brief

> **Accepted 2026-09-25, with one amendment.** Option A's front end (unfiltered film bus, no
> PFC) is adopted. The inverter is a **full bridge** rather than the half bridge sketched
> below. `docs/hardware/power-section-120v/COIL-MC.md` shows a 120 V half bridge reaches full
> power on only ~69–73 % of intended cookware, while a full bridge with a ~65–80 µH coil
> covers ~100 % at the same switch count and loss. Implementation:
> `zapote/power-stage-120v`. Rev38 is archived: `docs/archive/REV38.md`.

## Question

Is the current source of truth — Rev38 active PFC feeding a 400 V
electrolytic bank, then a half-bridge inverter — the right power
architecture for the product? Rev38 closure work is **paused** pending this
decision; no Rev38 file was changed by this brief.

## Product requirements used

| Requirement | Value | Source |
| --- | --- | --- |
| Product class | Countertop induction cooker with Control Freak-class precision (probe + through-glass sensing, closed-loop temperature hold) | Owner |
| Market | US and Mexico home kitchens: 120 V / 127 V nominal, 60 Hz | Owner |
| Supply | Standard outlet on a 15 A or 20 A circuit (the Control Freak's own manual specifies "120-volt, 60 Hz, AC only, 15/20-amp" supply) | Owner; Breville BMC800 US instruction book |
| Power | 1,800 W at the wall | `docs/handoffs/2026-09-24-zapote-standalone-pcb-release.md` (coil-intake worktree) |
| Low end | Hold from about room temperature (owner: "50–60 °F, can't chill") upward; the Control Freak itself covers 86–482 °F | Owner; Breville manual |
| Design line range for calculations | 108–140 V RMS (covers US −10% and Mexico 127 V +10%) | Assumption; confirm |

## Options

- **A — unfiltered-bus half bridge (conventional 120 V induction).** EMI
  filter → bridge rectifier → a few µF of film bus capacitance → half-bridge
  series-resonant inverter → coil. The bus follows |v_line|; the resonant load
  draws near-sinusoidal line current, so no PFC stage.
- **B — current source of truth.** Rev38 fused inlet, inrush relay/NTC,
  UCC28180 boost PFC, F2, 4 × 560 µF / 450 V bank at ~390–409 V, then a
  half bridge.

## Comparison

All inverter figures are the same first-harmonic, at-resonance method as
`zapote/inverter/evidence/plant_screen.rs`, averaged over the line cycle for
option A (`P_max = V_pk² / (π² R_total)`). They are capability screens, not
operating points.

| Criterion | A: unfiltered bus | B: PFC + 400 V bank |
| --- | --- | --- |
| Line current at 1,800 W input | 15.8 A at 120 V, 14.9 A at 127 V (PF 0.95, the conservative end of the 0.95–0.995 published for this topology — see `docs/hardware/BUS_CAPACITANCE_DERIVATION.md` §7) | 15.2 A at 120 V, 14.3 A at 127 V (PF 0.99) |
| Net effect on deliverable power at a fixed current | Baseline | ~2–5 % more power at the same current |
| Stored bus energy | ~0.1 J (5 µF at 198 V peak, 140 V line) | 179 J at 400 V; bleeders ≈ 1,008 s time constant |
| Highest DC working voltage | ~200 V peak | ~409 V (drives the provisional 16 mm reinforced creepage screen and the 104 DWW findings) |
| Extra power-entry blocks | EMI filter, fuse, MOV, bridge, film cap | + inrush relay/NTC, PFC stage, boost choke, F2 bank fuse and studs, bank discharge, bank-fault containment, AUX chain for PFC |
| Rev38 power-entry section size | Not needed | 296 references / 102 BOM lines, before any inverter |
| Reference coil (Infineon kit, ≈60 µH / 3.25 Ω loaded) | **Insufficient:** 898 W at 120 V, 727 W at 108 V even at resonance | Sufficient: ~1.7 kW modeled at 390 V, 47 kHz |
| Coil needed | Lower-impedance 120 V-class coil: R_total ≤ ~1.3 Ω gives 2,245 W at 120 V and 1,818 W at 108 V | Existing reference coil |
| Tank current at 1,800 W | ~37 A RMS line-cycle average, ~53 A RMS at line crest, ~74 A peak (R_total 1.3 Ω) | ~24 A RMS |
| Switch class | 600/650 V, 40–60 A IGBT (commodity 120 V cooktop class) | 1,200 V (IKW40N120H3 historical) |
| Restart/stop hazard | Removing gate drive stops power; bus holds no significant energy | Bank energy, F2 containment, inrush and restart sequencing, which drove the HOT receiver MCU and session protocol |
| Low-power holding | Line-synchronous burst (pulse-density) control; see below | Same need for burst control below minimum continuous power; each burst starts from a 400 V stiff bus |

## Low-temperature holding (the owner's 50–60 °F requirement)

Holding a pan at or just above room temperature needs an average power of
nearly zero. Neither architecture runs continuously at tens of watts: a
series-resonant half bridge has a minimum continuous power set by
switching loss and loss of soft switching. Both therefore need
**pulse-density (burst) control**, with the probe/under-glass loop setting
the density.

Option A has a structural advantage here. Bursts can start and stop at line
zero crossings, where its bus is near 0 V. Starts are soft, and the
resolution is one 8.33 ms half-cycle. For example, with 400 W bursts in a 1 s window, the
resolution is ~3.3 W average. Pan and food thermal time constants (seconds for a thin empty pan, minutes for a pot of liquid) filter this. The
Control Freak's precision comes from sensing and control, not from a
regulated bus. Architecture B gains nothing here.

**Check still owed:** temperature ripple on the thinnest intended pan at
the lowest setpoint, and 1 Hz-class load stepping on a shared kitchen
circuit.

## What each option reuses

- **A reuses** the frozen standalone boards on the coil-intake branch —
  RTD (probe), current sense, thermal, interlock and isolated UCC21550 gate
  drive — which are exactly the conventional architecture's protection and
  sensing blocks. Hardware over-current/over-temperature/interlock latch the
  gate driver's disable input independent of firmware. The existing
  ESP32-S3 firmware state machine carries over. The voltage-sense unit
  would be rescaled from 390 V to a ~200 V rectified bus and doubles as
  zero-crossing sync.
- **A parks:** Rev38 PFC, bank, F2 studs, bank discharge, inrush relay, the
  HOT receiver MCU/session protocol and most of the AUX supply chain. Keep
  the branch and records; do not delete.
- **New work in A:** fused EMI inlet and bridge, SELV auxiliary supply,
  half-bridge power stage and tank for a 120 V-class coil, burst control in
  firmware.

## Risks of A and the decisive evidence

1. **Coil.** No physical coil exists for either option. A needs a coil with
   roughly half the reference coil's reflected resistance, meaning fewer
   turns. **Decisive experiment:** obtain one commodity 120 V / 1,800 W
   cooktop coil and measure L and R with no pan and with the reference pans
   at 20–50 kHz. This fixes tank current, IGBT class and heatsink size. It
   is the same measurement the inverter U3 gate already requires.
2. **Current and heat.** About 1.5× the tank current of B means more
   conduction loss in switches and coil. This is normal for the product
   class; size it from the coil measurement.
3. **Zero-crossing soft switching.** Near line zero the bus voltage is low,
   so soft switching is partly lost. Handle it with the burst timing and
   check the switching waveforms.
4. **EMI.** The filter is still required: FCC Part 18 for the induction RF
   plus Part 15B for the digital logic.

## Regulatory notes (confirm with the certification lab)

- As far as this brief found, neither market mandates harmonic-current
  limits (the IEC/EN 61000-3-2 limits that motivate PFC in the EU). Mexico
  needs lab confirmation.
- The repo records UL 858 / IEC 60335-2-6 as the safety basis
  (`docs/REGULATORY_COMPLIANCE.md`). Portable countertop units are commonly
  listed under UL 1026; confirm which applies. Mexico: NOM safety
  certification (NOM-003-SCFI) via an accredited lab.
- A user-touchable probe must stay on SELV (or reinforced-insulated) in
  either option, so the ESP32-S3/SELV control domain and isolated gate drive
  stay as they are.

## Recommendation

Adopt **A**. At a fixed wall current, the PFC buys only ~2–5 % more power.
It costs ~1,800× the stored energy, twice the working voltage, and a
296-part power-entry section whose protocol exists mainly to manage that
bank. The one thing B genuinely has is compatibility with the Infineon
reference coil, and that coil was never a selected part.

Next steps if accepted:

1. Measure a 120 V-class coil with the reference pans.
2. Run the first-harmonic plant screen on the measured coil across 108–140 V.
3. Write the product source with this front end, reusing the five
   standalone units.
4. Define the burst-control and sensing requirements for ambient-to-482 °F
   holding.

## Sources

- Breville, *the Control Freak Home* instruction book (BMC800 US): supply requirement and 86–482 °F setpoints — https://assets.breville.com/BMC800/BMC800_US_IB_H23_LR.pdf
- `docs/hardware/BUS_CAPACITANCE_DERIVATION.md` §3, §7 (doubler ripple-current failure; low-filter high-PF precedent)
- `zapote/inverter/U2-ARCHITECTURE.md`, `zapote/inverter/evidence/provisional-coil-pan-model.md` (coil-intake worktree): reference coil, pan scenarios, plant-screen method
- `zapote/power-entry/passive-reva/protection/interface-integration-38/` (power-entry worktree): Rev38 part count, bank, creepage findings
- ST AN4713, *Induction cooking: IGBTs in resonant converters* — https://www.st.com/resource/en/application_note/an4713-induction-cooking--igbts-in-resonant-converters-stmicroelectronics.pdf
- Nuvoton half-bridge induction cooker application — https://www.nuvoton.com/applications/consumer/half-bridge-induction-cooker/
