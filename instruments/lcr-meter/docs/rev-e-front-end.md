# Rev E codec front end (design, 2026-10-20)

This is the circuit between the retained TIDA-060029 analog core and a TI TAC5112 codec (pin- and register-compatible with the TAC5212). It replaces the AD9833, its RC reconstruction, the C36 coupling, both THS4551 drivers and the ADS9224R. Decisions and their basis are in [rev-e-plan.md](rev-e-plan.md). Datasheet citations are to `sources/rev-e/TAC5112.txt` and the full datasheet SLASF24A (Table 7-9 to 7-12, §6).

## Source

- **Converter.** TAC5112 OUT1P/OUT1M, differential line output: 2 Vrms full scale, 1.65 V common mode, ≥ 600 Ω single-ended load.
- **Difference stage.** The existing OPA810 (X5) becomes a difference amplifier:
  - 2.2 kΩ in, 2.0 kΩ feedback and ground leg (0.1 %);
  - 270 pF across each 2.0 kΩ, for a 295 kHz pole on the DAC's out-of-band noise.
  - Gain is 0.909. The stage rejects the 1.65 V common mode, so the source is **DC coupled**: there is no coupling capacitor and no settle wait.
  - The residual offset at SOURCE_BUF is a few mV (DAC ±0.5 mV plus resistor mismatch against the 1.65 V common mode).
- **Level.** Firmware caps the source at 1.7 V peak at SOURCE_BUF, which is a DAC peak of 1.87 V differential (−3.6 dBFS).
- **Frequency.** The DAC writes samples at fs = 187.5 kHz (12 MHz BCLK = 120 MHz/10, FSYNC = BCLK/64), sharing FSYNC with the ADC, so source and capture are coherent by construction. Wideband mode is DAC_CH1_BW_MODE = 1; the passband is 0.46·fs = 86 kHz.

## Inputs

| Codec channel | + input | − input | Measures |
|---|---|---|---|
| CH1 (IN1P/IN1M) | HIGH follower (highbuf) | LOW follower (lowbuf) | Voltage across the DUT, as Rev D channel A |
| CH2 (IN2P/IN2M) | LOW follower (lowbuf) | TIA output (tia) | I·(R_iso + Z_f), as Rev D channel B (LOW − TIA; the TIA inverts) |

Each of the four legs is identical:
1. 1.00 kΩ series from the op-amp output, 1.00 kΩ to ground (0.1 %): K = 0.5, Thevenin 500 Ω.
2. 560 pF C0G to ground: a 568 kHz anti-alias pole ahead of the modulator.
3. 1 µF X7R coupling capacitor (C28323, already on the BOM).
4. BAT54S clamp to AVDD and ground on the codec side of the coupling capacitor.
5. 470 Ω in series to the pin.

**Why the attenuation.** The followers and the TIA swing around ground, so each channel is driven unbalanced. Its common mode moves by half its signal. The TAC5112's default AC-coupled mode tolerates 100 mVpp of common-mode variation. ADC_CHx_CM_TOL = 01 tolerates 1 Vpp (Table 7-10) at "a few dB" of noise. With K = 0.5 and the 1.7 V source cap, the worst common-mode swing is 0.85 Vpp and the worst differential peak is 0.85 V, 30 % of the 2.83 V peak full scale. The TAC5112 has no analog channel gain (no PGA field in the register map, only digital volume), so small signals use the converter at 0 dB. The resulting noise is in [rev-e-codec](../validation/rev-e-codec/README.md): worst 12.9 % of a tolerance at Rev D's capture time, about 4 % with the 10× longer captures that on-device averaging allows.

**Codec settings.**
- ADC_CHx_INSRC = 00 (differential).
- ADC_CHx_CM_TOL = 01.
- ADC_CHx_IMP = 10 (40 kΩ, which wideband mode requires).
- ADC_CHx_BW_MODE = 1.
- High-pass filter set to all-pass.
- AGC, limiter and any data-dependent processing off.

**Coupling corner.** 1 µF into 40 kΩ (±20 %) is 4 Hz. At 1 kHz that is 0.23° of phase. A ±15 % X7R drift between calibration and measurement moves it by 0.035° (6×10⁻⁴ rad), inside the 2 % bus-capacitor tolerance. At 27 kHz and above it is negligible. The divider resistors are 0.1 %, and the 40 kΩ internal impedance loads the 500 Ω divider by about 1 %. Its ±20 % spread is linear and calibrated out, and the two channels share one die.

