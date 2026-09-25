# F2-CREST post-capture runbook 39

This packet is a runbook only. It launches no simulator and does not read or
decompress the live F2-CREST38 trace. It is intended for a **new** output
directory after the runner is terminal, capture-stage1 reports host/compressor success,
and the complete pipeline result reports `transport_complete: true`.

The previous settled-native-capture-32 packet is explicitly incomplete
(`result.json` has `transport_complete: false` and its parent disposition is a
resource-guard abort). That packet must fail the preflight below; no analysis
result may be inferred from its truncated gzip.

## Frozen inputs and tools

```bash
ROOT=/private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/operating-matrix-07
CASE="$ROOT/faults/settled-direct-capture-38/F2-CREST"
OUT="$ROOT/faults/settled-postcapture-39/F2-CREST-analysis-<new-id>"
export SPICE_SCRIPTS=/opt/homebrew/Cellar/ngspice/45.2/share/ngspice/scripts
mkdir "$OUT" || exit 1                # refuse if it already exists
```

The binaries are pinned in `runbook-receipt.json`: pigz, the fault42 decoder,
prefault selector, normal15 event audit, normalizer, event metrics, frozen
strict checker, and phase auditor. Record `shasum -a 256` for every tool again
before starting. Also record hashes for `manifest.json`, `run-parameters.json`,
`source-identity.json`, `capture-metadata.json`, and `result.json`.

## Fail-closed preflight

Run these before opening the raw gzip:

```bash
test -f "$CASE/../runner.exit" || exit 1
jq -e '.transport_complete == true and .acceptance == false' "$CASE/result.json" || exit 1
jq -e '.host_success == true and .pigz_success == true and .host_rc == 0 and .pigz_rc == 0 and .metadata_status == "valid" and (.raw_trace_bytes|type == "number") and .raw_trace_bytes > 0 and (.raw_trace_sha256|type == "string" and test("^[a-f0-9]{64}$"))' "$CASE/capture-stage1.json" || exit 1
jq -e '.status == "complete" and .schema == "fault42" and .columns == 42 and .accepted == false and .copy_avoidance_only == true and (.rows|type == "number") and .rows >= 2' "$CASE/native-export-receipt.json" || exit 1
jq -e '.schema == "fault42" and .stop_reason == "solver_stopped" and .nonfinite_time == false and .backwards_count == 0 and .seen_names_mask == 65535 and .expected_names_mask == 65535 and .export_format == "ngspice-real-native" and .byte_order == "little" and .diagnostic_only == true and .accepted == false and (.points|type == "number") and .points >= 2' "$CASE/capture-metadata.json" || exit 1
jq -e '.kind == "f2-crest" and .tstop_s == 0.662 and .mutation_s == 0.6541666666667 and .expected_fault_s == 0.6541666666667 and .event_window_s == 0.002 and .observation_s == 0.002 and .turnoff_s == 0.000002 and .max_gap_s == 0.000000025 and .export_timeout_s == 900 and .bypass == false' "$CASE/run-parameters.json" || exit 1
test -s "$CASE/raw.trace.raw.gz" || exit 1
df -kP "$OUT"                 # retain at least 10 GiB throughout every pass
```

The immutable raw hash is recorded before the first pass and again after the
last pass. A changed hash invalidates the complete analysis. Every pass is
bounded to 900 seconds and must be stopped with all children reaped if the
10-GiB floor is crossed. The pipelines stream through pipes; they do not write
decoded or selected-prefix TSV files. The snippets below do not themselves
implement the deadline or disk supervisor: the parent must run each under
explicit process ownership and its bounded monitoring before use. Do not call
these unsupervised commands a guarded runner.

Compare raw size and full SHA-256 against both `capture-stage1.json` and
`result.json`. Compare every actual source/include/tool hash against the frozen
manifest and source identity, not merely record a new hash. Native export rows
must equal capture metadata points. Preserve the runner exit even when a
validator rejection leaves transport complete: it is not automatic acceptance.

## Prefix scan and endpoint

Use `set -o pipefail` and preserve the full `PIPESTATUS` array. The scan output
is only a small JSON report; its stdout is discarded:

```bash
set -o pipefail
/opt/homebrew/bin/pigz -dc "$CASE/raw.trace.raw.gz" 2>"$OUT/scan-pigz.stderr" \
  | /private/tmp/matrix07-fault-native-decoder-parent --schema fault42 --byte-order little 2>"$OUT/scan-decoder.stderr" \
  | /private/tmp/matrix07-prefault-selector-parent - - "$OUT/prefault-scan.json" 0.65 1e-6 --scan-only 2>"$OUT/scan-selector.stderr" \
  >/dev/null
codes=("${PIPESTATUS[@]}"); printf '%s\n' "${codes[*]}" > "$OUT/prefault-scan.exit"
for code in "${codes[@]}"; do test "$code" -eq 0 || exit 1; done
jq -e '.status == "OK" and .last_time_s >= .cutoff_s and .cutoff_gap_s >= 0 and .cutoff_gap_s <= 1e-6 and (.last_selected_time_s|type == "number") and .last_selected_time_s > 0 and .last_selected_time_s <= 0.65 and .last_selected_time_s >= 0.649999 and (.fault_inject_rising_edges|length) == 1' "$OUT/prefault-scan.json" || exit 1
PREFIX_END=$(jq -er '.last_selected_time_s' "$OUT/prefault-scan.json") || exit 1
```

