# Built-in 1 kHz / 60 kHz check output

Research, 2026-10-20. **Recommendation: qualify Rev B with an independently verified external source; prototype a detachable, approximately 4 Vpp checker before adding a 20 Vpp internal generator.** A checker can reveal damage or changed compensation. It cannot establish its own amplitude accuracy or certify 60 dB CMRR through 5 MHz.

Basis: [Rev B circuit](../circuit-revb.md), [qualification plan](../qualification.md), and PCB SHA-256 `b0c15add2b69967cee0593962e1b3b22795725ed36ccbfc408b05c3fb4002b65`. The repository hardware-baseline check passed separately; stage15b is not this probe or its stage53 application. No bench result, CAD change or BOM selection is implied.

## Voltage, circuit and power

The existing +4.800/−4.807 V supplies span only 9.607 V. A single-ended output cannot deliver 20 Vpp; even an ideal bridge gives only 19.214 Vpp differential before headroom losses. A bridge also lacks the earth-referenced signal needed to drive both tips together for the normal common-mode test. The unregulated ±9 V batteries likewise do not supply a dependable 20 Vpp swing.

A feasible separate prototype is a 9 V-to-24 V [LT8330 boost supply](https://www.analog.com/media/en/technical-documentation/data-sheets/LT8330.pdf), precision reference/divider levels of 0.125 and 2.625 V, an [ADG884 SPDT](https://www.analog.com/media/en/technical-documentation/data-sheets/ADG884.pdf) powered from the low-voltage rail, and an OPA810 at noninverting gain eight: nominal 1–21 V output, 20 Vpp, with a 100 Ω series resistor. A crystal-clocked timer selects 1/60 kHz; reference accuracy, divider ratios, switch charge injection and settling require verification. This is an architecture to develop, not a complete circuit.

[OPA810](https://www.ti.com/lit/ds/symlink/opa810.pdf) supports 27 V total supply, 70 MHz GBW and typical 200 V/µs slew rate. Its approximately 3.7 mA quiescent current costs 89 mW at 24 V: approximately 12 mA from 9 V assuming 85% conversion efficiency, before clock, reference, feedback and converter losses. LT8330's 6 µA headline is sleep current, not this operating budget. Its 2 MHz switching lies inside the probe bandwidth. A switched resistor load or bleeder also adds power. A 4 Vpp buffered source fits the existing rails and avoids the boost converter, though it gives five times less measurement signal.

## What the waveform proves

The source sees about 6.6 pF per tip plus fixture capacitance: one-tip differential testing and tied-tip common-mode testing have different loads. For an illustrative 100 pF total load, a 20 V transition in 100 ns needs 20 mA; 100 Ω adds approximately 22 ns RC rise time. Measure the actual terminal waveform under both loads. Generator high-impedance/50 Ω settings matter: [Keysight's 33500 guide](https://www.keysight.com/us/en/assets/9018-03290/user-manuals/9018-03290.pdf) illustrates the factor-of-two amplitude setting change.

At 200 V/µs, a 20 V transition takes approximately 100 ns for the full excursion; this typical extrapolation is not a guaranteed edge specification. A nominal 5 MHz single pole has 70 ns 10–90% rise time. The source would substantially influence the observed edge. Faster pulsing needs a separately designed driver; increasing clock frequency does not fix slew rate.

A 1 kHz square reveals dominant compensation droop/tilt, polarity and gross gain. A 60 kHz square adds a useful operating-band check and repeated-edge stress. Neither replaces measured gain/phase at 35/45/60 kHz and a sine sweep through 10 MHz. Distributed ladder/shield parasitics can remain after a pleasing square-wave adjustment. At 60 kHz the 83rd harmonic is 4.98 MHz and already −38.4 dBc for an ideal square; at 1 kHz the 4999th is approximately 5 MHz and −74 dBc. Harmonic amplitude and source edge must be measured before inferring probe response. [Tektronix's probe primer](https://www.tek.com/en/documents/whitepaper/abcs-probes-primer) explains this harmonic/bandwidth relationship.

## Mismatch and the measurement floor

Drive each tip separately, ground the other, then swap polarity and compare complex transfer functions. Tie both tips together at one physical source junction to measure common-mode leakage; equal-looking branches can introduce false mismatch.

At 20 Vpp, nominal differential outputs are 20 mVpp wide and 100 mVpp fine. At 60 dB CMRR the corresponding common-mode residuals are only **20 µVpp and 100 µVpp**. Use consistent amplitude conventions: the fundamental of an ideal 20 Vpp square is 25.46 Vpp, so an FFT fundamental calculation uses that value. The final unity OPA810's 6.3 nV/√Hz alone implies approximately 14 µVrms over an ideal 5 MHz rectangular noise bandwidth, before other stages and scope noise. A quiet source alone cannot establish this rejection floor.

Use coherent averaging/FFT or lock-in detection with stated equivalent noise bandwidth, source-off noise and synchronous-feedthrough controls. Averaging suppresses uncorrelated noise; clock pickup and shared-ground coupling survive it. Independently verify source levels and frequency with calibrated instruments; characterize edge/phase against a separate reference path. Shared rails/references can conceal correlated drift. Report a CMRR lower bound where residual uncertainty dominates.

## Integration and next experiment

Keep any generator behind the grounded low-voltage shield, with a short return to the BNC/shield reference. Route no check-output wire beside either ladder or through its insulation keepout. A panel penetration needs maintained insulation geometry, restraint and a covered/recessed docking fixture. Disabling the source leaves capacitance; disable clock/boost, disconnect its output and measure response/noise with the complete assembly fitted.

A live DUT lead contacting the check terminal could put HV onto the source and accessible hardware. A software enable or 100 Ω resistor is insufficient protection. Require physical mutual exclusion between DUT connection and docking **both disconnected tips**; do not add an ordinary exposed calibration post pending that design.

First compare an external verified 20 Vpp source with a detachable 4 Vpp checker: one tip, reversed tips and tied tips, both ranges, 1/60 kHz and swept sine. Record loaded amplitude, edge, spectra, noise bandwidth and uncertainty. Repeat with checker installed but off, batteries depleted, shield fitted and permitted lead motion. Add an internal source only if it improves repeatability without shifting measured gain/CMRR or creating an accessible HV path. Retain the full independent qualification procedure.
