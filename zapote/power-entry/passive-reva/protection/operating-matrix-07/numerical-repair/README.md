# Finite PWM edge investigation

The earlier prescribed-voltage ramp fixture omitted the mixed-signal bridge.
These fixtures restore the actual ADC, DFF and DAC chain, including the
declared 1 ns DAC edge, and the downstream gate/blanking loads. They are
small numerical reproductions, not complete power-stage operating points.

Both `early/` and `late/` abort at the held-PWM 2.5 V crossing with
`Timestep too small`, while ngspice returns exit code zero. The original
inspector checked monotonicity alone; its zero exit on a truncated trace is
not successful simulation completion. `regression-results.json` supersedes
that result and requires the requested endpoint using the strengthened
diagnostic inspector. The full operating-point checker already required its
endpoint and did not have this gap.

## Controlled isolation

| Probe | Reaches requested endpoint? | Interpretation |
|---|---|---|
| Original, early and late | No | Failure does not require long elapsed time |
| Disable blanking current only | No | Blanking is not required for this failure |
| Disable PWM output only | Yes | Removing the output path removes this failure; not a functional fix |
| Make external driver transfer linear only | No | Failure moves to `pwm`; external driver threshold is not required |
| Preserve the finite held-PWM ramp at the output | Yes | Functional output reaches 15 V and downstream gate charges |

The controller's DAC already creates a finite 0–5 V ramp. The original
`Bgate` re-thresholds that ramp into an ideal 0/15 V discontinuity at 2.5 V.
In this mixed-signal fixture that discontinuity prevents the transient solver
from advancing through the edge. The isolated changes above localize the
problem to that re-thresholding, rather than to the blanking capacitor or
external driver alone.

The candidate in `../controller-finite-edge/ucc28180.inc` scales the existing
DAC ramp to the output supply instead. Its midpoint, latch logic and
fault/OVP/PCL masks remain intact. This retains the already-declared edge
duration, not a vendor-derived transition-time claim. All six existing
controller fixtures pass without changing their limits, including PWM
timing, pulse hold and protection assertions. Independent full cold-start
verification is required before attributing the complete plant's previous
stall/duplicate-time failure to this same mechanism.

The diagnostic inspector still labels its output DIAGNOSTIC_ONLY. Passing
an isolated endpoint test is never operating-point acceptance.

## Undefined-state guard

Independent review identified a compatibility requirement in the first
finite-edge candidate: the original PWM DAC mapped digital undefined to
2.5 V, which the old strict comparator treated as off. Proportional scaling
would instead produce 7.5 V. `unknown-state/` demonstrates this and
`full-unknown/` reproduces it with the actual controller source and a forced
undefined PWM-data input. The complete candidate in
`../controller-finite-edge-safe/` maps only the PWM DAC's undefined state to
zero. All six focused fixtures still pass and their traces are byte-identical
to the finite-edge intermediate version. The actual-model regression passes
with the guard and fails when it is removed.
