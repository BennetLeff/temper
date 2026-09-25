# Independent review of the same-raw reanalysis

This review covers the completed stage-2 run in this directory. It did not
rerun ngspice and did not modify the source case, raw gzip, tools, or reports.
The raw identity remains SHA-256
`9be2bbe73cd0aee5c6751566bfa818968deeb24d68d6b76d323f56f76cbfd05e`, with
6,025,180 captured rows. All four transport children exited zero and the
receipt remains `REVIEW_PENDING` with `acceptance:false`.

## What the reports establish

The adapter saw an F2-START case, with declared mutation
`0.0749999999999999972 s` and observed injection
`0.0749999995039753869 s`. It retained 2,046,772 prefault rows and all
6,025,180 original rows. It found no equal-time groups, no logic changes, and
the expected single detector rise. The event-aware validator likewise saw
6,025,180 rows, retained 4,960,695 rows, reported zero equal/crossing/boundary
groups, one F2 edge, no F2 edge before the retained region, no missing terminal
right context, and finite node extrema.

The validator's frozen-checker result is exactly:

```
Pass {
  fault_time: 0.07591460642363172,
  retained_off_delay: 1.0680936685103504e-7,
  channel_peak: 1.6814413348320123e-10,
  passive_peak: 1.2441723389869948
}
```

That modeled result is within the declared F2 event window around 0.075 s and
the 2 us turn-off budget. The adapter reports detector rise at
0.0759146064236317225 s and latch-off at 0.0759147132329985735 s. The frozen
node screens are all below their limits: `vd=167.1825 < 500 V`,
`vb=127.0538 < 450 V`, `sw=168.1441 < 650 V`, `gate=14.9822 < 25 V`, and
`i(Lboost)=14.5271 < 100 A`. The adapter's post-detector channel peak is
`1.6814e-10 A`; its injection-window peak was `3.8032 A`. The passive peak
reported by the validator is `1.24417 A`.

The frozen checker therefore establishes the modeled F2 fault predicate: a
detector edge in the event window, an F2-open transition before it, a healthy
prefault/armed window, node screens within limits, current cessation within
the 2 us budget, and the configured post-event observation/gap checks. The capture metadata separately records `solver_stopped`, 6,025,180 points,
and finite time. The immutable run parameters declare `TSTOP=0.089 s`.

## Causal limitation

The reports do **not** prove that the detector caused the current to cease.
The adapter's last channel current above 0.10 A is
`0.0759140103389961268 s`, about `596.085 ns` **before** the detector rise at
`0.0759146064236317225 s`. Latch-off follows the detector by only
`106.809 ns`, and the post-detector channel current is already `1.68e-10 A`.
Thus the trace passes the frozen modeled screens, but current cessation
precedes the modeled detector edge. It does not establish fuse clearing,
hardware causality, or a settled 400 V bus. Those remain hardware/model
correlation questions.

Parent endpoint correction: the validator checks the final timestamp but does not
print it. The separate complete decode in `../startup-compact-candidate-20/parent-full-scan.json`
reports all 6,025,180 rows, first time `2e-10 s`, and last time
`0.08900000000000001 s`. This directly establishes the endpoint. Its selected
row count is one lower because a literal 0.089 cutoff is one ULP below the
last timestamp; the full scan and validation retain and check that final row.

The result is useful as a complete, source-bound diagnostic transport and as
evidence that the current frozen predicates evaluate to `Pass` on this raw
trace. It remains `REVIEW_PENDING`, not an operating-matrix acceptance.
