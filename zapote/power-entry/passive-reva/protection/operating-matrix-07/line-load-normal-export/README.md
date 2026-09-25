# Campaign 07 normal export storage reduction

This candidate addresses grid storage pressure only. It keeps the electrical
deck and its single `.save` line unchanged, so ngspice still delivers the
original 30 saved vectors and the first-invalid callback still checks all 16
diagnostics. After the solver has stopped, the host's `wrdata` command exports
only the 14 normalizer source vectors (`v(acsrc)`, `v(acn)`, `i(Vac)`,
`v(load)`, `v(vb)`, `i(Lboost)`, `v(vd)`, `v(sw)`, `v(gate)`, `v(q)`, `v(en)`,
`v(fault)`, `v(vcomp)`, `v(icomp)`); `time` remains implicit. No signal is
removed from the circuit or from the callback path. The host fails closed if
the required normal inventory or any of the 16 diagnostic names is absent or
duplicated in `.save`.

The callback also latches a nonfinite real value from any saved vector. A
normal run selects the 14-vector export; a run with that latch set selects the
original full saved inventory after stop, preserving the normalizer's ability
to reject the complete bad trace. The synthetic callback test covers a finite
time with a NaN internal diagnostic and verifies the full-export choice.

The exact five-argument protocol is unchanged:

```text
/tmp/matrix07-normal-reduced-export-host-07 \
  cold.cir WALL_SECONDS TARGET_SECONDS trace.tsv first-invalid.tsv
```

The full and reduced 50 us smokes used byte-identical copies of the same
cold-start deck and include closure. With `SPICE_SCRIPTS` set to the ngspice
45.2 script directory, both reached `5.000000000000e-5` s in 497 rows with
`first_invalid=false` and `seen_names_mask=65535`. The reduced host also recorded
`all_saved_finite=true` with `export_mode=normal14_poststop`. The Rust comparison checked
all 15 normal trace columns (time plus 14 signals) byte-for-byte across every
row, strict finite/increasing time and endpoint, and byte-identical output
from the existing 12-column Rust normalizer. The normalized files are retained
in each smoke directory as evidence.

This is export-only evidence, not a normal operating-point acceptance and not
a fault result. Successful grid runs will no longer retain continuous internal
diagnostic waveforms in the exported file; the first-invalid snapshot still
retains all 16 diagnostics. The parent independently compiled the host, passed
all five tests, regenerated both nonempty normalized files, and repeated the
comparison and strict trace inspection. The export tradeoff is accepted for
future grid runs; the live 650 ms baseline retains its original full export.

Build and run the bounded checks:

```sh
rustc --edition=2021 -D warnings --test progress.rs \
  -o /tmp/matrix07-normal-export-tests
/tmp/matrix07-normal-export-tests
rustc --edition=2021 -D warnings -O progress.rs \
  -L /opt/homebrew/opt/libngspice/lib -l ngspice \
  -o /tmp/matrix07-normal-reduced-export-host-07
rustc --edition=2021 -D warnings -O ../checker/normalize.rs \
  -o /tmp/matrix07-normalizer-07
rustc --edition=2021 -D warnings -O compare.rs \
  -o /tmp/matrix07-normal-export-compare-07
```

The full reference host is `/tmp/matrix07-hysteretic-driver-host`; neither
host has been used for the long matrix.
