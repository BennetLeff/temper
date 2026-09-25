# PWM finite-edge review

This is a read-only review of the `operating-matrix-07` numerical-repair
fixtures. No canonical experiment files were edited.

## Evidence

The hard-threshold variant uses a finite `UPWM_DAC` for `pwm_hold`, then
re-thresholds that analog waveform at 2.5 V:

```spice
Bgate pwm 0 V=(V(pwm_hold)>2.5) ? 15 : 0
```

The early fixture stalls at `1.0025e-6 s` (`drv_req`), and the late fixture
stalls at `0.351509 s` (`drv_req`). Removing only the blanking current source
(`no_blank`) leaves the same late stall. Replacing only the driver-request
comparator (`linear_driver`) leaves the same late stall but reports `pwm` as
the troublesome node. Removing the gate load (`no_gate`) reaches its end, as
does replacing Bgate with a continuous linear transfer (`linear_gate`).

The independent parent trace analysis found 1,913 intervals at or below
`1e-15 s`; 197 of those cross the `pwm_hold` 2.5-V threshold while none cross
`raw`. The absolute minimum interval is `5.551115123125783e-17 s`, with
`pwm_hold` changing by `2.78e-7 V` and PWM remaining high. This identifies a
repeatable numerical boundary interaction, but does not by itself identify a
specific ngspice device as the root cause.

## Minimal candidate

The proposed host-model change is:

```spice
Bgate gate gnd V=(V(fault)<2.5 && V(ov)<2.5 && V(pcl_hold)<2.5) ? \
  min(V(vcc,gnd),15.2)*clip(V(pwm_hold)/5,0,1) : 0
```

On private copies of the early and late fixtures this reaches the requested
end with no `Timestep too small` message. On a private copy of the patched
controller snapshot, the following checks all pass:

* PWM hold/reset checker;
* PWM edge/timing checker;
* 15-assertion functional protection fixture;
* current-loop pole/gain fixture;
* soft-start/SOC/retry fixture;
* precharged integrated witness.

The integrated witness reports F2 at `599.999504 us`, detector at
`675.384979 us`, external latch at `675.433999 us`, `VB_peak=390.512191 V`,
`VDS_peak=407.401010 V`, and final PWM `0 V`. These are host-model fixture
results, not hardware or silicon qualification.

## Logic and safety review

The continuous transfer preserves the finite DAC's 0-to-5-V edge, keeps the
nominal 0/15-V endpoints, and leaves fault, OVP, and PCL branches as explicit
hard-off conditions. It therefore removes only the normal PWM branch's
discontinuity. Existing gate checks based on stable high/low levels continue
to pass; edge timing should be checked against the declared DAC delay rather
than silently widened.

There is one hazard to close before treating this as accepted: the declared
DAC model has `out_undef=2.5`. If `pwm_hold` is ever genuinely undefined while
the safety branches are permissive, the new equation produces approximately
half gate drive instead of the old threshold branch's off state. The DFF has
`ic=0`, and the tested fixtures begin with `pwm_hold=0`, but this must be
verified explicitly. Add a startup/undefined-state assertion that gate stays
below the off-screen threshold, or provide a separate valid-state inhibit;
do not rely on an accidental initial value.

## Acceptance sequence

1. Apply the one-line Bgate change to the canonical candidate and regenerate
   its model hash.
2. Rerun all six existing controller fixtures plus the early/late numerical
   reproductions; require complete, finite, strictly increasing traces and no
   timestep abort.
3. Add the undefined-DAC/startup assertion described above and exercise fault,
   OVP, and PCL transitions while PWM is high.
4. Only after those checks pass, rerun the cold start through the 500-ms
   settled-operation endpoint and feed the trace to the independent operating
   point checker.

