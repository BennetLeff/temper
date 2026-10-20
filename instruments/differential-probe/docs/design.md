# Circuit and assembly decisions

## Signal path

Each leg has 10 MΩ above its tap. Five identical sections each contain two 1 MΩ resistors and one 33 pF capacitor. With `Rbottom = 10 MΩ / 1999 = 5002.501 Ω`, the DC attenuation is 2000:1. Matching time constants requires a total low-leg capacitance of 13.1934 nF, including component, clamp, buffer and layout capacitance. The ideal high-frequency input capacitance is approximately 6.6 pF.

R11/R31 are 4.99 kΩ, 0.01%; RV1/RV2 are 50 Ω, with the wiper tied to one end. The nominal trim setting is 12.501 Ω. All worst-direction 0.1% upper-string and 0.01% bottom-resistor corners require 7.000–18.003 Ω. A 50 Ω trimmer covers these corners without the reduced resolution of a 200 Ω part. This relies on the selected 0.1% upper resistors.

The initial low-leg capacitor population is 10 nF + 2.2 nF + 680 pF + 220 pF + 82 pF + 10 pF + 1 pF = 13.193 nF. This is a starting population, not a final calibration. Select or replace capacitors after measuring the assembled probe in its final shield. The archived ladder model needed about 12.877 nF with its assumed 0.2 pF node strays; that is an illustrative model result, not a PCB capacitance measurement. A 60 dB rejection goal cannot be obtained by merely ordering 5% capacitors.

U1/U2 buffer the taps through 220 Ω current-limiting resistors. The ADA4817 input range reaches only about 2.8 V below its positive supply; the proposed extended ±3 kV tip voltage produces ±1.5 V at the tap, inside the nominal ±4.8 V supply headroom. Power-down pin 8 is tied to the positive rail to enable the amplifier.

U3 subtracts the two buffered signals. Both input resistors are 499 Ω. SW1 selects matched upper/lower gain arms: 998 Ω (two 499 Ω in series) for ×2, or 4.99 kΩ for ×10. Thus `Vout ≈ (TIP_P − TIP_N)/1000` or `/200`. Use the gold-contact 7201SYZBE for this low-level circuit. Terminals 2 and 5 are the commons; 2–1/5–4 selects ×2 and 2–3/5–6 selects ×10. Label the panel by verified electrical position, not assumed lever direction.

The ADA4817 is a much faster amplifier than the desired probe bandwidth. Its data sheet recommends relatively low feedback resistance; the 4.99 kΩ gain arm, switch capacitance and wiring require a stability check. C62/C63 are paired 1 pF compensation positions, both initially DNP. Populate only from measured stability/response results, then remeasure both ranges and CMRR. Keep SW1 at U3 with short, symmetric connections; a long panel harness in the feedback loop is unacceptable. Change range with the DUT de-energized because switching can momentarily open feedback.

R69 (97.6 Ω, 1%) and C61 (330 pF, 5%) form a nominal 4.942 MHz pole. The 1% thick-film R69 is deliberate: it is a standard catalog part and does not set divider ratio or common-mode balance. Its tolerance and C61 tolerance place the ideal pole approximately between 4.66 and 5.25 MHz. U4 is an OPA810 unity buffer; R70 is 49.9 Ω series output isolation. The specified output is into a scope's 1 MΩ input. A 50 Ω termination roughly halves the signal and is outside this calibration.

## Protection and indication

D1/D2 are low-leakage BAV199 pairs clamping the buffer inputs to shunt references of approximately ±2.495 V plus a diode drop. D3 similarly clamps the output after R70. These are overload clamps, not precision ±3 V limiters: forward voltage, current and temperature change the clip level. The reverse-recovery behavior and charge injected into the reference wiring must be checked on hardware.

The ×10 range demands 7.5 V output for 1.5 kV differential input. U3 saturates before that, even though D3 limits the connector voltage. Output protection cannot guarantee rapid recovery of earlier amplifier stages.

U5 detects buffered-input magnitude above approximately 1.597 V (about 3.19 kV at a tip with ideal attenuation). U6 detects raw-output magnitude above approximately 2.997 V. Their open-collector outputs drive Q1 and the CD4013 set input; the LED stays on until reset. This indicates extended-range overload, **not** crossing the initial ±1.5 kV qualification target. The comparators have roughly 560 ns typical delay, so the LED is not evidence that every shorter peak was captured. Record scope clipping and raw waveform behavior as well.

TL431 shunts have 1 kΩ feed resistors and no output capacitors; a capacitor added to either reference requires a stability assessment against the TI data sheet. Reference bias is about 2 mA after the threshold-divider loads. The output clamp can add tens of milliamps during saturation; verify shunt temperature, output-driver current and recovery together.

## Supply, grounding and assembly

Two 9 V batteries feed ADP7142/ADP7182 regulators through a separate silver-contact 7201SYZQE power switch and reverse-polarity diodes. Nominal rails are +4.800 V and −4.807 V. The gold signal switch is not used as the supply switch. Expect roughly 60–80 mA per battery before overload loads; verify actual current, regulator temperature and battery runtime. The design has no low-battery validity indicator: record both rails before and after measurements, and stop using results if either leaves its calibrated range.

