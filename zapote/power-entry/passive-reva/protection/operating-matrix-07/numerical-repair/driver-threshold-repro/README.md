# Bdriver_req threshold reduced reproduction

Date: 2026-09-20

The fresh full-plant first-invalid capture exposes the current authored
external driver boundary at the failure callback:

| node | value |
|---|---:|
| `xu.pwm_hold` | 0.806666955455170864 V |
| `pwm` | 2.42000086636551259 V |
| `pwm_input` | 2.20000078760501117 V |
| `drv_req` | 15 V |
| `drv` | -1.05338461270755833e-7 V |
| `disable` | 0.103568513062932382 V |
| `xu.raw` | 5 V |

`pwm=3*pwm_hold` and the 1 kΩ/10 kΩ input divider make
`pwm_input=0.90909*pwm`, so the measured crossing is exactly the
`Bdriver_req` 2.2-V threshold. The full-plant snapshot is retained as
`sources/full-plant-first-invalid.tsv`.

## Bounded reduced pair

`baseline.cir` starts from the existing finite-edge `late-safe` fixture and
moves its prescribed raw edge to the full-plant first-invalid timestamp
`0.256990362212805523 s`. It retains the 1-ns ADC/DAC edges, finite
`Bgate=3*V(pwm_hold)`, 1 kΩ/10 kΩ PWM divider, hard `Bdriver_req` 2.2-V
comparison, 18.75-ns driver-delay capacitor, 1 Ω driver source, 10 Ω gate
resistor, 10 kΩ gate pulldown, and 12 nF + 112 pF + 344 pF capacitive load.
`finite-driver.cir` changes only `Bdriver_req` to a diagnostic 0.2-V linear
transition centered at 2.2 V; it is a sensitivity probe, not an adopted
hardware model or arbitrary acceptance fix.

Both decks complete to `EDGE+200 ns` and pass a strict Rust checker requiring
the exact nine-column header, finite rows of exactly nine values, strictly
increasing time, a first sample in the declared `EDGE-20 ns..EDGE` late
window, no local step above 50 ns, endpoint reach within 1 ps,
`pwm_hold>4.99 V`, gate peak above 10 V, and a `pwm_input` threshold-crossing
witness. The checker also rejects malformed width, duplicate headers, NaN or
infinite values, and truncated endpoints:

| deck | rows | last time (s) | non-increasing | max gate | threshold sample |
|---|---:|---:|---:|---:|---|
| baseline hard threshold | 60 | 0.256990562212805473 | 0 | 10.597604527 V | `drv_req=15`, `drv=2.155 mV`, gate≈0 |
| finite 0.2-V diagnostic | 60 | 0.256990562212805473 | 0 | 10.597516880 V | `drv_req=11.437 V`, `drv=6.006 mV`, gate≈0 |

The prescribed PWL reduced fixture therefore does **not** reproduce the
full-plant same-time failure, even with the measured threshold timestamp. The
finite-transition variant also passes, so it demonstrates bounded numerical
sensitivity but does not justify changing the model. The cause remains
unresolved: the reduced fixture omits the full controller and the coupled
power-stage/load trajectory, and the current evidence does not identify
whether either omission, or their interaction, is decisive. A next reduced
reproduction must retain the actual Braw/Biamp/Cvcomp feedback state (and save
raw, phase, m2, pwm_q/pwm_hold, pwm_input, drv_req, drv, gate) while
preserving this measured threshold.

## Timing check and artifacts

`check.rs` is compiled with `rustc --edition=2021`; its output is in
`results/*.check`. The executable accepts optional `EDGE_S LATE_START_S END_S
MAX_GAP_S` overrides, but the retained results use the defaults shown above.
ngspice logs and exported traces are retained in `results/` and show the normal
bounded fixture completion. No full plant deck, controller include, timestep,
tolerance, deduplication rule, or acceptance limit was modified.
