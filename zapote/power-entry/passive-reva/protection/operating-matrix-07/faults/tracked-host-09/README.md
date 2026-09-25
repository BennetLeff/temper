# Fault tracking host 09 (prepared, unexecuted)

This directory prepares the fault-specific five-argument tracker for the
materializer's corrected case decks. It is a transport/export check only; it
does not claim a normal operating point, fault response, or component safety.

`progress.rs` is the first-invalid callback host with the hysteretic driver's
16 diagnostic names (`xdriver.driver_req` and `xdriver.drv_delay`). It keeps
the existing wall/sim watchdog and exact protocol:

```text
/private/tmp/matrix07-fault-tracked-host-09 \
  case.cir WALL_SECONDS TARGET_SECONDS trace.tsv first-invalid.tsv
```

The prepared case deliberately has two `.save` lines. The host validates both
lines, requires the normal line to contain the original 30 signals and the
second line to match the exact 17-column fault schema plus four branch/marker
signals, then exports their ordered union once (41 signals plus `time`). This
retains the complete normal inventory for prefault checks while preventing
duplicate header names. The 16 diagnostic callback names remain in the
first-invalid snapshot; they are also in the normal `.save` inventory.

The source-bound copy is under `input/F2-START/`. Its copied case hash and
closure hashes are recorded in `manifest.json`; the host source and binary
hashes bind the executable to this schema. The corrected materializer case
has a strictly ordered final schedule point (case hash
`8f2500cf7706dd1bef9134306813c210c42a4951b9fa5487eb799534f43ae76a`). The
bounded export smoke completed for all seven prepared cases in about a second
total at 20 us simulated time per case. Each produced 42 header fields (`time`
plus 41 unique signals), all finite, with the normal 30, fault 17, evidence 4,
and 16 diagnostic coverage checks recorded by `verify_trace.rs`. Each trace
reached the exact 20 us endpoint with strictly increasing time. The verifier
also measures actual solver intervals over the required detector window
(`T_FAULT-PREFAULT_WINDOW` through 20 us), including the interval crossing its
start, and all seven stayed below 25 ns. The 25 ns instrumentation lead before
that required window is reported separately by `verify_schedule.rs`.
`verify_schedule.rs` checks the pacing instrument too: crest and short cases
begin at 8.975 us, zero begins at 10.975 us, startup begins at 0.975 us, and
each reaches 20 us with a nominal 25 ns maximum gap, including the boundary
bracket. Set `SPICE_SCRIPTS` to the ngspice script directory exactly as in the
manifest; without it the shared library can reject XSPICE model setup before
simulation. That missing environment caused the earlier UADC setup failure;
it is separate from the materializer's corrected duplicate endpoint.

Build and unit-test without running a campaign:

```sh
rustc --edition=2021 -D warnings --test progress.rs \
  -o /tmp/matrix07-fault-tracked-tests
/tmp/matrix07-fault-tracked-tests
rustc --edition=2021 -D warnings -O progress.rs \
  -L /opt/homebrew/opt/libngspice/lib -l ngspice \
  -o /private/tmp/matrix07-fault-tracked-host-09
rustc --edition=2021 -D warnings -O verify_trace.rs \
  -o /tmp/matrix07-fault-trace-verify-09
# pass the case's required-window start and add --strict-gap
/tmp/matrix07-fault-trace-verify-09 smoke/trace.tsv smoke/capture-metadata.json \
  2e-5 9e-6 --strict-gap
rustc --edition=2021 -D warnings -O verify_schedule.rs \
  -o /tmp/matrix07-fault-schedule-verify-09
```

The F2-START case remains outside the fault checker until the adapter's
startup event contract is reviewed. The materializer's case label and the
normalizer's accepted `Kind` names are not silently mapped by this host.
