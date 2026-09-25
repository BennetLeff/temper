# Equal-time observable metric bound

Status: bounded math review only. No trace, checker, source, or acceptance
policy was changed, and this does not approve the rejected full-B trace.

This note gives a conservative, parent-evaluable bound for the effect of an
equal-time callback group on the existing observable integrals. It keeps all
rows and all extrema. It does not claim that a saved terminal trace proves
hidden controller state, instantaneous protection, or hardware behavior.

## Group geometry

Let one maximal equal-time group have serialized time `t` and rows whose
integrand values are `f_1 ... f_m`. Let the immediately preceding and
following *positive-time* rows be at `t_L < t < t_R`. For a final settled
window `[lo, hi]`, clip the neighbor widths to the window:

```text
delta_L = max(0, t - max(t_L, lo))
delta_R = max(0, min(t_R, hi) - t)
f_min   = min(f_1 ... f_m)
f_max   = max(f_1 ... f_m)
```

If a trapezoid implementation chooses any one group representative `f*`, the
two adjacent contributions are
`0.5*delta_L*(f_L+f*) + 0.5*delta_R*(f*+f_R)`. Therefore the worst difference
between any two representative choices is the conservative bound

```text
B_area(f, group) <= 0.5 * (delta_L + delta_R) * (f_max - f_min).
```

This uses all group extrema, not only the first and last row; a peak followed
by a return at the same serialized time cannot hide inside the bound. If the
group is at a window boundary, one clipped neighbor width is zero. A terminal group needs separate endpoint/stop evidence; absence of right
context alone does not distinguish a legitimate final output group from a stall.

For the final-window mean, divide `B_area` by `T = hi - lo`. Compute the
actual metric twice as well (first-row and last-row representative); the
formula is a conservative check on that observed difference, not a reason to
discard intermediate rows.

## Existing normalizer conventions and integrands

The source normalizer maps `v_ac = v(acsrc)-v(acn)` and
`i_ac = -i(Vac)` (`checker/normalize.rs:69–73`). It maps
`v_load = v(load)` and `i_load = v(load)/RLOAD` (`:73–75`); the campaign load
is 190 ohm. The checker then integrates these products in
`operating_point_checker.rs:225–229`.

Apply the group bound to these functions:

| Existing observable | Integrand `f` | Bound to compare |
| --- | --- | --- |
| `Vrms` | `v_ac^2` | `B_area/T` is a mean-square bound; evaluate RMS at both metric endpoints, or use the exact square-root interval. |
| `Irms` | `i_ac^2` | Same mean-square treatment. The sign reversal is already in the normalizer. |
| real input power | `v_ac * i_ac` | Signed product; group products cover actual rows. For interpolated states use interval corner products, which are conservative despite possible correlation. |
| load power | `v_load^2 / 190` | Positive product after the normalizer mapping. |
| mean bus voltage | `v_b` | `B_area/T` directly has volts. |
| each 60 Hz bus-cycle mean | `v_b` | Clip `delta_L/R` to that cycle and recompute each cycle mean. |

Derived values such as PF should be recomputed from the two policy results
and enclosed by conservative interval propagation. Agreement of first and last
choices alone cannot exclude an interior group extremum. For cycle drift, compare the two complete vectors of
cycle means and report the direct drift difference; a conservative scalar is
the sum of the largest absolute bound for the two cycles that determine the
max/min pair.

The existing checker’s thresholds remain the comparison margins: bus envelope
389.615 V +/-5%, cycle drift `<0.005`, input-current screen 15 A, VD 500 V,
VB 450 V, VDS 650 V, |VGS| 25 V, settled ARM/on fractions `>=0.99`, and the
existing energy tolerance `max(1 W, 0.5%*|Pin|)` (`operating_point_checker.rs:
284–328`). No new physical limit is introduced. If the bounded metric interval
crosses one of those existing boundaries, classify that metric as ambiguous;
if it stays on one side, the timestamp convention did not change its existing
screen classification.

## Known storage energy and endpoint handling

The checker’s modeled storage expression is

```text
E(VB,VD,IL) = 0.5*2240e-6*VB^2
            + 0.5*19.8e-6*VD^2
            + 0.5*180e-6*IL^2
```

(`operating_point_checker.rs:206–208`). For every equal group, report

```text
B_E_group = max(E(row in group)) - min(E(row in group)).
```

