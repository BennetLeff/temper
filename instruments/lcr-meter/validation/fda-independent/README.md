# Independent FDA loop audit

This audit independently reproduces the original driver concern and checks the selected Revision C compensation using **two TI macro-model architectures**. It is a standalone FDA test with ideal input sources; the coupled LCR-chain results are separate. Neither model establishes physical stability or ADC accuracy.

## Reference circuit and selected change

The complete [ADS9224REVM guide SBAU315B](https://www.ti.com/lit/pdf/SBAU315), printed pages 6 and 26, shows a 10 Ω resistor on **each amplifier output before the feedback takeoff**, a 1 kΩ feedback resistor in parallel with 100 pF, and a further 4.32 Ω resistor between that takeoff and each ADC input. Each ADC input has 330 pF to ground; 3.3 nF connects the differential pair. The abbreviated ADC datasheet diagram omits part of this network. The retained guide is `../../sources/ti/ADS9224REVM-SBAU315B.pdf`.

Revision C selects **22 Ω before the takeoff**, retaining 100 pF, 1 kΩ, 4.32 Ω, 330 pF and 3.3 nF. The larger resistor improves modelled phase margin. This is a documented derivative of the EVM circuit. Its extra filtering and output drop require calibration and physical qualification. This audit includes 16 pF from each ADC pin to ground as a static load; a separate switched-load experiment checks acquisition recovery.

The RGT package's 3.3 Ω paths connect the main outputs to optional FB pads. They are not in series with its main OUT pads. External feedback is taken from the post-22 Ω nodes; the dedicated FB pads are left unconnected. This follows the functional block diagram and the conditional use of the internal feedback traces in THS4551 §9.1/§13.1.1. It is an electrical inference from those diagrams, rather than an explicit vendor instruction to leave the pads unconnected. The EVM uses the RUN package, which has no separate FB pads.

## Models and loop measurement

- Current 2021 GWL PSpice model: unmodified `../../sources/ti/models/ths4551.lib`, SHA-256 `0a8c0db4398d7849ef46ba831bac4bc5f09352c9ead3a7be6a3a7e36d5a21527`.
- Original 2016 TI model: embedded in the official [SBOC476 test archive](https://www.ti.com/lit/zip/SBOC476), retained as `../../sources/ti/SBOC476.zip`, SHA-256 `45db38edfabfef56b09ccf52eda5a4fcbc4eeea1151bb767b31fcb8e7ff15c69`. `run.rs` extracts its 978 length-prefixed ASCII records and verifies byte-for-byte equality with `ths4551-legacy-extracted.lib`, SHA-256 `0bda2d15075b4065cd67937da5f29409f2e2b54d4f597d950da0d2918255837a`.

The 2016 model explicitly includes the datasheet's two internal 0.6 pF output-to-input capacitors. The newer GWL model uses a different topology without those explicit capacitors. Adding them to the newer library without evidence would alter that model. Both original source libraries remain intact.

`run.rs` creates clearly named **instrumented copies** solely for measuring loop gain. Each adds a DC-zero, AC-one voltage source to one voltage-controlled forward-stage input and changes that input's node name. These are ideal control terminals with no input current. Every external feedback path, bias current, input capacitance and, in the legacy model, both physical 0.6 pF feedback capacitors remain on the returned side of the cut. Thus the original DC circuit is unchanged. Return ratio is minus returned differential control voltage divided by injected forward differential control voltage. This independent internal cut avoids the external bilateral Y-matrix reduction used by the full-chain harness. It does not measure the separate internal common-mode servo's loop margin.

## Results

| Driver network | GWL margin | Legacy margin |
|---|---:|---:|
| Original derivative | 13.95° at 22.21 MHz | 13.24° at 21.66 MHz |
| EVM 10 Ω / 100 pF | 47.48° at 26.79 MHz | 42.51° at 26.62 MHz |
| Selected 22 Ω / 100 pF | 63.76° at 18.87 MHz | 60.38° at 19.20 MHz |
| Lowest selected-network corner | 62.57° | 59.19° |

The selected network passes nominal plus all 64 combinations of six signed variation groups: inside-output resistance ±1%; outside resistance ±1%; input/feedback resistors opposed at ±0.1%; feedback capacitors ±5%; ADC filter capacitors ±5%; and 5 V supply ±5%. Resistors and capacitors within each group move together; this is not every independent component mismatch. The current-source inputs are ideal and omit upstream OPA2810 impedance. Temperature is 27 °C and the models are typical, without semiconductor process corners. This test covers the differential loop, not every coupled circuit mode.

Each sweep runs 1 Hz to 1 GHz at 120 points/decade. The reducer unwraps phase, requires exactly one descending unity crossing, checks finite values and all 1081 rows, and requires >45° for every selected case. `min_return_difference` records the minimum sampled |1+T|, not an analytical global minimum. Logs verify output DC within 20 mV of 2.048 V, GWL internal MID within 50 µV of half supply, and no transient-OP fallback. The 2016 model uses a different internal supply topology and has no equivalent `MID` check. Dynamic gmin stepping is allowed when it reaches the true DC operating point.

Reproduce with `sh run.sh`, Rust and KLU-enabled ngspice 45.2. PSpice compatibility and strict `reltol=1e-5`, `abstol=1e-12`, `vntol=1e-7` are explicit. Generated instrumented copies, all 134 circuits/logs/sweeps, `results.csv` and `results.txt` are retained. These nominal/corner simulations support this compensation choice; a scoped hardware test must still verify it.
