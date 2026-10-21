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
| CH2 (IN2P/IN2M) | TIA output (tia) | LOW follower (lowbuf) | I·(R_iso + Z_f), as Rev D channel B |

Each of the four legs is identical:
1. 1.00 kΩ series from the op-amp output, 1.00 kΩ to ground (0.1 %): K = 0.5, Thevenin 500 Ω.
2. 560 pF C0G to ground: a 568 kHz anti-alias pole ahead of the modulator.
3. 1 µF X7R coupling capacitor (C28323, already on the BOM).
4. BAT54S clamp to AVDD and ground on the codec side of the coupling capacitor.
5. 470 Ω in series to the pin.

**Why the attenuation.** The followers and the TIA swing around ground, so each channel is driven unbalanced. Its common mode moves by half its signal. The TAC5112's default AC-coupled mode tolerates 100 mVpp of common-mode variation. ADC_CHx_CM_TOL = 01 tolerates 1 Vpp (Table 7-10) at "a few dB" of noise. With K = 0.5 and the 1.7 V source cap, the worst common-mode swing is 0.85 Vpp and the worst differential peak is 0.85 V, 30 % of the 2.83 V peak full scale. Firmware raises channel gain to 12 dB when the signal leaves room. That costs 2 dB of SNR, so the input-referred noise falls by 10 dB. The resulting noise is in [rev-e-codec](../validation/rev-e-codec/README.md): worst 5.2 % of a tolerance.

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

A **100 pF C0G from DUT_LO (the J3 LO pin side of R_iso) to ground** is new in Rev E, placed at J3 next to R_iso.
- **Why.** The range relays put pad copper, contact-to-coil and pole-to-pole capacitance on TIA_OUT. With the stress estimates of those parasitics, the TIA's worst margin falls to 38.5°.
- **What it does.** It lowers the TIA's loop gain near crossover, as fixture capacitance already does. The worst case then becomes 56.0°, above the Rev D floor of 51.3°.
- **Effect on measurement.** DUT_LO is a virtual ground measured by the LOW follower, so the capacitor's current is the TIA error current only. It is linear and removed by calibration.
- **Noise.** No change at the precision of the noise table.

Details and the rejected alternatives are in [stability-full-chain](../validation/stability-full-chain/README.md).

## Supplies, clocks and control

- **AVDD.** 3.3 V from a second AP2112K-3.3 off 5 V (the 3V3 line already on the BOM). The 5VA ferrite rail and its ADS9224R/THS4551 loads go away.
- **IOVDD.** The digital 3V3 rail.
- **VREF.** 2.75 V default, decoupled per the datasheet.
- **ADDR.** Pin strap.
- **RP2040 pins.** BCLK, FSYNC, DIN and DOUT on one PIO state machine (full duplex, 10 system clocks per BCLK), plus I2C SCL/SDA. That is six GPIOs, from the eleven freed by removing the ADS9224R and AD9833. The relays take four more (shared RESET, three SET).

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

The codec network loads TIA_OUT exactly as the THS4551 did. The remaining weakest loop is the source driver (X6A). The relay's contact-to-coil and pole-to-pole capacitance on SOURCE_BUF take it from Rev D's 55.3° (`fixedriso`, 1000 pF fixture) to 50.9° at the same fixture and 48.3° with no fixture. That still passes 45°. The stress values are estimates until the relay layout is extracted. Rerun `fixedrelaycng100` then.

## Remaining risks

- The four bench items above. An EVM loopback settles them.
- **Relay parasitics.** They are estimated, not measured. If an extracted or measured TIA_OUT capacitance exceeds the stress set (about 23 pF effective on TIA_OUT), rerun before ordering.
- **Clamp.** BAT54S forward recovery and capacitance into a 40 kΩ input were never simulated in a transient. The 470 Ω and the AC coupling bound the effect, but the fault transient stays a hand calculation.
- **Codec input impedance spread** (±20 %). The divider and the calibration absorb it on the same die. Temperature drift between calibration and measurement is unpublished.
