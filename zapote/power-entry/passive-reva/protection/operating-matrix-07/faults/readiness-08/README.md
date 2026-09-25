# Fault-campaign readiness audit 08

Status: **PLANNED / UNEXECUTED** (2026-09-20).

This audit is preparation for the first fault runs after matrix 07 accepts a
contiguous cold-start normal trace. It does not claim normal operation,
protection operation, hardware safety, fuse interruption, or component
qualification. The current normal run must first pass the existing operating-
point checker with its exact end point and input hashes.

## What is ready and what is missing

The existing fault validator already has the right high-level safety rule for
a failed-short switch: a low gate does not count as interruption while
`i(Vchannel)` remains nonzero. It also reports `i(Vbody)`/`i(Lboost)` as
separate passive-current evidence. Its 11 Rust unit tests pass:

```text
rustc --edition=2021 --test faults/fault_checks.rs \
  -o /tmp/temper07_fault_readiness_checks
/tmp/temper07_fault_readiness_checks
```

The current cold deck is not yet a fault deck. Its `.save` line has
`v(acsrc)`, `v(acn)`, `i(Vac)`, `v(load)`, `v(vb)`, `i(Lboost)`, `v(vd)`,
`v(sw)`, `v(gate)`, `v(q)`, `v(en)`, `v(fault)`, `v(vcomp)`, and `v(icomp)`.
It does **not** emit the fault checker's exact interface: direct line voltage,
`i(Vchannel)`, `i(Vbody)`, `v(standby_req)`, `v(arm)`, or `v(permit)`. It also
does not emit branch identity currents for `Sf2` or either boost diode. The
first fault deck must add those signals and be checked for the exact header
before any campaign verdict is read.

The checker has one remaining evidence gap that the host must close in the
deck/receipt: only F2-open has a trace-visible mutation (`v(f2ctl)`).
Switch-short and diode-short are selected by the command-line kind, but the
trace does not prove that the declared graph mutation actually occurred. Each
such deck therefore needs an explicit fault-injection control column (or an
equivalent receipt-bound source hash and event marker) and a recorded
mutation time. A low gate or a detector edge alone is not a mutation witness.

## Minimal first batch after a normal pass

Run these three cases, in this order, from the accepted cold source:

1. **F2-CREST** — open F2 at the first selected settled interval whose
   `abs(v(acsrc,acn))` is within 1% of the local crest. This is the smallest
   healthy-path shutdown case and exercises the detector/latch while the
   bridge/boost path is carrying its largest source voltage.
2. **F2-ZERO** — repeat with an AC zero crossing. It is a separate case because
   the inductor current and diode conduction state differ even when the bus
   voltage is similar.
3. **SW-SHORT** — add a declared low-ohmic switch-short branch at the same
   accepted settled operating point. This is a required negative safety result:
   gate shutdown must not receive interruption credit, and sustained channel
   current must be reported as `PROTECTION_GAP`. The current checker also
   categorically disallows a `PASS` for a failed-short kind, so its
   `PROTECTION_GAP` result is a negative-control classification, not proof that
   the measured waveform had a particular current. The case receipt must carry
   the actual `i(Vchannel)` peak and duration and keep that measurement
   separate from the negative-control verdict.

Do not start with `F2-START`, `DIODE-SHORT`, or `BOTH-SHORT`. F2-START needs a
separate startup event contract. The diode and simultaneous-short cases need
the branch-current and energy/inductor model review first. `BYPASS-NEG` is a
validator negative control after one positive-path deck is mechanically
verified; it is never a circuit pass.

## Required starting state

Every first-batch deck is a mechanical edit of the accepted
`normal-tracked/cold.cir`. Keep all original zero initial conditions and the
same controller/clamp/standby includes. Choose `T_FAULT` only after the
normal trace identifies a settled interval and record its phase and bus/load
values. Do not add `.ic` values to `vd`, `vb`, `Lboost`, or controller state,
and do not substitute the old precharged integration-06 deck. A simulator
restart from a validated contiguous prefix is acceptable only when its state
transport is independently receipted; no such restart receipt currently
exists.

