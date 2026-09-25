# Nine-point 650 ms launch runbook

This is a launch checklist, not an execution receipt. The source is still
live and unaccepted: `normal-hysteretic-settling-extension/execution.json`
currently says `accepted: false`. Do not use that file as the baseline receipt.
Run the matrix only after the parent records a separate accepted receipt for
the exact settling-extension source below.

## Fixed inputs

Use these paths exactly:

```sh
BASE=/private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/operating-matrix-07
SOURCE="$BASE/normal-hysteretic-settling-extension"
MANIFEST="$BASE/line-load-prep/manifest.json"
BASELINE="$BASE/host/accepted-normal-hysteretic-settling-065.json"
OUT="$BASE/line-load-runs/hysteretic-settling-650ms"
RUNNER=/private/tmp/matrix07-line-load-runner-host
TRACKED=/private/tmp/matrix07-normal-grid-host
NORMALIZE=/private/tmp/matrix07-normalize
CHECKER=/private/tmp/matrix07-checker
SPICE_SCRIPTS=/opt/homebrew/Cellar/ngspice/45.2/share/ngspice/scripts
PIGZ=/opt/homebrew/bin/pigz
```

The source deck declares `TSTOP=650m`; the command must use `--end-s 0.65`.
The nine manifest rows are fixed and must remain unchanged:

| id | line RMS (V) | RLOAD (ohm) |
|---|---:|---:|
| LL01 | 108 | 416.460488957 |
| LL02 | 108 | 208.230244479 |
| LL03 | 108 | 115.683469155 |
| LL04 | 120 | 374.814440062 |
| LL05 | 120 | 187.407220031 |
| LL06 | 120 | 104.115122239 |
| LL07 | 132 | 374.814440062 |
| LL08 | 132 | 187.407220031 |
| LL09 | 132 | 104.115122239 |

The manifest's `source_identity` is intentionally `PENDING`; the runner binds
the actual source through `BASELINE` instead. Do not edit the manifest to make
that field look accepted.

## Preconditions

1. The parent must create `BASELINE` only after the complete 0.65 s settling
   trace passes the maintained normalizer and strict checker. It must have
   exactly this semantic shape (the runner also rejects duplicate critical
   JSON keys):

   ```json
   {
     "status": "accepted",
     "accepted": true,
     "endpoint_s": 0.65,
     "deck_sha256": "64 lowercase hexadecimal characters",
     "includes_sha256": "64 lowercase hexadecimal characters"
   }
   ```

   `target_end_s` may be used instead of `endpoint_s`, but not with a different
   value. The runner requires `status=accepted`, `accepted=true`, a positive
   numeric endpoint exactly equal to `0.65`, and both 64-character hashes.

2. Check the receipt and all executable paths without starting a simulation:

   ```sh
   jq -e '
     type == "object" and .status == "accepted" and .accepted == true and
     ((.endpoint_s // .target_end_s) == 0.65) and
     (.deck_sha256 | type == "string" and test("^[0-9a-f]{64}$")) and
     (.includes_sha256 | type == "string" and test("^[0-9a-f]{64}$"))
   ' "$BASELINE"
   jq -e '.accepted == false' "$SOURCE/execution.json"
   jq -e '(.status == "planned_unexecuted") and ([.points[].id] | sort) == ["LL01","LL02","LL03","LL04","LL05","LL06","LL07","LL08","LL09"]' "$MANIFEST"
   test -x "$RUNNER" -a -x "$TRACKED" -a -x "$NORMALIZE" -a -x "$CHECKER" -a -x "$PIGZ"
   test -d "$SPICE_SCRIPTS"
   test ! -e "$OUT"
   shasum -a 256 "$RUNNER" "$TRACKED" "$NORMALIZE" "$CHECKER" "$PIGZ"
   df -h "$BASE"
   ```

   The runner recomputes the source deck SHA and the recursive include-closure
   SHA from `SOURCE` and compares them with `BASELINE`; its include digest is
   the SHA-256 of sorted `relative-name\0file-sha256\n` records. A receipt from
   another source directory, even with the same endpoint, must fail this check.
   The runner records the actual source, host, checker, and compressor hashes
   in `OUT/source-identity.json` after launch.

