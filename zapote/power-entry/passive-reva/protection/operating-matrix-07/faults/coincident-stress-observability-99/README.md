# Coincident stress observability candidate 99

This is a bounded diagnostic candidate derived from the frozen
`faults/bypass-observability-55/main.rs` instrument. It is intended for parent
review and a later saved-archive run; it has not been run on a campaign raw
archive and makes no protection or hardware claim.

The original fault42 validation and report fields are retained. The added
`post_injection.coincident_currents` block tracks six named currents:
`i(Lboost)`, `i(Vchannel)`, `i(Vbody)`, `i(Vf2sense)`, `i(Vdboost1sense)`, and
`i(Vdboost2sense)`. For each current it records the signed overall maximum by
absolute value, with row/time, q/en/gate/fault and all six current values; the
corresponding maximum restricted to the same row satisfying
`q <= 2.5`, `en <= 2.5`, and `abs(gate) <= 0.2`; the count of such off rows;
and the count among them with absolute current above 0.1 A. Equal timestamps
remain separate samples and counts are sample counts, never durations.

The candidate preserves the frozen checks for exact 42-column schema, finite
fields, nondecreasing timestamps, one post-cutoff marker edge, endpoint
`0.662 s`, and a strictly later sample. It accepts no result. A future run
must use a complete, hash-bound saved archive and a unique no-clobber output.

Build and unit-test commands (already completed):

```sh
rustc --edition=2021 -D warnings faults/coincident-stress-observability-99/main.rs \
  -o /private/tmp/matrix07-coincident99-candidate
rustc --edition=2021 -D warnings --test faults/coincident-stress-observability-99/main.rs \
  -o /private/tmp/matrix07-coincident99-tests
/private/tmp/matrix07-coincident99-tests
```

Result: 10 tests passed, including same-row coincidence versus different-row
non-coincidence, negative-current absolute peaks, duplicate timestamps,
nonfinite/backwards/header/endpoint and marker validation.

Source SHA-256 (candidate):
`159db79ad627bd8ad7d37e252c697909b3130ef9bc9c5c2b11e8e3c04bdaf9b0`

Frozen source SHA-256 (55):
`e14d67e007466f087d71e0d933ac6d985f80efb7c6926058ff781bc67e3b081a`

Candidate binary SHA-256:
`1655945783315d6830921ffac84301a37f5ddae7199e59d5359a78cebe13a1ec`

