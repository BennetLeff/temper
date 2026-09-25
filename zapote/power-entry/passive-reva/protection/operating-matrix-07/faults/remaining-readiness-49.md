# Remaining settled-fault readiness audit

This is a launch-readiness review only. It does not run ngspice, decode a
campaign trace, or promote any prepared case to an acceptance result. The
source of truth for each deck is its manifest under
`faults/settled-compact-prep-24/prepared/`; all five cases remain
`PREPARED_UNEXECUTED_COMPACT_PACER_CANDIDATE`.

## Priority

Run **F2-ZERO first** after the current single-solver/storage gate clears. It
is the second positive F2 state and exercises a materially different source
phase while using the same `f2-open` validator contract. Completing it gives
the campaign both crest and zero stress points before failed-short topology
experiments. Its longer prefix and horizon are intentional: the manifest uses
`T_FAULT=0.6583333333333`, a 10 ms prefault window, `TSTOP=0.682`, and 10 ms
checker/observation windows.

Then run **SW-SHORT** at the settled crest. It is the shortest path to the
categorical failed-channel result and uses the same 2 ms timing as the crest
case. Run **DIODE-SHORT** only after the terminal-level branch-model gate is
explicitly recorded; run **BOTH-SHORT** after that (or serialize it immediately
after SW-SHORT if the parent accepts the same gate). Run **BYPASS-NEG** last as
the harness negative control, unless a transport regression makes it useful
earlier. The negative control costs a full capture but cannot add a protection
claim.

The proposed order is a prioritization, not permission to launch. Every case
still needs a fresh output directory, the storage floor, and the parent’s
single-solver gate.

## Case contracts and expected interpretations

| case | manifest timing | runner kind / validator kind | expected interpretation |
| --- | --- | --- | --- |
| F2-ZERO | `.6583333333333`, `.682`, prefault/window/observation `.010` | `f2-zero` / `f2-open` | `PASS` is the only positive model-screen result; otherwise retain `FAIL` or indeterminate evidence. |
| SW-SHORT | `.6541666666667`, `.662`, `.002` | `switch-short` / `switch-short` | `PROTECTION_GAP` when earlier node screens pass, regardless of whether measured channel current is over the checker threshold; a node-screen violation is `FAIL`. |
| DIODE-SHORT | `.6541666666667`, `.662`, `.002` | `diode-short` / `diode-short` | Ordinary healthy-switch checker result only. It is a terminal-level graph experiment, not a dual-die current, thermal, or package result. |
| BOTH-SHORT | `.6541666666667`, `.662`, `.002` | `both-short` / `both-short` | `PROTECTION_GAP` when earlier node screens pass; `FAIL` takes precedence for an over-limit node. Gate-off never interrupts the failed channel. |
| BYPASS-NEG | `.6541666666667`, `.662`, `.002` | `bypass-neg` / `f2-open` plus `--bypass` | Expected checker rejection for a bypassed detector, never a protection pass. A complete raw capture is still required to diagnose the negative control. |

The categorical short result must be reported separately from actual measured
`i(Vchannel)`, `i(Vbody)`, `i(Lboost)`, F2, and diode-sense branch currents.
`faults/fault-matrix.md` and `faults/branch-model-review-13.md` require this
separation. In particular, `i(Vdboost1sense)` is the current in an
instrument-created terminal path; the retained common-cathode diode model does
not expose an independently physical die branch.

## Exact prepared-source checks

Each manifest repeats the same six-file baseline closure (`cold.cir`,
`ucc28180-pwm-latch.inc`, `protection.inc`, `standby.inc`, `clamp.inc`, and
`authored_logic_hysteretic.inc`). The compact case hashes are:

```text
F2-ZERO     b704ebd646dce1da7cf03518478ac1956e3a0bffbae804bd28ff383f4a6fb6c1
SW-SHORT    3ba13389962a9550edcc7ca5486109f4793c6082e94a50fe18f0bc1f6f889ace
DIODE-SHORT d5a78e2c878447110a13c54cc3052b3dff7e862dc3e79a5fbd8e973257ac5f78
BOTH-SHORT  c35139cff49f8f43db43a4dca9cff13c06c0289150b09dab12ba5aff29ffcb51
BYPASS-NEG  c6ea3dca688918137282ed3fd3d0ffa17c2b740d68ab52bab306ee3e8b228180
```

The first four use the baseline `protection.inc` hash
`61385002bc7c55313814b7ea606c1198129da20a1f76cd44fe197de0468a70e8`;
BYPASS-NEG deliberately has the separate protection mutation hash
`d9b499bbba3f2636ac926a3c8782943d3144798cfe4faa765ceaf7774628a025`.
Before launch, verify every output file against that case's `output_sha256`,
and let runner-45 recheck the source listing and manifest timing. Do not copy a
case's output hash or source identity from F2-CREST.

The compact source has an intentional endpoint caveat in all five manifests:
the finite materializer endpoint value differs from the repeating compact PWL
prediction. The actual final ngspice sample must satisfy the endpoint contract;
the predicted value is not evidence. A clean solver exit or a syntactically
valid pacing deck cannot waive this check.

## Required prefix, phase, and pipeline gates

