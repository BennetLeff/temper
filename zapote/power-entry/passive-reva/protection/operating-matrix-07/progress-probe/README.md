# Bounded progress-tracking probe

User requested a second simulation with live progress, run for about one
minute to assess completion time. The original CLI process was not modified
or signalled. This run uses libngspice 45.2, the same electrical deck, same
saved vectors, and byte-identical includes. Only the original `.control`
run/export/quit block is removed so the host can control execution.
`inputs.json` records identity. Sparse and the original tolerances remain.

The Rust harness installs SendData and SendInitData callbacks; both are
needed in this version to initialize per-point transfer. It copies only the
scale time into an atomic, records a callback count, and prints/writes a
progress row about every ten wall seconds. It never retains library-owned
pointers or queries mutable vectors concurrently. At 60 wall seconds it
requests bg_halt, waits for an idle solver, and exports the partial bus trace.
No electrical acceptance is inferred from the harness exit status.

The smoke circuit reached exactly 1 ms; 1,011 reported data callbacks matched
the exported row count, and the callback endpoint matched the exported time.
The initial smoke attempt omitted SendInitData and reported zero callbacks;
that instrumentation defect was corrected before the power-stage run.

Build/run from this directory:

```sh
rustc --edition=2021 -O progress.rs -L /opt/homebrew/lib -l ngspice -o /private/tmp/matrix07-progress
SPICE_SCRIPTS=/opt/homebrew/Cellar/ngspice/45.2/share/ngspice/scripts \
  /private/tmp/matrix07-progress cold.cir 60 0.5 > run.log 2>&1
```

Use a separate directory for each execution: filenames are fixed. This is
a bounded diagnostic harness, not yet a production campaign supervisor.
The wall limit excludes setup and the final halt/export overhead. No
automatic stall timeout or resume-from-file capability is implemented.

## Measured result

| Wall time | Simulated time | Fraction of 500 ms |
|---:|---:|---:|
| 10.08 s | 16.81 ms | 3.36% |
| 20.09 s | 26.64 ms | 5.33% |
| 30.10 s | 40.45 ms | 8.09% |
| 40.14 s | 55.73 ms | 11.15% |
| 50.15 s | 59.45 ms | 11.89% |
| 60.04 s | 66.16 ms | 13.23% |

The final halt/export took total wall time to 61.23 s. The final partial
trace has 1,412,803 finite, strictly increasing rows, endpoint
0.06616456597578449 s, and bus voltage 120.7815 V. The endpoint agrees with
the final callback. Two points arrived between the 60-second observation
and completion of the halt; this is expected. The existing diagnostic Rust
inspector independently verified ordering and the recorded endpoint.

Average-rate linear extrapolation gives about 7.56 minutes total. Using the
last observed ten-second interval instead gives about 10.66 more minutes
from the 60-second observation. These are conditional extrapolations, not
an ETA guarantee or a confidence interval. Early startup rate varies by more
than fourfold across the recorded windows; later solver difficulty can
invalidate either estimate. The probe does not reach the previously
problematic 350 ms region and cannot locate the original CLI run's current
time. It was executed concurrently with that original run.

Primary API basis: [ngspice shared library](https://ngspice.sourceforge.io/shared.html).
