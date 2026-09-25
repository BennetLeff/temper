# Line/load manifest preparation

`generate_manifest.rs` is the sole authority for the nine planned points. It
uses Rust `f64` arithmetic and emits `manifest.json`; Python is not used to
derive any load value.

```sh
rustc --edition=2021 -O generate_manifest.rs -o /tmp/matrix07-line-load-manifest
/tmp/matrix07-line-load-manifest > manifest.json
```

The grid is 108/120/132 VAC RMS crossed with 25/50/90% of the conditional
cap:

```text
cap(V) = min(1800 W, 15 A × V) × 0.90
Ptarget = cap(V) × load_fraction
RLOAD = 389.615² / Ptarget
```

Unity PF and 90% efficiency are assumptions for selecting a resistor value,
not measured performance. Actual Vrms, Irms, PF, input/load power, bus
envelope, drift, current peaks, controller state and energy balance must come
from the strict operating-point checker after a normal prefix is accepted.

The existing 120 V / 190 ohm witness is a reference only: its ideal-bus load
power is approximately 798.947 W, near the 120 V / 50% grid target (810 W),
but it is not relabeled as that grid point.

Every point is `planned_unexecuted`. No nine simulations were run. The source
deck and include hashes stay `PENDING_ACCEPTED_COLD_SOURCE`/`PENDING` until
the corrected cold-source run is accepted. Do not substitute a rejected or
earlier deck hash.
