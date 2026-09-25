# Adapter validation receipt

No long power-stage simulation was run for this readiness slice.

Commands:

```text
rustc --edition=2021 -D warnings --test fault_normalize.rs \
  -o /tmp/temper07_fault_normalize_tests_warnings
/tmp/temper07_fault_normalize_tests_warnings
```

Result: **9 passed, 0 failed**.

The controls cover:

* positive F2 case with separate `v(acsrc)`/`v(acn)` columns;
* positive ngspice sensor names (`vchannel#branch`, `vbody#branch`, and the
  three `v...sense#branch` currents) plus direct `v(acsrc,acn)`;
* declared F2 kind with the wrong mutation (no `f2ctl` falling edge);
* missing required channel column;
* duplicate header anywhere in the raw table;
* nonmonotone time;
* `NaN` in an unused extra column;
* finite source columns whose subtraction overflows the derived AC voltage;
* the actual streaming `BufRead`/`BufWriter` path preserving both exact
  headers.

The positive fixture deliberately keeps channel current above 0.10 A after
both the detector edge and the modeled latch/gate-off edge. The receipt checks
that post-detector and post-latch peaks/timestamps are reported separately;
they are not relabeled as post-injection measurements.

The executable build also passed `-D warnings` and is available as
`/tmp/matrix07-fault-normalize` for host review. No output from this adapter
has been treated as a circuit or protection acceptance result.
