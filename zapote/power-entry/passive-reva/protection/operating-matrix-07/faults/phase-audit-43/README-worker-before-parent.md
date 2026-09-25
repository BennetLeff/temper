# Phase-audit 43 diagnosis: equal-time source conflict

Status: diagnosis only. This note does not change `phase-audit-35`, the
fault checker, the captured raw trace, or any acceptance result.

## Evidence currently available

The complete F2-CREST38 capture is bound by raw SHA-256
`d78e8e2f7c28b8ba9c10ce499af2813202ede8b2e173c39cfdc0ee3d650484fd`, with
32,237,324 decoded rows and endpoint `0.662 s`. The independent phase scan
completed with exit 1 and report:

```json
{"status":"REJECTED","acceptance":false,"error":"conflicting equal-time source values at an event/local interval are indeterminate"}
```

The independent prefault scan did establish one marker edge at
`0.654166666170675426 s`, with edge-row `v(acsrc,acn)=169.705627484768428 V`.
Reanalysis 40 now reports 39 equal-time groups (178 raw rows), with
`logic_changes=0`, and all transport/validator children exited zero. Its
machine-readable local subset is retained in
`measured-equal-groups.json`. There are exactly two groups in
`[0.6500000000000, 0.6583333333333] s`:

| group time (s) | rows | marker values | source range (V) | spread (V) | strict left `(t,V)` | strict right `(t,V)` |
|---|---|---|---:|---:|---|---|
| 0.651585501386003 | 30186531--30186532 | {0} | [95.50340201418759, 95.50340201418760] | 1.42e-14 | (0.6515855013860029, 95.50340201418360) | (0.6515855013860031, 95.50340201419557) |
| 0.654166666666700 | 30640147--30640150 | {5} | [169.70562748477140, 169.70562748477144] | 2.84e-14 | (0.6541666665009511, 169.70562748477104) | (0.6541666666667001, 169.70562748477138) |

Both have strict-time left/right contexts; their source values are listed in
the JSON receipt. The observed injection edge from the independent prefault
scan is `0.654166666170675426 s`, while the nearest equal-time group is
`0.654166666666700 s` (delta `4.9602455476e-10 s`). That group has no marker
state change (`threshold_crossing=false`, all group markers 5); the left context
is already above threshold and the right context remains high. Thus the
measured equal-time source conflicts do not themselves contain the marker
transition, although the phase scanner's strict event-neighbor receipt must
still be retained for the exact edge ordering.

The maximum local source spread is `2.842170943040401e-14 V`, roughly
`1.675e-16` of the 169.7056 V crest and far below the 1% crest allowance
(`1.6970562748476843 V`). This is a magnitude observation only; it does not
turn the rejected phase report into a pass or replace a measured local peak.

## Why phase-audit-35 rejects

`phase_audit.rs` increments `equal_source_conflicts` whenever adjacent rows
have identical timestamps, different source values, and that timestamp lies in
the declared local interval (`.650 .. .6583333333333 s`). `finish()` rejects if
the count is nonzero. This is independent of the magnitude of the difference;
even a sub-ulp change is currently classified as indeterminate. Equal-time
marker threshold changes are a separate hard rejection and must remain hard:
the marker transition has no defined temporal ordering. Initial-high markers,
backwards time, and missing strict-time event/peak neighbors likewise remain
invalid.

## Smallest sound route after the context report

Preserve every row and every equal-time group. Do not select first/last rows or
interpolate through the group. For each equal-time source group in the local
interval, report timestamp, row ids, marker values, and the observed source
range `[min(v), max(v)]`; reject any group containing a marker state change.

For a crest claim, use a conservative range test. Let `[Elo,Ehi]` be the
absolute-source range of the edge group and `[Plo,Phi]` the absolute-source
range of the accepted local-peak group(s), with strict positive-time neighbors
on both sides of the plateau. A sufficient all-orderings test for the existing
1% amplitude criterion is:

```text
Elo >= (1 - 0.01) * Phi
Ehi <= (1 + 0.01) * Plo
```

The common simpler bound `Elo >= 0.99 * Phi` is valid only when the peak range
is known to contain the edge range (as it normally will when `Phi` is the local
maximum); the report should still emit both ranges so that assumption is
reviewable. The local peak must be interior to the interval and bracketed by
strictly earlier/later timestamps. A tied peak magnitude at distinct times is
not automatically an amplitude failure, but it must be represented as a
plateau/range and retain its strict outer neighbors rather than silently
choosing one row.

