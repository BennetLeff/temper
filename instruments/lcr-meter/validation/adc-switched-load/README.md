# Independent ADC switched-load stress check

This bounded simulation supports retaining **1 MSPS**. It does not establish ADC accuracy or qualify the complete meter. The full-chain amplifier stability evidence is maintained separately.

## Circuit and limits

Revision C uses the EVM feedback/output topology with the inside-feedback resistor increased to 22 Ω; the optional dedicated RGT FB pads are unused. The unmodified TI THS4551 model drives the board's exact FDA network: 1 kΩ input/feedback resistors, 22 Ω on each main output before the feedback takeoff, 100 pF across each 1 kΩ feedback resistor, 4.32 Ω from each takeoff to its ADC input, 330 pF from each ADC input to ground, and 3.3 nF differential. Supply is 5 V, common mode 2.048 V, and excitation is an ideal single-ended 100 kHz sine with 1.8 V peak. The ideal input voltage sources omit the upstream OPA2810s and their real output impedance/loading; this is deliberately a standalone check.

[ADS9224R SBAS876C](../../sources/ti/ADS9224R.pdf), §7.3.1.1, supplies the typical 120 Ω sampling-switch resistance, 16 pF sampling capacitor and 1 pF hold-mode input capacitance. Each input has a controlled ideal switch plus 120 Ω and a 16 pF capacitor, with a separate 1 pF pin capacitor. Switch on-resistance is 0.01 Ω and off-resistance 1 TΩ. These are linear approximations, not a validated ADC macro model.

Five copies test sample capacitors reset during hold to: both 2.048 V, opposite 0/4.096 V, opposite 4.096/0 V, both 0 V, and both 4.096 V. The imposed resets create differential and common-mode charge disturbances. They are artificial stress conditions; the ADC's actual SAR switching sequence and charge injection are not known from this model. There is no claim that these cases bound every physical charge transient.

A sixth FDA continuously drives the same 120 Ω/16 pF acquisition network as a tracking reference. Reported errors compare the switched sampling-capacitor voltages with this reference immediately before sampling closes. This removes ordinary signal/filter phase lag from the recovery comparison. The result is **remaining disturbance from switching**, not total sine-wave tracking error or instrument error.

## Timing and results

Both tests use a 1 µs period. The operating test allows sampling during approximately the last 640 ns. This is deliberately shorter than the 685 ns left after the ADC's specified 315 ns maximum READY delay at 1 MSPS; the READY delay is used as a conservative scheduling boundary, not as a model of the internal sampling switch. The separate stress test allows only approximately 140 ns and is a negative control. It is not an exact 3 MSPS timing model.

ngspice 45.2, PSpice compatibility, KLU, trapezoidal integration; `reltol=1e-5`, `abstol=1e-12`, `vntol=1e-7`. All six TI model internal MID nodes were checked at 2.5 V. No transient operating-point fallback was accepted. No vendor library was changed. The THS4551 model SHA-256 is `0a8c0db4398d7849ef46ba831bac4bc5f09352c9ead3a7be6a3a7e36d5a21527`.

| Test | Maximum differential recovery error, 0.5 ns maximum step | At 0.25 ns maximum step | Compared with 62.5 µV half-LSB |
|---|---:|---:|---|
| 640 ns operating window | 0.9158 µV | 0.9166 µV | Below threshold in this model |
| 140 ns stress window | 66.45 µV | 66.43 µV | Exceeds threshold; negative control detected |

Worst sampling-capacitor common-mode discrepancy is about 9.1 mV in the operating test and 3.8 mV in the stress test, relative to the continuously tracking reference. This is a sampling-capacitor endpoint comparison, not the instantaneous ADC pin common mode. Across both maximum timesteps, all actual ADC input pins after 3 µs remain between 1.0394 V and 3.0135 V, and their instantaneous pair common mode remains between 1.9228 V and 2.1300 V, within the specified 1.848–2.248 V interval. Both absolute pin and common-mode limits are executable assertions. Values cover all five reset states and eleven sample endpoints after startup, spanning a full sine period. The 16-bit bipolar full-scale span is 8.192 V, so one LSB is 125 µV and half an LSB is 62.5 µV.

This result gives no clearance to increase conversion rate. Actual conversion kickback, voltage-dependent sampling resistance/capacitance, source-amplifier interaction, component tolerances, PCB coupling, reference noise and ADC nonlinearity remain outside this experiment. Scope checks with actual CONVST timing and calibration against independent standards remain necessary.

## Reproduce

Run `sh run.sh` from this directory with Rust and KLU-enabled ngspice 45.2 installed. `NGSPICE=/absolute/path/to/ngspice sh run.sh` selects a binary explicitly. The script generates and runs both decks, checks all values are finite and all model MID nodes are correctly biased, checks the operating threshold and short-window negative control, then repeats with half the maximum timestep. Sources, generated circuits, logs, numeric data and `results.txt` are retained here and under `half/`.
