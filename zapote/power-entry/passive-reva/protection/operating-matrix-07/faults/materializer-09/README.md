# Matrix 07 fault materializer (preparation only)

`materializer.rs` copies the six-file closure of
`normal-hysteretic-driver-candidate`, hashes each original file with external
`shasum -a 256`, and writes a fresh case directory. It accepts an explicit
case, `T_FAULT`, `TSTOP`, and `PREFAULT_WINDOW`; it rejects nonfinite or
nonpositive values, an unordered endpoint, a prefault window below 1 us, and
an existing output directory.

The source contract accepts exactly one `.param RLOAD=190 TSTOP=<value>
STEP=500n` line. `<value>` may be a finite positive seconds value or a finite
positive SPICE `m` (milli) value, so both the current `500m` source and the
settling-extension `650m` source are covered. RLOAD, STEP, line shape, and
all other source bytes remain exact; duplicates, malformed suffixes, and
nonpositive/nonfinite TSTOP values fail closed. The inverse unit test proves
that materializing and reversing the 650m source restores its electrical deck
byte-for-byte. This is source compatibility only and does not accept either
normal source or launch a simulation.

The seven named cases are `F2-CREST`, `F2-ZERO`, `F2-START`, `SW-SHORT`,
`DIODE-SHORT`, `BOTH-SHORT`, and `BYPASS-NEG`. The rewrites are mechanical:
F2 and both diode legs receive ideal 0-V branch sense sources; DIODE-SHORT
shorts the `sw -> d1_path` leg in parallel with Dboost1; SW-SHORT adds the
`sw -> channel_source` failed-short branch; BOTH-SHORT combines those two
mutations; BYPASS-NEG applies the F2 mutation and sets the protection
`BYPASS=1` parameter. The original normal `.save` line remains, followed by
the exact 17-column fault schema and four branch/marker extras.

Each case receives finite 1-ns control edges and a `fault_inject` marker
equal to the actual control voltage continuously (`5-V(f2ctl)` for F2 open,
the short-control voltage for a failed short, and the maximum of both for
BOTH-SHORT). Acceptance can threshold that marker at 2.5 V; the SW hysteresis
models switch near 2.6 V rising and 2.4 V falling. The receipt therefore
bounds command-to-marker ambiguity by the 1-ns edge plus accepted solver
sampling instead of inventing a hard-time marker. An isolated
alternating 25-ns PWL source paces from
`T_FAULT-PREFAULT_WINDOW-25 ns` through `TSTOP`, including the entry
boundary. This is an instrumentation load and is not a production-model
claim.

Build and test without running ngspice:

```sh
rustc --edition=2021 -D warnings --test materializer.rs -o /tmp/matrix07_materializer_tests
/tmp/matrix07_materializer_tests
rustc --edition=2021 -D warnings -O materializer.rs -o /tmp/matrix07_materializer
```

Example preparation command:

```sh
/tmp/matrix07_materializer \
  ../../normal-hysteretic-driver-candidate F2-CREST \
  1.0e-5 2.0e-5 1.0e-6 prepared/F2-CREST
```

Generated outputs are marked `PREPARED_UNEXECUTED`. They have no accepted
normal operating point, startup proof, phase/crest selection, or fault
verdict. Execution remains blocked until the accepted source, event choice,
prefault prefix instrumentation, and startup/endpoint checker contract are
reviewed. The materializer deliberately does not extend or invoke the fault
checker and does not launch full simulations.
