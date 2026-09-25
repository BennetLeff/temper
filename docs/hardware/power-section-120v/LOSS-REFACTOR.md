---
title: 120 V power section — loss budget and low-loss refactor
date: 2026-09-25
status: design screen (no part ordered, no measurement)
calculation: power_section.rs → power-section-output.txt, section "Loss refactor comparison"
baseline: POWER-SECTION.md
---

# Loss budget and low-loss refactor

> **Update 2026-09-25:** the selected part is the 650 V IPW65R018CFD7 (same
> 18 mΩ class, 234 nC gate charge) for surge margin, in a full bridge
> (row B1). The 600 V figures below remain the analysis basis; the source is
> `zapote/power-stage-120v`.

All rows use the same conditions: 120 V line, 15 A input limit, PF 0.95,
1,710 W input, and the same pan-reflected resistance. Each row changes one
thing on top of the previous one. "Pan W" is what reaches the food. At a fixed
15 A input limit, every watt saved becomes cooking power instead of heat.

## Where the 267 W goes today (A0)

| Loss | W | Share | Set by |
| --- | ---: | ---: | --- |
| **Coil winding** | **169** | 63 % | R_coil / R_total = 10.5 %, derived from the Infineon kit chart |
| IGBTs (2) | 60 | 22 % | V_CE(sat) knee (~0.8 V) × ~36 A tank current, plus turn-off tail |
| Bridge rectifier | 29 | 11 % | Two diode drops × 15 A |
| EMI, capacitor ESR, wiring, aux | ~10 | 4 % | Allowance pending part selection |
| **Total** | **267** | 84.4 % efficient | |

The coil is the dominant term. No switch or rectifier change can recover
more than about 45 W, but the coil alone holds about 170 W.

## Options, measured on one basis

| Config | Change | Rect. W | Switch W | Coil W | Total W | Pan W | Eff. |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A0 | Baseline: 2 × IHW40N65R5, diode bridge, coil 10.5 % | 29.3 | 59.6 | 169 | 267 | 1,443 | 84.4 % |
| A1 | 1 × IPW60R018CFD7 per position | 29.3 | 46.2 | 170 | 255 | 1,455 | 85.1 % |
| A2 | 1 × C3M0015065K (SiC) per position | 29.3 | 40.0 | 171 | 250 | 1,460 | 85.4 % |
| A3 | 2 × CFD7 per position | 29.3 | 23.8 | 172 | 235 | 1,475 | 86.2 % |
| A4 | A3 + low-side synchronous rectifier | 22.5 | 23.9 | 173 | 229 | 1,481 | 86.6 % |
| A5 | A4 + coil 7 % | 22.5 | 24.8 | 116 | 173 | 1,537 | 89.9 % |
| **A6** | **A4 + coil 5 %** | 22.5 | 25.4 | 83 | **140** | **1,570** | **91.8 %** |
| A7 | A6 + full synchronous rectifier | 15.8 | 25.5 | 83 | 134 | 1,576 | 92.2 % |
| B1 | Full bridge, 4 × CFD7, coil 5 % | 22.5 | 25.4 | 83 | 140 | 1,570 | 91.8 % |
| B2 | Full bridge, 4 × IGBT, coil 10.5 % | 29.3 | 46.7 | 170 | 256 | 1,454 | 85.0 % |
| C1 | Coil 5 % only, IGBTs kept | 29.3 | 62.9 | 80 | 182 | 1,528 | 89.3 % |

What the comparison shows:

1. **Coil quality is worth about 3× everything else combined.** C1 (coil only) saves
   85 W. A4 (all semiconductor changes, coil unchanged) saves 38 W.
2. **Paralleling beats exotic silicon.** In a half bridge the full tank
   current always flows through one switch position, so conduction is
   I² × R_on. Two CFD7s in parallel (23.8 W) beat one SiC device (40.0 W). SiC's
   hot-resistance advantage is real, but its 4.7 V body-diode drop during dead
   time and its preference for a −4 V gate hold it back here.
3. **A full bridge doesn't reduce MOSFET loss for the same silicon.** B1
   equals A6: half the current through twice the devices in series. It helps
   the IGBT case only through lower turn-off current (B2), and it halves
   current in the capacitors, current transformer and wiring. That's a
   construction benefit, not an efficiency one.
4. **Synchronous rectification is the smallest lever:** 7–14 W.

## The refactor, in priority order

