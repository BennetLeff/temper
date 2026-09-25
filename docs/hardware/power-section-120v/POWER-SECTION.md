---
title: 120 V power section — schematic and justified BOM (full bridge)
date: 2026-09-25
status: source compiled and audited (zapote/power-stage-120v); native board, parts confirmation and physical tests open
decision: docs/adr/2026-09-25-front-end-architecture-brief.md
calculations: power_section.rs (loss comparison), coil_mc.rs (coil/pan robustness)
source: zapote/power-stage-120v/elec/src/power_stage_120v.ato (build-receipt.json pins hashes)
---

# 120 V power section: schematic and justified BOM

Targets: 120 V (US) and 127 V (Mexico), 60 Hz, 15 A input limit, holding from room
temperature upward. Revision history:
- An earlier half-bridge draft was replaced after COIL-MC.md showed it reached full power on only
  ~69–73 % of intended cookware.
- Four safety changes from the pre-schematic review are included:
  - DC-bus shoot-through OCP
  - thermal cutoffs in the gate supply
  - 650 V MOSFETs
  - hardware-visible phase and four gate signals

## 1. Topology choices

| Decision | Chosen | Why, and what was rejected |
| --- | --- | --- |
| Front end | Bridge rectifier + 5 µF film bus, no PFC | See the ADR. PFC gives ~2–5 % more power at the same current for 179 J stored energy and ~300 parts. |
| Inverter | **Full bridge**, series resonant capacitor | Twice the drive voltage lets the coil have 4× impedance at half the current. Robust across cast iron to clad pans (COIL-MC.md: ~100 % of intended cookware at 114 V and 127 V vs ≤ 73 % for any half bridge). Same switch count and loss as the paralleled half bridge (LOSS-REFACTOR.md, B1 = A6). Cost: one more gate driver. |
| Switch | 4 × Infineon **IPW65R018CFD7** (650 V, 18 mΩ, fast body diode) | ZVS resonant use. 650 V instead of 600 V for surge margin against the MOV's 455 V clamp. Paralleled superjunction beats single SiC here; IGBT tail loss is avoided. Must never run capacitive (body-diode hard recovery): the controller needs a phase inhibit. |
| Gate drive | 2 × UCC21550B, per-leg bootstrap, fail-safe DIS | Circuit reused from the repo's verified gate-drive unit, moved onto the power board so the gate loops stay short. |
| Bus current | 1 mΩ Kelvin shunt in the leg return + TLV3201 + ISO7710F | Shoot-through never passes the tank CT. The ~91 A trip reaches the SELV latch through a default-low isolator. |
| Thermal backstop | Heatsink and under-glass Microtemp cutoffs in series with the gate-supply input | A non-electronic stop that removes all gate drive, so firmware is not relied on for over-temperature (IEC 60335-1 cl. 19 / Annex R burden). |
| Supplies | IRM-20-15 (SELV) + IRM-05-15 (gate/HOT 5 V) | Certified modules (IEC/UL 62368-1, IEC 61558, 4.2 kVac I/O). HOT loads stay off the SELV supply. |

## 2. Operating envelope (nominal 70 µH coil, 120 V, 15 A input = 1,710 W)

| Quantity | Value | Source |
| --- | --- | --- |
| Tank current | ~18.7 A rms (line-average), ~37 A peak | power_section.rs B1 |
| MOSFET loss (4 devices) | ~25 W | power_section.rs B1 |
| Bridge rectifier loss | ~29 W (diodes) | power_section.rs |
| Coil loss | ~83 W at a 5 % coil-loss target; ~170 W at the kit-derived 10.5 % | LOSS-REFACTOR.md |
| Efficiency | ~90–92 % at the 5 % coil target | LOSS-REFACTOR.md |
| Operating frequency | ~33–39 kHz full power (p05–p95 over pans) | coil_mc.rs |
| Lowest continuous power at 60 kHz | ~150 W median; phase-shift control and line-synchronous bursts go lower | coil_mc.rs |
| Stored bus energy | 0.1 J | ADR |

## 3. Schematic

The authoritative schematic is the Atopile source. The native KiCad schematic will be
generated from it. This is the readable map.

