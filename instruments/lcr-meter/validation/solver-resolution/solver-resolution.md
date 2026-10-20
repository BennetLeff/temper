# Full coupled analog model: convergence evidence

The complete DDS/source amplifier, four OPA2810 channels, both THS4551 channels, their real 2.048 V common-mode loading and ADC RC loads converge without changing the official TI amplifier libraries. This is a circuit-model qualification result, not a measured PCB result.

## Reproducible solver result

`gear.cir` and `klu.cir` differ only by `set klu` in the control block (`solver-only.diff`). The first fails with ngspice's SPARSE solver; the second produces the complete AC analysis using KLU. These A/B cases use reltol=0.001 and Gear integration. The preserved logs are `sparse-same-circuit.log` and `klu-same-circuit.log`. They establish a solver-dependent numerical issue, not that the physical circuit was unstable or the TI models needed alteration.

For strict operating-point, AC and transient validation, the circuit uses KLU, reltol=1e-5, abstol=1e-12 A, vntol=1e-7 V and Gear integration. `offset-nodeset.inc` contains only initial voltage guesses from a verified nominal operating point. SPICE releases these guesses while finding the solution. No `.ic`, `uic`, ideal isolation buffer, supply-current omission, model edit or extra global shunt is used in the accepted runs.

The `.nodeset` entries are limited to resistor endpoints because this KLU implementation cannot add missing diagonal matrix entries for some ideal-source-only nodes. `filter_seed.rs` generates that subset. The earlier all-node and global-shunt experiments are not the accepted method. Ideal loop-probe insertion remains numerically sensitive; the parent validation uses separate resistive-port Y-matrix de-embedding and owns its loop-gain evidence.

## False operating-point regression

The vendor model contains an internal 1 F capacitor (`C_C34`) at `N317950`, a reference driven by two 1 MΩ supply-divider resistors and a 1 TΩ ground path. `E_E6` copies it to `MID`. Its approximately 500,000 s artificial time constant is a model device, not a board component.

Ngspice's fallback can report `Transient op finished successfully` while this internal reference is near zero, even though the FDA supplies are 5 V and ground. A true DC solution has MID approximately 5/(2+1e-6) = 2.499998750 V. This wrong state changes the subsequent linearization and can also retain a spurious charge on the external source AC-coupling capacitor. Therefore an exit code, finite rows or that message alone cannot qualify an analysis.

`op_guard.rs` rejects the preserved `target-base.raw` negative example (MID≈9.711e-10 V). It accepts the strict nominal operating point and all six final DC/AC/transient cases, each with MID≈2.499998751 V. It also checks that the externally AC-coupled source input has its correct near-zero DC bias. `dc-regression.md` records the actual results.

## Real loading is retained

The FDA 1 kΩ input resistors draw approximately −1.02 mA from the HIGH buffer, −2.045 mA from the shared LOW buffer, and −1.02 mA from the TIA at DC. These values come from output-current sensors already present in the unmodified OPA2810 model. Independent external-resistor KCL residuals are approximately 1 pA, consistent with omitted input-bias/off-leakage paths. This confirms that the accepted circuit is fully coupled under FDA common-mode bias.

The THS4551 RGT 3.3 Ω element is retained in the physical OUT-to-feedback-pin branch, as shown in the datasheet block diagram; it is not moved into the ADC load path. The model's physical output drives the external 4.02 Ω / 330 pF / 3.3 nF ADC filter. Static 16 pF ADC input capacitors are included; switched-capacitor acquisition kickback is not.

## Transient scope and limits

`verified-results.md` covers three ranges and representative Stage 53 loads: 100 nF, 500 nF, 9 µF, 0.5 Ω+50 µH, matched 5 kΩ, and matched 100 kΩ with 5 pF feedback compensation. Each requires a valid true DC point, 561 AC rows from 10 Hz to 100 MHz, and a complete 120 µs transient. The common 50 kHz source in this transient set is a dynamic stress stimulus; it is not the intended 1 kHz bus-capacitor measurement.

`corner-results.csv` compares the uncompensated 5 kΩ range against the proposed 10 pF feedback capacitor using a 1 µA, 1 ns-edge current disturbance across the DUT. The grid covers fixture capacitance 0/25/100 pF, AFE rails ±11.4/12/12.6 V, and FDA supply 4.75/5/5.25 V, retaining VOCM=2.048 V. Every case separately checks the internal MID voltage against its actual supply before accepting the transient. Overshoot and settling refer to this specified disturbance, not every possible input or load. A larger shunt fixture capacitance can smooth that current edge; absence of ringing alone does not prove phase margin.

The simulation uses nominal vendor macro-models at 27°C, ideal supply sources, and lumped fixture capacitance. It does not qualify regulator startup/noise, temperature/process extremes, real package/PCB parasitics, ADC switching, calibration accuracy, output short circuits, or physical phase margin. Those require the parent's loop analysis and prototype measurements.

## Replay

Run in this directory with ngspice 45.2 (KLU enabled) and the local `.spiceinit` containing `set ngbehavior=ps`. The model include paths identify the unmodified library files; hashes and simulator identity are recorded separately.

```sh
rustc --edition=2021 -O op_guard.rs -o op_guard
rustc --edition=2021 -O filter_seed.rs -o filter_seed
rustc --edition=2021 -O make_cases.rs -o make_cases
rustc --edition=2021 -O verify_nominal.rs -o verify_nominal
rustc --edition=2021 -O corner_pulse.rs -o corner_pulse
ngspice -b klu-offset-op.cir > klu-offset-op.log 2>&1
./op_guard base-offset-op.raw
./filter_seed base-offset-op.raw strict-no-probes.cir regenerated-offset.inc
# Compare generated .nodeset lines with offset-nodeset.inc before replacing any seed.
./make_cases
./op_guard
./verify_nominal
./corner_pulse
```

Do not execute different decks that write the same data filenames concurrently. Do not infer a pass from the generator completing: the row-count, finite-value, final-time, MID-state and KCL guards are part of the evidence.
