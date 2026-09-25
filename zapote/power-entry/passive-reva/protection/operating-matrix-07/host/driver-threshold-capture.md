# First-invalid capture: host assessment

The source-identical electrical model reproduced the original first invalid
pair at data rows 9,736,223/9,736,224, t=0.256990362212805523 s. The callback
snapshot and full exported trace agree. All sixteen requested internal signals
were captured. The simulator halted at 0.257011794868494181 s after 531.868818
wall seconds; both producer and compressor exited zero. The full trace
inspector correctly exited one: 9,737,177 finite rows, one nonincreasing
interval. This is successful diagnostic capture, not normal-point acceptance.

At the invalid step PWM input is 2.200000787605 V, just above the authored
driver's 2.2 V switching threshold. Driver request is 15 V while the delayed
driver output remains approximately zero; controller raw PWM is high and
fault, OVP and PCL masks are inactive. The preceding time steps collapse to
one binary64 ULP, 5.551115123e-17 s. The retained earlier trace shows tiny
steps already around 60.507 ms. Thus this is not simply a repeated static
output row or a machine-utilization problem.

This locates a concrete boundary to test. It does not by itself prove which
full-plant feedback path makes the discontinuity numerically pathological.
The short prescribed-input bridge/RC fixture passes with both a hard driver
threshold and a finite diagnostic transition, so it does not reproduce the
complete failure. A bounded full-plant sensitivity experiment changes only
the driver's PWM transfer; separately, the unchanged TI driver model is being
checked with active PWM, disable and AUX-loss stimuli before any adoption.
