---
title: 120 V power section — schematic and justified BOM (full bridge)
date: 2026-09-25
status: approved source revision in progress; refreshed native shelf and physical qualification open
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
| Front end | Bridge rectifier + 5.8 µF nominal film bus, no PFC | C5/C6 supply 5.4 µF; four local capacitors supply 0.4 µF. The ADR's PFC comparison used the earlier 5.0 µF bus and is historical. The [capacitor screen](../../../zapote/power-stage-120v/BUS-CAP-SCREEN.md) does not calculate power factor. |
| Inverter | **Full bridge**, series resonant capacitor | Twice the drive voltage lets the coil have 4× impedance at half the current. Robust across cast iron to clad pans (COIL-MC.md: ~100 % of intended cookware at 114 V and 127 V vs ≤ 73 % for any half bridge). Same switch count and loss as the paralleled half bridge (LOSS-REFACTOR.md, B1 = A6). Cost: one more gate driver. |
| Switch | 4 × Infineon **IPW65R018CFD7** (650 V, 18 mΩ, fast body diode) | ZVS resonant use. The MOV's quoted 455 V pulse clamp does not bound returned tank energy or voltage at the MOSFETs; D3 and physical overshoot tests carry the open 650 V margin check. Paralleled superjunction beats single SiC here; IGBT tail loss is avoided. The controller needs a phase inhibit to avoid capacitive operation and body-diode hard recovery. |
| Gate drive | 2 × UCC21550B, per-leg bootstrap, fail-safe DIS | Circuit reused from the repo's verified gate-drive unit, moved onto the power board so the gate loops stay short. |
| Bus current and voltage | 1 mΩ Kelvin shunt in the leg return + TLV3201; bus OVP TLV3201; NAND; ISO7710 | Shoot-through never passes the tank CT. The ~61 A trip and the ~280 V bus OVP reach the SELV latch on one default-high isolated fault line. |
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
| Stored bus energy at 140 V RMS line crest | 0.114 J in nominal 5.8 µF bank | BUS-CAP-SCREEN.md; excludes returned tank energy |

## 3. Schematic

The authoritative schematic is the Atopile source. The native KiCad schematic
is regenerated from it. This is the readable connection map; external coil,
PE wire and removable link jumpers are assembly connections, not PCB net joins.

```text
J1.1 L → F1 → L1 winding 1–4 → L_FILT ─┐
J1.2 N ─────→ L1 winding 2–3 → N_FILT ─┼→ BR1 GBJ2510
 C1/R1+R2, RV1 before L1; C2 after L1 ┘
 C3 L_FILT→PE; C4 N_FILT→PE (Y1, 10 mm pitch, 8.5 mm nominal pad gap)
 Cord PE → chassis/heatsink stud → separate branch wire → J6 PE → C3/C4, R38
 R38 0 Ω: PE → controller SELV_GND (functional bond only)

BR1+ → RECT_P → J7 ── external removable jumper ── J8 → BUS_P
BR1− → RECT_N → J9 ── external removable jumper ── J10 → HV_RET
 BUS_P↔HV_RET: C5/C6 (2 × 2.7 µF TDK, four pins each),
                C38–C41 (4 × 0.1 µF TDK, two per bridge leg),
                D3 MRT130KP295CV TVS, R3+R4 bus bleed
 HV_RET → R5 1 mΩ Kelvin shunt → LEG_RET
 (R5 pad 1 power LEG_RET, pad 2 sense LEG_RET, pad 3 OCP_KELVIN_N,
  pad 4 power HV_RET; keep Kelvin copper out of the power path)

LEG A: Q2 high drain BUS_P, source SW_A; Q3 low drain SW_A, source LEG_RET
LEG B: Q5 high drain BUS_P, source SW_B; Q6 low drain SW_B, source LEG_RET
Each local bus capacitor returns to HV_RET; returning to LEG_RET would
bypass R5 during shoot-through. Gate loops use U1/U2, 3.9 Ω gate resistors,
10 kΩ gate-source returns, 1 nF/1 kV snubbers and UF4007 bootstraps.

Tank: SW_A → T1 CST3015 primary → COIL_FEED → J2 M4 stud
      → external coil → J5 M4 stud → RES_A → C21∥C22∥C23 (CDE 942C, 0.54 µF) → SW_B
      R22–R25: 4 × 470 kΩ bleed across RES_A and SW_B (τ ≈ 1 s)
      T1 secondary → J4.13/14 → current-sense board

Gate auxiliary: L_FILT → J3 thermal cutoff loop → PS2 IRM-05-15
                → V15_LS/LEG_RET → U3 78L05 → HOT5
Controller supply: L_FILT/N_FILT → PS1 IRM-20-15 → V15_SELV/SELV_GND
Bus sense: BUS_P → R26–R29 (4 × 470 kΩ) → VSENSE_IN → R30 15.8 kΩ → LEG_RET
           U4 AMC1311 isolated output → J4.11/12 VBUS_P/N
Fault: U5 LM4040 REF25 (5.6 kΩ bias); U6 OCP ≈ 61 A;
       U7 OVP ≈ 280 V; U8 LVC1G00 NAND → U9 ISO7710DWR → J4.10 BUS_FAULT
HOT/controller barrier: U1/U2, U4, U9, T1, PS1; D5 placement floor ≥8.0 mm.
J4: V15_SELV, SELV_GND×4, V3V3 in, four PWMs, PERMIT, BUS_FAULT,
    VBUS_P/N and CT_S1/S2.
```