**Protection.** An op-amp output can rail at power-up, or the TIA can drift while no range relay is closed. A ±11 V step reaches the clamp node through the 1 µF as about ±5.5 V. The BAT54S limits it to AVDD + 0.4 V or −0.4 V, at about 7 mA peak decaying in 0.5 ms. The 470 Ω keeps the pin current to tens of µA, within the 0–5.6 V input rating (−0.3 V abs max; the internal diode carries the small remainder). The clamp's few-pF junction capacitance sits behind 500 Ω; its nonlinearity is −110 dB at 60 kHz (1.8 MΩ against 500 Ω).

## TIA stability capacitor

A **100 pF C0G from DUT_LO (LCUR, the jack side of R_iso) to ground** is new in Rev E. C78 sits on the LCUR run at (179.5, 102.4), between the J9 jack and R_iso.
- **Why.** The range relays put pad copper, contact-to-coil and pole-to-pole capacitance on TIA_OUT. With the stress estimates of those parasitics, the TIA's worst margin falls to 38.5°.
- **What it does.** It lowers the TIA's loop gain near crossover, as fixture capacitance already does. The worst case then becomes 56.0°, above the Rev D floor of 51.3°.
- **Effect on measurement.** DUT_LO is a virtual ground, so the capacitor's current is the TIA error current only. It is linear and removed by calibration.
- **Noise.** No change at the precision of the noise table.

Details and the rejected alternatives are in [stability-full-chain](../validation/stability-full-chain/README.md).

## Four-terminal jacks (2026-10-21)

The 2-pin DUT header is replaced by four right-angle BNCs on the top edge (SAMZO BNC-KYWE-295-W4-N, C41416668, hand fit). They are at 22 mm pitch, the usual 4TP spacing, and in the Keysight front-panel order read facing the jacks: L CUR, L POT, H POT, H CUR. Shells go to GND. The board grows 5 mm, to 140 × 105 mm, to carry them.

| Jack | Net | Connects to |
|---|---|---|
| J3 HCUR | DUT_HI | the RG resistors (source side), as the header's HI pin did |
| J7 HPOT | HPOT | U6B +IN (HIGH follower) |
| J8 LPOT | LPOT | U7B +IN (LOW follower) |
| J9 LCUR | DUT_LO | R94 (R_iso) into the TIA summing node, as the header's LO pin did |

- **What changes.** Channel A = HPOT − LPOT is now the voltage at the DUT's own terminals, so lead and contact resistance drop out of it.
- **Current channel.** Channel B = LPOT − TIA_OUT = I·(R94 + RF‖CF + R_LCUR). R_LCUR is the LCUR lead plus its contacts: tens of mΩ against 122 Ω or more of Zf + R94. It is a real gain term that calibration with the same leads absorbs; per-insertion contact variation is ≤ 1e-4 of it. The host model (Zf = R94 + RF‖CF) is unchanged.
- **Two-terminal use.** R105 and R106 (1 kΩ, basic) tie HPOT to HCUR and LPOT to LCUR on the board. Two-terminal leads therefore still read, with lead resistance included. A Kelvin lead in parallel is about 0.1 Ω, so the 1 kΩ carries a fraction of 1e-4 of the sense signal.
- **Routing.** Each run is on its own layer where the others cross: HCUR on B.Cu along the back of the jacks and down the east edge; HPOT on In2; LPOT on F.Cu then In2; LCUR on F.Cu then B.Cu into the Rev D approach to R94. Hand routed in `cad/tools/rev_e_routes.py`.
- **Reference relay K4.** A fourth TQ2SA closes HCUR onto R107 (1 kΩ 0.1 %) to LCUR for the firmware `REFCAPTURE` self-check ([range switching §3.5](rev-e-range-switching.md)).

## Supplies, clocks and control

