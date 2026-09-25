# Timestamp policy review: equal-time accepted records

This is a policy review only. It does not change the timestamp checker, alter
the circuit, rerun ngspice, or turn any trace into an accepted operating point.
The question is narrower: if the simulator emits finite rows with
non-decreasing serialized time, can an isolated equal-time group be retained
for normal-operation metrics without hiding a state change? Fault timing is
included because row order at an equal timestamp can affect a detector, latch,
or switch transition.

## Decision in one paragraph

Finite, non-decreasing timestamps plus isolated equal-time groups and verified
later forward progress can support a **diagnostic** view of time-integral and
peak metrics. It does not, by itself, establish electrical-model accuracy,
bounded stored energy, or a qualified operating point. Every row must remain in
the evidence stream. A zero-duration interval contributes zero measure to an
ordinary time integral, but the rows at that time still participate in peak
scans and event ordering. The existing strict `dt > 0` acceptance checker
therefore remains unchanged until the exact callback contract and a bounded
event-state experiment justify a release-policy change.

## Evidence and its limits

The exact ngspice 45.2 archive used by the source audit has SHA-256
`ba8345f4c3774714c10f33d7da850d361cec7d14b3a295d0dc9fd96f7423812d`.
The parent-verified excerpt has SHA-256
`3e0ebe5e8b6017329095c1b6f466ebf11d045396cfd4d7c814b2bf4709a50014`.
Those excerpts establish the following source path:

```
CKTaccept -> CKTdump -> OUTpData -> sh_ExecutePerLoop
```

`dctran.c` calls `CKTaccept` and then dumps the accepted time. The shared
callback path defines `vecindex` as an accepted-point index, but neither the
header nor the manual promises that successive callback `time` values are
strictly increasing. The excerpt shows no monotonic-time filter. With XSPICE,
the temporary-breakpoint and `CKTminBreak` paths can request very small steps.
For the present 500 ns maximum step, the source rule
`CKTdelmin = 1e-11 * CKTmaxStep` gives approximately `5e-18 s`, below the
binary64 ULP near 0.5 s (approximately `1.11e-16 s`). A positive internal
step can consequently serialize to the same binary64 time. This is a mechanism
consistent with the traces, not proof of the failing internal delta or of
electrical correctness.

The same-time audits are materially different:

* The hysteretic extension has 22,759,008 rows, two equal-time groups, five
  rows in those groups, and three repeats. The largest group has three rows,
  followed by `1.1102230246251565e-16 s` of positive progress. The largest
  within-group `v(xdriver.drv_delay)` change is about `3.96e-8 V`; the trace
  later advances by about 21.4 us before the host export stops.
* The native COMPHYS trace has 11,176,288 rows, one three-row group, two
  repeats at `0.25973229078302656 s`, followed by
  `5.5511151231257827e-17 s` of progress. It advanced about 16.41 us before
  the strict host stopped. It is still rejected and incomplete.
* The original hard-driver run has about 1,126,438 non-increasing intervals
  and stalls at `0.34853453797626816 s`. This is a persistent numerical stall,
  not evidence that an isolated event group is equivalent to a healthy trace.

The diagnostic reader already retains every row, rejects backward and
non-finite time/value fields, requires positive progress after an equal group,
and reports per-column extrema and equal-group deltas. Its result is
diagnostic-only. The current strict candidate remains rejected; the continuing
diagnostic run is not a baseline or an acceptance result.

## Three separate claims

### 1. Timestamp validity

The raw stream is structurally usable for this proposed diagnostic policy when
all fields are finite, time never goes backward, each equal-time group is
closed by a positive timestamp, and the input is not truncated. Preserve the
original row order and exact values. Do not deduplicate, interpolate, or
replace a group by its first or last row.

This is a statement about the serialized waveform. It says nothing about
whether a converged nonlinear state is physically accurate.

### 2. Numerical forward progress

An equal-time group is only a candidate event group. A future classifier should
record its start/end row and time, group size, every adjacent/full-group analog
delta, the next positive `dt`, and the positive-time advance reached within a
predeclared observation window. Maximum-gap checks apply to positive intervals;
an equal interval cannot conceal a later long gap. A watchdog and a bound on
simulated forward progress are appropriate. A duplicate-count bound must be
predeclared from an API/numerical experiment, not chosen after inspecting a
trace; the observed maximum of three is evidence for review, not a released
limit. Until that evidence exists, strict `dt > 0` remains the qualification
gate.

The 1.1-million-row hard-driver stall must fail this health test even if a
non-decreasing parser exists. Conversely, a short group followed by positive
progress must remain visible for review rather than being silently rejected as
if it were the same failure.

### 3. Electrical and model accuracy

Finite values and resumed time do not prove that analog state, switch timing,
or protection behavior is correct. Equal-time rows can carry state changes
that matter to stress peaks, detector/latch ordering, and a hard-short current
classification. Include every row in extrema scans, including rows with
`dt = 0`. For a conventional time integral, integrate only positive intervals;
the equal-time interval has zero duration. That convention must not be used to
erase an event or to claim an energy balance when the required state vectors
were not saved.