1. **Specify and buy the coil for loss, not only inductance** (saves about 85 W). Target
   R_coil / R_total ≤ 5 % with the reference pan at the operating frequency, meaning
   winding AC resistance ≤ ~59 mΩ against ~1.12 Ω reflected. Levers:
   - fine-strand litz, with strand diameter well below the 0.34 mm copper skin depth at 38 kHz
     (for example 0.1 mm), because proximity loss dominates
   - more copper in the same window
   - ferrite bars under the winding for coupling
   - the thinnest practical glass and air gap
   - a winding diameter matched to the target pans

   This is a **measurement gate**, not a claim: the 5 % figure is a target,
   and the current 10.5 % comes from one evaluation-kit chart.
2. **Replace the IGBTs with 2 × IPW60R018CFD7 per position** (saves about 36 W). Reasons:
   - The CFD7 fast body diode is built for ZVS/resonant bridges
     (Q_rr 1.56 µC typ, trr 223 ns typ).
   - It is fully on at the existing gate board's 0/15 V drive, so the UCC21550 board stays.
   - Gate power rises to about 0.6 W at 40 kHz, still well within the gate supply.

   Cost: four TO-247 devices instead of two, a higher per-device price (check
   distributor pricing), and a hard requirement to stay inductive. Driving an
   SJ MOSFET body diode into hard recovery (capacitive mode, below resonance,
   or during pan removal) is the classic failure. Phase detection from the
   current-sense signal must inhibit switching before operation crosses to
   capacitive.
3. **Raise the operating frequency once the switches are MOSFETs.** Reflected pan
   resistance rises roughly with √f (skin effect in the pan), while
   well-designed litz resistance rises much more slowly. Moving from ~38 to ~60 kHz
   would cut the coil fraction by roughly a fifth. With IGBTs this is
   penalized by turn-off tail loss; with ZVS MOSFETs it costs little. This
   is a **first-order assumption to confirm in the coil measurement**
   (measure R_pan and R_coil across 20–60 kHz, as §7 of POWER-SECTION.md
   already requires).
4. **Low-side synchronous rectification** (saves about 7 W), using NXP TEA2206T with two
   600 V MOSFETs. It also provides X-capacitor discharge, so RB1a/b can be removed.
   NXP intends the part for supplies with a boost-PFC first stage.
   Behavior on this nearly unfiltered bus (continuous conduction to near zero
   crossing, HF ripple on the bus) needs NXP confirmation or a bench test. Full
   synchronous rectification (A7, another 7 W) needs high-side drive and isn't
   worth it yet.

## What the refactor buys beyond efficiency

- **Heatsink load:** rectifier + switches drop from 89 W to 48 W (A6), so a smaller
  heatsink and a quieter fan will do.
- **Coil heat:** 169 W → 83 W. The coil sits under the glass beside the
  through-glass temperature sensor, so less coil self-heating also means
  less sensor error and less stress on litz insulation.
- **Cooking power at the same 15 A outlet limit:** 1,443 W → 1,570 W reaching the pan
  (+9 %). At 127 V the same gain applies against the 1,800 W cap.

## Model limits

- MOSFET turn-off is assumed lossless (ZVS with snubber). Bench waveforms
  must confirm it at full power and at the 50 kHz light-load end, where the
  current at turn-off falls.
- Hot resistances are conservative combinations (max at 25 °C × typical
  temperature ratio). Typical parts will do somewhat better.
- The ~10 W fixed allowance covers the EMI choke, capacitor ESR, wiring and
  aux supplies; it was not calculated.
- The coil fraction is held constant across frequency within each row.
  Item 3 is a separate, unmodeled assumption.

## Sources

- Infineon IPW60R018CFD7 datasheet v2.0 (R_DS(on) 15/18 mΩ at 25 °C, 29 mΩ typ at 150 °C, Q_rr 1.56/3.12 µC, trr 223/446 ns, Qg 251 nC, V_SD 1.0 V): https://www.infineon.com/dgdl/Infineon-IPW60R018CFD7-DS-v02_00-EN.pdf?fileId=5546d46262b31d2e01635e133c12291d
- Wolfspeed C3M0015065K datasheet (15/21 mΩ at 25 °C, 20 mΩ typ at 175 °C, V_SD 4.2–4.7 V, V_GS op −4/15 V): https://assets.wolfspeed.com/uploads/2024/01/Wolfspeed_C3M0015065K_data_sheet.pdf
- NXP TEA2206T active bridge rectifier controller datasheet: https://www.nxp.com/docs/en/data-sheet/TEA2206T.pdf
- Infineon IHW40N65R5 datasheet Rev 2.3 (baseline): https://infineon.com/dgdl/Infineon-IHW40N65R5-DS-v02_03-EN.pdf?fileId=5546d461464245d30146adf2552300ab