## 4. Low-power holding (room temperature and up)

The full bridge gives two low-power mechanisms:
- **Phase-shift control** between the legs, at fixed frequency, for smooth continuous power
  below the ~150 W frequency-control floor. The lagging leg loses ZVS at deep phase shift, so bench-check it.
- **Line-synchronous bursts** of whole 8.33 ms half-cycles, starting and stopping at bus zero
  crossings (from VBUS). At 1 s windows this gives ~1–2 W average resolution.

The probe (RTD board) and under-glass sensor close the temperature loop.

## 5. BOM with justification (to reconcile with `zapote/power-stage-120v/frozen/default.csv` after re-freeze)

Status: **V** = the rating that decides the choice was checked against the datasheet;
**C** = identity chosen, a rating or order code still to confirm; **F** = footprint to draw or vendor.

| Ref | Qty | MPN | Why | Status |
| --- | ---: | --- | --- | --- |
| Q2,Q3,Q5,Q6 | 4 | IPW65R018CFD7 | 650 V rating; transient and trip-return margin remains unqualified (ORACLE-REVIEW.md withdraws the earlier bus bound); 18 mΩ max at 25 °C; fast body diode for ZVS | V (rating); C (circuit stress) |
| U1,U2 | 2 | UCC21550BDWKR | Reinforced 5 kVrms dual driver, 4 A/6 A, UVLO outputs low; repo-verified DWK pin map | V |
| D1,D2 | 2 | UF4007-E3/54 | Bootstrap, 1000 V, same as gate-drive unit | V |
| R10,R12,R18,R20 | 4 | RC1206FR-073R9L | Gate series 3.9 Ω (bench-tune) | V |
| Q1,Q4 / R6,R14 / R7,R15 / R8,R16 | 2 each | AO3400A / 1k / 100k / 10k | Fail-safe DIS: PERMIT low, floating or unpowered = disabled | V |
| R9,R17 | 2 | RC0603FR-0739KL | Dead time ≈ 8.6 × 39 + 13 ≈ 348 ns (nominal) | V |
| R11,R13,R19,R21 | 4 | RC0603FR-0710KL | Gate-source hold-off | V |
| C12,C13,C19,C20 | 4 | GRM31A5C3A102JW01D | 1 nF 1 kV C0G drain-source snubbers | C |
| C21,C22 / C23 | 2 / 1 | 942C12P22K-F / 942C12P1K-F | 0.54 µF series resonant bank for 70 µH / 32 kHz; 10.3 + 10.3 + 9.2 A vs ~18.7 A | V (current); C (AC V vs f); F |
| R22–R25 | 4 | RC1206FR-07470KL | Resonant-bank bleed: an OCP trip can leave ~250 V on C_res; 1.88 MΩ, τ ≈ 1 s. Check each resistor's voltage and heating over the actual tank waveform | V (part); C (waveform stress) |
| T1 | 1 | CST3015-100ED | 1:100, 88 A, 5 kVrms reinforced; ~37 A peak tank | V |
| C5,C6 | 2 | B32656G0275J000 | 2 × 2.7 µF/1000 V four-pin TDK radial film bus, 5.4 µF nominal; confirm electrode pairing on received parts and assembly retention | V (catalog ratings); C (assembled stress) |
| C38–C41 | 4 | B32652A0104K000 | 100 nF/1000 V, two per leg, BUS_P to HV_RET through the shunt power path | V (catalog ratings); C (assembled ripple and heat) |
| D3 | 1 | MRT130KP295CV | DC-link TVS at C5/C6; actual terminal clamp and pulse energy need transient measurement | V (datasheet pulse); C (assembled surge) |
| R3,R4 | 2 | RC1206FR-07220KL | 440 kΩ bus bleed, nominal τ ≈ 2.55 s at the new 5.8 µF total | V (part); C (actual discharge) |
| R5 | 1 | WSK2512R0010FEA | 1 mΩ 4-terminal shunt, ~0.35 W | C (power at temperature) |
| U6 / U5 / R31 | 1 each | TLV3201AIDBVR / LM4040A25IDBZR / RC0603FR-075K6L (5.6k) | 40 ns comparator; 2.5 V reference, 120.8 µA cathode current at the checked DC corner (REFERENCE-BIAS.md); complete shutdown latency unqualified | V (selected ratings and DC corner) |
| R32,R33 / R34 / R35 | 2 / 1 / 1 | RT0603BRD0710KL / 10K5 / 10K (0.1 %) | Offset and threshold network, trip ≈ 61 A (TLV3201 ±5 mV → ±10 A, before other tolerances). Lowered from 91 A as risk reduction; returned tank energy remains unbounded: ORACLE-REVIEW.md | V (nominal network); C (fault response) |
| U7 / R36 / R37 / C33 | 1 each | TLV3201AIDBVR / RT0603BRD0710KL / RT0603BRD07140KL / 1 nF C0G | Bus OVP ≈ 280 V from the VSENSE_IN tap; hardware restart inhibit | V |
| U8 | 1 | SN74LVC1G00DBVR | NANDs OCP-OK and OVP-OK into U9; either fault drives BUS_FAULT high | V |
| C30 / C31 | 1 / 1 | 100 pF / 1 nF C0G | ~0.5 µs node filter; threshold decoupling | V |
| U9 | 1 | ISO7710DWR | Reinforced 5 kVrms; **non-F = output high if side 1 unpowered and side 2 powered**. TI DW0016B HV land pattern, 8.1 mm across the barrier | V |
| U4 / R26–R29 / R30 / C27 | 1 / 4 / 1 / 1 | AMC1311BDWVR / 470k 1206 / 15.8k 0.1 % / 1 nF | Bus sense 1/120 (198 V → 1.65 V of 2 V range); ≤ 50 V per 1206 | V |
| BR1 | 1 | GBJ2510-F | 25 A 1000 V bridge, ~29 W on heatsink | V; F (on power-entry branch) |
| F1 | 1 | 0326020.MXP + Littelfuse 102071 clips | 20 A slow-blow ceramic; 15 A ÷ 0.75 | V (fuse); C (clip rating) |
| RV1 | 1 | TMOV20RP175E | 175 Vrms thermally protected MOV, 455 V clamp | C; F |
| L1 | 1 | B82726S2203A020 | 20 A, 1.6 mH, ~4.5 mΩ (~2 W). Windings 1–4 and 2–3 per TDK drawing | V (pins); F |
| C1,C2 / R1,R2 | 2 / 2 | R463R410000M1M / 120k 1206 | 1 µF X2 310 VAC; bleed to 24.7 V after 1 s (limit 34 V) | V |
| C3,C4 | 2 | DE1E3RA222MA4BP01F | 2.2 nF Y1; 10 mm pitch and 1.5 mm local pads give 8.5 mm nominal copper gap; verify component and board insulation | V (part); C (assembly) |
| PS1 | 1 | IRM-20-15 | SELV 15 V 1.4 A, 4.2 kVac, pin 1 = AC/L | V |
| PS2 | 1 | IRM-05-15 | Gate/HOT 15 V, **pin 1 = AC/N** (differs from IRM-20) | V |
| U3 | 1 | MC78L05ACHT1G | HOT 5 V from 15 V | V |
| J1 | 1 | Phoenix 1711725 | Two-position, 5.08 mm L/N terminal; applicable UL use group/current still to confirm | V (identity); C (applicable current) |
| J2,J5,J7–J10 | 6 | Würth 74650074 | Separate M4 coil studs and two pairs of removable-link studs; 50 A max at 20 °C, THR reflow, PCB 1.6–2.0 mm. No individual terminal voltage rating | V (part); C (assembled current and insulation) |
| J6 | 1 | Phoenix 1704004 | One-position PCB PE branch from direct chassis bond; keep ≥8 mm from HOT | V (part); C (assembled earth path) |
| J3 | 1 | B2P-VH(LF)(SN) | TCO loop, 250 V 10 A | V |
| J4 | 1 | Molex 0430451612 | SELV 2×8 header | C (order code) |
| C7,C8,…(14) / C9,C10,…(6) | 14 / 6 | C0603C104K5RACTU / GRM32ER71H106KA12L | Bypass and bootstrap | V |

