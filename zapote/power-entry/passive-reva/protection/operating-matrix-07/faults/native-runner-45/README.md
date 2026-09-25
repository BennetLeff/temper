# Native fault runner 45 (global outer-gap candidate)

This is an unlaunched fork of `faults/native-runner-29/supervisor.rs`. It
preserves runner-29's anonymous native capture transport, source/include
closure checks, manifest/timing binding, metadata and row-count guards, disk
floor, bounded timeout, FIFO cleanup, child kill/reap, and diagnostic-only
receipt. It does not start ngspice or consume a campaign case in this folder.

The candidate fixes only the timing-bound propagation at the stage-2 boundary:
`run-parameters.json.max_gap_s` remains the immutable prepared capture value
and must be exactly 25 ns. `gap-policy.json` records that value as both the
capture/local frozen-inner bound and records the separate 1 us global bound.
The adapter and outer event-aware validator receive 1 us; the unchanged inner
fault checker retains its own 25 ns local event guard. No local pacing rule is
widened and no timestamp is edited. Runner-29 already maps CLI `switch-short`
to the manifest `SW-SHORT` spelling; this candidate leaves that binding unchanged.
The candidate still requires
`--bypass` to match the immutable run parameters and always writes
`acceptance:false` in its diagnostic result. A validator exit zero remains a
review receipt, never a protection or hardware claim.

## Verification

```sh
rustc --edition=2021 -D warnings --test supervisor.rs \
  -o /tmp/matrix07-native-runner45-tests
/tmp/matrix07-native-runner45-tests
# 12 passed, 1 ignored, 0 failed (the inherited-fd probe is sandbox-ignored)
rustc --edition=2021 -D warnings -O supervisor.rs \
  -o native-runner45-supervisor
```

The focused regressions require exactly `25e-9` for the prepared local
parameter and map it to `1e-6` for the outer adapter/validator; nonfinite,
looser, or tighter capture values fail closed. No runtime proof, capture, or
solver result is included here; parent review must bind the frozen source/tool hashes and
choose a fresh output directory before any adoption.
