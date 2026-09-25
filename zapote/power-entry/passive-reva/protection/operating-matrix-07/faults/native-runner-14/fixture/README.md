# Native runner transport fixture (TEST_ONLY)

This case is a five-row deterministic native fault42 producer. It never
invokes ngspice and is not an electrical or protection result. It exercises the
FIFO -> pigz -> native decoder -> event-aware adapter -> event-aware validator
pipeline and leaves one compressed `raw.trace.raw.gz` plus reports.

```sh
cp -R fixture /tmp/matrix07-native-runner14-fixture
/tmp/matrix07-fault-native-runner14 \
  /tmp/matrix07-native-runner14-fixture \
  /tmp/matrix07-native-runner14-synthetic-host \
  /opt/homebrew/bin/pigz \
  /private/tmp/matrix07-fault-native-decoder-parent \
  /private/tmp/matrix07-fault-adapter-parent \
  /private/tmp/matrix07-fault-validation-parent \
  2e-6 f2-start 1e-6 2e-7 1e-6 2e-6 2e-6 1e-6 2 10
```

Set `SPICE_SCRIPTS` to the reviewed ngspice scripts directory before invoking
the command; the supervisor requires this binding even for the fixture:
`SPICE_SCRIPTS=/opt/homebrew/Cellar/ngspice/45.2/share/ngspice/scripts`.

The fixture remains `REVIEW_PENDING`; validator output is diagnostic and cannot
imply campaign acceptance. The runner refuses reused outputs and removes FIFOs
after success or failure.
