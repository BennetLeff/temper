# F2-CREST settled native capture 32 (prepared, unexecuted)

This directory is a byte-for-byte copy of the parent-reviewed compact candidate
at `/private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/operating-matrix-07/faults/settled-compact-prep-24/prepared/F2-CREST`. It contains no trace and no acceptance result. No simulation was
launched while preparing it. The copied `manifest.json` is unchanged; its
`output_sha256.case.cir` and six source-closure hashes are the authority.
`copy-verification.json` records source/destination SHA-256 equality and the
reviewed executable hashes.

## Parameters fixed by the copied manifest

- mutation / expected F2 edge: `T_FAULT = 6.541666666667e-1 s`
- end: `TSTOP = 6.620000000000e-1 s`
- prefault/event window: `2.000000000000e-3 s`
- compact local pacing step and adapter/checker maximum gap: `2.5e-8 s`
- observation after the event: `2.000000000000e-3 s`
- turnoff reporting bound: `2.000000000000e-6 s`
- native host wall limit: `3600 s`; export/compressor timeout: `900 s`

The deck's first compact PWL corner is the exact finite timestamp
`6.521666416667e-1 s`; do not replace it with a recomputed decimal. The compact
endpoint is intentionally recorded as different from the finite materializer's
forced endpoint. Inspect the actual final sample before classification.

## Launch gate

Wait until the parent confirms that at least one currently live normal solver
has finished, free storage covers the forecast archive, other live exports and the
10 GiB reserve, and this copied source closure has been hash-verified. The
parent must also bind the accepted baseline source. This fault trace must
later prove its own normal prefix; it cannot inherit baseline acceptance. This packet
must not be launched merely because the case is mechanically prepared.

The reviewed runner uses the native anonymous-pipe capture candidate and creates
its outputs inside the case directory. Run from a shell that exports the exact
ngspice script directory:

```sh
ROOT=/private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/operating-matrix-07
CASE="$ROOT/faults/settled-native-capture-32/F2-CREST"
export SPICE_SCRIPTS=/opt/homebrew/Cellar/ngspice/45.2/share/ngspice/scripts
"/private/tmp/matrix07-fault-runner29-parent" \
  "$CASE" \
  /private/tmp/matrix07-fault-native-host-parent \
  /opt/homebrew/bin/pigz \
  /private/tmp/matrix07-fault-native-decoder-parent \
  /private/tmp/matrix07-fault-adapter-parent \
  /private/tmp/matrix07-fault-validation22-parent \
  6.620000000000e-1 f2-crest \
  6.541666666667e-1 2.000000000000e-3 \
  6.541666666667e-1 2.000000000000e-3 \
  2.000000000000e-6 2.500000000000e-8 \
  3600 900
```

A nonzero runner exit is a failed/incomplete run, never an acceptance result.
The runner's case directory must be new: it refuses pre-existing generated
outputs. Keep `raw.trace.raw.gz` even if a later validator rejects the case.

## Required normal-prefix and actual-phase audit

Run the analysis commands in **bash**, with the parent monitoring each owned
pipeline under a 900 s deadline and the 10 GiB disk floor. Preserve each exit
array and every report; a nonzero child status rejects that pipeline. No giant
decoded or selected-prefix TSV is written. The three passes below read the
same immutable canonical gzip. Record its hash before and after analysis.

First scan all42 fields and find the last actual sample at or before650ms:

```bash
cd "$CASE"
set -o pipefail
/opt/homebrew/bin/pigz -dc raw.trace.raw.gz \
  | /private/tmp/matrix07-fault-native-decoder-parent --schema fault42 --byte-order little \
  | /private/tmp/matrix07-prefault-selector-parent - - prefault-scan.json 0.65 1e-6 --scan-only
scan_codes=("${PIPESTATUS[@]}")
printf '%s\n' "${scan_codes[*]}" > prefault-scan.exit
for code in "${scan_codes[@]}"; do test "$code" -eq 0 || exit 1; done
jq -e '.status == "OK" and .last_time_s >= .cutoff_s and .cutoff_gap_s >= 0 and .cutoff_gap_s <= 1e-6 and (.fault_inject_rising_edges | length) == 1' prefault-scan.json >/dev/null || exit 1
PREFIX_END=$(jq -r '.last_selected_time_s' prefault-scan.json)
```

Use `PREFIX_END` for both normal audits. A last sample a few nanoseconds
before0.65 is not padded, shifted or forced to0.65. The unchanged selector
requires a maximum1us cutoff gap. Require each later selector report to agree
with this scan's selected rows/endpoint and full rows.

Stream the exact selected normal15 samples to the event auditor:

```bash
/opt/homebrew/bin/pigz -dc raw.trace.raw.gz \
  | /private/tmp/matrix07-fault-native-decoder-parent --schema fault42 --byte-order little \
  | /private/tmp/matrix07-prefault-selector-parent - - prefault-audit-select.json 0.65 1e-6 \
  | /private/tmp/matrix07-normal15-event-audit-host --end-s "$PREFIX_END" --rload 190 --events normal15-events.tsv > normal15-audit.txt
audit_codes=("${PIPESTATUS[@]}")
printf '%s\n' "${audit_codes[*]}" > prefault-audit.exit
for code in "${audit_codes[@]}"; do test "$code" -eq 0 || exit 1; done
jq -e '.status == "OK"' prefault-audit-select.json >/dev/null || exit 1
```

Then stream the same prefix through the maintained190ohm normalizer and the
unchanged normal electrical-metrics tool (including its switching guard):

```bash
/opt/homebrew/bin/pigz -dc raw.trace.raw.gz \
  | /private/tmp/matrix07-fault-native-decoder-parent --schema fault42 --byte-order little \
  | /private/tmp/matrix07-prefault-selector-parent - - prefault-metrics-select.json 0.65 1e-6 \
  | /private/tmp/matrix07-normalize 190 \
  | /private/tmp/matrix07-event-metrics-host --end-s "$PREFIX_END" > normal-metrics.txt
metrics_codes=("${PIPESTATUS[@]}")
printf '%s\n' "${metrics_codes[*]}" > prefault-metrics.exit
for code in "${metrics_codes[@]}"; do test "$code" -eq 0 || exit 1; done
jq -e '.status == "OK"' prefault-metrics-select.json >/dev/null || exit 1
```

Parent acceptance requires complete matching counts, finite/nondecreasing
samples, unambiguous equal-time groups with bounds small relative to each
margin, and all original bus/drift/current/power/stress/armed/on screens.
Exit0 or a selector's statusOK alone does not establish normal operation.
Retain the legacy strict checker result separately when assessing the prefix;
never remove or alter repeated-time rows to make it pass.

The actual `fault_inject_rising_edges[0]` supplies the injection time and
`v_acsrc_acn`. Verify the F2-CREST1% local-crest gate against observed source
samples (120Vrms sinusoidal reference peak~169.7056V); do not substitute a
nominal timestamp for a measured edge. A phase, source-prefix or completeness
failure prevents a settled-fault acceptance. Preserve complete electrical
failures as failures and incomplete captures as incomplete evidence.

## Evidence and interpretation boundaries

The runner/decoder/adapter/validator chain is evidence transport. Preserve its
raw gzip, metadata, reports, source/tool hashes, and process exits. The adapter's
schema status and validator result do not establish hardware protection. F2-CREST
is an F2-open case; report channel current and residual body/boost/F2 branches
independently. Endpoint and phase checks are necessary but do not establish electrical
waveform equivalence to the finite materializer. Evaluate this exact captured
compact-source case and retain that limitation.

**Status: PREPARED_UNEXECUTED. Parent review and storage gate required.**