3. Confirm storage before launch. The retained 500 ms baseline gzip is about
   4.02 GB; nine 650 ms traces can exceed the available ~51 GiB once raw
   artifacts, first-invalid snapshots, logs, and per-case metadata are kept.
   `df` is a gate, not a forecast: do not launch unless the parent has measured
   enough free space for all nine complete `trace.tsv.gz` files with margin.

## Staged launch commands

After all three preconditions pass, stage the run explicitly. The runner
always validates the complete nine-row manifest, then `--cases` selects a
unique subset in manifest order. The first command launches only LL01 and
LL02 into a fresh output directory. `--first-invalid-snapshot` is required
because this host implements the five-argument tracker protocol.

```sh
OUT_FIRST2="$BASE/line-load-runs/hysteretic-settling-650ms-first2"
test ! -e "$OUT_FIRST2"
"$RUNNER" \
  --source "$SOURCE" \
  --baseline "$BASELINE" \
  --manifest "$MANIFEST" \
  --output "$OUT_FIRST2" \
  --tracked "$TRACKED" \
  --normalize "$NORMALIZE" \
  --checker "$CHECKER" \
  --spice-scripts "$SPICE_SCRIPTS" \
  --workers 2 \
  --wall-limit 2700 \
  --end-s 0.65 \
  --pigz "$PIGZ" \
  --first-invalid-snapshot \
  --cases LL01,LL02
```

Review both complete receipts before starting the remaining seven:

```sh
cat "$OUT_FIRST2/status.json" "$OUT_FIRST2/LL01/result.json" "$OUT_FIRST2/LL02/result.json"
cat "$OUT_FIRST2/LL01/checker-report.txt" "$OUT_FIRST2/LL02/checker-report.txt"
test "$(jq -r .status "$OUT_FIRST2/status.json")" = selected_cases_checker_accepted
test "$(jq -r '.selected_cases | join(",")' "$OUT_FIRST2/status.json")" = LL01,LL02
```

If either case is rejected, incomplete, or storage is not adequate, stop and
do not launch the remaining cases. Once the review gate passes, use a distinct
output directory and select exactly LL03 through LL09:

```sh
OUT_REMAINING7="$BASE/line-load-runs/hysteretic-settling-650ms-remaining7"
test ! -e "$OUT_REMAINING7"
"$RUNNER" \
  --source "$SOURCE" \
  --baseline "$BASELINE" \
  --manifest "$MANIFEST" \
  --output "$OUT_REMAINING7" \
  --tracked "$TRACKED" \
  --normalize "$NORMALIZE" \
  --checker "$CHECKER" \
  --spice-scripts "$SPICE_SCRIPTS" \
  --workers 2 \
  --wall-limit 2700 \
  --end-s 0.65 \
  --pigz "$PIGZ" \
  --first-invalid-snapshot \
  --cases LL03,LL04,LL05,LL06,LL07,LL08,LL09
```

`--pigz` is restricted to two workers; each compressor uses four threads, so
the export stage is capped at eight compressor threads. The output remains a
gzip stream and is consumed by the existing `gzip -cd` pipeline. The runner
waits for each tracker and compressor, then runs the unchanged normalizer and
checker. A rejected point remains rejected; a partial trace or compressor
failure is a runner failure.

For either staged output, review each result and retain its source identity:

```sh
cat "$OUT_FIRST2/LL01/result.json" "$OUT_FIRST2/LL02/result.json"
cat "$OUT_FIRST2/LL01/checker-report.txt" "$OUT_FIRST2/LL02/checker-report.txt"
cat "$OUT_FIRST2/LL01/stop.txt" "$OUT_FIRST2/LL02/stop.txt" 2>/dev/null || true
```

Continue only if the selected output contains complete per-case receipts and
the first staged status is `{"status":"selected_cases_checker_accepted"}`;
the remaining-seven status has the same selected-case status. A default run
without `--cases` is the only form that writes `{"status":"all_checker_accepted"}`.
Any
`rejected`, `runner_failure`, `scheduler_timeout`, truncated trace, or missing
first-invalid snapshot is an investigation stop, not a reason to widen the
checker or relaunch over the same output directory.