For F2 cases, retain the existing `Vf2ctl` control and make the open edge
explicit at `T_FAULT` (5 V until `T_FAULT-1n`, then 0 V). For SW-SHORT, add a
parallel, event-controlled low-ohmic branch from `sw` to `channel_source`;
leave the healthy MOS model unchanged so the mutation is explicit. The source
hash, event time, resistance, and branch name belong in the per-case receipt.

## Current-channel contract

The first fault deck should save at least the following vectors, in this
order, and the host should normalize only names/whitespace:

```text
time v(acsrc,acn) v(vd) v(vb) v(sw) v(gate) i(Lboost) i(Vchannel) i(Vbody) i(Vac) v(q) v(en) v(fault) v(f2ctl) v(standby_req) v(arm) v(permit) i(Vf2sense) i(Vdboost1sense) i(Vdboost2sense) v(fault_inject)
```

The first 17 fields are the current Rust checker's exact interface. The last
four are mandatory campaign evidence additions: `i(Vf2sense)` identifies the
F2 path, `i(Vdboost1/2sense)` identifies remaining diode/passive current, and
`v(fault_inject)` proves the declared switch/diode mutation. ngspice 45.2 does
not expose direct switch/diode current vectors, so these are named ideal
zero-volt sense-source branches. Do not infer branch current from `v(sw)`, a
low gate, or `i(Lboost)` alone.

The validator's node screens remain model screens (`vd` 500 V, `vb` 450 V,
`sw` 650 V, `gate` 25 V, `Lboost` 100 A). They are not silicon, fuse, thermal,
or mains-safety ratings. In particular, a `SW-SHORT` run that produces a low
gate and persistent channel current is a protection gap even if every voltage
screen passes.

## First-batch commands (after acceptance)

The host should copy the accepted source into one directory per case, apply
only the declared mechanical mutation, hash the resulting deck and the four
included model files (`ucc28180-pwm-latch.inc`, `protection.inc`, `standby.inc`,
and `clamp.inc`), and launch ngspice with the same options as the accepted
normal run. The existing `matrix07-normalize` is the normal-operating adapter:
it emits 12 normal fields and **must not** be piped into the 17-column fault
checker. A fault-specific Rust adapter must first map the raw vectors into the
exact fault header (and retain the four branch/injection additions), for
example `/private/tmp/matrix07-fault-normalize` built from
`fault_normalize.rs` after its unit tests pass.
The fault checker consumes a file path, not stdin:

```sh
gzip -cd F2-CREST/raw.tsv.gz > F2-CREST/raw.tsv
/private/tmp/matrix07-fault-normalize F2-CREST/raw.tsv F2-CREST/TRACE.tsv \
  F2-CREST/supplement.tsv F2-CREST/adapter-report.txt \
  TSTOP f2-crest T_FAULT EVENT_WINDOW MAX_GAP
/private/tmp/matrix07-fault-checks F2-CREST/TRACE.tsv TSTOP f2-open \
  T_FAULT DETECTOR_WINDOW TURNOFF_BUDGET OBSERVATION MAX_GAP
```

The exact command must use the case's numeric `T_FAULT` and bounds from its
receipt; the placeholders above are not executable values. Preserve the raw
deck, command, simulator identity, stderr/stdout, trace (including partial or
failed traces), and Rust verdict. A solver exit code or a low gate is never a
pass by itself.

The adapter source and tests are in this readiness directory. It is still an
adapter, not the fault verdict: the resulting `TRACE.tsv` must be passed to
the independent Rust fault checker, and the supplemental report must be
retained with the case. Do not replace it with a shell/Python column remix.

Build and run its bounded-memory controls with:

```sh
rustc --edition=2021 --test fault_normalize.rs \
  -o /tmp/temper07_fault_normalize_tests
/tmp/temper07_fault_normalize_tests   # 9 passed
rustc --edition=2021 -O fault_normalize.rs -o /tmp/matrix07-fault-normalize
```

The CLI uses `BufRead`/`BufWriter`, keeps one previous row and scalar metrics,
and rejects every nonnumeric/nonfinite field, including unused extra columns.
