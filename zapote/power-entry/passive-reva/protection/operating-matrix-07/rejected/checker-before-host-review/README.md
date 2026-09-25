# Operating-point checker (matrix-07)

`operating_point_checker.rs` is an independent, standard-library-only Rust
CLI. It reads a streaming trace from stdin (or `--input FILE`) and fails
closed on schema, numeric, time, coverage, gap, and sampling errors.

Build and run:

```sh
rustc --edition=2021 -O operating_point_checker.rs -o /tmp/operating-point-checker
rustc --edition=2021 --test operating_point_checker.rs -o /tmp/operating-point-checker-tests
/tmp/operating-point-checker-tests
/tmp/operating-point-checker < normal.tsv
```

The exact twelve-column header is one whitespace-separated line:

```text
time_s v_ac_v i_ac_a v_load_v i_load_a v_b_v i_l_a v_d_v v_ds_v v_gs_v armed on
```

The adapter producing this file owns polarity and semantics. `v_ac_v` and
`i_ac_a` are instantaneous voltage/current into the converter, so positive
time-integrated input power is required. `armed` and `on` are numeric booleans
(greater than 0.5 is true). A simulator's `i(Vsource)` convention must be
negated in the adapter when it is defined out of the converter; for the
integration fixture this is `v(acsrc,acn)` and `-i(Vac)`, with the source
floating relative to HOT0. No aliases or missing columns are accepted.
`on` means the local controller enable/healthy operating state, not an
instantaneous PWM gate waveform; legitimate PWM duty variation near line
zero must not drive it low.

All RMS, power, PF, bus means, cycle drift and fractions use trapezoidal
time integration. Rows are never averaged arithmetically; this matters for
adaptive simulator timesteps. The final three 60-Hz cycles are selected as
the settled window and boundary values are linearly interpolated. The default
switching sampling guard rejects a step larger than 1/(8×130 kHz); use
`--no-switch-check` only for diagnostic unit tests, never for acceptance.

The default source contract is 108–132 VAC RMS, 60 Hz, 15 A RMS and a
389.615 V nominal bus. The provisional normal-point engineering screens are
bus mean ±5%, bus cycle-mean drift below 0.5% over the final three cycles, and
input Irms ≤15 A. These are simulation screens, not product requirements or
thermal ratings. Node checks report VD 500 V (conditional screen), VB 450 V,
VDS 650 V and |VGS| 25 V. A report always says
`qualification=NOT_CLAIMED`: an I²R/loss estimate and this checker cannot
qualify junction, case, PCB, enclosure or inlet temperature.

`REJECTED` means no acceptance result exists. A parsed trace can instead
produce `engineering_screen=STOP` for a failed screen, disabled/unstable
controller (`armed` fraction <0.5 or `on` fraction <0.01), wrong power sign,
node-limit excursion, insufficient integer-cycle coverage, or possible
switching-current aliasing. Do not widen criteria to make a branch green.

The checker also rejects mains Vrms outside 108–132 V, non-finite or
out-of-range PF, and non-positive load power. A load-power result above source
power is retained as evidence for a stored-energy/window-definition review;
it is never silently treated as an efficiency gain.
