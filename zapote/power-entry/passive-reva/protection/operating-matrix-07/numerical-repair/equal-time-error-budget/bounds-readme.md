# Equal-time event bounds (diagnostic only)

`bounds.rs` consumes the small `audit.rs --events` artifact, rather than the
30-million-row trace.  It validates the tab-separated schema, finite values,
nondecreasing event times, one context row per group, and a non-empty GROUP
state set.  A group must have both positive adjacent intervals; an incomplete
EOF group is rejected instead of fabricating a context.

For each group, every saved GROUP state and both adjacent context states are
included in the min/max interval.  This matters when a duplicate returns to
its starting value after an interior peak, and it keeps nonlinear products
bounded along an interpolated context-to-group trajectory.  The bound permits
an arbitrary value in that full hull at both adjacent endpoints:

```text
(t_group - t_left + t_right - t_group) * (f_max - f_min)
```

The complete adjacent widths are intentionally used whenever an interval
touches a requested window.  They are a safe overestimate when a group lies
outside the window or straddles a boundary (a deliberate factor-of-two
conservative charge relative to the half-width endpoint estimate).  Exact
binary64 timestamp
coincidences with `0.6`, `37/60`, `19/30`, or `0.65` are counted and reported;
they are not evidence of an internal solver step.  A future ULP perturbation
budget must remain conditional rather than being silently added here.

The scalar diagnostics are `vac=acsrc-acn`, `iin=-iVac`, `inputP=vac*iin`,
`loadP=v(load)^2/190`, `ac2=vac^2`, `i2=iVac^2`, and `VB=v(vb)`.  For
`inputP`, interval products of both independent ranges cover negative and
cross-zero values; square ranges include a zero interior minimum.  These
intervals are conservative for interpolated cross-variable states and are not
an assertion that the simulator followed any particular interpolation path.

The report also counts logic-state changes and reports the three original E3
saved states (Cbank, Clocal, and Lboost) as a numerically stable relative
spread plus sum-absolute adjacent impulses.  It is not a closed energy total:
selected-state list, omitted capacitances/inductances, and source anchors are
those documented in the parent [`README.md`](README.md).  No field is an
acceptance criterion or a replacement for a converged physical transient.

Build and tiny tests:

```text
rustc --edition=2021 -D warnings bounds.rs -o bounds
rustc --edition=2021 -D warnings --test bounds-tests.rs -o bounds-tests
./bounds-tests
```

`bounds-tests.rs` covers an interior return peak, both adjacent widths in a
linear VB bound, negative/cross-product intervals, an exact cycle-boundary
timestamp, and malformed schema.  The complete event artifact used for the
parent's 650 ms trace is a bounded 144 KiB input; this tool does not rescan the
raw trace.