Require `PREFIX_END` finite, positive, no later than `0.65`, and within 1 us of
the cutoff. Use that exact value for all later tools; never force the endpoint
to `0.65`.

## Diagnostic passes

Run each command as a separate bounded pass, preserving each exit array
and every child stderr: scan3, event audit4, metrics5, legacy5, phase3. A nonzero event-audit, metrics, selector, or
phase child is a diagnostic failure. The strict checker is intentionally kept
separate and may reject equal timestamps; its rejection and any upstream
broken-pipe statuses are recorded verbatim and do not cancel the valid
event-aware passes.

```bash
# Event-aware normal15 audit; output is a bounded report, not a trace.
set -o pipefail
/opt/homebrew/bin/pigz -dc "$CASE/raw.trace.raw.gz" 2>"$OUT/audit-pigz.stderr" \
  | /private/tmp/matrix07-fault-native-decoder-parent --schema fault42 --byte-order little 2>"$OUT/audit-decoder.stderr" \
  | /private/tmp/matrix07-prefault-selector-parent - - "$OUT/prefault-audit-select.json" 0.65 1e-6 2>"$OUT/audit-selector.stderr" \
  | /private/tmp/matrix07-normal15-event-audit-host --end-s "$PREFIX_END" --rload 190 --events "$OUT/normal15-events.tsv" \
  >"$OUT/normal15-audit.txt" 2>"$OUT/normal15-audit.stderr"
codes=("${PIPESTATUS[@]}"); printf '%s\n' "${codes[*]}" > "$OUT/prefault-audit.exit"

# Normalizer plus event-aware metrics, retaining the switching guard.
set -o pipefail
/opt/homebrew/bin/pigz -dc "$CASE/raw.trace.raw.gz" 2>"$OUT/metrics-pigz.stderr" \
  | /private/tmp/matrix07-fault-native-decoder-parent --schema fault42 --byte-order little 2>"$OUT/metrics-decoder.stderr" \
  | /private/tmp/matrix07-prefault-selector-parent - - "$OUT/prefault-metrics-select.json" 0.65 1e-6 2>"$OUT/metrics-selector.stderr" \
  | /private/tmp/matrix07-normalize 190 2>"$OUT/metrics-normalize.stderr" \
  | /private/tmp/matrix07-event-metrics-host --end-s "$PREFIX_END" \
  >"$OUT/normal-metrics.txt" 2>"$OUT/normal-metrics.stderr"
codes=("${PIPESTATUS[@]}"); printf '%s\n' "${codes[*]}" > "$OUT/prefault-metrics.exit"

# Legacy strict result is retained, never relabeled as a pass.
set -o pipefail
/opt/homebrew/bin/pigz -dc "$CASE/raw.trace.raw.gz" 2>"$OUT/legacy-pigz.stderr" \
  | /private/tmp/matrix07-fault-native-decoder-parent --schema fault42 --byte-order little 2>"$OUT/legacy-decoder.stderr" \
  | /private/tmp/matrix07-prefault-selector-parent - - "$OUT/prefault-legacy-select.json" 0.65 1e-6 2>"$OUT/legacy-selector.stderr" \
  | /private/tmp/matrix07-normalize 190 2>"$OUT/legacy-normalize.stderr" \
  | /private/tmp/matrix07-checker --end-s "$PREFIX_END" \
  >"$OUT/legacy-checker.stdout" 2>"$OUT/legacy-checker.stderr"
codes=("${PIPESTATUS[@]}"); printf '%s\n' "${codes[*]}" > "$OUT/legacy-checker.exit"

# Independent measured local-crest phase evidence.
set -o pipefail
/opt/homebrew/bin/pigz -dc "$CASE/raw.trace.raw.gz" 2>"$OUT/phase-pigz.stderr" \
  | /private/tmp/matrix07-fault-native-decoder-parent --schema fault42 --byte-order little 2>"$OUT/phase-decoder.stderr" \
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

Require all scan/audit/metrics/phase children zero and matching full/selected
row counts across complete selector reports. Full decoded counts must match
capture metadata. Audit equal-time ambiguity and observable sensitivity against
the unchanged electrical margins; zero exit alone is not parent acceptance.

Finally, hash the raw again and write a receipt containing the before/after raw
hash, all pass exit arrays, report paths, `PREFIX_END`, source/manifest/tool
hashes, and `accepted: false`. Keep the canonical raw gzip and every report.
