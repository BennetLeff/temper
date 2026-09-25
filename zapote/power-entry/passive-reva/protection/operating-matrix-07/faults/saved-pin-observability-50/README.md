# Saved pin observability scan

`main.rs` is a read-only Rust scanner for an already decoded F2-CREST
`fault42` stream. It does not invoke ngspice, read the raw binary, or accept
the fault result. The input is the exact 42-column TSV emitted by the existing
decoder/adapter contract; columns may be reordered, but names must match
exactly (case-insensitively) and every row must contain finite values.

The scanner requires a nonempty stream beginning within 1 ns of `t=0`,
nondecreasing time (equal timestamps are retained), and an endpoint within 1 ns
of `t=0.662 s`. It identifies exactly one low-to-high `v(fault_inject)` edge
from the rows. A threshold transition at an equal timestamp is rejected as
ambiguous. The healthy window is `[0, 0.65 s]`; the post-injection window starts
at the observed edge time and ends at the trace endpoint.

For the full, healthy, and post-injection windows it records row counts,
timestamped extrema for `v(isense)`, `v(xu.pcl_hold)`,
`v(xu.pcl_request)`, external `v(fault)`, internal `v(xu.fault)`,
`v(fault_inject)`, and `v(f2ctl)`, plus counts of ISENSE samples outside TI's
recommended `[-1.1, 0] V` and absolute `[-24, 7] V` ranges. These are
observability measurements only. The JSON always carries `"accepted":false`
and explicitly makes no PCL-accuracy, diode-current, vendor, hardware, SOA, or
thermal qualification claim. The external `v(fault)` and internal
`v(xu.fault)` fields are reported separately to prevent index confusion.

Build and run the bounded unit tests without external crates:

```sh
rustc --edition=2021 -D warnings --test main.rs \
  -o /private/tmp/matrix07-saved-pin-observability-50-tests
/private/tmp/matrix07-saved-pin-observability-50-tests
rustc --edition=2021 -D warnings -O main.rs \
  -o /private/tmp/matrix07-saved-pin-observability-50
```

The standalone invocation is:

```sh
/private/tmp/matrix07-saved-pin-observability-50 \
  <decoded_fault42.tsv> <observability-report.json>
```

The current tests cover valid equal-time retention, nonfinite data, backward
time, equal-time marker transitions, schema width/name errors, initial-high
markers, multiple edges, and endpoint mismatch. No full F2-CREST scan was run
by this bounded implementation; the parent may apply it to the preserved raw
trace after review.

Parent review: use `/private/tmp/matrix07-saved-pin50-parent - new-report.json` for piped input. Existing output is refused. Ten unit tests and six independent CLI probes passed. The named healthy window is a time selection; this scanner does not establish healthy operation, source phase or maximum time gaps. Those claims require the separately accepted source-bound F2-CREST38 prefix/phase receipts. Row counts are not durations.
