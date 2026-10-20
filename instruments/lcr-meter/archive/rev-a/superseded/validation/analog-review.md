# Analog loop sensitivity study — 2026-10-20

**Result: no obvious instability in the modeled cases; actual AD8606 stability
and measurement accuracy remain unqualified.** This study is supporting design
evidence, not an acceptance test for a manufactured instrument.

The schematic analyzer was run before this review. Connectivity and passive
values were then checked against `cad/design.json`; custom generic op-amp models
were necessary because the automatic subcircuit templates cannot represent this
coupled source-buffer/TIA loop. No manufacturer AD8606 model was used.

## Modeled circuit

The drive amplifier is a follower, followed by the actual 10 Ω source resistor.
The external TIA uses the selected parallel R/C branch, with the permanent
1 MΩ/22 pF branch also present. The TIA bias divider is 47 kΩ/47 kΩ with 1 µF
bypass. The internal AD5933 receive amplifier is approximated by its 20 kΩ input
load into that bias reference. That approximation does not model the AD5933
internal amplifier, ADC, DAC, DFT window or acquisition errors.

| Selected feedback | Selected parallel capacitance |
|---:|---:|
| 20 Ω | 100 nF |
| 200 Ω | 10 nF |
| 2 kΩ | 1 nF |
| 20 kΩ | 100 pF |

All four branches have a nominal R×C pole near 79.6 kHz. This changes receive
gain and phase throughout the operating band; calibration must be performed
at every measured frequency with the same physical jumper and fixture.

Each amplifier model has DC open-loop gain 100,000, a dominant pole, a second
pole, finite series output resistance, 4 pF differential input capacitance and
2 pF input capacitance to ground on each input. Parameter sets are sensitivity
assumptions, not AD8606 production limits:

| Model | Dominant-pole GBW parameter | Second pole | Output resistance |
|---|---:|---:|---:|
| nominal_generic | 10 MHz | 20 MHz | 20 Ω |
| slow_high_ro | 8 MHz | 10 MHz | 50 Ω |
| fast_low_ro | 12 MHz | 40 MHz | 10 Ω |

The external fixture adds a hypothetical 1 µH and 0.2 Ω in series with the
return, and 100 pF from each DUT terminal to ground. These are assumed stress
values, not parasitics extracted from the routed PCB or an actual fixture.

The 32 load cases, each run with three amplifier models, include:

- Resistances at 0.25×, 1× and 2.5× the selected feedback resistance.
- Capacitors with those same reactance magnitudes near 50 kHz.
- An open fixture on each feedback range.
- 20 µH/1 Ω, 80 µH/2 Ω and 150 µH/1 Ω coil-like series loads on the 20 Ω range.
- A 9 µF/0.05 Ω series load on the 20 Ω range, evaluated near 1 kHz.

## Simulations and observed results

ngspice 45.2 ran an AC sweep from 1 Hz to 100 MHz and a 1 ms transient for all
96 cases. The transient injects a 100 mV, 1 µs pulse with 10 ns edges directly
at the source follower input, after the AC-rebias network. It is a ring-decay
stress stimulus, not a simulation of the DDS waveform or startup sequence.

| Observed quantity across the 96 cases | Result |
|---|---:|
| Driver output extrema during pulse test | 1.6202–1.7798 V |
| TIA output extrema during pulse test | 1.0642–1.9053 V |
| Maximum TIA peak-to-peak variation during final 100 µs | 1.72 µV |
| Largest source-follower AC gain anywhere in the sweep | 1.4227× |
| Cases with finite outputs inside 0–3.3 V and final-window variation <1 mV | 96/96 |

The source-follower peaking occurs with a high-impedance capacitive load in
the slow/high-output-resistance model. This is a reason to inspect ringing
on the actual board. These results do **not** establish phase margin, prove
stability for all loads, or establish an error budget. A 1 kHz analog result
does not qualify the AD5933's low-frequency DFT behavior.

A preliminary held DC step produced slow TIA bias drift on resistive/coil
loads because the bypassed divider is loaded through the receive resistor.
That drift was not evidence of oscillation. The final, saved study uses the
short pulse above to distinguish ring decay from that expected DC behavior.

## Reproduction

From the project root:

```
rustc --edition=2021 -D warnings -O validation/analog-review.rs -o /tmp/lcr-analog-review
/tmp/lcr-analog-review validation/analog-review
```

This requires `ngspice` on PATH. The Rust source generates each netlist, invokes
ngspice, checks its exit status and output structure, and writes `results.csv`.
The `cases/` files preserve netlists and logs from the reported run. Their raw
data output paths are temporary run paths; regenerate them with the harness
instead of executing the archived netlists directly. Large raw traces are not
retained. The model and extraction assumptions are explicit in the source.

Before trusting hardware measurements, verify supply/bias levels, unloaded
drive amplitude, capacitive-load ringing and TIA swing with an oscilloscope,
then validate calibration against an independent third resistor and known
L/C standards across the intended band. Check both C and L reactance signs.
Slew rate, output-current limiting, rail saturation, noise, offsets, temperature,
real layout parasitics and exact amplifier phase response were not modeled.
