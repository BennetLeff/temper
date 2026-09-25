# Clamp resistor sensitivity (simulation-only)

This bounded experiment compares the existing 220 ohm ISENSE path with 100,
47, and 22 ohms using the **Diodes Inc. BAV23C** SPICE model.  Diodes Inc. is
an alternative manufacturer to the selected Vishay BAV23C; this result does
not qualify or replace the selected part.  The model was downloaded from
<https://www.diodes.com/spice/download/1530/BAV23C.spice.txt> and retained as
`diodes-bav23c.spice.txt` (SHA-256 is recorded in `manifest.json`).

The source shunt remains 10 mOhm.  Each DC sweep extracts the shunt voltage
needed to reach the controller SOC (-0.285 V), typical PCL (-0.400 V), and
maximum PCL (-0.438 V) anchors.  `resistor_sensitivity_checks.rs` owns the
transport checks, interpolation, current calculation, and fault-log KCL
checks; the TSV files are only ngspice transport output.

## Commands

```sh
ngspice -b -o sensitivity.log sensitivity.cir
rustc --edition=2021 -O resistor_sensitivity_checks.rs -o resistor_sensitivity_checks
rustc --edition=2021 --test resistor_sensitivity_checks.rs -o resistor_sensitivity_checks_tests
./resistor_sensitivity_checks_tests
./resistor_sensitivity_checks . > sensitivity-results.txt
```

The checker passed two unit tests and all 16 sweep files (finite values,
strictly descending shunt sweep, complete 4-column `wrdata` rows), then passed
all 16 `-5 V` fault points with log-order and KCL checks.  This is a short DC
fixture, not a startup or full-plant run.

## Measured tradeoff

At the PCL maximum anchor, lower RIN reduces the model's hot threshold error
relative to an ideal 10 mOhm shunt, but raises fault current approximately as
`(5 V + V_ISENSE)/RIN`.  Representative results from the checker:

| RIN | PCL-max shunt-current excess at 125 C | -5 V clamp current at 25 C | RIN x 1 nF |
|---:|---:|---:|---:|
| 220 ohm | +93.95% | 19.1 mA | 220 ns |
| 100 ohm | +42.70% | 41.5 mA | 100 ns |
| 47 ohm | +20.07% | 86.9 mA | 47 ns |
| 22 ohm | +9.39% | 182.2 mA | 22 ns |

At -40 C, the same PCL-max excess is 0.30%, 0.14%, 0.06%, and 0.03%,
respectively.  The full temperature/threshold table is in
`sensitivity-results.txt`.

## Limits and next discriminating test

These numbers are behavior of one vendor's **alternative, as-is** model.
They do not establish BAV23C pulse/SOA, resistor pulse rating, controller
damage limits, or a guaranteed hot forward-voltage bound.  Reducing RIN also
changes the existing 1 nF pole, so this DC table cannot be used as a dynamic
equivalence claim.  In particular, the 22 ohm case reaches about 180--186 mA
in the model under the declared -5 V fault; no adoption is implied.

Before changing the circuit, obtain selected-part evidence: a vendor model
for the selected Vishay device or a bounded VF-versus-current/temperature
characterization, plus the pulse duration and resistor/diode thermal limits.
Then repeat the same fixtures with that evidence and a transient clamp pulse.
