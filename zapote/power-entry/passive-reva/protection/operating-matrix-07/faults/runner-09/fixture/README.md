# Synthetic 42-column transport fixture

This fixture is a deterministic 20 us, 1001-row stream for exercising the
actual adapter/checker CLI. It is not a circuit and must never be sent to
ngspice. Copy this directory to a fresh output directory before running the
supervisor, because the supervisor refuses to overwrite receipts.

```sh
cp -R fixture /tmp/matrix07-runner-fixture-42
/tmp/matrix07-fault-supervisor-09 \
  /tmp/matrix07-runner-fixture-42 \
  /absolute/path/to/fixture/synthetic-tracker.py \
  /tmp/matrix07-fault-runner-adapter-09 \
  /tmp/matrix07-fault-runner-checker-09 \
  /opt/homebrew/bin/pigz \
  20e-6 f2-crest f2-open 10e-6 2e-6 2e-6 25e-9 2 5
```

Expected transport classification is `checker_pass`; this is not an
engineering acceptance claim.
