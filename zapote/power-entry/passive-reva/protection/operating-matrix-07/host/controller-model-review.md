# Controller model review during experiment 07

The frozen experiment06 controller is a host-authored functional surrogate,
not TI's transistor-level or validated transient model. Full startup exposed
an error that its short precharged witness did not exercise.

## Reset feedback defect

The old ICOMP current source reset ICOMP toward 3 V whenever the general
fault flag was asserted. That flag included ICOMP below 0.2 V. Near this
boundary the reset raised ICOMP and removed its own condition, producing
chatter and a timestep collapse at about 58.289846 ms in the initial
startup attempt. This is a model defect, not evidence of a hardware fault.

[TI's UCC28180 datasheet, SLUSBQ5D](https://www.ti.com/lit/ds/symlink/ucc28180.pdf),
sections 8.3.7, 8.3.8 and 8.3.17, distinguish general PWM/VCOMP fault handling
from the ICOMP 3 V reset. The latter is documented for OVP_H, ISOP and OLP.
The new reset condition uses those causes. UVLO remains a general inhibit;
an ICOMP reset specifically caused by UVLO is not established by that text.

## DC offset, dynamics and PWM

[TI expert support on ICOMP saturation](https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/1292214/ucc28180-v_icomp-saturation)
gives a nominal ICOMP offset of 0.72 V, a gain proportional to K1/M1, and
an upper clamp around 6 V. The answer qualifies its equation as a belief;
these are useful model assumptions, not guaranteed silicon limits.

For the negative ISENSE pin voltage, the resulting target is
`0.72 + K1*(-2.5*VISENSE)/M1`. Rewriting the amplifier in target-error form
must retain `GMI*M1/K1*(target-ICOMP)`. A worker's intermediate rewrite
omitted M1/K1. Host review caught this: that intermediate 70 ms completion
is not accepted as normal-operation evidence. Equation 100 independently
fixes the pole at `GMI*M1/(K1*CICOMP)`; a DC agreement cannot test it.

Datasheet Figure 28 shows a positive ramp plateau during minimum off time,
then a linear ramp. Its numerical baseline is unlabeled. A 0.72 V baseline
is inferred from the support answer and the minimum-off-time test at
ICOMP=0.72 V. The candidate ramp is therefore 0.72 V until nominal 570 ns,
then `0.72 + M2*(phase-570 ns)` with M2 converted from V/us. This inference
must remain visible in every acceptance claim. Minimum-off timing and the
current-loop pole require separate fixture checks before a long plant run.

The nominal 0.72/6 V clipping, +/-50 uA amplifier limit and ideal reset
dynamics are not temperature/tolerance or partial-power qualification.
The old TI average model is not a transient oracle and its different
offset/delay constants are not imported to make the candidate pass.

The source analysis was independently reviewed by a Luna subagent; the
parent checked the actual equations and the rendered Figure 28. Historical
experiment06 files remain unchanged. Passing its old functional fixtures
cannot erase the newly identified evidence limitation.

## Missing PWM memory exposed by the long run

The first completed 500 ms diagnostic had 19,863,514 rows, but the
independent parser rejected row 9,330,280. Two adjacent records have exactly
the same time, 0.256936160003138625 s, and different voltage/current values.
Nearby steps reach floating-point time resolution. The raw compressed trace
hash is `b5e121ebd8cef86e8fba061196a03a866e37afe8ac724f349767a2a2dd47018f`.
These are not identical rows that could be losslessly discarded. No
operating-point acceptance is taken from this run. It also retained biased
controller capacitor initial conditions and omitted the corrected clamp,
so it was already a diagnostic rather than the final cold-start fixture.

Host inspection of datasheet section 8.2's block diagram found another
missing state: the PWM comparator sets an S/R latch, and the oscillator / 
minimum-off circuit resets it. The surrogate instead gated directly from
the comparator. That permits feedback to withdraw a pulse within its own
cycle, contrary to the depicted latch. Such immediate feedback is a
plausible cause of the observed numerical chatter; fixing the omitted
latch is independently justified even before that causal hypothesis is
confirmed by a new full run.

`controller-probes/pwm-hold.cir` forces a comparator recrossing within a
cycle. The old surrogate fails the requirement to retain the gate pulse.
The corrected candidate must pass that test, the existing controller tests,
and a completed strictly ordered plant trace. No timestamp tolerance or
row deletion is used to turn the old run into a pass.
