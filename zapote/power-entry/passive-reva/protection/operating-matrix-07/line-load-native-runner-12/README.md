# Native line/load runner candidate (matrix-07)

This is a production-candidate orchestration harness for the accepted
`event-aware-normal-v1` modeled baseline. It is deliberately separate from
the legacy ASCII runner and does not launch a campaign in this preparation
step. The native host writes a little-endian ngspice real binary raw plot to a
FIFO. A `pigz -p4` child retains one compressed `raw.trace.raw.gz` per case.
After the producer and compressor finish, the runner performs bounded scans:

1. native decoder (`--schema normal15 --byte-order little`) to the raw-15 event
   audit, with `--end-s`, `--rload`, and an owned `--events` output path;
2. decoder to the maintained 12-column normalizer and unchanged checker; and
3. decoder to the normalizer and event-aware metrics evaluator.

No uncompressed trace is retained. Every child is waited/reaped, pipeline
failures are recorded, and a case can only finish as
`complete_review_pending`. The runner never turns an event-audit exit, metrics
screen, or checker result into an automatic operating-matrix acceptance.

The runner binds all six baseline source files before launch and checks their
hashes against `accepted-baseline-11/acceptance.json`. It verifies the source
closure again after each case's transport pipeline. Generated decks replace
only the `VAC_RMS` and `RLOAD` tokens; all include bytes are copied and hashed.
The baseline policy and source hashes are explicit; a legacy fake
`status=accepted` receipt is rejected. Existing output directories are refused.
A 10 GiB free-space floor is checked before and during the run.

## Build and preflight

```sh
rustc --edition=2021 -D warnings -O runner.rs \
  -o /private/tmp/matrix07-line-load-native-runner-12
/private/tmp/matrix07-line-load-native-runner-12 --self-test

/private/tmp/matrix07-line-load-native-runner-12 --inspect \
  --source /private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/operating-matrix-07/accepted-baseline-11 \
  --baseline /private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/operating-matrix-07/accepted-baseline-11/acceptance.json \
  --manifest /private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/operating-matrix-07/line-load-prep/manifest.json \
  --output /private/tmp/matrix07-native-preflight-output \
  --tracked /private/tmp/matrix07-normal-native-host-12 \
  --normalize /private/tmp/matrix07-normalize \
  --checker /private/tmp/matrix07-checker \
  --decoder /private/tmp/matrix07-native-stream-host \
  --event-metrics /private/tmp/matrix07-event-metrics-host \
  --event-audit /private/tmp/matrix07-normal15-event-audit-host \
  --workers 2 --end-s .65
```

The final audit binary is not present in this preparation receipt, so the
inspect command intentionally fails closed until the parent supplies the
source-bound `/private/tmp/matrix07-normal15-event-audit-host`. The expected
CLI is stdin normal15 text plus `--end-s T --rload R --events PATH` and a
structured diagnostic report on stdout; it is not a checker or acceptance
program.

A full run should begin with one selected case, then be reviewed before
admitting a second worker. The runner accepts `--cases LL01` or a unique
manifest-order subset such as `--cases LL01,LL02`; it always validates the
complete nine-point manifest first. Use a fresh output directory and the
parent's 3600 s producer wall bound / 900 s export bound. No full launch is
included here.
