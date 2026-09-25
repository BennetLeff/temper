# F2-CREST prefix-analysis readiness 34

This is a read-only interface audit of the prepared F2-CREST post-capture
commands. It did not read the live F2-CREST raw file, launch or restart a
process, or modify a binary. The conclusions below are based on the selector,
normalizer, event-auditor, event-metrics, and legacy checker sources currently
bound by the parent launch packet.

## Interface checks

The README's selector invocation has the right interface:

```text
prefault_normal_audit RAW42 NORMAL15_OUT REPORT_JSON CUTOFF_S MAX_CUTOFF_GAP_S [--scan-only]
```

`RAW42=-` reads stdin, `NORMAL15_OUT=-` writes the canonical 15-column stream
to stdout, and the report path must be a real file. The scan at `0.65 1e-6`
validates every 42-field row, requires nondecreasing time, requires the complete
input to reach the cutoff, and requires the last selected sample to be within
1 us. It preserves equal-time rows. The later passes can therefore use the
scan's `last_selected_time_s` as `PREFIX_END`; they must not force the end back
to `0.65`.

The selected stream is compatible with both diagnostics:

* `normal15-event-audit-host` consumes the exact 15-column native normal header.
  Its default start is zero, its `--end-s` endpoint tolerance is 1 ns, and its
default switching-step bound is `1/(8*130000) = 9.615384615e-7 s`. It retains
equal-time groups for diagnostics.
* `matrix07-normalize 190` consumes the 13 source columns that are a subset of
  the selected normal15 header and emits the exact 12-column checker header.
  It has no end argument; the downstream tool owns endpoint validation.
* `matrix07-event-metrics-host --end-s "$PREFIX_END"` consumes that 12-column
  stream, keeps its default switching guard, and is diagnostic only. A selector
  cutoff gap below 1 us can still be rejected here if an interior selected step
  exceeds the roughly 0.962 us switching bound; that is a real diagnostic
  failure, not a reason to disable the guard by adding `--no-switch-check`.

The README's `PIPESTATUS` handling is necessary. A selector may have emitted
rows before a late decoder/input error, so no report or partial stdout is usable
unless every child exits zero and the selector report says `status:"OK"`.

## Exact legacy strict-checker pass

The current README says to retain the legacy strict result but omits its exact
command. After the selector scan and prefix endpoint are known, run a separate
pass (do not splice it into the event-metrics pass):

```bash
set -o pipefail
/opt/homebrew/bin/pigz -dc raw.trace.raw.gz \
  | /private/tmp/matrix07-fault-native-decoder-parent --schema fault42 --byte-order little \
  | /private/tmp/matrix07-prefault-selector-parent - - prefault-legacy-select.json 0.65 1e-6 \
  | /private/tmp/matrix07-normalize 190 \
  | /private/tmp/matrix07-checker --end-s "$PREFIX_END" > legacy-checker.stdout 2> legacy-checker.stderr
legacy_codes=("${PIPESTATUS[@]}")
printf '%s\n' "${legacy_codes[*]}" > legacy-checker.exit
```

`matrix07-checker` requires the exact 12-column normalized header, a first time
at or before 1 us, a final time within 1 ns of `--end-s`, at least three integer
mains cycles, and its default switching guard. It rejects equal timestamps as
`time not strictly increasing`. That strict rejection is expected if the native
fault trace contains retained equal-time rows; the event-aware audit/metrics pass
must remain the authoritative diagnostic for those rows.

When the checker rejects early, it can close stdin while the selector or
normalizer is still writing. The upstream process may then exit nonzero with a
broken-pipe/EPIPE-derived write error. This is expected transport fallout from a
legacy checker rejection, not a pass and not evidence that the raw trace was
invalid. Record all five `legacy_codes` and the checker and upstream stderr logs. Any nonzero code
means the legacy pass has no acceptance result; never hide it with `|| true`,
ignore `PIPESTATUS`, or remove equal-time rows. If the strict checker reaches EOF
and rejects for an electrical screen, upstream processes may still exit zero;
that remains a checker rejection. The raw capture and event-aware reports stay
separate.

Using `PREFIX_END` rather than literal `0.65` is valid for the strict checker:
the selector deliberately permits a final selected sample up to 1 us before the
cutoff, while the checker permits only 1 ns endpoint error. Passing literal
`0.65` could therefore manufacture a truncated-end failure even when the exact
selected prefix is valid. The event auditor and event metrics must use the same
`PREFIX_END` for their endpoint-derived windows.

## Phase evidence gap

The selector report's `fault_inject_rising_edges[0]` records the actual edge time
and the single-row `v_acsrc_acn` value. That is necessary evidence, but it is
not by itself sufficient to prove the F2-CREST requirement. The requirement is
the first accepted settled event whose absolute source voltage is within 1% of
the **local sampled crest**. One edge sample can be close to a nominal peak by
coincidence, and the selector does not retain the neighboring source samples or
compute a local maximum.

Before any F2-CREST interpretation, the parent must add a receipt from a second
read-only decoded pass (or an equivalent reviewed phase scanner) containing at
least:

* observed injection time and the exact edge-row `v(acsrc,acn)`;
* the local sampled maximum of `abs(v(acsrc,acn))` around that settled crest,
  with its timestamp and bracketing rows;
* the comparison `abs(edge_value)` versus that measured local maximum, showing
  the declared 1% bound; and
* confirmation that the edge is the first selected settled event and that the
  healthy prefault window remains valid.

The nominal sinusoidal peak (~169.7056 V for 120 Vrms) may be a reference, but it
cannot replace this measured local-crest receipt. A phase mismatch or missing
neighbor/peak evidence leaves the case incomplete even if the selector report
is `OK` and the native validator exits zero.

## Disposition

The streaming prefix commands are structurally compatible with the reviewed
Rust interfaces, provided they use the exact `PREFIX_END` and retain all
`PIPESTATUS`/reports. Add the explicit legacy checker pass above and require a
separate local-sampled-crest receipt. Neither diagnostics nor the legacy checker
alone establishes hardware protection or a settled fault acceptance.