This is a separate observable spread. A `dt == 0` segment contributes zero
measure to a trapezoid integral, but a nonzero `B_E_group` must not be silently
converted into zero input/output power. If the group is exactly at the start or
end of the final energy window, evaluate `E(at_boundary)` under both first-row
and last-row conventions and report that endpoint ambiguity. If it is interior,
the endpoint `dE/dt` term itself is unchanged; still report the selected
same-time energy spread as a possible instantaneous modeled update. Neither
calculation closes unmeasured controller, switch, parasitic, or thermal energy.

The existing `energy()` expression is a modeled accounting term, not a proof of
total physical energy closure. A missing saved storage state is therefore a
model-bound caveat, not a reason to alter the timestamp parser.

## Extrema and discrete signals

Every row in every group must remain available to all-row extrema scans. The
existing checker already scans the complete trace for IL, VD, VB, VDS, and VGS
peaks (`operating_point_checker.rs:259–274`), so there is no “omitted peak”
error term when raw rows are preserved.

The full event audit found no same-time changes in the saved discrete columns
(`v(q)`, `v(en)`, `v(fault)`, `v(xu.raw)`, `v(xu.pwm_hold)`, `v(pwm)`,
`v(pwm_input)`, `v(xdriver.driver_req)`, `v(xu.ov)`, `v(xu.fault)`,
`v(xu.pcl_hold)`, and `v(xu.pcl_request)`). That is evidence about these
saved signals only. It does not qualify unsaved internal state. A future group
with a discrete toggle must retain the event in the report; a zero-duration
toggle can be invisible to a fraction integral even when a terminal settled
screen remains at 1.0.

## Binary64 time representation bound

At the full-B event range through 0.65 s, the largest binary64 spacing is
`u = 1.1102230246251565e-16 s`. The event audit counted 66 repeated adjacent
intervals. If each serialized timestamp is conservatively treated as having
an independent +/-0.5-ULP representation error, one interval-width error is
at most `u`, so the total absolute timestamp-width budget is

```text
66*u = 7.327471962526033e-15 s.
```

If the implementation elects to use +/-1 ULP per timestamp, use the explicit
two-sided bound `2*66*u = 1.4654943925052066e-14 s` instead. For an observable
whose absolute integrand is bounded by `F_max` over the retained trace, a
deliberately conservative normalized contribution is
`B_time <= N_time*u*F_max/T` (or twice that under the +/-1-ULP convention).
Use the observed raw-vector bounds for `F_max`; do not multiply unrelated
per-column extrema when the product range can be computed directly.

This is a conditional binary64 quantization sensitivity calculation only.
The retained .17e export round-trips the saved binary64 values; it does not
introduce the repeated times through insufficient decimal precision. The
66-times-ULP expression does not bound cumulative solver error or prove that
each hidden integration step had that duration. It does not reveal the solver’s
internal requested `CKTdelta`; claiming a sub-ULP internal step from the equal
serialized times would be speculation. The exact ngspice 45.2 source audit
already establishes the relevant accepted-output path and binary64 mechanism.

## Parent-evaluable acceptance of the diagnostic metric

For each existing observable, produce:

1. the unchanged strict result (the duplicate full-B trace remains rejected);
2. the first-row and last-row duplicate-policy metric values;
3. `B_area` from all group min/max values, `B_E_group` for modeled storage,
   and the optional binary64 `B_time` term;
4. the interval obtained by adding those bounds to the metric result; and
5. a comparison against the **existing** checker threshold or sign condition.

If the whole bounded interval stays within the same existing screen result,
the observable’s numerical classification is robust to the duplicate
representative. If it crosses a threshold, report that metric as ambiguous;
do not invent a tighter screen or erase rows. For all-row peaks, compare the
actual retained extrema directly because preservation makes their omission
error zero.

This test is enough to establish a modeled numerical-metric result after the
complete full run. It is not a new physical standard and does not turn the
rejected strict trace into an accepted baseline by itself. Hardware limits,
hidden states, and instantaneous protection remain the project’s existing
model-bound claims.


## Parent correction for clipped nonlinear interpolation

The half-width GROUP-range formula above applies when integrand endpoints
are selected directly. The actual checker clips intervals by interpolating
state first and then evaluating nonlinear products; GROUP products alone
need not enclose those values. The implemented conservative audit instead
forms interval hulls over LEFT, every GROUP row, and RIGHT (including
`vac = acsrc-acn`), bounds squared/product integrands by interval arithmetic,
and charges the **full** adjacent width times that hull's integrand range
whenever the segment intersects the measurement window. This deliberately
loose bound also covers both clipped endpoints varying. Boundary-energy
ambiguity is treated separately. First/last convention agreement is useful
corroboration, not a substitute for the interval bound.
