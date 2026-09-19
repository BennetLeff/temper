# Diode-side film reservoir: bounded design screen

The F2-open experiment already contains an immediate-off equation for a
healthy, controllable U9. This checkpoint evaluates only the effect of moving
the diode-side local film capacitor from the selected 1.5 µF toward 10, 22 or
47 µF. It does not add a new circuit model.

For the retained crest inputs (`Vin = 169.7056 V`, `L = 180 µH`), the equation
is:

```text
Vpeak = Vin + sqrt((V0 - Vin)^2 + (L/C) I0^2)
```

At the 424.68 V detection-state example and 40 A residual current, the ideal
immediate-off screen gives:

| C | Vpeak | unfused energy at 500 V |
| ---: | ---: | ---: |
| 10 µF | 476.0 V | 1.25 J |
| 22 µF | 449.2 V | 2.75 J |
| 47 µF | 436.4 V | 5.88 J |

The larger capacitor provides real peak-voltage headroom in this healthy-U9
screen. It also stores more energy, so the capacitor itself becomes a larger
unfused object after F2 opens. The 47 µF option is therefore not automatically
safer than 22 µF; it trades lower healthy-switch overshoot for 5.88 J at 500 V.

The screen does **not** establish that the controller detects the fault before
the peak, that U9 turns off within the required delay, that the controller
restarts safely, or that a failed-short U9 is interrupted. Those obligations
remain with the F2/coordination and controller qualification work. A diode-side
capacitor must not be used as a substitute for a series interrupter.

The reproducible Rust source is `film_reservoir_screen.rs`; it has two tests
and is intentionally kept under this protection checkpoint rather than added
to the general harness. Build with:

```text
rustc --edition=2021 -O film_reservoir_screen.rs -o /tmp/film-reservoir-screen
/tmp/film-reservoir-screen
```

**Decision:** 22 µF is the smallest screened value that brings the 40 A,
424.68 V example below 450 V while adding 2.75 J of local stored energy. It is
a candidate for the next ECO only; controller timing, capacitor pulse rating,
layout inductance and the entire fault/protection contract remain open.