```text
L ─J1.1─ F1 20A ─┬─ RV1 TMOV 175V ─┐                     BR1 GBJ2510
N ─J1.2──────────┼─────────────────┤  L1 CMC 20A      ┌─────────┐ +  BUS_P ──┬─────────┬──────────────┬───────────┐
PE─J1.3─┐        ├─ CX1 1µF X2 ────┤ ═══════════ ─┬───┤ ~     ~ ├──────────┐ │ C5,C6   │ R3+R4        │           │
        │        └─ R1+R2 240k ────┘ ═══════════ ─┼───┤         │ −  HV_RET│ │ 2×2.5µF │ bleed        │           │
        │                        CX2 1µF X2 ──────┤   └─────────┘          │ │ 942C    │              │           │
        └──── CY1, CY2 2.2nF Y1 (L,N → PE)                                 │ └────┬────┘              │           │
                                                                           └──────┴── R5 1mΩ shunt ── LEG_RET     │
                                                                                     (pads 1/2 leg side,          │
                                                                                      3/4 bus side; S2 Kelvin     │
                                                                                      → OCP_KELVIN_N)             │
   LEG A (U1 UCC21550)                                 LEG B (U2 UCC21550)                                        │
   Q2 high: D=BUS_P  S=SW_A                            Q5 high: D=BUS_P  S=SW_B ◄──────────────────────────────────┘
   Q3 low : D=SW_A   S=LEG_RET                         Q6 low : D=SW_B   S=LEG_RET
   3.9Ω gate R, 10k G-S, 1nF/1kV D-S snubbers, UF4007 bootstrap, 10µF+100n per rail, 39k dead time

   Tank:  SW_A ── J2 (coil 70 µH nom.) ── T1 CST3015 primary ── RES_A ── C21∥C22∥C23 (0.22+0.22+0.10 µF 942C12) ── SW_B
          T1 secondary ── J4.13/14 → current-sense board (burden, tank OCP, phase comparator)

   Gate supply: L_FILT ── J3 (loop through heatsink + under-glass Microtemp TCOs) ── PS2 IRM-05-15 ── V15_LS / LEG_RET
                V15_LS ── U3 78L05 ── HOT5 (U4, U6, U7 side 1)
   SELV supply: L_FILT/N_FILT ── PS1 IRM-20-15 ── V15_SELV / SELV_GND ── J4.1/2

   Bus sense:   BUS_P ── 4×470k ── VSENSE_IN ── 15.8k 0.1 % ── LEG_RET ;  U4 AMC1311 → VBUS_P/N (J4.11/12)
   Shoot-through OCP (all ref. LEG_RET):
                REF25 (U5 LM4040, 6.8k bias) ─10k─ OCP_NODE ─10k─ OCP_KELVIN_N ;  100 pF node filter
                REF25 ─10.5k─ OCP_THRESH ─9.76k─ LEG_RET    (0.1 % thin film; trip ≈ 91 A)
                U6 TLV3201: + = OCP_NODE, − = OCP_THRESH → OCP_OK_HOT → U7 ISO7710F → BUS_OCP_OK (J4.10)
 - - - - - - - - - - - - - reinforced barrier: U1/U2 (primary side), U4, U7, T1, PS1 - - - - - - - - - - - - - - - -
   J4 Micro-Fit 2×8: V15_SELV, SELV_GND×4, V3V3 in, PWM_HA/LA/HB/LB, PERMIT, BUS_OCP_OK, VBUS_P/N, CT_S1/S2
```

## 4. Low-power holding (room temperature and up)

The full bridge gives two low-power mechanisms:
- **Phase-shift control** between the legs, at fixed frequency, for smooth continuous power
  below the ~150 W frequency-control floor. The lagging leg loses ZVS at deep phase shift, so bench-check it.
- **Line-synchronous bursts** of whole 8.33 ms half-cycles, starting and stopping at bus zero
  crossings (from VBUS). At 1 s windows this gives ~1–2 W average resolution.

The probe (RTD board) and under-glass sensor close the temperature loop.

## 5. BOM with justification (from `zapote/power-stage-120v/build/default.csv`)

Status: **V** = the rating that decides the choice was checked against the datasheet;
**C** = identity chosen, a rating or order code still to confirm; **F** = footprint to draw or vendor.

