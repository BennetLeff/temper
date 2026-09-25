# Independent controller probes

This directory snapshots the revised nominal UCC28180 surrogate and tests
its individual equations before normal-operation claims. The input hash is
in `model-input.json`; historical experiment06 is unchanged.

Run `rustc --edition=2021 -O checks.rs -o /tmp/controller07-checks` and
`rustc --edition=2021 -O pwm_checks.rs -o /tmp/pwm07-checks`. For each
`functional`, `current-loop`, and `soft-start` fixture, run
`ngspice -b NAME.cir`, then `/tmp/controller07-checks NAME NAME.tsv`.
Run `ngspice -b pwm-ramp.cir` and `/tmp/pwm07-checks pwm-ramp.tsv` for the
additional timing probe. Recorded outputs are `*-checks.txt`.

Host reruns passed:

- 15 functional assertions, including UVLO and OVP hysteresis, standby,
  open/short sensing, cycle-latched PCL, and the voltage-compensator response.
- Current averaging: nominal 36.979065 us time constant, observed response
  0.632185 at one time constant; 118 kHz oscillator check.
- Capacitor-backed soft start, SOC discharge/recovery, standby and retry.
- PWM leading edges at 0.570004, 1.228660 and 2.545964 us for externally
  fixed ICOMP of 0.72, 1.72 and 3.72 V at VCOMP=3 V and RFREQ=16.2 kohm.
- An ICOMP short inhibits the gate without triggering its own 3 V reset.

The current-loop fixture begins at 3.72 V to match the new nominal offset.
Its gain and pole expectations remain tied to the datasheet equations.
The 0.72 V offset/plateau is an inference from TI's expert support and the
datasheet's minimum-off-time test, as explained in
`../host/controller-model-review.md`. The probes validate implementation
of that interpretation; they do not establish fidelity to real silicon.

Two deliberate regressions in `negative-controls/` must fail: dropping
M1/K1 from the amplifier coefficient (measured response nearly 1 instead of
0.632), and restoring the old unshifted PWM ramp (wrong crossing time).
The unchanged screen rejected both, with normal simulator completion.

No source-current, thermal, parasitic or full operating-envelope claim is
made by these isolated fixtures. They supply prerequisites for the plant
tests, not a substitute for them.
