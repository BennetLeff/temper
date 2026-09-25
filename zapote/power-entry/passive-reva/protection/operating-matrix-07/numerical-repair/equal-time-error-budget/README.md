# Equal-time event and numerical energy diagnostic

`audit.rs` is a streaming diagnostic for a raw 31-column operating trace.  It
does not edit an acceptance checker, change tolerances, or classify a circuit as
qualified.  The parent runner may pipe a complete TSV (after decompression) to
it and select an event artifact:

```text
rustc --edition=2021 -D warnings audit.rs -o audit
audit --events equal-time-events.tsv < trace.tsv > equal-time-summary.txt
```

Every exact-equal timestamp group is written to the event artifact with all of
its rows and its immediate left/right context.  The artifact is bounded by the
number of equal-event rows and contexts; it is not a duplicate of the full
trace.  The summary reports group/repeat counts, first/last group times, largest
group, and missing right-context groups.

For each adjacent pair inside an equal group, the tool reports per-column
absolute and normalized changes.  The normalization uses the source options
`reltol=2e-4`, `vntol=1e-7` for voltage-like columns, and `abstol=1e-10` for
current columns:

```text
normalized = abs(delta) / (reltol*max(abs(a),abs(b)) + voltage_or_current_absolute_tolerance)
```

`within_solver_tolerance` is a numerical diagnostic.  It is not proof that a
repeated timestamp is acceptable or physically harmless.

Time and controller/discrete-state columns are deliberately reported with
`max_normalized=N/A`: source-scaled solver tolerances do not give a meaningful
error budget for an event timestamp or a logic level.  Their exact change
count and largest absolute delta remain visible.  Voltage and current columns
retain the normalized diagnostic above.

The selected-state energy section uses signed
`0.5*C*(b-a)*(b+a)` for capacitors and the same expression with `L` and current
for `Lboost`.  `Cgd` uses the saved differential state `v(gate)-v(sw)`.  Signed
and sum-absolute values are retained for every pair, plus a sum-absolute upper
contribution bound over the selected states only.  The parameter values and
source anchors are fixed in [`parameter-spec.txt`](parameter-spec.txt), whose
SHA-256 is printed in the report.  The selected list is intentionally not a
closed circuit-energy total: omitted terms include bridge/boost/body-diode
junction capacitances, `Cvsense`, `Cvcomp_s`, protection-divider/timer/fast-path
capacitors, source/stray inductances, device channel energy, and any un-saved
controller state.

`tests.rs` covers signed energy cancellation versus sum-absolute disturbance,
common-mode rejection for `Cgd`, adjacent-group contexts, EOF context loss,
identical rows, duplicate peaks, malformed headers, backward time, and
non-finite data.  Tests and the warning-clean standalone build use tiny
synthetic traces only; no long trace or simulation is run here.
