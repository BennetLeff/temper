# Phase audit 35

This is a standalone, read-only Rust phase-evidence scanner for a decoded
native `fault42` stream. It reads one whitespace TSV from stdin and emits one
compact JSON report to stdout. It does not read a raw capture, mutate a source,
run ngspice, run the fault checker, or make a protection/operating-point claim.

The parser requires exactly the declared 42 fault columns by name (case
insensitive, reordered names are mapped by name), rejects duplicate/missing/
unknown columns, validates every numeric field as finite, rejects backwards
time, and preserves equal-time rows in its streaming state. Memory is O(1)
apart from the 42-field row and a few before/after samples. An equal-time source
conflict in the local interval or at a marker edge is rejected as indeterminate.

## Build and tests

```sh
rustfmt phase_audit.rs
rustc --edition=2021 -D warnings --test phase_audit.rs \
  -o /private/tmp/matrix07-phase-audit35-worker-tests
/private/tmp/matrix07-phase-audit35-worker-tests
rustc --edition=2021 -D warnings -O phase_audit.rs \
  -o /private/tmp/matrix07-phase-audit35-worker
```

The bounded unit suite has eleven tests: crest and zero positives, an early tied
subpeak reset, wrong phase, missing/duplicate event, backwards/nonfinite input,
incomplete endpoint/interval, conflicting equal-time source, equal-time marker
transition, initial-high marker, and oversized-header controls. The scanner
requires the event and local peak to be strictly bracketed by distinct-time
neighbors and rejects a tied maximum; this is deliberately conservative phase
evidence. The worker build and test run are recorded in `manifest.json`.

## Invocation

For the prepared F2-CREST capture, the parent should run this only after the
capture has completed and the raw hash is recorded, using a second read-only
pass through the reviewed decoder:

```bash
set -o pipefail
/opt/homebrew/bin/pigz -dc raw.trace.raw.gz \
  | /private/tmp/matrix07-fault-native-decoder-parent --schema fault42 --byte-order little \
  | /private/tmp/matrix07-phase-audit35-worker \
      --end-s 6.620000000000e-1 \
      --expected-event-s 6.541666666667e-1 \
      --local-start-s 6.521666666667e-1 \
      --local-end-s 6.561666666667e-1 \
      --kind crest \
      --tolerance 0.01 > phase-audit.json
codes=("${PIPESTATUS[@]}")
printf '%s\n' "${codes[*]}" > phase-audit.exit
for code in "${codes[@]}"; do test "$code" -eq 0 || exit 1; done
jq -e '.status == "PHASE_EVIDENCE_OK" and .acceptance == false and .criterion.pass == true' \
  phase-audit.json >/dev/null
```

The local interval in this example is the declared ±2 ms crest-selection
window. The parent may choose a different predeclared interval, but it must
contain the expected event, be fully covered by the trace, and include the
actual local source peak. For `--kind zero`, the interval must also include a
positive adjacent crest; the scanner then applies `abs(edge) <= tolerance*peak`.
The event must be the unique observed `fault_inject` low-to-high transition and
must be within 2 ns of `--expected-event-s`.

A `PHASE_EVIDENCE_OK` report is phase evidence only. It does not prove the
healthy prefault arm/permit/q/en window, detector/latch behavior, current
interruption, electrical screens, thermal safety, or hardware qualification.
Those remain the adapter, validator, checker, and parent-review obligations.

## Report contents and limits

The JSON report includes the declared parameters, row/equal-time counts, first
and final times, endpoint error, unique edge count, equal-source conflict count,
the edge sample plus before/after neighbors, the local absolute-source maximum
plus before/after neighbors, and the crest/zero criterion values. The scanner
requires final time within 1 ns of `--end-s`, local interval coverage, exactly
one rising edge, strict interior event/peak neighbors, and a finite positive
local peak. Header and row lines are bounded at 16 KiB before appending, so a
malformed unterminated line fails closed. It does not interpolate,
resample, drop duplicate rows, or infer a nominal sinusoidal phase. A nominal
120 Vrms peak is not used as a substitute for the measured local peak.
