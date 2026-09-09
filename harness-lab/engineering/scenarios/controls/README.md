# Synthetic rawfile parser control

This fixture exercises ngspice ASCII waveform retention and parsing only. It
is not an LMR51430 model, has no vendor qualification, and must remain marked
synthetic in every receipt. Expected behavior is a 1 kOhm / 1 uF RC circuit driven by a 0–1 V ramp over 1 ms, with
time constant 1 ms: `v(out)` approaches 1 V exponentially after `v(in)` rises.
