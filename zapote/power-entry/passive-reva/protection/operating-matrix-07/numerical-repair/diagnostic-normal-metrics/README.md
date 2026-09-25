# Normal-run VB cycle diagnostic

`metrics.rs` is a diagnostic-only streaming analyzer for a complete normal raw
31-column TSV trace.  It requires the named columns `time`, `v(vb)`,
`i(Lboost)`, `v(vd)`, `v(sw)`, and `v(gate)`, validates finite fields and
nondecreasing timestamps, then reports the final three explicit 60 Hz intervals:

```text
[0.600000000000000, 0.616666666666667]
[0.616666666666667, 0.633333333333333]
[0.633333333333333, 0.650000000000000]
```

For each interval it clips the positive-duration row segments to the interval
and integrates `v(vb)` with the linear trapezoid rule.  Exact-equal timestamp
rows have zero duration, but remain in the stream: their values contribute to
prefix extrema/stress and the last value is the right endpoint for the next
positive-duration segment.  The analyzer reports means and VB min/max for all
three cycles only when the requested endpoint and each interval are covered.
Missing endpoint, backward time, nonfinite data, or an incomplete interval is a
hard diagnostic error and produces no misleading cycle means.

The report also includes first/last time, row count, duplicate-group/repeated-row
counts, largest positive time gap, and whole-prefix extrema for inductor current,
VD, VB, switch-node voltage to ground, and absolute gate voltage.  It does not
calculate energy, impose ripple/drift thresholds, or issue PASS/accepted or
qualification claims.  It reports the diagnostic-only range of the three means
divided by the first mean when that denominator is positive; a zero or negative
first mean is reported as undefined.  Equal-time transients therefore remain an
explicit model limitation of the trapezoid calculation.  Cycle VB extrema still
include every raw row whose timestamp is inside the closed interval, including
internal duplicate peaks; those rows have no duration in the integral.

Build and test without a workspace or dependency:

```text
rustc --edition=2021 -D warnings metrics.rs -o metrics
rustc --edition=2021 -D warnings --test tests.rs -o metrics-tests
metrics-tests
metrics < trace.tsv
```

`tests.rs` covers known linear-ramp integrals at exact cycle boundaries, one
positive segment spanning all three cycles, duplicate-row peaks with
zero-duration handling, missing endpoint, backward time, nonfinite data, and
exact boundary coverage.  No simulation is run by this folder.
