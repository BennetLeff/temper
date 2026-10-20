# AD8130 differential receiver: conditional simplification

Research date: 2026-10-20. Baseline: Rev B [design](../design.md), [circuit record](../circuit-revb.md), and generated BOM. Candidate replaces U1/U2 ADA4817 buffers, U3 OPA810 subtractor and six gain resistors; no CAD/BOM changes.

**Verdict:** AD8130 can function directly from these taps, but is a prototype candidate requiring recalibration and offset qualification. “High impedance” does not mean FET-like input current. Its useful simplification is one receiver replacing three amplifiers; its intrinsic CMRR cannot correct mismatched dividers, clamps, or receiver input capacitances.

## Part and connection

[ADI lists AD8130ARZ](https://www.analog.com/en/products/ad8130.html) in 8-lead SOIC, with AD8130ARZ-REEL7 as a reel option; AD8130ARMZ is the smaller MSOP alternative. Use SOIC for the first coupon. AD8129 is unsuitable here: its minimum stable gain is ten and its differential operating range is only ±0.5 V, conflicting with the required ×2 receiver and 1.5 V maximum differential tap signal.

Follow the separate input/feedback architecture in [UG-133, Figure 1](https://www.analog.com/media/en/technical-documentation/user-guides/UG-133.pdf): +IN pin 1, −IN 8, −VS 2, PD 3, REF 4, FB 5, OUT 6, +VS 7. Ground REF, connect 499 Ω OUT–FB and 499 Ω FB–ground, giving `Vout = 2(Vtap+ − Vtap−)`. Retain the ×5 stage, selector, filter and output driver. Two ordinary gain resistors replace the subtractor's ratio-matched six; their ratio controls gain, not input subtraction balance. The datasheet's resistorless ×2 circuit also drives REF with the signal: it is a single-ended summing connection, unsuitable for this differential function. Use local bypassing and short feedback routing; UG-133 deliberately removes plane capacitance around FB.

## Electrical facts and consequences

The [Rev. C datasheet, Tables 2/4](https://www.analog.com/media/en/technical-documentation/data-sheets/AD8129_8130.pdf) gives these AD8130 values at ±5 V, mostly at unity gain:

| Quantity | Value; typical unless marked |
|---|---|
| Supply range; quiescent current | ±2.25–±12.6 V; 10.8 mA, 11.6 mA maximum |
| Input common mode; differential operation | ±3.8 V at zero differential; ±2.5 V |
| Output swing | ±3.6 V / ±4.0 V into 150 Ω / 1 kΩ |
| Input resistance, differential/common mode | 6 MΩ / 4 MΩ |
| Input capacitance, differential/common mode | 3 pF / 4 pF |
| Signal-input bias; offset current | ±0.5/±2 µA; ±0.08/±0.4 µA, typical/maximum |
| Offset voltage | 0.4/1.8 mV typical/maximum; 3.5 mV full-temperature maximum |
| Typical temperature slopes | Offset 20 µV/°C; bias 5 nA/°C; offset current 0.2 nA/°C |
| Noise, voltage/current | 12.5 nV/√Hz above 10 kHz; 1 pA/√Hz above 100 kHz |

At ±4.8 V, ±0.75 V initial and ±1.5 V extended individual taps appear comfortably inside the input envelope. Gain two demands at most ±3 V, also plausible with the retained light loading. These are extrapolations from ±5 V specifications, not combined common-mode/differential or load guarantees. Measure the envelope's corners. Receiver dissipation is approximately 104 mW; replacing the two existing 19 mA buffers alone saves approximately 27 mA, plus U3's current.

The upper 10 MΩ in parallel with 5002.501 Ω makes exactly 5 kΩ tap resistance; including protection gives 5220 Ω. Thus `IbR = 2.61 mV` typical, `10.44 mV` maximum per input. Equal resistances cancel common bias in subtraction, leaving `IosR ≈ 0.418/2.09 mV`. Adding intrinsic offset gives approximately **0.818 mV typical / 3.89 mV pessimistic 25°C input-referred**, before feedback-input current effects: **1.64/7.78 V referred to the HV tips**. Full-temperature offset alone corresponds to 7 V at the tips. Typical offset-current drift contributes another 1.04 µV/°C; typical slopes are not guaranteed bounds.

Matching existing source resistances helps; large compensation resistors increase noise and capacitance sensitivity. REF/FB bias compensation addresses that separate pair, not signal-input offset. Trimming removes room-temperature zero, not drift. U5 loses BUF_P/N's isolated sensing outputs: tap sensing or another monitor topology requires a new loading/threshold budget. The 10.44 mV per-tip bias bound exceeds existing ±5 mV buffer-zero acceptance even when differential bias cancels.

Differential loading scale is `2×5220/6M ≈ 0.174%`; recalibrate both DC and AC compensation. It is not safe to treat the input resistance as infinite or assume its typical value tracks between devices or temperature.

## CMRR, noise and faults

The ±5 V table specifies **90 dB minimum DC–100 kHz**, 80 dB minimum at 2 MHz, and 70 dB typical at 10 MHz; the headline 94 dB belongs to AD8129. These conditions do not guarantee 60 dB for a gain-two probe at 5 MHz. [ADI's CMRR-test explanation](https://ez.analog.com/amplifiers/a/documents/c/ad8130-faq/DO10072/ldc---ad8130-29-cmrr-test-circuit) uses tied inputs and explicitly warns that external filter mismatch degrades rejection.

Here `Zs = 220 + 5000/(1+jω·5000·13.1934nF)` approaches 220 Ω at 5 MHz. An effective 1 pF capacitance imbalance produces approximately `ω|Zs|ΔC = 0.00691`, only **43 dB** rejection; allocating all 60 dB to this mechanism permits merely **0.145 pF**. Clamps, routing and input capacitance require measurement; intrinsic CMRR cannot remove already-converted differential error.

The white current-noise contribution would be 7.38 nV/√Hz with unsuppressed DC source resistance, but only 0.31 nV/√Hz at 5 MHz because of the bottom capacitor. Do not extend the specified white-current-noise floor into the low-frequency region. Voltage noise alone implies about 56 mVrms HV-referred over an ideal rectangular 5 MHz bandwidth; actual noise needs the complete filter and feedback network.

[ADI's power-off guidance](https://ez.analog.com/video/a/documents/do8718/ad8130-overvoltage) limits internal input-diode current to 5 mA; absolute input limits remain within 0.3 V of the rails. A 1.5 V step into an unpowered input through 220 Ω alone can initially exceed that current: the 13 nF tap capacitor bypasses 5 kΩ during an edge. Reassess external clamps, discharge and sequencing. PD is not isolation; pull it to +VS for operation. Test disabled, one-rail and unpowered states.

## Bounded next test

Build one receiver coupon at ±4.8 V using two actual tap-equivalent RC sources and existing protection. Measure zero/current loading, differential gain and clipping across the simultaneous tap limits; sweep CMRR from DC through 35/60 kHz to 5 MHz, first with tied low-impedance inputs, then full sources, then added 0.2/1 pF imbalance. Repeat at 0/25/60°C and during fine-stage overload, power sequencing and current-limited clamp events. Require the existing calibrated ±2%/≤1° main-band targets, analog-zero warning budgets, and a frequency-resolved 60 dB rejection budget before replacing Rev B. No such measurements exist yet.
