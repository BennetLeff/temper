# F2-CREST post-capture runbook 39

This packet is a runbook only. It launches no simulator and does not read or
decompress the live F2-CREST38 trace. It is intended for a **new** output
directory after stage-1 reports `transport_complete: true`.

The current settled-native-capture-32 packet is explicitly incomplete
(`result.json` has `transport_complete: false` and its parent disposition is a
resource-guard abort). That packet must fail the preflight below; no analysis
result may be inferred from its truncated gzip.

## Frozen inputs and tools

```sh
ROOT=/private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/operating-matrix-07
CASE="$ROOT/faults/settled-native-capture-32/F2-CREST"
OUT="$ROOT/faults/settled-postcapture-39/F2-CREST-analysis-<new-id>"
export SPICE_SCRIPTS=/opt/homebrew/Cellar/ngspice/45.2/share/ngspice/scripts
mkdir "$OUT"                         # refuse/reselect if it already exists
```

The binaries are pinned in `runbook-receipt.json`: pigz, the fault42 decoder,
prefault selector, normal15 event audit, normalizer, event metrics, frozen
strict checker, and phase auditor. Record `shasum -a 256` for every tool again
before starting. Also record hashes for `manifest.json`, `run-parameters.json`,
`source-identity.json`, `capture-metadata.json`, and `result.json`.

## Fail-closed preflight

Run these before opening the raw gzip:

```sh
jq -e '.transport_complete == true' "$CASE/result.json"
jq -e '.schema == "fault42" and .stop_reason == "solver_stopped" and .nonfinite_time == false and .backwards_count == 0 and (.points|type == "number") and .points >= 2' "$CASE/capture-metadata.json"
jq -e '.kind == "f2-crest" and (.tstop_s|type == "number") and (.mutation_s|type == "number") and (.event_window_s|type == "number") and (.observation_s|type == "number") and (.turnoff_s|type == "number") and (.max_gap_s|type == "number") and (.export_timeout_s|type == "number")' "$CASE/run-parameters.json"
test -s "$CASE/raw.trace.raw.gz"
df -kP "$OUT"                 # retain at least 10 GiB throughout every pass
```

The immutable raw hash is recorded before the first pass and again after the
last pass. A changed hash invalidates the complete analysis. Every pass is
bounded to 900 seconds and must be stopped with all children reaped if the
10-GiB floor is crossed. The pipelines stream through pipes; they do not write
decoded or selected-prefix TSV files.

## Prefix scan and endpoint

Use `set -o pipefail` and preserve the full `PIPESTATUS` array. The scan output
is only a small JSON report; its stdout is discarded:

```sh
set -o pipefail
/opt/homebrew/bin/pigz -dc "$CASE/raw.trace.raw.gz" \
  | /private/tmp/matrix07-fault-native-decoder-parent --schema fault42 --byte-order little \
  | /private/tmp/matrix07-prefault-selector-parent - - "$OUT/prefault-scan.json" 0.65 1e-6 --scan-only \
  >/dev/null
codes=("${PIPESTATUS[@]}"); printf '%s\n' "${codes[*]}" > "$OUT/prefault-scan.exit"
for code in "${codes[@]}"; do test "$code" -eq 0 || exit 1; done
jq -e '.status == "OK" and .last_time_s >= .cutoff_s and .cutoff_gap_s >= 0 and .cutoff_gap_s <= 1e-6 and (.fault_inject_rising_edges|length) == 1' "$OUT/prefault-scan.json"
PREFIX_END=$(jq -er '.last_selected_time_s' "$OUT/prefault-scan.json")
```

Require `PREFIX_END` finite, positive, no later than `0.65`, and within 1 us of
the cutoff. Use that exact value for all later tools; never force the endpoint
to `0.65`.

## Diagnostic passes

Run each command as a separate bounded pass, preserving its five-child (or
four-child) exit array and stderr. A nonzero event-audit, metrics, selector, or
phase child is a diagnostic failure. The strict checker is intentionally kept
separate and may reject equal timestamps; its rejection and any upstream
broken-pipe statuses are recorded verbatim and do not cancel the valid
event-aware passes.