- **AVDD (3V3A).** 3.3 V from a second AP2112K-3.3 (U15, the 3V3 line already on the BOM) fed from 5VA, Rev D's ferrite-filtered 5 V (FB1, C103). The ADS9224R and THS4551 loads are gone, so 5VA now feeds only this LDO. The relay coils take the digital 5 V instead (R101 2.2 Ω, C112 22 µF; [range-switching §3.2](rev-e-range-switching.md)), so their pulses stay off the codec supply.
- **IOVDD.** The digital 3V3 rail.
- **VREF.** 2.75 V default, decoupled per the datasheet.
- **ADDR.** Pin strap.
- **RP2040 pins** ([firmware wiring contract](../firmware-rev-e/README.md#wiring-contract)):
  - DIN GPIO2 (out), DOUT GPIO3 (in), BCLK GPIO4 and FSYNC GPIO5 on one PIO state machine (full duplex, 10 system clocks per BCLK);
  - I2C0 on GPIO8/9, with the codec at 0x50 (ADDR to ground);
  - relay drive: SET_HI (100 kΩ) GPIO6, SET_LO (100 Ω) GPIO7, shared RESET GPIO10, SET_MED (5 kΩ) GPIO11, SET_REF (K4 reference) GPIO14.

  All of these come from the pins freed by removing the ADS9224R and AD9833.

## Open items

Bench only:
- wideband response to 85 kHz;
- gain compression at 27–60 kHz;
- clock acceptance at 187.5 kHz in auto mode (read CLK_DET_STS);
- whether CM_TOL = 01 is allowed together with wideband mode (the datasheet's wideband SNR row uses the default AC-coupled setting). If it is not, use CM_TOL = 10 (rail-to-rail) with the same network.

A TAC5112/TAC5212 evaluation module settles all four with a loopback.

## Stability results

The cases are those of [range-switching §6](rev-e-range-switching.md), run on this front end. All carry the Rev D extracted board string. The full table is in [stability-full-chain](../validation/stability-full-chain/README.md).

| Configuration | Worst phase margin | Min. abs(1+T) |
|---|---:|---:|
| Codec load, jumpers (Rev D as built: 51.3°, 0.573) | 51.30° | 0.573 |
| + relays, nominal parasitics | 48.64° | 0.536 |
| + relays, stress parasitics | 38.48° (fails) | 0.422 |
| **+ relays + 100 pF at DUT_LO, stress** (grid, attribution, weld) | **55.97°** | 0.608 |
| same, source-driver loop (`drive`), stress | 48.29° | 0.563 |
| **As built, extracted Rev E layout + R104 47 Ω** (`reverelaycng100_r104`): TIA, stress | **58.07°** | 0.629 |
| same, source-driver loop (`drive`), stress relays, high board corner | **46.77°** | 0.590 |
| same, `high` / `low` followers, stress | 56.49° / 56.34° | 0.699 / 0.691 |

The codec network loads TIA_OUT exactly as the THS4551 did. The remaining weakest loop is the source driver (X6A). The relay's contact-to-coil and pole-to-pole capacitance on SOURCE_BUF take it from Rev D's 55.3° (`fixedriso`, 1000 pF fixture) to 50.9° at the same fixture and 48.3° with no fixture. That still passes 45°. **Extracted layout (2026-10-21).** Extracting the routed board ([layout-parasitics README-rev-e](../validation/layout-parasitics/README-rev-e.md)) replaced the board estimates.
- TIA_OUT carries 10.0 pF to ground nominal, less than the estimate.
- SOURCE_BUF carries 9.8 pF, which the estimate never modelled. 2.4 pF of it came from its In2 route stacked over DUT_HI.
- With that copper, the source driver fell to 38.46° at the stress relay set.
- The board now has R104 (47 Ω) between U6A and the relay bus, with feedback at the pin, and the SOURCE_BUF route moved 3.4 mm off DUT_HI (coupling 0.155 pF). The driver is back to 46.77° at stress and 49.80° nominal.
- The cost is a 147 Ω source resistance on the 100 Ω range: less drive into low impedances, no accuracy change, since HI and the current are measured directly.
- What remains of the margin depends on the relay's contact-to-coil and pole-to-pole capacitance, which are unpublished. Measure one relay before relying on the last 2°.

## Remaining risks

- The four bench items above. An EVM loopback settles them.
- **Relay parasitics.** The board copper is now extracted. The relay-internal capacitances are still estimates and set the source driver's 46.77° worst case. Measure one TQ2SA (contact-to-coil, pole-to-pole) and rerun `reverelaycng100_r104`.
- **Clamp.** BAT54S forward recovery and capacitance into a 40 kΩ input were never simulated in a transient. The 470 Ω and the AC coupling bound the effect, but the fault transient stays a hand calculation.
- **Codec input impedance spread** (±20 %). The divider and the calibration absorb it on the same die. Temperature drift between calibration and measurement is unpublished.
