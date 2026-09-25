# Late 501 ms repeated-timestamp diagnosis

This folder records a bounded diagnosis of the
`normal-hysteretic-settling-extension` trace that stopped at approximately 501 ms
(the preceding 500 ms candidate had completed its requested horizon).  It is
diagnostic evidence only.  It does not change the full-plant source, relax the
strict trace checker, or establish an accepted normal baseline.

## Observed failure

The 650 ms settling extension reached a first non-increasing timestamp at
`t = 0.501554914485680681 s` (row indices `22757955` and `22757956`).  The
captured state is in
[`first-invalid.tsv`](../../normal-hysteretic-settling-extension/first-invalid.tsv).
At that instant:

| signal | value |
| --- | ---: |
| `pwm_input` | `2.19998914099196519 V` |
| `pwm` | `2.42955322526938744 V` |
| `xu.pwm_hold` | `0.809851075089795813 V` |
| `xdriver.driver_req` | `14.9999999999999716 V` |
| `xdriver.drv_delay` | `4.01881825656310270e-8 V` |
| `xu.phase` | `1.93904670375832922e-6 V` |
| `isense` | `-44.5686826054632 mV` |
| `disable` | `104.086116764481 mV` |

The preceding same-time row had `drv_delay = 6.31427861899156580e-10 V`.
The diagnostic inspection found simultaneous changes in `v(acsrc)`, `i(Vac)`,
`i(Lboost)`, `v(vd)`, `v(sw)`, `v(gate)`, `v(icomp)`, `xdriver.drv_delay`,
`xu.blank`, `isense`, and the controller state.  Thus the failure is not an
isolated output-node change: it occurs while the power-stage/controller feedback
is moving as well.  The captured values are preserved in
[`inspection.txt`](../../normal-hysteretic-settling-extension/inspection.txt).

This resembles the earlier 256.990 ms failure, but does not prove one common
cause.  That capture has `pwm_input = 2.20000078760501117 V`, `drv_req = 15 V`,
and `drv = -1.05338461270755833e-7 V`; see
[`first-invalid.tsv`](../../first-invalid-capture/run/first-invalid.tsv).
The two events are both near the PWM hysteresis boundary, while their controller
history and power-stage conditions differ.

## Bounded reduced fixtures

The authored hysteretic model is unchanged from
[`authored_logic_hysteretic.inc`](../driver-hysteresis-candidate/authored_logic_hysteretic.inc)
and makes the native `SW_PWM_H`, `SW_INM_H`, and `SW_AUX_H` states authoritative
(lines 10--21).  `Bpwm_logic`, `Binm_logic`, and `Baux_logic` only normalize the
known switch endpoints (lines 23--30); `Bdriver_req` combines those states at
line 36.  The finite output pole is the starting approximation at lines 37--39.

Five small driver/controller decks exercised the recorded late-time edge without
a long full-plant run:

* [`recorded-rise.cir`](recorded-rise.cir) uses the recorded near-threshold input
  and a 1 ns rising step.  Its load is a passive gate-capacitance proxy, not the
  full plant's `Msw`/body-diode/downstream network.
* [`recorded-steep-rise.cir`](recorded-steep-rise.cir) repeats it with a 1 ps
  step.
* [`recorded-held-high.cir`](recorded-held-high.cir) holds PWM high and then
  approaches the threshold from above.
* [`recorded-smooth-rise.cir`](recorded-smooth-rise.cir) adds a diagnostic-only
  1 ohm/5 nF output pole inspired by the vendor macro model; it is not an adopted
  replacement.
* [`controller-edge.cir`](controller-edge.cir) retains the ADC/DFF/DAC controller
  edge and the hysteretic driver in a reduced load.

To close that load-model gap without launching a cold run,
[`recorded-power-stage.cir`](recorded-power-stage.cir) replays the near-threshold
edge against the candidate's explicit `Msw`, `Dbody`, `Dboost1/2`, `Cgs`, `Cgd`,
and `Cds` network.  It initializes `Cds` at `378.1958 V`, `Cgd`/`Cgs` at the
captured gate state, the inductor at `4.1048 A`, and a fixed `VD=376.9614 V`.
These are local initial conditions, not a replay of the bridge, controller, or
absolute-time history.  The strict checker [`check_power_stage.rs`](check_power_stage.rs)
compiled with `rustc --edition=2021 -D warnings -O` and reported 20,046 finite,
strictly increasing rows through 200 ns, `driver_req_max=15 V`, a
Miller-loaded `gate_max=8.576551013 V`, and `sw_min=0.238802674 V`.  This richer
local load also completes without a repeated timestamp, so the late full-plant
failure still requires coupling or history absent from this replay.  The result is captured in
[`power-stage-check.txt`](power-stage-check.txt), and is not an equivalence or
qualification result.

The fixtures intentionally do not claim to replay the full switch environment:
the full deck has `Msw`, `Dbody`, `Dboost1/2`, `Cgs=12 nF`, `Cgd=112 pF`, and
`Cds=344 pF` (see
[`cold.cir`](../../normal-hysteretic-driver-candidate/cold.cir), lines 27--39),
while the five driver/controller decks use a capacitive gate proxy.  The
power-stage deck includes the explicit switch network, but its fixed source and
VD nodes do not include the full bridge or feedback path.  Therefore neither
class can establish that the actual 378 V drain, approximately 4.1 A inductor
current, diode commutation, and Miller coupling are benign at the full-plant
failure edge.  That distinction is why these passes are evidence against a
standalone driver-input reproduction only.

[`check.rs`](check.rs) is a strict finite, strictly-increasing-time checker.  It
was compiled with `rustc --edition=2021 -D warnings -O`; the five reduced outputs
are summarized in [`fixture-check.txt`](fixture-check.txt).  Every one of those
five fixtures completed past `0.501555 s`; row counts were 29, 34, 38, 7, and 73
respectively.  No fixture reproduced a repeated timestamp.  These results rule
out the standalone
recorded input edge plus this reduced driver/load as a sufficient reproduction;
they do not rule out a coupled full-plant event or an absolute-time/history
effect.

## Model boundary and next evidence

The TI macro model remains the oracle and is not edited.  Its input loading and
comparator/output behavior are documented in
[`UCC27511A.lib`](../../../f2-shutdown-04/vendor/UCC27511A_TINA_TRANS/UCC27511A.lib).
The authored model deliberately collapses OUTH/OUTL into one output node, so the
reduced fixtures cannot establish source/sink-current equivalence.  The smooth
fixture is useful as a sensitivity probe only; its passing result is not a
solver repair or a fidelity claim.

The most plausible bounded hypotheses are:

1. A native `SW_PWM_H` state transition and the resulting `Bdriver_req` change
   are coincident with controller/power-stage feedback at the late absolute time.
2. The driver delay state is traversing its finite pole while the power-stage
   nodes move; the near-zero `drv_delay` before the invalid row is evidence of a
   transition, not a static 15 V output plateau.
3. A mixed analog/state event involving `blank`, `phase`, current sense, or the
   bridge/boost network is the missing coupling.  The reduced decks do not retain
   enough history to choose among these hypotheses.

The next useful bounded receipt is instrumentation of the existing full deck (or
a short replay with equivalent controller history) for `pwm_input`, the native
PWM state, `pwm_hold`, `driver_req`, `drv_delay`, `gate`, `phase`, `blank`,
`isense`, `icomp`, and the bridge/boost currents at the first boundary crossing.
Changing output thresholds, filtering duplicate rows, widening endpoint windows,
or substituting the authored model based on these reduced passes would discard the
failure rather than explain it.  No such change is made here.
