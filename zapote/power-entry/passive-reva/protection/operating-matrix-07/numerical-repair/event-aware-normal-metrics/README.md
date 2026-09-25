# Event-aware normal metrics (diagnostic only)

`metrics.rs` is a standalone, streaming diagnostic evaluator for the maintained
12-column operating trace. It does not replace
`../../checker/operating_point_checker.rs`, does not change its acceptance
policy, and never prints an engineering or product PASS. A successful run ends
with `engineering_screen=REPORTED_NOT_ACCEPTED` and
`qualification=NOT_CLAIMED`.

The evaluator keeps the last three mains cycles plus the configured gap window,
rather than loading a full trace. This is bounded window storage (roughly
three cycles of rows at the source sample rate), while the scalar whole-prefix
peaks and transition counters are retained for the complete input. Equal-time
rows are retained for extrema and event diagnostics. They contribute zero area
to trapezoidal integrals, and the last row in an equal-time group feeds the
following positive-time segment. There is no timestamp snap tolerance:
cycle boundaries must match an input timestamp exactly or be linearly
interpolated between adjacent positive-time rows.

The evaluator rejects missing or malformed headers, non-finite values,
backwards time, gaps above `--max-gap-s`, optional switching steps above
`--max-step-s`, missing startup, insufficient three-cycle coverage, and an
endpoint that does not equal `--end-s`. It reports RMS input/load values,
real input/load power and PF, bus extrema/drift and cycle means, stable
three-state energy change (factored difference of squares), equal-time
storage impulses, whole-prefix peaks, state fractions/transitions,
all-interval and equal-time-only column deltas, and boundary ambiguity.
Derived screens are reported for review only.

## Build and tests

From this directory:

```sh
rustc --edition=2021 -D warnings --test metrics.rs \
  -o /tmp/matrix07-event-metrics-tests
/tmp/matrix07-event-metrics-tests

rustc --edition=2021 -D warnings -O metrics.rs \
  -o /tmp/matrix07-event-metrics
```

The binary reads stdin by default. `--input FILE` is also supported.
`--end-s SECONDS` is required; `--cycles 3` is explicit and currently the
only accepted cycle count. For traces with intentional switching gaps, the
caller may pass `--no-switch-check` while retaining the gap check:

```sh
gzip -cd ../event-aware-normal-metrics-oracle/base.tsv.gz \
  | /tmp/matrix07-event-metrics --end-s .05
```

## Oracle evidence

The independent fixtures in
`../event-aware-normal-metrics-oracle/` are not simulations or acceptance
receipts. The strict base trace is accepted by the unchanged checker; the
three variants are deliberately rejected by it because they contain exact
equal-time groups.

The diagnostic evaluator was run against all four compressed fixtures after
the exact-f64 endpoint/boundary serialization check:

* base: exit 0, `vrms=120.208153`, `irms=3.535534`,
  `real_input_power_w=425.000000`, `load_power_w=425.000000`,
  `engineering_screen=REPORTED_NOT_ACCEPTED screens=0`;
* equal-time exact: exit 0, one duplicate row, no boundary ambiguity;
* equal-time stress peak: exit 0, whole-prefix `vds_v=700.000000`,
  one reported screen, no acceptance claim;
* equal-time cycle boundary: exit 0, whole-prefix `vb_v=405.000000` and
  `vd_v=405.000000`, `boundary_duplicate_ambiguity=true`, and a non-zero
  selected equal-time storage impulse.

The source of truth for the 12-column strict checker is bound by SHA-256 in
`manifest.json`; fixture bytes and their exact timestamp assertions remain
in the oracle directory. The evaluator has no hidden total-energy-closure
requirement and says nothing about thermal, switching-loss, hardware, or
product-compliance qualification.
