# Nonstopping first-invalid diagnostic host (prepared, unexecuted)

This host is a diagnostic copy of
`normal-hysteretic-settling-extension/progress.rs` for the unchanged
650 ms electrical source. It keeps the five-argument protocol, full `.save`
export, first-invalid snapshot, all 16 diagnostics, wall-time watchdog, and
120-second simulated-time stall watchdog. It does not alter the circuit or
the normalizer/checker contract.

The callback still captures the first non-increasing sample once, but a
duplicate timestamp no longer halts the simulation. It counts duplicates and
continues accepting later points. A genuinely backwards time step increments
the separate backwards counter and the main loop stops promptly with
`reason=negative_time_step`; a nonfinite time retains the finite guard and
stops with `reason=nonfinite_time`. Wall and stall watchdogs remain in the
main loop. Metadata and `stop.txt` explicitly record
`continue_after_duplicate=true`, `diagnostic_only=true`, duplicate/backwards
counts, and the full-export mode.

The synthetic callback tests cover first-invalid capture, duplicate
continuation to a later point, negative-step separation, finite/nonfinite
guards, and missing diagnostic handling. The binary is unique:
`/private/tmp/matrix07-nonstopping-diagnostic-host`. No simulation has been
launched from this directory and no accepted receipt is produced.

Build and run only the bounded unit checks:

```sh
rustc --edition=2021 -D warnings --test progress.rs \
  -o /tmp/matrix07-nonstopping-tests
/tmp/matrix07-nonstopping-tests
rustc --edition=2021 -D warnings -O progress.rs \
  -L /opt/homebrew/opt/libngspice/lib -l ngspice \
  -o /private/tmp/matrix07-nonstopping-diagnostic-host
```
