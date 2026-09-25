# Cold-run settling analysis

This is a diagnostic analysis of the unchanged 500 ms normal-hysteretic-driver
cold trace. It does not alter the simulation source, relax the checker, or
claim a qualified operating point.

## Input identity and method

The input is the canonical compressed trace
`../trace.tsv.gz`, whose recorded and recomputed SHA-256 is
`dd20b2bb827a0fc876fa95f83fcb023e66e3207fcab854c13982e5ab3469d032`.
The one-pass Rust analyzer is [`analyze.rs`](analyze.rs); it was compiled with
`rustc --edition=2021 -D warnings -O` (source SHA-256
`81539dd7d7e09a91f7d2d2bc47a8c09bfdeada9965bc770728dd4606ff4306bd`). It pipes
`gzip -dc` into a buffered reader and never materializes the expanded trace.
The resulting cycle table is [`cycles.tsv`](cycles.tsv).
The compact receipt [`fit.rs`](fit.rs), compiled with the same flags (source
SHA-256 `b5687225093e470294a09df35e934e3ff4b2aefeb63ba9df9109a59e2710b108`),
reads only that table and writes the reproducible output in
[`fit-output.txt`](fit-output.txt).

```sh
rustc --edition=2021 -D warnings -O analyze.rs -o analyze
./analyze ../trace.tsv.gz cycles.tsv
rustc --edition=2021 -D warnings -O fit.rs -o fit
./fit cycles.tsv > fit-output.txt
```

Rows are integrated over integer 60 Hz periods. Cycles 15–29 cover the
0.250–0.500 s interval. `q_mean_v` and `en_mean_v` are voltage means (not
fractions); both are exactly 5 V in every analyzed cycle. The table also keeps
VB mean/min/max/ripple, absolute inductor-current peak, VD peak and gate peak.

## Measured late trend

The final three measured VB means are 375.392137548 V, 376.527130062 V and
377.555374379 V. Their span is 2.163236831 V, or 0.5763% using the first
cycle mean (the denominator used by the existing checker; 0.5746% using the
three-cycle average), matching the checker’s 0.5763% cycle-drift stop. Late mean increments
and ripple ratios were:

| transition | ΔVB mean (V) | next-cycle ripple ratio |
| --- | ---: | ---: |
| 20→21 | 1.903905 | 0.973280 |
| 21→22 | 1.763402 | 0.975981 |
| 22→23 | 1.650540 | 0.973761 |
| 23→24 | 1.536474 | 0.980615 |
| 24→25 | 1.436521 | 0.976787 |
| 25→26 | 1.319289 | 0.973770 |
| 26→27 | 1.225368 | 0.980786 |
| 27→28 | 1.134993 | 0.977300 |
| 28→29 | 1.028244 | 0.973532 |

A log-linear fit of the late increments (transitions ending at cycles 20–29)
gives a per-cycle ratio of 0.92466, equivalent to a rough 0.213 s time
constant, with 0.0155 RMS log residual. Fits starting at cycles 21 and 22
give ratios 0.92721 and 0.92651 (0.221 s and 0.218 s; 0.0091 RMS residual).
This is only an extrapolation of the observed trend; it is not a proof that
the plant remains in the same regime.

Under those fits, a 0.600 s endpoint (cycle 35) projects a final-three-cycle
span of about 1.35–1.38 V (0.355–0.363% using the first cycle as denominator)
and VB mean near 382.3–382.4 V. A 0.650 s endpoint (cycle 38) projects a span
of about 1.09–1.10 V (0.279–0.288% with that denominator) and VB mean near
384.1 V. The earlier, less-stationary
fit beginning at cycle 19 gives a lower endpoint (about 381.9 V at 0.600 s and
383.3 V at 0.650 s), which bounds model-form uncertainty more usefully than a
single point estimate.

The bounded next experiment should therefore use the prepared 650 ms source
extension. It provides three additional late cycles beyond the plausible
600 ms minimum and leaves the measured acceptance criteria unchanged. The
projection is a scheduling aid only: the extended trace must pass the existing
finite/strict-time and cycle-drift checks from direct measurement before any
endpoint is considered.

No thermal, fuse, hardware, or product qualification follows from this table.