For a zero claim, use the conservative lower bound on the local peak:

```text
Ehi <= 0.01 * Plo
```

and require `Plo > 0` plus the same strict bracketing. This avoids treating an
ambiguous equal-time group as exactly zero merely because one member is zero.

These bounds are evidence rules, not an acceptance change yet. They can only be
considered after reanalysis reports the actual ranges and shows that the marker
edge itself is unambiguous. Until then, retain the phase-audit rejection.

For this measured capture, a still smaller successor rule can avoid selecting a
member of any equal-time group. Let `D` be the maximum source-voltage range of
any local equal-time group (`D = 2.842170943040401e-14 V` here), let `E` be the
edge-row source value from the independent edge report, and let `P` be the
maximum absolute source value over all retained local samples. Since absolute
value is 1-Lipschitz, all choices within an equal-time group lie in
`[max(0,|E|-D), |E|+D]`, and a local maximum can be bounded below by
`max(0,P-D)`. A conservative crest screen is therefore

```text
max(0, |E| - D) >= 0.99 * P
```

and a conservative zero screen is

```text
|E| + D <= 0.01 * max(0, P - D)
```

These retain every row, preserve the original 1% criterion, and do not infer a
temporal order inside a duplicate group. They still require the existing strict
event/peak bracketing and hard marker-transition rejection. They are a proposed
diagnostic successor only; `phase-audit-35` remains unchanged.

## Successor implementation candidate

`phase_audit.rs` is a standalone streaming candidate. It requires the same
exact fault42 schema and finite/nondecreasing input, consumes every row, and
keeps only the current timestamp group plus scalar extrema and edge/peak
contexts. It rejects missing startup, incomplete endpoint/local coverage,
initial-high markers, backwards time, equal-time marker threshold changes,
multiple rising edges, event-time error above 2 ns, and missing strict-time
neighbors. A later larger source value in the same timestamp group is included
before that group is considered as a peak.

The output status is `PHASE_BOUNDS_REPORTED` with `acceptance:false` and
`qualification:NOT_CLAIMED`. `sufficient_bound_pass` is diagnostic only; it is
not a protection or operating-point verdict. Separate groups with equal peak
magnitudes are counted with first/last times and are not described as one
temporal plateau. Counts are named `local_equal_group_raw_rows` and
`local_equal_groups`; they count rows/groups inside the declared local
interval, not all duplicate timestamps in the trace. Bound arithmetic is
rounded outward by one representable binary64 step (including the observed
source-spread `D` and the crest factor) and overflows fail closed. The report
emits both `max_source_spread_v_D_observed` and the conservative
`max_source_spread_v_D_bound`. Both the first and last maximal groups must have
strict interior neighbors; a tied maximum at the local interval boundary is
rejected.

Build and unit-test commands:

```sh
rustc --edition=2021 -D warnings --test phase_audit.rs -o /private/tmp/matrix07-phase-audit43-tests
/private/tmp/matrix07-phase-audit43-tests       # 10 passed
rustc --edition=2021 -D warnings -O phase_audit.rs -o /private/tmp/matrix07-phase-audit43
```

Source SHA-256: `c4640136e0ecb53d179b5702cc59779155a6ea6a90289ca4e8eaef75432f447d`.
Test binary SHA-256: `8e12b5ac3929dd2f650b32b5c5e760cbf0a91f376b3fbb82ede3a0bb77bba0e3`.
Diagnostic binary SHA-256: `039857a25c5aa8fbb1a8c5d138c3b4031bec4cef2beb4437383b445d11dddd29`.
No full raw scan was run by this candidate and no phase35/checker source was
modified.

The reanalysis receipt used to produce this note emits, for every conflicting
equal-time group:

* timestamp and contiguous row ids;
* marker values and whether a threshold state changes;
* source values and absolute range;
* whether the group is the first rising-edge group, an edge neighbor, or a local
  peak candidate; and
* strict-time rows immediately before and after the group.

The receipt binds the unchanged raw SHA-256 and child exit statuses. The
measured ranges are sufficient to exercise the successor diagnostically, but
the original phase35 rejection remains frozen and no protection verdict is
promoted by this candidate.
