# Reanalysis-23: bounded stage-2 transport candidate

This folder contains a **worker-review candidate** for reanalyzing an already
captured native `fault42` trace. It never invokes ngspice and it never writes
to the captured case. The intended input is the immutable
`faults/startup-compact-candidate-20/` capture; no live reanalysis has been
launched from this folder.

The supervisor validates `capture-metadata.json`, `run-parameters.json`, the
case manifest and its declared output hashes, `capture-stage1.json`, the raw
gzip byte count/hash, the source identity closure, and the executable hashes.
The validator executable may be an explicitly recorded diagnostic override;
the expected and actual path/hash are written to
`validator-tool-override.json`. It then streams

```
raw.trace.raw.gz -> pigz -dc -> fault42 decoder -> adapter -> validator
```

through two owned FIFOs. No decoded TSV is retained. Every child is polled
under the case export timeout, the 10 GiB free-space floor is checked while
the pipeline runs, and all children are killed/reaped on timeout, disk
failure, or wait failure; an early nonzero child is retained in the status
record and bounded by the same timeout. Existing output directories are
refused. Source and tool hashes, plus the raw trace hash, are checked again
after a successful transport.

The receipt always says `acceptance:false` and `REVIEW_PENDING`; a zero exit
from transport or validation is diagnostic evidence only. A validator fault
verdict is not converted into an engineering pass.

## Reproducible bounded check

The synthetic source under `fixtures/synthetic-case/` is a five-row,
`TEST_ONLY` fixture copied from the reviewed native-runner fixture. Its
`capture-stage1.json` binds the copied 555-byte raw gzip. The command below
uses the reviewed validator22 binary as a deliberate tool override and writes
to a fresh output directory:

```sh
rustc --edition=2021 -D warnings supervisor.rs -o /tmp/matrix07-reanalysis23
/tmp/matrix07-reanalysis23 \
  fixtures/synthetic-case fixtures/synthetic-output-rerun \
  /opt/homebrew/Cellar/pigz/2.8_1/bin/pigz \
  /private/tmp/matrix07-fault-native-decoder-parent \
  /private/tmp/matrix07-fault-adapter-parent \
  /private/tmp/matrix07-fault-validation22-parent
```

Observed bounded result: four children exited zero, five rows were retained
by both adapter and validator, and the receipt classification was
`COMPLETE_REVIEW_PENDING` with `acceptance:false`. The validator override is
recorded in `fixtures/synthetic-output/validator-tool-override.json`.

Unit checks:

```sh
rustc --edition=2021 -D warnings --test supervisor.rs \
  -o /tmp/matrix07-reanalysis23-tests
/tmp/matrix07-reanalysis23-tests
```

The four tests cover finite-positive parameter parsing, control-character
JSON escaping, timeout kill/reap, and FIFO type verification.

## Planned real invocation (parent review required)

Do not run this command until the parent explicitly reviews the immutable
source and disk headroom. The production capture currently records
6,025,180 points and raw gzip SHA-256
`9be2bbe73cd0aee5c6751566bfa818968deeb24d68d6b76d323f56f76cbfd05e`; use a
new empty output directory and the validator22 override:

```sh
/tmp/matrix07-reanalysis23 \
  faults/startup-compact-candidate-20 /private/tmp/matrix07-reanalysis23-live \
  /opt/homebrew/Cellar/pigz/2.8_1/bin/pigz \
  /private/tmp/matrix07-fault-native-decoder-parent \
  /private/tmp/matrix07-fault-adapter-parent \
  /private/tmp/matrix07-fault-validation22-parent
```

This is a transport/diagnostic reanalysis only. The original capture and its
stage-1 receipt remain authoritative for source and raw-trace identity.
