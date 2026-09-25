# F2 timing preflight (analytical, not acceptance evidence)

This note predeclares bounded timing choices for the three F2-open cases
before an accepted `matrix07_normal` prefix exists.  It does **not** claim a
detector time, phase, or fault waveform.  The exact F2 transition and detector
edge must be measured and retained from the accepted trace; the checker uses
the predeclared injection time as its search centre while the detector latency
is reported separately.  These are only finite search and observation
horizons.

## Why F2 open is not an instantaneous detector event

The candidate deck has `Clocal=19.8 uF`, `Cbank=2240 uF`, and a retained
divider mismatch factor `MISMATCH=1.0355871886`.  At the nominal
`VB=389.615 V` screen, 3.5587% corresponds to approximately:

```
delta_V = 389.615 V * 0.0355871886 = 13.865 V
C_local / C_bank = 0.008839
t_to_deltaV = C_local * delta_V / |I_mismatch|
```

That last expression is only a sensitivity estimate; `I_mismatch` is not a
measured quantity here.  It gives 2.745 ms at 0.1 A, 0.915 ms at 0.3 A,
0.275 ms at 1 A, 91.5 us at 3 A, and 27.5 us at 10 A.  Thus an F2-open
detector can plausibly appear in tens/hundreds of microseconds near a crest,
while near a mains zero the available input power is proportional to
`sin^2(2 pi 60 t)` and the divergence can take milliseconds.  The estimate
does not prove that the candidate detector will assert in any of those times;
boost control, load, diode states, source phase, and the detector's comparator
polarity still have to be observed.

The deck's explicit `Rlocal=450 kOhm` bleed would by itself take roughly
`C_local*delta_V/(389.615/450 kOhm) = 0.317 s` to create that voltage difference.
That is why the horizons are planning bounds for the coupled switching/source
behavior, not a claim that the passive capacitor mismatch alone forces a fault.

The protection include gives the short internal scales separately:
`FAULT_TAU=79.3 ns`, latch delays of 19 ns, and a retriggerable
`CT_HOLD=132 us`.  At the retained approximately 129.1 kHz switching rate,
one period is 7.746 us.  The existing 2 us turn-off budget is therefore about
0.258 switching periods and is retained unchanged.  It is a response budget
after a detector edge, not a license to search indefinitely for the edge.

## Predeclared finite horizons

The following horizons are for run planning and trace retention.  They are
not the `DETECTOR_WINDOW` argument to the checker.

| case | event selection | detector search after accepted F2 edge | post-detector observation |
|---|---|---:|---:|
| F2-CREST | first accepted settled-normal event with `abs(v(acsrc,acn))` within 1% of local crest | 2 ms | 2 ms |
| F2-ZERO | first accepted settled-normal event with `abs(v(acsrc,acn))` within 1% of local zero | 10 ms | 10 ms |
| F2-START | first event after a qualified armed/permit prefix, before settled-normal operation | 10 ms | 2 ms |

The 2 ms crest horizon covers the model's fast 10-to-1 A sensitivity range
and more than 15 `CT_HOLD` intervals.  The 10 ms zero horizon spans one full
120 Hz rectified-power period (8.333 ms) plus margin, so the next power crest
is available to expose a mismatch.  The startup horizon uses the same full
rectified period because the source phase is not known in advance.  If a trace
shows no detector edge by the relevant horizon, record `INDETERMINATE` with
the retained trace and explain whether the cause is insufficient modeled
mismatch, startup sequencing, or an unobserved source/control state; do not
quietly extend the horizon after seeing a miss.

The post-detector values are long enough to cross the 132 us retriggerable
timer repeatedly and to expose an immediate re-arm.  The 10 ms zero case also
includes the next rectified-power cycle.  They are observation lengths, not
thermal dwell or hardware qualification.

## Coherent invocation and 25 ns local pacing

The campaign intentionally centres its predeclared timing contract on the
injected fault time `t_F`:

1. Materialize with `T_FAULT=t_F`, `TSTOP` beyond the table's search plus
   observation horizon, and `PREFAULT_WINDOW` equal to 2 ms for F2-CREST or
   10 ms for F2-ZERO/F2-START.  The existing `materializer.rs` generates its
   isolated 25 ns pacing from
   `T_FAULT-PREFAULT_WINDOW-25 ns` through `TSTOP` (constants and checks at
   lines 26--29 and 132--176).  This is the declared timing instrument, not a
   posthoc detector trace.
2. Run `fault_normalize.rs` with `MUTATION_S=t_F`.  Its
   `StreamState::observe` (lines 317--356) validates the injection/F2 edge and
   reports `detector_rise_s` and latch timing separately.  A 1 us normalizer
   edge window may be used because the deck's finite PWL mutation edge is
   declared at 1 ns; using the broad window here is also valid when the input
   source is known to use that same predeclared event window.
3. Run the unchanged `fault_checks.rs` with `EXPECTED_FAULT=t_F`,
   `DETECTOR_WINDOW=2 ms` for crest or `10 ms` for zero/start,
   `TURN_OFF_BUDGET=2 us`, and `OBSERVATION` from the table.  The checker
   searches for a detector rising edge inside that injection-centred window
   (`fault_checks.rs:201--215`); its shared window also defines the prefault
   healthy slice (`:217--243`) and the strict local sample-gap interval
   (`:278--282`).  The detector latency remains an output (`t_D-t_F`) and is
   not used to move the predeclared centre.

This deliberately accepts the wider prefault and pacing interval as part of
the campaign contract.  For a settled crest/zero case, the accepted normal
prefix must remain healthy across that interval.  For startup, choose `t_F`
only after a qualified armed/permit prefix at least 10 ms long (for example,
after 71 ms in this deck only if the trace proves that prefix); otherwise use
the distinct unarmed-startup criteria below.  The 25 ns pacing is about 310
samples per 129.1 kHz switching period.  Each 10 ms of the paced region therefore requires
roughly 400,000 points (a 10 ms prefault window plus 10 ms search and 10 ms
post-detector observation can require about 1.2 million points), a bounded file-size/runtime cost rather
than a reason to relax the rule.

## Startup qualification boundary

The current checker requires at least two prefault rows in the declared event
window with `fault < 2.5` and both `q` and `en` above 2.5.  Because the
injection-centred startup window is 10 ms, choose `t_F` only after a
contiguous armed/permit/healthy prefix at least 10 ms long (for example,
`t_F >= 71 ms` in this deck only when the trace verifies it).  An F2 event
before `q/en` are qualified is a different startup experiment and must be
recorded `UNEXECUTED` or handled by a separate startup criterion; it cannot be
made to pass by inventing an initial state or loosening this checker.

## Remaining stress questions

* The checker’s `|i(Lboost)| <= 100 A` value is a chosen model screen, not an
  inductor thermal or saturation rating.  Exceeding it is a model-screen
  failure; staying below it does not qualify the Würth part.
* A detector edge may be delayed by the authored controller, source impedance,
  inductor state, or comparator state.  The capacitor estimate cannot choose
  the detector latency relative to the declared injection `EXPECTED_FAULT`.
* Crest and zero cases must retain separate source phase, F2 edge, detector
  edge, gate/channel cessation, and passive-current records.  A healthy gate
  low state does not establish that residual inductor/diode/capacitor current
  has stopped.
* No case is acceptance evidence until the host accepts the contiguous
  cold-start normal prefix and records source/include hashes, simulator
  options, and the exact event selection.

No source deck, checker, tolerance, response budget, or circuit component was
changed by this preflight.
