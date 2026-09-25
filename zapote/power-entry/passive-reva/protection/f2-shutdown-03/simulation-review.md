# F2 transient simulation review

Reviewed the frozen worker output under
`/private/tmp/temper-f2-sim-luna/zapote/power-entry/passive-reva/protection/f2-shutdown-03/simulation/`.
The summary was regenerated after the final extractor edit (summary mtime
20:12:56 UTC), and all raw logs were checked for ngspice warnings.  Frozen
source hashes are:

```
f2_shutdown_template.cir  751439ba5d6cf74b3ff3626625bc5b328199b1ae14c7ff1af14adbd4bde894f6
run_cases.sh              02a959ca1278af934925057d97fcad0c76833a24cf5ce6ce293df7d2ee0fe25c
extract.rs                e3d54b7dd5f5b6f5b099b1d599f4a0b147e6b089cf9f080518c26eba83311c73
traces/summary.csv        8d7fd22fbec544d3aca1b3c4470cdf1cd28fecc7d06bbf910b593c8fd3426fe1
```

## Checks that now pass

* `extract.rs` now requires exactly 22 finite trace values and computes switch
  current from the saved `v(sw_mid)`–`v(sw_sense)` drop across the explicit
  1 mOhm sense resistor (`f2_shutdown_template.cir:59-60,130,136`; the
  extraction is at `extract.rs:64-99`).  There is no gate/iL fallback, so the
  cessation metric is based on the actual switch branch in these traces.
* The cessation search first finds the final nonzero switch-current sample,
  then requires current, Q, EN, and gate to be low.  The later-current scan
  catches return pulses.  This avoids treating an ordinary PWM off interval as
  shutdown (`extract.rs:118-141,180-184`).
* F2-open 40/45/50 A runs pass at 0.734/0.728/0.726 us threshold-to-current
  cessation.  The 50 A 1 ns timestep refinement passes at 0.723 us.  The
  adverse cases report actual current at F2 opening (about 48.6/49.7/53.8 A),
  rather than only the `.param IINIT` value.
* `fault_clear_held_arm` now substitutes `ARM_HOLD=200u`; the ARM level spans
  the permit fault and is not merely the initial 500 ns pulse.  `fresh_rearm`
  uses a fresh ARM2 edge at 260 us after permit/rail recovery and is reported
  as a successful positive rearm with an explicit later switch-current pulse.
* The delayed-gate negative control fails (4.889 us and 477.6 V), and the
  failure is now named in the summary.  No generated raw log contains a
  non-increasing-PWL or other ngspice warning.
* The XSPICE `d_dff` latch is the active model (`f2_shutdown_template.cir:107-116`)
  and the generated traces contain the expected q/en/gate transitions.

## Remaining limitations to carry into the canonical report

* `reverse_mismatch` is under the absolute threshold (VB=425 V, VD=410 V),
  but the model does not assert the filtered fault until roughly 120.4 us;
  the resulting 120.5 us cessation is a FAIL.  This is honest evidence that
  the authored comparator surrogate does not demonstrate a prompt isolated
  reverse-mismatch response in this setup.  It must not be described as a
  passing mismatch test.
* `absolute_vd_ov` is a FAIL because the filtered fault does not assert,
  while the mirrored `absolute_vb_ov` case passes.  The asymmetry is a model
  stimulus/initialization limitation: both divider filter capacitors are
  initialized from `vd` (`run_cases.sh:18`), and the boost transient changes
  the input before the comparator surrogate settles.  Report the vd case as
  failed/indeterminate evidence rather than claiming symmetric absolute-OV
  coverage.
* `permit_loss_return` and `rails_invalid_return` each keep the opposite input
  scheduled for a later drop (runner lines 62-63).  Their PASS assertion is a
  broad `t >= 100 us` all-low check (`extract.rs:188-194`), not an event-window
  check tied to the actual return edge.  They demonstrate the intended
  default-off state in this trace, but do not independently prove each
  input's return sequence or a pre-return high state.  The canonical report
  should retain that limitation and avoid calling these isolated edge tests.
* The fresh-rearm PASS is intentionally a safety-screen exception: the first
  cessation is absent because the expected post-recovery pulse occurs.  The
  report records that pulse, but the extractor does not independently assert
  a pre-ARM Q/EN-low interval or the exact input-return edge; this is weaker
  evidence than a dedicated edge assertion.
* The current-cessation test requires no later branch current through the end
  of the simulated trace, but it has no separately parameterized multi-us
  dwell interval.  The long post-event windows in the normal/F2 cases make
  the reported passes useful for this bounded experiment; they are not a
  hardware qualification claim.

The canonical source topology remains consistent with the simulation's
987 kOhm + 200 Ohm + 5.62 kOhm tapped dividers, two comparator channels, HCS21
health gates, retained HCS74 latch, and UCC27624 EN/gate path.  MOSFET, diode,
comparator, and latch timing remain explicitly behavioral/typical surrogates;
the results are therefore transient-model evidence only.
