# Isolated 2.5 V hard-boundary reproduction

This fixture is a bounded experiment, not a production-model change. It
copies the stalled surrogate's hard comparisons for `Bgate` and `Bblank` and
the protection path's `Rpwm/Rpwmpd/Bdriver_req/Rdriver_delay/Cdriver_delay`,
`Rdriver/Rgate/Rgs`, plus the power-stage `Cgd/Cgs/Csw` values. `Cblank=1 pF`
and `Bblank` are copied verbatim. The held PWM source is a finite PWL ramp
through 2.5 V; the warm fixture stays at 2.4999999 V then crosses to
2.5000001 V around the absolute halt time.

The original decks use `ngspice-45.2` with default analog tolerances,
`set numdgt=17`, and `set wr_singlescale`. The maximum transient step is 1 ns
for the 1-us edge and 1 us for the 351.5-ms edge, so the long test has about
351,533 rows rather than forcing 351 million rows. The Rust reducer
(`analyze.rs`) accepts the resulting strict 9-column scale/value output and
checks finite, increasing time before computing min dt, 2.5-V crossings,
gate transitions, and blank transitions.

An initial `.tran 1n` large-edge invocation was deliberately terminated by
the bounded command timeout before completion (it would require roughly 351
million nominal steps). It was not used for any result. The final runs use a
1-us maximum step and preserve 17-digit `wrdata` output; the earlier default
8-digit output was rejected by the strict reducer because rounded timestamps
created duplicate times.

| fixture | rows | min dt (s) | crossing time (s) | crossing dt (s) |
|---|---:|---:|---:|---:|
| `boundary-small.cir`, edge 1 us | 1,214 | 1.0000000000000001e−11 | 1.0005000000000004e−6 | 1.0000000000000751e−9 |
| `boundary-large.cir`, edge 351.508835331273 ms | 351,533 | 2.6913438144759994e−10 | 0.3515088374491286 | 2.2421445811104945e−9 |
| `boundary-warm.cir`, same large edge, 2.4999999→2.5000001 V | 351,533 | 2.6913438144759994e−10 | 0.3515088374491286 | 2.2421445811104945e−9 |

The large-edge and warm runs both produce one hold crossing and one gate
transition. At the crossing the held node is 2.500000042 V, `pwm=15 V`,
`blank=1.121072302e−3 V`, and the delayed gate is 7.041442605e−3 V. The
absolute-time fixture therefore does not reproduce the captured sub-ULP
interval by itself, even when the held value is warm and only ±0.1 µV around
2.5 V. This is evidence against the isolated hard `Bgate`/`Bblank` boundary
being sufficient; it does not rule out interaction with the complete
controller/state/event network.

Commands:

```sh
ngspice -b boundary-small.cir > boundary-small-final.log 2>&1
ngspice -b boundary-large.cir > boundary-large-final.log 2>&1
ngspice -b boundary-warm.cir > boundary-warm.log 2>&1
rustc --edition=2021 -O analyze.rs -o /tmp/matrix07-repro-analyze
/tmp/matrix07-repro-analyze boundary-small.raw > small.stats
/tmp/matrix07-repro-analyze boundary.raw > large.stats
/tmp/matrix07-repro-analyze boundary-warm.raw > warm.stats
```

Source hashes are in `SHA256SUMS`. No canonical deck or model was edited.
