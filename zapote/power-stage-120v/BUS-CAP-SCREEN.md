# DC bus capacitance sensitivity

The approved C5/C6 change is two 2.7 µF, 1000 V TDK B32656G0275J000
capacitors. Four 0.1 µF local bus capacitors add 0.4 µF. This gives 5.4 µF
bulk and 5.8 µF total, versus the previous 5.0 µF bulk bus. The separate
0.54 µF resonant bank is unchanged.

The refreshed [power section screen](../../docs/hardware/power-section-120v/power_section.rs)
compares these values with capacitor-only equations. At 140 V RMS line crest,
60 Hz line frequency and 33 kHz switching frequency:

| Case | Bus capacitance | Energy at line crest | Ideal 33 kHz ripple voltage per ampere RMS | Ideal 60 Hz `C·dV/dt` peak |
| --- | ---: | ---: | ---: | ---: |
| Previous bulk | 5.0 µF | 0.098 J | 0.965 V/A | 0.373 A |
| New bulk | 5.4 µF | 0.106 J | 0.893 V/A | 0.403 A |
| New bulk and local | 5.8 µF | 0.114 J | 0.832 V/A | 0.433 A |

Thus, **at the same assumed 33 kHz sinusoidal bus ripple current**, the
ideal capacitive voltage term falls 13.8% from 5.0 to 5.8 µF. This is a
sensitivity calculation, not a prediction of the actual bus waveform. The
local capacitors' placement, ESL, ESR and current division will determine
their real benefit; the older script's 21.6 A bus ripple is from a different
half-bridge tank and cannot be reused for this full bridge.

The extra 0.8 µF holds 0.0157 J more at 140 V line crest. Its ideal
line-following `C·dV/dt` peak changes by 0.060 A, compared with a 15 A
input-current design point. Those small perturbations support treating the
capacitance change as a minor input-current effect in an initial screen.
**The script's 0.95 power factor is an assumed input, not a calculated
result.** It has no coupled rectifier, line impedance, EMI choke, control or
input-current waveform model and therefore cannot confirm actual power
factor or harmonic compliance. Measure line current and power factor on a
prototype at the intended power, line voltage and cooking load.

The energy values describe capacitors charged by the line only. Tank energy
return can raise the bus above line crest; this screen does not bound
overshoot or qualify the TVS, 650 V MOSFETs or new capacitors during faults.

Reproduction from the repository root:

```sh
rustc --edition=2021 --test docs/hardware/power-section-120v/power_section.rs -o /tmp/ps120t
/tmp/ps120t
rustc --edition=2021 -O docs/hardware/power-section-120v/power_section.rs -o /tmp/ps120
/tmp/ps120 > docs/hardware/power-section-120v/power-section-output.txt
```

Run on 2026-09-25 from source branch base `54ed42cec`: 6/6 Rust tests pass.
The source SHA-256 is `33cb3b7e4ffb84d5bc2004c9d1240c2d0e203f2ebfbf6a4a90f5c1b234df1778`;
the generated output SHA-256 is
`a0952d2539f1a8047c77b40094bc42e36957d832b1e6113d08aa1296fd73084a`.