Off-board, in the J3 loop: two Microtemp G4A thermal cutoffs, one at the heatsink (~120 °C)
and one under the glass (rating after thermal measurement; up to 257 °C available).

## 6. Verification so far

- The prior 104-part source/native revision passed its audit, parity and
  connectivity checks. The approved capacitor and terminal changes form a
  newer source revision; consult its refreshed build and verification receipts
  after regeneration before quoting current counts or test results.
- The Rust audit checks part identity against the resolved export
  (Atopile's netlist part field is aliased), HOT/controller barrier sides,
  shunt orientation, the two open rectifier/bus links, the capacitor returns,
  tank path, fault polarity and connector map.

This is connectivity evidence only. Voltage, timing, creepage, thermal and EMI are not verified.

## 7. Open items, in decision order

1. Coil and pan measurement (COIL-MC.md): validates the retained resonant bank,
   CT burden and operating frequency limits.
2. Confirm the remaining "C" ratings above against the assembled waveform and
   enclosure. Four-pin radial construction does not establish retention;
   confirm the M4 THR profile and actual PCB thickness is within 1.6–2.0 mm.
3. Glass-underside temperature at the maximum setpoint, to choose the under-glass cutoff rating.
4. Controller-side hardware: BUS_FAULT now matches the existing healthy-low/fault-high interlock input. CT phase inhibit, complete shutdown timing, HOT5 brownout and supply-loss behavior remain unverified (FAULT-INTERFACE.md). D5 conditionally approves one functional PE bond and an 8.0 mm placement floor; insulation qualification is still open (D5-BASIS.md).
5. Regenerated native source projection and qualified creepage rules; the
   earlier bus/tank peak examples are not design bounds. Verify ERC/DRC/parity
   after each native revision.
6. Bench: dead time, gate resistors, snubbers, OCP trip, ZVS at light load and deep phase shift,
   conducted EMI pre-scan (FCC Part 18 / 15B).
7. Certification basis and CT insulation evidence: UL 858 vs UL 1026,
   NOM-003-SCFI, applicable IEC 60335-1 edition and IEC 60664-4 stress.
   The certification-lab call and RCA 12A3 teardown have not occurred.

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
- Phoenix 1711725: https://www.phoenixcontact.com/en-de/products/pcb-terminal-block-mkds-3-2-508-1711725
- Phoenix 1704004: https://www.phoenixcontact.com/en-us/products/printed-circuit-board-terminal-kds-3-1704004
- Würth 74650074: https://www.we-online.com/components/products/datasheet/74650074.pdf
- TDK radial bus and local capacitors: https://product.tdk.com/en/system/files/dam/doc/product/capacitor/film/mkp_mfp/data_sheet/20/20/db/fc_2009/mkp_b32651_658.pdf
- Vishay WSK2512: https://www.vishay.com/docs/30108/wsk2512.pdf
