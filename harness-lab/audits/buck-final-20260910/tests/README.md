# Closeout verification

## Latest follow-up

- The updated Rust unit suite passed all 47 tests, including startup compliance
  and a streamed 1,000,001-row binary control. The [binary integration log](followup-binary-integration.log)
  records three passing tests covering malformed files, paths, format binding,
  Python exponent identities, tampered settings, and equal ASCII/binary
  measurement results. Total: 50 Rust tests.
- [Full Python follow-up](followup-python-final.log): 138 tests passed in
  124.912 seconds with the current judge. Six new host tests exercise the
  binary collector, runtime/size limits, canonical settings text, streaming
  hash and trusted-root handling. Clippy with warnings denied, Rust formatting,
  and focused Python lint/format checks passed.
- [Real native startup evaluation](../full-scenario-readiness/native-startup-15v-500ma/protocol-v2/host-verification.json)
  decoded 4,015,356 samples and passed the startup protocol. The overall packet
  remains blocked because the model is unapproved and the matrix is incomplete.
- The earlier [follow-up Python run](followup-python.log) selected KiCad 10.0.6
  for legacy 10.0.4 fixtures and hit their explicit version guard. The corrected
  full-suite run uses installed 10.0.4 for those fixtures. Actual v2 qualification
  continues to select isolated 10.0.6; no version requirement was relaxed.

These updates invalidate older admission receipts. Native qualification and
engineering collection must be repeated on the final source/evidence state
before scored admission. The historical 36-control v2 receipt below remains
evidence for its original source state.

## Earlier closeout collection

- [Rust and umbrella-check log](rust-and-format.log): all 38 Rust tests passed;
  Clippy with warnings denied and Rust formatting passed. The umbrella
  `make check` then stopped at pre-existing Python formatting drift in
  `run_buck_trials.py`, `telemetry.py` and `test_telemetry.py`. It did not pass.
- [Final full Python suite](python-132-final.log): 132 tests passed in 125.876 s
  after the v2 runtime and circuit adapter changes. Tests ran outside the
  filesystem/process sandbox because native workers and loopback sockets are
  required. No external telemetry was exported by the tests.
- [Focused boundary/layout suite](boundary-layout-24.log): 24 tests passed
  after the new control geometry; the later full suite includes these tests.
- [Final native qualification](../native-tool/qualification/qualification.json):
  36 controls qualified using the root v2 launcher and isolated KiCad 10.0.6.
  All three witness runs for each of four variants passed; deliberately broken
  cases failed or became indeterminate as specified. Operation recovery and
  edit-budget/input boundaries also passed.
- [Engineering report](../engineering/report.json): source/candidate integrity
  passes for nine components; independent electrical-layout and presentation
  checks pass. Overall admission remains blocked by component/model evidence.
- [Preflight](../preflight/results.json): blocked before any solver attempt;
  telemetry disabled. This is a verified admission failure, not a successful
  live preflight or a measured model result.

The 13-case waveform test uses synthetic rawfiles as instrument controls. Its
startup/load verdicts exercise actual waveform checks, while its model receipt
is rejected. The approved component/model registries remain empty. No test log
in this directory establishes physical performance.

`python-132.log` is the earlier successful full suite before the runtime
selection changes; `python-132-final.log` records that earlier closeout state.
Expected argparse rejection messages appear during malformed-input tests;
the unittest summary determines whether those tests passed.
