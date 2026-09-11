# LMR51430 datasheet model exercise

These native ngspice decks are bounded development checks for the
datasheet-derived `LMR51430XDDCR` model. They are not a vendor model,
qualification protocol, or hardware prediction.

The decks include `../../models/lmr51430-datasheet/model.lib`, which is the
model package owned by the model exercise. The runner copies the model and its
parameter provenance ledger into the output, along with the exact deck and
runner sources used for the run, and records their SHA-256 hashes. The external
ground pin is named
`GND0` and is tied to ngspice node `0` in every deck. The model instance uses
the required order `VIN SW GND FB EN CB`.

`run_exercise.sh` runs one authoritative, short check covering:

- 1 ms VIN ramps to 13.5, 15, and 16.5 V with an unloaded 1 TOhm load and a
  6.6 Ohm resistive load (0.5 A nominal at 3.3 V);
- nominal 15 V / 0.5 A steady state;
- 0.05 -> 0.5 A and 0.05 -> 1 A load steps;
- the nominal and reduced capacitor values (4.54 uF input and 22.01 uF output),
  plus 4.48 and 6.72 uH. The reduced values are sensitivity assumptions, not
  guaranteed minimum capacitance floors.

The generated case decks, ngspice logs, native `.meas` output, and SHA-256
manifest are written below `/tmp/temper-lmr-datasheet-exercise` by default.
The run is intentionally short (20 ms cases, 20 ns maximum step) and is a
development sweep, not the adopted closure-wave or full switching matrix.

Run from the repository root for the full 10-case matrix:

```sh
harness-lab/engineering/scenarios/lmr51430-datasheet/run_exercise.sh
```

Use `LMR_QUICK=1` for the bounded 3-case development check:

```sh
LMR_QUICK=1 harness-lab/engineering/scenarios/lmr51430-datasheet/run_exercise.sh
```

The load-step deck uses a 3 ms development pulse with a 0.1 A/us transition;
the pulse is shortened from the 10 ms hardware load-pulse target to keep this
exploratory run short.

The model is approximate. KP/KI are not changed by this exercise; any
deviations under corner or load conditions are recorded as model sensitivity.
