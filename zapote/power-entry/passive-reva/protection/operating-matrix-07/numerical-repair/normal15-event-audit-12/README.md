# Normal15 event-aware numerical audit

This standalone Rust tool audits the exact 15-vector normal trace emitted by
the native adapter.  It is diagnostic only and does not replace the retained
checker or issue an operating-point verdict.  The input header must be exactly

```text
time v(acsrc) v(acn) i(Vac) v(load) v(vb) i(Lboost) v(vd) v(sw) v(gate) v(q) v(en) v(fault) v(vcomp) v(icomp)
```

The stream is checked for finite fields, nondecreasing time, configured start
and end, and the original switching step ceiling (default
`1/(8*130000) = 9.615384615e-7 s`).  Use an explicit load resistance and event
artifact path in a campaign invocation:

```text
normal15-event-audit --end-s 0.65 --rload 190 --events normal15-events.tsv < normal15.tsv > normal15-audit.txt
```

Start and end are checked within an explicit `1e-9 s` endpoint tolerance to
accommodate the native writer's first scheduling quantum (the tiny adapter
probe begins at `2e-10 s`); this tolerance does not alter any row or switching
step check.

Every exact-equal timestamp group retains all GROUP rows and immediate
LEFT/GROUP/RIGHT context.  Adjacent groups may share context timestamps; each
group is validated by source-row adjacency.  A terminal group without a RIGHT
row is counted as missing context and is not assigned an invented bound.

The report keeps stable factored E3 changes for the bank capacitor, local
capacitor, and boost inductor, including max relative spread and sum-absolute
same-time impulses.  Time and logic columns (`q`, `en`, `fault`) report exact
changes but `max_normalized=N/A`; only physical voltage/current columns use
`reltol=2e-4` with `vntol=1e-7` or `abstol=1e-10`.

The report labels all-adjacent-row deltas separately from same-time-only
deltas.  Same-time rows are the event diagnostic; all-row values are context
for spotting ordinary switching slew.  Equal-time buffering is capped at one
million rows per group and fails closed beyond that bound.

Event bounds use the full LEFT/GROUP/RIGHT state hull and the complete adjacent
width `(t_group-t_left)+(t_right-t_group)`.  This is intentionally a loose
factor-of-two estimate for endpoint substitution and covers nonlinear
cross-variable products.  Functions are `vac=acsrc-acn`, `iin=-iVac`,
`inputP=vac*iin`, `loadP=v(load)^2/Rload`, `ac2=vac^2`, `i2=iVac^2`, and
`VB=v(vb)`.  The final three intervals are derived from the configured end as
`[end-3/60,end-2/60]`, `[end-2/60,end-1/60]`, and `[end-1/60,end]`; exact
boundary coincidences are counted, not treated as internal solver-step
evidence.  These bounds and E3 values are diagnostics, not acceptance limits
or a closed energy model.  A terminal missing-right group still contributes
its saved E3/logic diagnostics but receives no fabricated interval bound.

Build and tests:

```text
rustc --edition=2021 -D warnings audit.rs -o normal15-event-audit
rustc --edition=2021 -D warnings --test tests.rs -o normal15-event-audit-tests
./normal15-event-audit-tests
```

Tests cover exact event contexts, E3 interior peak/return, asymmetric
differential AC², standard-resistance load power, cycle boundaries, terminal
groups, nonfinite/backward rows, exact headers, max-step rejection, and N/A
logic normalization.  No full simulation is run by this directory.
