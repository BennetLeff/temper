# Circuit and assembly decisions

## Signal path

Each leg has 10 MΩ above its tap. Five identical sections each contain two 1 MΩ resistors and one 33 pF capacitor. With `Rbottom = 10 MΩ / 1999 = 5002.501 Ω`, the DC attenuation is 2000:1. Matching time constants requires a total low-leg capacitance of 13.1934 nF, including component, clamp, buffer and layout capacitance. The ideal high-frequency input capacitance is approximately 6.6 pF.

R11/R31 are 4.99 kΩ, 0.01%; RV1/RV2 are 50 Ω, with the wiper tied to one end. The nominal trim setting is 12.501 Ω. All worst-direction 0.1% upper-string and 0.01% bottom-resistor corners require 7.000–18.003 Ω. A 50 Ω trimmer covers these corners without the reduced resolution of a 200 Ω part. This relies on the selected 0.1% upper resistors.

The initial coarse population is 10 nF + 2.2 nF + 680 pF + 220 pF + 47 pF + 10 pF + 1 pF = 13.158 nF. CT1/CT2 are EW Electronics GKG60015 top-adjust ceramic trimmers, 12–60 pF / 100 V, with nominal setting 35.4 pF before parasitics. Their rotor connects to GND and stator to the tap. The manufacturer temperature coefficient is N2200 ±800 ppm/°C; their small contribution to total capacitance limits the nominal composite contribution to about −6 ppm/°C, but tracking and temperature behavior still need measurement.

The trimmers provide fine adjustment through shield tool holes; the coarse bank still needs selection when component tolerance or parasitics exceed that adjustment range. Change coarse parts only with the DUT disconnected, then close the shield. Use low-voltage excitation and an insulated adjustment tool for fine adjustment; withdraw the tool before accepting the reading. The archived ladder model needed about 12.877 nF with assumed 0.2 pF node strays. That illustrates why a nominal population and one trimmer cannot guarantee broadband 60 dB rejection.
U1/U2 buffer the taps through 220 Ω current-limiting resistors. The ADA4817 input range reaches only about 2.8 V below its positive supply; the proposed extended ±3 kV tip voltage produces ±1.5 V at the tap, inside the nominal ±4.8 V supply headroom. Power-down pin 8 is tied to the positive rail to enable the amplifier.

U3 is an OPA810 fixed ×2 difference amplifier. R61/R62 are 499 Ω inputs and paired 499 Ω resistors form each 998 Ω gain arm. U12 is a separate OPA810 noninverting ×5 stage: 499 Ω to ground and four series 499 Ω feedback resistors. Both feedback networks remain connected in either range. R100 (49.9 Ω) isolates the fine-stage input branch from U3.

SW1 selects between the fixed ×2 output and the cascaded ×10 output, each through its own 49.9 Ω isolation resistor, before the common filter and U4 output buffer. Only pole 1 is used: pin 1 WIDE_SEL, pin 2 SELECTED, pin 3 FINE_SEL; pins 4–6 are NC. R103 (1 MΩ) returns SELECTED to ground during contact opening. Use the gold-contact 7201SYZBE and verify electrical position rather than assuming lever direction. The manufacturer’s generic technical data specifies break-before-make unless noted otherwise; verify it on the received switch. The isolation resistors limit momentary output contention if contacts overlap; contact bounce and settling remain bench checks.

Range selection no longer opens amplifier feedback. There is no circuit requirement to de-energize the DUT merely to select a range, but the transition is not a valid measurement interval. Keep the selector harness short and contained in the low-voltage compartment. Opening the enclosure or moving HV connections still requires de-energization.

