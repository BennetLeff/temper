# Settled compact-pacer preparation (six cases)

This folder prepares the six settled fault decks that follow the accepted
650 ms normal source: `F2-CREST`, `F2-ZERO`, `SW-SHORT`, `DIODE-SHORT`,
`BOTH-SHORT`, and `BYPASS-NEG`. `F2-START` remains the separate startup case
in `startup-compact-candidate-20/`. The source closure is the six files bound
by `accepted-baseline-11/acceptance.json`; each case manifest repeats those
hashes and hashes every compact output file.

Each compact deck has exactly two deliberate transformations beyond the
materializer output: the finite alternating `Vschedule`/`Rschedule_probe`
block is replaced by the reviewed repeating source
`PWL(0 0 25n 1 50n 0) r=0`, delayed at the exact first finite-PWL timestamp,
and one `.options klu` line is added after the deck title, matching
`startup-klu-candidate-17`. The generated materializer
decks are retained under `expanded-materialized/` for source comparison; the
launch candidates are the small files under `prepared/` and contain no raw
trace.

The manifest preserves the materializer's uppercase case name while recording
the native CLI spelling separately: `SW-SHORT` maps to runner/adapter kind
`switch-short`; `DIODE-SHORT`, `BOTH-SHORT`, the F2 cases, and `BYPASS-NEG`
use their corresponding lowercase hyphenated kinds. This avoids a later
runner-kind mismatch without changing source identity.

The proposed settled events are:

| case | `T_FAULT` | prefault window | `TSTOP` | checker window / observation |
| --- | ---: | ---: | ---: | ---: |
| F2-CREST | 0.6541666666667 s | 2 ms | 0.662 s | 2 ms / 2 ms |
| F2-ZERO | 0.6583333333333 s | 10 ms | 0.682 s | 10 ms / 10 ms |
| SW-SHORT | 0.6541666666667 s | 2 ms | 0.662 s | 2 ms / 2 ms |
| DIODE-SHORT | 0.6541666666667 s | 2 ms | 0.662 s | 2 ms / 2 ms |
| BOTH-SHORT | 0.6541666666667 s | 2 ms | 0.662 s | 2 ms / 2 ms |
| BYPASS-NEG | 0.6541666666667 s | 2 ms | 0.662 s | 2 ms / 2 ms |

The times are analytic 60 Hz phase selections after the accepted 650 ms
endpoint. They must be checked against each actual fault trace's sampled
`v(acsrc,acn)` before any checker result is considered. Short cases retain the
existing categorical `PROTECTION_GAP` expectation and must still report actual
channel/branch currents independently. `DIODE-SHORT` and `BOTH-SHORT` remain
behind the branch-model review gate. `BYPASS-NEG` is a negative control, never
a protection pass.

The compact pacer starts at the exact finite source's first corner,
`T_FAULT - PREFAULT_WINDOW - 25 ns`, and supplies the 25 ns corner contract
before the event. Each manifest records the literal timestamp and checks it
against the expanded deck. The parent must compare that start
against the *actual detector-time* search window in the validator, including
detector latency; the declared mutation time alone is not sufficient evidence.

## Endpoint caveat

The isolated compact-pacer benchmark proves syntax, finite rows, corner
coverage, and the 25 ns local pacing contract only. It does not prove
electrical equivalence in this power stage. For these decimal phase times, the
finite materializer explicitly forced a final PWL value at `TSTOP`, while the
repeating compact source interpolates its phase. Every case manifest records
the finite endpoint value and the compact predicted value; all six currently
have `endpoint_equal: false` (the compact prediction is approximately
`0.333332`). The parent must inspect the actual compact
ngspice endpoint and either accept that instrumentation difference under the
endpoint policy or reject the candidate. No waveform equivalence or fault
acceptance is claimed here.

## Bounded preparation checks

The source-bound materializer tests and compile are:

```sh
rustc --edition=2021 -D warnings --test faults/materializer-09/materializer.rs \
  -o /tmp/matrix07-materializer24-tests
/tmp/matrix07-materializer24-tests
rustc --edition=2021 -D warnings -O faults/materializer-09/materializer.rs \
  -o /tmp/matrix07-materializer24
```

The six output manifests are `PREPARED_UNEXECUTED_COMPACT_PACER_CANDIDATE`.
They require, before any launch, an accepted settled prefix, actual source
phase verification, compact endpoint review, the native capture/decoder/
adapter/validator receipts, and enough storage for every canonical raw trace.
No ngspice simulation, fault checker, or acceptance operation was run by this
preparation.