| Ref | Qty | MPN | Why | Status |
| --- | ---: | --- | --- | --- |
| Q2,Q3,Q5,Q6 | 4 | IPW65R018CFD7 | 650 V vs ~200 V bus + 455 V surge clamp; 18 mΩ max at 25 °C; fast body diode for ZVS | V |
| U1,U2 | 2 | UCC21550BDWKR | Reinforced 5 kVrms dual driver, 4 A/6 A, UVLO outputs low; repo-verified DWK pin map | V |
| D1,D2 | 2 | UF4007-E3/54 | Bootstrap, 1000 V, same as gate-drive unit | V |
| R10,R12,R18,R20 | 4 | RC1206FR-073R9L | Gate series 3.9 Ω (bench-tune) | V |
| Q1,Q4 / R6,R14 / R7,R15 / R8,R16 | 2 each | AO3400A / 1k / 100k / 10k | Fail-safe DIS: PERMIT low, floating or unpowered = disabled | V |
| R9,R17 | 2 | RC0603FR-0739KL | Dead time ≈ 8.6 × 39 + 13 ≈ 348 ns (nominal) | V |
| R11,R13,R19,R21 | 4 | RC0603FR-0710KL | Gate-source hold-off | V |
| C12,C13,C19,C20 | 4 | GRM31A5C3A102JW01D | 1 nF 1 kV C0G drain-source snubbers | C |
| C21,C22 / C23 | 2 / 1 | 942C12P22K-F / 942C12P1K-F | 0.54 µF series resonant bank for 70 µH / 32 kHz; 10.3 + 10.3 + 9.2 A vs ~18.7 A | V (current); C (AC V vs f); F |
| T1 | 1 | CST3015-100ED | 1:100, 88 A, 5 kVrms reinforced; ~37 A peak tank | V |
| C5,C6 | 2 | 942C6W2P5K-F | 5 µF film bus, 2 × 19.5 A rms rating vs ~23 A | V; F |
| R3,R4 | 2 | RC1206FR-07220KL | Bus bleed, τ ≈ 2.2 s | V |
| R5 | 1 | WSK2512R0010FEA | 1 mΩ 4-terminal shunt, ~0.35 W | C (power at temperature) |
| U6 / U5 / R27 | 1 each | TLV3201AIDBVR / LM4040A25IDBZR / 6.8k | 40 ns comparator; 2.5 V reference, 368 µA bias | V |
| R28,R29 / R30 / R31 | 2 / 1 / 1 | RT0603BRD0710KL / 10K5 / 9K76 (0.1 %) | Offset and threshold network, trip ≈ 91 A (normal bus peak ~37–42 A) | V |
| C30 / C31 | 1 / 1 | 100 pF / 1 nF C0G | ~0.5 µs node filter; threshold decoupling | V |
| U7 | 1 | ISO7710FDWR | Reinforced 5 kVrms; **F = output low if side 1 unpowered** | V |
| U4 / R22–R25 / R26 / C27 | 1 / 4 / 1 / 1 | AMC1311BDWVR / 470k 1206 / 15.8k 0.1 % / 1 nF | Bus sense 1/120 (198 V → 1.65 V of 2 V range); ≤ 50 V per 1206 | V |
| BR1 | 1 | GBJ2510-F | 25 A 1000 V bridge, ~29 W on heatsink | V; F (on power-entry branch) |
| F1 | 1 | 0326020.MXP + Littelfuse 102071 clips | 20 A slow-blow ceramic; 15 A ÷ 0.75 | V (fuse); C (clip rating) |
| RV1 | 1 | TMOV20RP175E | 175 Vrms thermally protected MOV, 455 V clamp | C; F |
| L1 | 1 | B82726S2203A020 | 20 A, 1.6 mH, ~4.5 mΩ (~2 W) | C (pin numbering); F |
| C1,C2 / R1,R2 | 2 / 2 | R463R410000M1M / 120k 1206 | 1 µF X2 310 VAC; bleed to 24.7 V after 1 s (limit 34 V) | V |
| C3,C4 | 2 | DE1E3RA222MA4BP01F | 2.2 nF Y1; ~0.2 mA leakage at 127 V | V |
| PS1 | 1 | IRM-20-15 | SELV 15 V 1.4 A, 4.2 kVac, pin 1 = AC/L | V |
| PS2 | 1 | IRM-05-15 | Gate/HOT 15 V, **pin 1 = AC/N** (differs from IRM-20) | V |
| U3 | 1 | MC78L05ACHT1G | HOT 5 V from 15 V | V |
| J1 / J2 | 1 / 1 | Phoenix 1711039 / 1711026 | 24 A 400 V screw terminals: mains / coil | V / C (order code) |
| J3 | 1 | B2P-VH(LF)(SN) | TCO loop, 250 V 10 A | V |
| J4 | 1 | Molex 0430451612 | SELV 2×8 header | C (order code) |
| C7,C8,…(12) / C9,C10,…(6) | 12 / 6 | C0603C104K5RACTU / GRM32ER71H106KA12L | Bypass and bootstrap | V |