Each fault trace must prove its own contiguous healthy prefix. The accepted
F2-CREST normal-prefix receipt at
`faults/settled-prefix-analysis-42/normal-prefix/acceptance.json` is useful
precedent, but it does not transfer acceptance to any other fault trace or
source hash. For each new capture, run the full42 prefault scan, select the
actual last sample at or before 650 ms, and feed that exact endpoint to both
normal audits. Require all child exit codes, matching selected/full row counts,
finite/nondecreasing rows, accepted bus/current/power/drift/stress screens,
and an unambiguous ARM/PERMIT/q/en healthy prefix. Preserve the legacy strict
checker result separately; its EPIPE after a repeated-time rejection is not an
upstream transport success.

The source-phase check must use the actual `v(acsrc,acn)` and marker edge from
that same raw42 trace. For F2-ZERO, the 10 ms event window must contain the zero
edge and strict-time neighboring samples around a local crest used for the 1%
bound; do not reuse the crest interval or a nominal sinusoid timestamp. For
the crest-timed three cases and BYPASS-NEG, verify the measured edge and a
strictly bracketed local crest in the declared 2 ms interval. The group-aware
phase successor (`faults/phase-audit-43/`) may provide the diagnostic bound,
but it remains `acceptance:false`; a phase report alone never establishes the
healthy prefix or electrical limits.

Use the parent-reviewed runner-45 binary
`/private/tmp/matrix07-fault-runner45-parent` (source SHA
`b131c153db6a67f3da961bda0b2a5a7c417271f68c0141c7af664059c87219a3`, binary
SHA `98a8c07622dcd257a919107c366775009dfd918b45c4bb72e8fb603d7dc92abb`).
The older runner-29 command shown in the historical F2-CREST README is not the
current launch command. Pass `25e-9` as the immutable capture gap; runner-45
maps only the outer adapter/validator bound to `1e-6`. The inner checker remains
25 ns. Use native lowercase kinds exactly as shown in the table, and pass
`--bypass` only for BYPASS-NEG. A nonzero child or runner exit is incomplete or
rejected evidence, never a protection verdict.

## Harness assumptions that must not become verdicts

* `faults/native-runner-45/parent-review.json` records 12 tests plus one
  sandbox-ignored inherited-FD test. That proves the candidate transport and
  timing mapping, not a full fault capture. Parent must bind the decoder,
  adapter, validator, ngspice script directory, and all hashes in the fresh
  case receipt.
* The runner's `bypass-neg` route intentionally invokes the `f2-open` validator
  with `--bypass`; it is not a separate protection algorithm. The frozen
  checker returns `Fail("protection detector is bypassed")` before evaluating
  the waveform, so that categorical exit alone proves only flag wiring. The
  negative-control receipt must also retain the measured detector/fault marker,
  q, en, gate, channel, and post-event rows and report whether a real
  latch-off/current-cessation witness is absent. Do not relabel that waveform
  finding as the primary checker verdict, and do not call a bypassed trace a
  successful protection result.
* `SW-SHORT` and `BOTH-SHORT` must not be credited for gate/q/en turnoff. Their
  parallel low-ohmic branch is gate-independent, and `PROTECTION_GAP` is a
  categorical classification after node screens, not a claim that current was
  below or above one arbitrary threshold.
* `DIODE-SHORT` is approved only as the reviewed shared-terminal graph
  experiment. Any result about individual die allocation, package current
  sharing, fuse interruption, SOA, or thermal behavior is unreachable from this
  model and must be excluded from the receipt.
* No case may inherit F2-CREST's raw trace, phase, endpoint, or prefix result.
  A rejected or incomplete trace remains retained evidence; widening a gap,
  event window, node limit, or observation horizon after the fact is a failed
  campaign contract.

The five cases therefore provide a clear next sequence, but none is ready for
automatic promotion: first satisfy the per-case prefix/phase/endpoint gates,
then classify the frozen checker result with the branch-specific limits above.

## BYPASS-NEG latch-field limitation

The frozen adapter (`faults/event-aware-adapter-13/fault_normalize.rs`) reports
`detector_rise_s`, `latch_off_s`, and channel peaks/last-above times in separate
fields. Its state machine only starts latch timing and the
`channel_*_after_detector` / `channel_*_after_latch` accumulators after an
observed detector edge. In a genuine BYPASS-NEG trace the detector edge is
absent, so `latch_off_s=none` and the after-detector/after-latch values remain
zero by construction; that is not, by itself, proof that q/en/gate never went
off. The checked and supplemental streams still retain q, en, gate, channel,
fault, and marker rows, so the parent should compute a clearly labelled
post-injection waveform summary (last q/en/gate-off witness and channel-current
retention) from those retained rows.

If a second diagnostic is useful, feed the same immutable BYPASS-NEG checked
stream to the frozen checker with the **bypass flag omitted**, and store that
output under a `waveform_only_no_bypass` label. This must not rewrite the case's
actual `bypass-neg` metadata or acceptance field: it is only a counterfactual
check showing whether the waveform contains a detector/latch witness. The
primary run must remain the expected `protection detector is bypassed` failure,
and a missing detector edge or missing off witness in the counterfactual must
be reported separately rather than promoted to a circuit verdict.