```sh
# Event-aware normal15 audit; output is a bounded report, not a trace.
set -o pipefail
/opt/homebrew/bin/pigz -dc "$CASE/raw.trace.raw.gz" \
  | /private/tmp/matrix07-fault-native-decoder-parent --schema fault42 --byte-order little \
  | /private/tmp/matrix07-prefault-selector-parent - - "$OUT/prefault-audit-select.json" 0.65 1e-6 \
  | /private/tmp/matrix07-normal15-event-audit-host --end-s "$PREFIX_END" --rload 190 --events "$OUT/normal15-events.tsv" \
  >"$OUT/normal15-audit.txt" 2>"$OUT/normal15-audit.stderr"
codes=("${PIPESTATUS[@]}"); printf '%s\n' "${codes[*]}" > "$OUT/prefault-audit.exit"

# Normalizer plus event-aware metrics, retaining the switching guard.
set -o pipefail
/opt/homebrew/bin/pigz -dc "$CASE/raw.trace.raw.gz" \
  | /private/tmp/matrix07-fault-native-decoder-parent --schema fault42 --byte-order little \
  | /private/tmp/matrix07-prefault-selector-parent - - "$OUT/prefault-metrics-select.json" 0.65 1e-6 \
  | /private/tmp/matrix07-normalize 190 \
  | /private/tmp/matrix07-event-metrics-host --end-s "$PREFIX_END" \
  >"$OUT/normal-metrics.txt" 2>"$OUT/normal-metrics.stderr"
codes=("${PIPESTATUS[@]}"); printf '%s\n' "${codes[*]}" > "$OUT/prefault-metrics.exit"

# Legacy strict result is retained, never relabeled as a pass.
set -o pipefail
/opt/homebrew/bin/pigz -dc "$CASE/raw.trace.raw.gz" \
  | /private/tmp/matrix07-fault-native-decoder-parent --schema fault42 --byte-order little \
  | /private/tmp/matrix07-prefault-selector-parent - - "$OUT/prefault-legacy-select.json" 0.65 1e-6 \
  | /private/tmp/matrix07-normalize 190 \
  | /private/tmp/matrix07-checker --end-s "$PREFIX_END" \
  >"$OUT/legacy-checker.stdout" 2>"$OUT/legacy-checker.stderr"
codes=("${PIPESTATUS[@]}"); printf '%s\n' "${codes[*]}" > "$OUT/legacy-checker.exit"

# Independent measured local-crest phase evidence.
set -o pipefail
/opt/homebrew/bin/pigz -dc "$CASE/raw.trace.raw.gz" \
  | /private/tmp/matrix07-fault-native-decoder-parent --schema fault42 --byte-order little \
  | /private/tmp/matrix07-phase-audit35-parent \
      --end-s 6.620000000000e-1 \
      --expected-event-s 6.541666666667e-1 \
      --local-start-s 6.500000000000e-1 \
      --local-end-s 6.583333333333e-1 \
      --kind crest --tolerance 0.01 \
  >"$OUT/phase-audit.json" 2>"$OUT/phase-audit.stderr"
codes=("${PIPESTATUS[@]}"); printf '%s\n' "${codes[*]}" > "$OUT/phase-audit.exit"
```

The strict checker is expected to say `time not strictly increasing` when
retained equal-time rows are present. Preserve its stderr and all five exit
codes. The phase report is evidence only: `PHASE_EVIDENCE_OK` cannot establish
healthy prefault operation, protection timing, current interruption, thermal
safety, or hardware qualification. Event-aware metrics and phase output remain
diagnostic and must be reviewed with their reports and margins.

Finally, hash the raw again and write a receipt containing the before/after raw
hash, all pass exit arrays, report paths, `PREFIX_END`, source/manifest/tool
hashes, and `accepted: false`. Keep the canonical raw gzip and every report.
