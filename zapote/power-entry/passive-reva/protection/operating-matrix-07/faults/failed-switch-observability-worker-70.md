# Applicability review: bypass55 observability on settled fault archives

Date: 2026-09-21. This is a read-only tool applicability review. It does
not run the diagnostic, scan an archive, launch a solver, or produce an
acceptance result.

## Decision

`/private/tmp/matrix07-bypass55-parent` can be applied **unchanged as a
bounded diagnostic** to the own fault42 archives for SW-SHORT, BOTH-SHORT,
and DIODE-SHORT, provided each archive is independently source/tool bound and
the decoder output is the reviewed exact 42-column fault42 schema. All three
prepared cases use the same `.662 s` endpoint and late fault mutation at
`.6541666666667 s`; the tool's fixed endpoint and post-`.650 s` injection
guards therefore cover their declared timing. It does not need to know the
fault kind to parse or summarize the trace.

This is observability only. It must be run once per saved archive after the
full runner has completed, retaining every runner/decoder/adapter/validator
exit and the report hash. It is not a replacement for the own healthy-prefix,
phase, endpoint, event, or electrical reviews. The initial F2-ZERO pipeline
header failure remains an open reason for the parent to decide whether the
runner output is usable.

## Guards and coverage

The frozen binary is bound by `faults/bypass-observability-55/parent-review.json`
(`main.rs` SHA-256 `e14d67e007466f087d71e0d933ac6d985f80efb7c6926058ff781bc67e3b081a`,
binary SHA-256
`3bff9b4312cf9bb3c2118219e0f3bc5406482d8c2b83b728ad851b663bb40f6c`). Its
schema check requires exactly the 42 named columns (order may vary), with no
duplicates or extras. Every field must parse as finite numeric data. It
rejects a negative or late start, backward time, an initially-high marker,
multiple marker rises, a marker fall, an equal-time marker threshold
transition, an endpoint other than `.662 s` within 1 ns, and a missing sample
strictly after the marker. Input lines are capped at 16 KiB and output uses
`create_new`.

After the sole post-cutoff `v(fault_inject)` rising edge, it retains sampled
extrema and first/last times for `v(fault)`, `v(q)`, `v(en)`, `v(gate)`,
`i(Vchannel)`, `i(Vbody)`, and `i(Lboost)`. It also counts rows with
`abs(i(Vchannel)) > 0.1 A`, `abs(v(gate)) > 0.20 V`, `v(q) > 2.5 V`,
`v(en) > 2.5 V`, and rows where all three sampled off predicates hold:
`q <= 2.5 V`, `en <= 2.5 V`, and `abs(gate) <= 0.20 V`.

The implementation includes the injection row in post-injection statistics,
preserves equal-time rows in counts, and does not enforce a maximum time gap,
minimum row count, healthy prefix, phase, or continuity. Those omissions are
intentional diagnostic limits and must stay in the receipt interpretation.

## Fault-kind applicability and misleading labels

For SW-SHORT and BOTH-SHORT, `i(Vchannel)` is the current through the sensed
MOS channel source and includes the failed parallel low-ohmic branch. A high
channel count or extrema can expose retained current after sampled controller
off predicates, but the report does not establish a causal failed-switch
mechanism. The frozen protection checker may reject earlier on a node or
detector-event screen; this tool remains useful on the raw fault42 stream
because it does not call that checker and does not require a latch event.

For DIODE-SHORT, the prepared graph shorts the common diode terminal pair
`sw` to `vd` through the modeled diode-side path. `i(Vdboost1sense)` is an
instrument-created branch probe behind a zero-volt sense source; it is not an
independent physical die current. The observability tool does not summarize
that branch at all, which is safe but means it cannot answer even a modeled
diode-branch-current question. `i(Vchannel)` remains the MOS channel probe,
not diode current.

The JSON keys `channel_a`, `body_a`, and `lboost_a` are generic ampere labels,
not named physical phases or die branches. `simultaneous_q_en_gate_off` is a
count of rows satisfying the three predicates at the same sampled timestamp;
it is not a continuous-off interval, a causal conjunction, or evidence that
current was off at those same samples. The independent `channel_above` count
likewise cannot be joined causally to the off count. Any statement about
coincidence must be explicitly limited to sampled rows.

## Sufficiency and narrow follow-up

The existing tool is sufficient for the requested detector-independent sampled
off/current observability on all three fault kinds. No new framework or code is
needed. If the parent needs a stronger statement, the narrow addition should
be a separate report over the same immutable output that joins predicates on
the same timestamp (and records the time gap around each transition), while
still refusing to call the result causal or continuous. For DIODE-SHORT only,
an optional separately reviewed diagnostic could include the two modeled
`i(Vdboost*sense)` columns, clearly labelled as instrument branches; that is
outside this tool's current contract and must not be described as physical die
current.

The frozen `--bypass` validator rejection remains a separate negative-control
fact. It occurs before waveform evaluation, so it cannot replace this
post-capture diagnostic or be called a successful protection result by itself.
