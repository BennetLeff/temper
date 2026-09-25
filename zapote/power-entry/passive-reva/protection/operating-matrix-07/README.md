# Operating matrix 07

This is the next simulation campaign for the Temper AC power-entry/PFC
stage and its shutdown protection. It is not an induction-coil inverter
qualification. Hardware is unavailable. Work is delegated to Luna agents
with host review and independent reruns; historical experiment06 is frozen.

## Current evidence

| Work | Evidence and boundary |
|---|---|
| Correct ISENSE clamp | Candidate source compiled and exported independently. Resolved pins place the diode after the 220 ohm resistor, with the correct polarity and unused pin isolated. Nominal circuit tests pass. |
| Clamp temperature | The assumed diode model fails the chosen loading screen at 85 and 125 C and substantially understates low-voltage conduction compared with the selected vendor's typical curve. Even its nominal pass does not qualify the selected part. |
| Default-off standby | Physical two-FET standby topology passes five sequencing windows, floating-command default-off and a doubled-capacitance sensitivity run. Removing the inhibit device fails as expected. MOSFET dynamics remain assumed. |
| Controller repair | Startup exposed reset feedback, current-loop scaling and missing PWM-latch defects in the authored surrogate. A minimal mixed-signal fixture now reproduces an additional gate-transition failure. Preserving the finite DAC edge fixes that fixture; mapping undefined PWM to zero prevents an intermediate 7.5 V output. The complete candidate passes all six controller fixtures and an actual-model undefined-state regression with a failing negative control. |
| Complete normal startup | Earlier attempts stalled or exported nonincreasing timestamps. The tracked replacement froze at 348.534538 ms and exported a full partial trace. Strict checks found nonincreasing timestamps beginning at 256.990362 ms and rejected it. The finite-edge isolated repair did not resolve all complete-plant numerical defects. No accepted settled operating point exists. |
| Three mains voltages / three loads | Pending accepted normal startup. No completed nine-point sweep is claimed. |
| Faults from settled operation | Cases and independent checker prepared; physical campaign is UNEXECUTED pending an accepted starting state. |
| Hardware correlation | Observation/comparison specification prepared. No hardware measurements exist. |

## Where to review

- `clamp/README.md`: corrected source, nominal results, temperature limits;
  `clamp/host-rerun/` contains independent compiler, export and SPICE results.
- `standby/README.md`: default-off circuit and sequencing results.
- `host/controller-model-review.md`: source-backed reset correction and the
  explicitly inferred ICOMP/PWM offset.
- `controller-probes/README.md`: independent controller tests and negative controls.
- `controller-finite-edge-safe/README.md`: current controller candidate and
  its six host-verified fixtures. `controller-latched-explicit/` is the
  prior explicit-latch baseline; `controller-finite-edge/` is an intermediate
  candidate superseded by the undefined-state guard.
- `numerical-repair/README.md`: mixed-signal failure reproduction, controlled
  ablations, endpoint checks, and undefined-state positive/negative controls.
- `normal-tracked/`: current full cold run with progress and stop/export limits.
- `normal-finite-edge-safe/`: terminated unobservable attempt and its identified inputs.
- `checker/README.md`: operating-point criteria and the maintained trace adapter.
- `line-load-prep/manifest.json`: nine planned line/load points, generated
  in Rust; every point remains explicitly unexecuted.
- `faults/README.md`: bounded fault cases, checker and UNEXECUTED status.
- `checker/hardware-validation-spec.md`: measurements needed to correlate a
  future prototype with the simulation.
- `runtime-experiment/README.md`: rejected numerical-speed experiments.
- `hardware-audit/`: live CPU/memory profile, stopped obsolete run, and
  primary-source assessment of threading support for this circuit.
- `host/frozen-input-check.json`: 131 experiment06 artifacts and eight
  external inputs remain byte-identical to their prior receipt.
- `normal-startup/stalled-351ms/`: exact corrected cold deck, include files,
  log and stall receipt. Batch interruption discarded the in-memory waveform;
  no partial waveform or passing regulation result is claimed.
- `host/stall-investigation.md` and `diagnostic-capture/`: subsequent bounded
  replay and measured numerical behavior, explicitly diagnostic only.

## Acceptance sequence

Accept a completed, adequately sampled normal run before treating its final
cycles as a reference state. Require approximately 390 V regulation, limited
drift, actual positive input/load power, <=15 A input RMS, a continuously
enabled loop, and node-specific voltage screens. Startup peaks remain visible.
These are declared model screens, not thermal, magnetic, silicon or safety
qualification. The controller is a host-authored nominal surrogate, the
auxiliary rails/sequencing are explicit ideal stimuli, and magnetic saturation,
temperature, parasitics and fuse arcs are unqualified.

Only accepted operating conditions can feed the subsequent fault campaign.
A failed-short switch cannot receive credit for interrupting current because
its gate went low. A simulator exit code or a passing checker unit test is
not a circuit pass. Worker summary files with old schemas/semantics remain
diagnostic history; the maintained Rust checker owns acceptance.