The selected 10 µF, 25 V, 1210 X7R regulator capacitors need an effective-capacitance check at actual bias and temperature; maintain at least the regulator's specified 2.2 µF. Three ADA4817s account for about 57 mA typical quiescent current. Small TSOT regulator thermal behavior with fresh batteries must be checked. Local 100 nF bypasses accompany each amplifier, comparator and latch supply.

GND is the BNC shell, scope earth and fixed electrostatic shield. Battery power does **not** make this a galvanically isolated input. Keep the scope's protective earth intact. Route shield displacement current to the BNC/shield bond without sharing the sensitive tap or gain-reference return path. Preserve equal geometry and thermal conditions between divider legs.

At 3 kV DC on one tip, ideal leg dissipation is approximately 0.90 W, or 90 mW per 1 MΩ resistor. At 3 kV peak sinusoidal voltage it is approximately 0.45 W per leg. Each segment sees approximately 600 V peak and each resistor approximately 300 V under ideal sharing. These values do not replace voltage-coefficient, temperature, transient-sharing or insulation qualification. At 60 kHz and 3 kV peak, 6.6 pF draws about 5.28 mArms. A 70 V/ns edge implies about 0.46 A instantaneous displacement current before added stray capacitance. Neither number establishes acceptable disturbance on stage 53.

The grounded enclosure, tip lead routing and final PCB are part of the compensation network. Determine clearance/creepage from the actual working voltage, transient environment, altitude, material and pollution conditions before layout release. No CAT rating is claimed. Do not put a continuous ground plane beneath the high-voltage ladder merely because the low-voltage amplifier needs good grounding. Keep the low-voltage RF layout compact while preserving the ladder's insulation and measured capacitance.

## Pin and footprint checks

Custom symbols use the selected package, not a generic op-amp pinout:

| Part/package | Critical mapping |
|---|---|
| ADA4817-1ARDZ, RD-8-4 | 1 feedback, 2 −IN, 3 +IN, 4 −VS, 5 NIC, 6 OUT, 7 +VS, 8 PD, 9 exposed pad |
| ADP7142, TSOT-5 | 1 VIN, 2 GND, 3 EN, 4 ADJ, 5 VOUT |
| ADP7182, TSOT-5 | 1 GND, 2 VIN, 3 EN, 4 ADJ, 5 VOUT |
| TL431BIDBZR, DBZ | 1 cathode, 2 REF, 3 anode; do not substitute TL432 pin mapping |
| BAV199, SOT-23 | 1 outer anode, 2 outer cathode, 3 series junction |
| OPA810, SOIC-8 | 2 −IN, 3 +IN, 4 −VS, 6 OUT, 7 +VS; 1/5/8 NC |

The local ADA4817 footprint derives from KiCad's SOIC-8 exposed-pad footprint, with pad 9 resized to the RD-8-4 nominal 2.29 × 2.29 mm exposed pad. Analog Devices Rev. I changed the package designation from RD-8-1 to RD-8-4. Lead pitch is 1.27 mm; the package drawing gives exposed-pad dimensions 2.18–2.39 mm. The PCB revision contains four 0.9 mm square paste apertures within that pad; assembly-process qualification remains required. The PTS645 reset switch footprint represents its internally common terminal pairs as duplicate pad numbers 1 and 2; both copies are physically routed. See the [layout notes](layout.md) for slot, shielding and mounting details.

The pad-number audit detects missing or extra numbers; it does not certify land-pattern geometry or prove that a selected library footprint matches every dimensional detail. Offboard switches, BNC and battery clips intentionally have no PCB footprint.

## Reference sources

- [Altium differential probe project](https://resources.altium.com/p/differential-oscilloscope-probe-project): architectural starting point; its attenuator is replaced.
- [ADA4817 data sheet](https://www.analog.com/media/en/technical-documentation/data-sheets/ADA4817-1_4817-2.pdf) and [RD-8-4 package](https://www.analog.com/media/en/package-pcb-resources/package/pkg_pdf/soic_edrd/rd-8-4.pdf).
- [ADP7142](https://www.analog.com/media/en/technical-documentation/data-sheets/ADP7142.pdf), [ADP7182](https://www.analog.com/media/en/technical-documentation/data-sheets/ADP7182.pdf), [OPA810](https://www.ti.com/lit/ds/symlink/opa810.pdf).
- [TLV170x](https://www.ti.com/lit/ds/symlink/tlv1704.pdf), [CD4013B](https://www.ti.com/lit/ds/symlink/cd4013b.pdf), [TL431](https://www.ti.com/lit/ds/symlink/tl431.pdf), [BAV199](https://assets.nexperia.com/documents/data-sheet/BAV199.pdf).
- [Stackpole HVCB](https://seielect.com/Catalog/SEI-HVCB.pdf), [RNCF](https://seielect.com/Catalog/SEI-RNCF.pdf), [Bourns 3296](https://www.bourns.com/docs/product-datasheets/3296.pdf).
- [C&K 7000 series, manufacturer data sheet](https://www.littelfuse.com/assetdocs/littelfuse-ck-toggle-7000-series-datasheet?assetguid=fed01bc6-88d0-4bda-b896-13c98cf9e90e).

All remaining component-specific links are in the generated BOM.
