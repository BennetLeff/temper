# Controller candidate preserving the finite PWM edge

Only the `Bgate` transfer is changed relative to `controller-latched-explicit`:
when permitted, output voltage follows the existing DAC's normalized 0–5 V
ramp rather than introducing a second ideal comparator at 2.5 V. All three
fault/OVP/PCL masks remain in place. The declared DAC edge remains 1 ns;
this is a nominal surrogate assumption, not qualified silicon timing.

`../numerical-repair/README.md` records the failing minimal reproduction and
the independent one-change probes. `results.json` records all six existing
fixtures passing without changed acceptance thresholds. `model-input.json`
identifies the exact candidate. The full cold-start run is retained under
`../normal-finite-edge/`; do not infer an operating-point pass from these
controller fixtures or a simulator exit code.