The common filter uses R69 = 97.6 Ω and C61 = 180 pF. Including the selected output's 49.9 Ω isolation resistor and detector/DC-return loading gives an effective source resistance near 147.37 Ω and a calculated RC pole of 6.000 MHz. A first-order amplifier cascade estimate gives 5.65 MHz wide and 5.00 MHz fine bandwidth; these are typical-model calculations, not guaranteed or simulated responses. The archived TI model predicts 5.55 MHz wide and 5.09 MHz fine with a representative 120 pF cable/scope load, using ideal buffer sources and supplies. Its 60 kHz phase is about −0.92° wide / −1.16° fine before the HV divider and buffers, reinforcing the need for range-specific phase calibration. The vendor model’s overdrive clipping exceeds its ideal rails slightly, so exact clipping and recovery are not physical predictions. The selector loading introduces about 0.254% attenuation, giving approximately 1002.6:1 and 200.52:1 before calibration. Calibrate the complete output path.

U4 is an OPA810 unity buffer; R70 is 49.9 Ω series output isolation. Use a scope's 1 MΩ input. A 50 Ω termination roughly halves the signal and is outside this calibration. See [Rev B circuit calculations and evidence](circuit-revb.md) for the detailed gain, loading and warning budgets.
## Protection and indication

D1/D2 are low-leakage BAV199 pairs clamping the buffer inputs to shunt references of approximately ±2.495 V plus a diode drop. D3 similarly clamps the output after R70. These are overload clamps, not precision ±3 V limiters: forward voltage, current and temperature change the clip level. The reverse-recovery behavior and charge injected into the reference wiring must be checked on hardware.

The fine range would demand 7.5 V output for 1.5 kV differential input. U12 saturates before that. In wide range the unused U12 can therefore be saturated while the selected output is valid. Verify that U12 overdrive, input bias current and rail/reference coupling do not disturb U3 or the wide output. The output clamp does not guarantee rapid recovery of earlier amplifier stages.

U5 watches both buffered inputs; U6 watches SELECTED through a 2:1 divider, so saturation of the unused fine output does not alone assert the output warning. The tip references use 25.5 kΩ / 10 kΩ dividers and the output references use 29.4 kΩ / 10 kΩ, giving nominal thresholds of ±0.7028 V at the input buffers and ±1.2665 V on SELECTED. These correspond approximately to 1.406 kV per tip, 1.266 kV wide differential and 253 V fine differential. The intentionally early thresholds leave tolerance margin before the initial qualification limits. The conditional static late-trip budget is about 1491 V per tip and 1364 V wide / 294 V fine, subject to the temperature, reference and calibrated-gain assumptions in the circuit record. Actual analog zero offsets must remain within ±25 mV wide / ±130 mV fine, with individual buffer offsets within ±5 mV. Scope zero subtraction does not remove offset seen by the comparator.

The comparator outputs drive Q1 and the CD4013 set input; the LED stays on until reset. It flags the initial-envelope warning, including during extended-range qualification. It is not a fast protective trip or proof that every short peak was captured: the comparators have roughly 560 ns typical delay, with additional latch/path delay. Record clipping and actual waveform behavior as well.
TL431 shunts have 1 kΩ feed resistors and no output capacitors; a capacitor added to either reference requires a stability assessment against the TI data sheet. Reference bias is about 2 mA after the threshold-divider loads. The output clamp can add tens of milliamps during saturation; verify shunt temperature, output-driver current and recovery together.

## Supply, grounding and assembly

Two 9 V batteries feed ADP7142/ADP7182 regulators through a separate silver-contact 7201SYZQE power switch and reverse-polarity diodes. Nominal rails are +4.800 V and −4.807 V. The gold signal switch is not used as the supply switch. Expect roughly 60–80 mA per battery before overload loads; verify actual current, regulator temperature and battery runtime. The design has no low-battery validity indicator: record both rails before and after measurements, and stop using results if either leaves its calibrated range.

The selected 10 µF, 25 V, 1210 X7R regulator capacitors need an effective-capacitance check at actual bias and temperature; maintain at least the regulator's specified 2.2 µF. Two ADA4817s account for about 38 mA typical quiescent current; the three OPA810 stages add their own quiescent and signal-load current. Small TSOT regulator thermal behavior with fresh batteries must be checked. Local 100 nF bypasses accompany each amplifier, comparator and latch supply.

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