Off-board, in the J3 loop: two Microtemp G4A thermal cutoffs, one at the heatsink (~120 °C)
and one under the glass (rating after thermal measurement; up to 257 °C available).

## 6. Verification so far

- Atopile 0.2.69 build: 91 components, 67 nets, no errors.
- Rust audit (`zapote/power-stage-120v/audit.rs`): PASS; 17/17 tests, 16 deliberate miswires caught.
  It covers part identity against the resolved export (Atopile's netlist part field is aliased), the
  HOT/SELV barrier pin sides, shunt orientation, fail-safe DIS, the TCO-gated supply, OCP polarity,
  the tank path and the header map.
- Hashes: `zapote/power-stage-120v/build-receipt.json`.

This is connectivity evidence only. Voltage, timing, creepage, thermal and EMI are not verified.

## 7. Open items, in decision order

1. Coil and pan measurement (COIL-MC.md): sets the resonant bank, CT burden and frequency limits.
2. Confirm the "C" items above against manufacturer drawings; draw or vendor the "F" footprints.
3. Glass-underside temperature at the maximum setpoint, to choose the under-glass cutoff rating.
4. Controller-side hardware: interlock latch on BUS_OCP_OK, CT phase inhibit, SELV–PE bond.
5. Native schematic and PCB with creepage rules (≈200 V bus, ≈430 V-peak tank nodes), then
   ERC/DRC/parity.
6. Bench: dead time, gate resistors, snubbers, OCP trip, ZVS at light load and deep phase shift,
   conducted EMI pre-scan (FCC Part 18 / 15B).
7. Certification basis: UL 858 vs UL 1026, NOM-003-SCFI.

## Sources

- Infineon IPW65R018CFD7: https://www.infineon.com/cms/en/product/power/mosfet/n-channel/500v-950v/ipw65r018cfd7/
- CDE 942C: https://www.cde.com/resources/catalogs/942C.pdf
- Coilcraft CST3015: https://www.coilcraft.com/getmedia/df31d5fe-b3af-4586-82a7-7b773ac9f838/cst3015.pdf
- TI ISO7710: https://www.ti.com/lit/ds/symlink/iso7710.pdf
- TI AMC1311: https://www.ti.com/lit/gpn/AMC1311
- MEAN WELL IRM-20 / IRM-05: https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF , https://www.meanwell.com/Upload/PDF/IRM-05/IRM-05-SPEC.PDF
- Littelfuse 326 series 0326020: https://www.littelfuse.com/products/fuses-overcurrent-protection/fuses/cartridge-fuses/3ab-3ag-6-3x32mm-fuses-cartridge-fuses/326/0326020
- Littelfuse TMOV: https://www.littelfuse.com/assetdocs/varistors-tmov-datasheet?assetguid=bd475732-1071-4352-b8aa-f78b0007eb05
- TDK B82726S2203A020 (DigiKey): https://www.digikey.com/product-detail/en/tdk-electronics-inc/B82726S2203A020/495-5741-ND/3502593
- Phoenix MKDS 3/3 1711039: https://www.phoenixcontact.com/en-us/products/printed-circuit-board-terminal-mkds-3-3-1711039
- Vishay WSK2512: https://www.vishay.com/docs/30108/wsk2512.pdf
