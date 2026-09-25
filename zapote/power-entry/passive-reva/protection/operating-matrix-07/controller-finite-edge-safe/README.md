# Finite PWM edges with undefined-state inhibition

This is the complete candidate. Relative to `controller-latched-explicit`,
Bgate preserves the existing finite PWM DAC edge and the PWM DAC maps an
undefined digital state to zero volts. Fault, OVP and PCL masks remain in
place. The unknown-state regression in `../numerical-repair/unknown-state/`
shows why the undefined-state mapping is necessary: the intermediate model
would otherwise command 7.5 V.

All six existing controller fixtures pass without adjusted limits. Their
traces are byte-identical to the finite-edge intermediate candidate, as
recorded in `results.json`. The known-state early/late numerical fixtures
also reach their required endpoints. `model-input.json` pins this model.

The tracked full cold-start attempt is `../normal-tracked/`, at the planned
500 ms checkpoint. It failed: timestamps first repeat at 256.990362 ms and
eventually freeze at 348.534538 ms. Its full partial trace is retained and
rejected by the unchanged checker. The earlier unobservable attempt in
`../normal-finite-edge-safe/` was terminated without an exported trace.
The unchanged operating-point checker requires the last
three complete mains cycles to meet its regulation, drift, power and current
screens. Full-waveform validity and startup peak checks are also required.
These focused regressions do not establish a
normal operating point. Timing and device dynamics remain nominal surrogate
assumptions; there is no hardware qualification.