Fault timing is stricter in meaning than a normal integral: preserve equal-time
order, use the source row that first meets the detector/latch predicate, and do
not invent a timestamp between equal rows. Require positive progress after the
group and the declared local sampling-gap bound before classifying the trace.

## What the current deck actually saves

`normal-hysteretic-driver-candidate/cold.cir` includes
`ucc28180-pwm-latch.inc`, `protection.inc`, `standby.inc`, and `clamp.inc`.
Its `.save` line contains `time` plus 30 signals. The principal saved energy
coordinates are:

* `v(vb)` for `Cbank`, `i(Lboost)` for `Lboost`, and `v(vd)` for `Clocal`;
* `v(sw)`, `v(gate)`, and `v(isense)` for selected device/sense capacitance
  nodes; and
* `v(vcomp)`, `v(icomp)`, and `v(xdriver.drv_delay)` for selected controller
  state.

The included files add many additional capacitors and state nodes. Examples
are `Cblank`, `Cdf`, `Cbf`, `Civdo`/`Civbo`/`Civdh`/`Civbl`/`Civbh`/`Civdl`,
`Cirefd`/`Cirefb`, the `Cch_*` fault filters, `Cltimer`, `Catimer`, `Cfast`,
`Cfastout`, `Cfault`, `Chealth`, `Csmall*`, and the standby `Cigs`, `Cigd`,
`Cids`, `Cpgs`, `Cpgd`, and `Cpds`. Internal controller/protection nodes such
as `vsense`, `vcomp_s`, `dh`, `bh`, `ch_vd`, `ch_vb`, `ch_fwd`, `ch_rev`,
`ltimer`, `atimer`, `fast_input`, `fast_good`, `health`, `inhibit_gate`, and
`permit_gate` are not all present in the current `.save` vectors. Some switch
memory is algebraic/XSPICE state rather than a saved capacitor voltage.

The saved trace alone does not supply every stored-energy coordinate.
`i(Lboost)` supplies that linear inductor's coordinate when its value and
reference are fixed. Missing capacitor voltages require additional evidence:
direct samples, exact reconstruction, or a conservative analytical bound
derived from the actual source network. Absence of a saved vector is not proof
that no such bound is possible. This review has not derived those bounds.

## Concrete guards for a future diagnostic policy

These are proposed predeclared guards, not changes to the current checker:

1. Require an exact unique header, finite values in every column, non-decreasing
   time, a complete endpoint, and no backward interval. Retain the raw row and
   row index on every violation.
2. For each equal-time group, retain all rows and report group size, adjacent
   deltas, full-group extrema/deltas, and the first subsequent positive `dt`.
   Require that subsequent progress and the observation window are present;
   equal-time EOF is invalid.
3. Apply local maximum-gap and forward-progress bounds only to positive time
   intervals. Do not use a row-count cap unless a source/API experiment has
   established it before the campaign.
4. Scan peaks over every row, including equal-time rows. Compute integrals over
   positive intervals only, and expose the count and duration of zero intervals
   in the report.
5. For an energy-bounded result, obtain the voltage across each relevant
   capacitor and current through each relevant inductor, or supply an exact
   reconstruction or conservative analytical bound. Identify the terms covered
   by the claimed error budget and justify exclusions. Record element/model
   parameter hashes and source/work terms used in the residual. Report any
   remaining unbounded contribution rather than passing by omission.

These guards preserve stress and event evidence. They do not assert that a
same-time group is physically correct; they make the remaining uncertainty
explicit.

## Minimal evidence needed before changing acceptance

No hardware proof is required to answer this timestamp-policy question.
The following controlled experiments would help isolate the cause:

1. an exact-version, bounded deck that produces a finite equal-time group and
   then resumes positive progress;
2. a companion deck that produces a true no-progress stall under the same
   callback path; and
3. an independent check that the callback packet is an accepted output record,
   rather than a display interpolation/event notification.

Parent review: a reduced reproducer and companion stall deck are useful
diagnostics, not mandatory mathematical prerequisites invented for this
campaign. The exact callback source is already verified. A complete full-cold
trace can itself supply reproducible event evidence; retained stalled traces
and adversarial fixtures can test rejection behavior. Any revised acceptance
policy still needs an explicit numerical error argument, preserved raw
states/extrema/event order, independent validation, and a separately reported
result under the original strict checker. The current review does not supply
that error argument or authorize a policy change.

## What this review proves

It proves that the strict `dt > 0` rule is a conservative project acceptance
policy rather than a demonstrated ngspice callback contract, and that a
non-decreasing diagnostic can preserve isolated equal-time state changes
without hiding them. It also identifies missing saved state coordinates; it
does not establish that conservative analytical bounds on them are impossible.

It does **not** prove normal operation, fault protection, switch interruption,
electrical-model accuracy, or hardware equivalence. No checker or acceptance
decision is changed by this document.
