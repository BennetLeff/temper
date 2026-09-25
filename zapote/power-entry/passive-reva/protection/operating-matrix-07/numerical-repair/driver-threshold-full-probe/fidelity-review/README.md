# Authored finite-driver fidelity review

This bounded probe compares the current finite authored transfer in
`../source/protection-finite-driver.inc` with the unchanged TI UCC27511A
transient model used by the retained 35 µs interface fixture. It does not
qualify either model or the hardware. The vendor model is the official TI
SLVMCJ6 extraction recorded in
`f2-shutdown-04/vendor/README.md`, with the primary device reference
[UCC27511A datasheet](https://www.ti.com/lit/ds/symlink/ucc27511a.pdf).

Both decks use the same 0–5 V PWM input ramps, fixed 15 V auxiliary supply,
qualified disable input, 10 kΩ gate pulldown and 12 nF gate load. The vendor
deck has split 10 Ω `OUTH`/`OUTL` paths; the authored deck has one 11 Ω
output path following its delay pole. `vendor-threshold.cir` uses the unchanged model.
`authored-threshold.cir` uses the current authored law:

```
Vdriver_req = 15 V × clamp((PWM_in - 2.1 V) / 0.2 V, 0, 1)
Rdriver_delay = 1 Ω, Cdriver_delay = 18.75 nF
```

The local `.spiceinit` selects PSpice compatibility before either model is
parsed. `check_fidelity.rs` is compiled with `rustc --edition=2021 -D warnings`
and rejects malformed, non-finite, non-increasing, or incomplete traces before
reporting interpolated 13.5 V output crossings.

Reproduction:

```sh
ngspice -b -o vendor-threshold.log vendor-threshold.cir
ngspice -b -o authored-threshold.log authored-threshold.cir
rustc --edition=2021 -D warnings -O check_fidelity.rs -o /tmp/check_driver_fidelity
/tmp/check_driver_fidelity vendor-threshold.tsv authored-threshold.tsv
```

The checked traces end at exactly 8 µs and contain 8,048 vendor / 8,020
authored finite rows. Measured loaded behavior:

| transfer observation | TI model | authored transfer | difference |
| --- | ---: | ---: | ---: |
| `OUTH=13.5 V` rising input | 2.264 V | 2.280 V | −16 mV |
| `OUTH=13.5 V` falling input | 1.080 V | 2.280 V | −1.200 V |
| implied input hysteresis | 1.184 V | 0 V | +1.184 V |
| loaded gate 4 V rising | 2.455 V / 2.491 µs | 2.515 V / 2.503 µs | −60 mV / −11.9 ns |
| loaded gate 4 V falling | 0.335 V / 5.933 µs | 1.146 V / 5.771 µs | −811 mV / +162 ns |
| loaded gate peak | 14.9869 V | 14.9820 V | +4.9 mV |

The finite law is close to the vendor model for the rising 13.5 V crossing and
high plateau, but it does not represent the model's low-going input threshold:
the vendor output crossing occurs near 1.08 V while the authored demand
crossing occurs near 2.28 V. These dynamic output crossings include propagation
delay and are not exact comparator thresholds. The TI model's comparator
parameters are 2.2 V rising and 1.2 V falling: the authored transfer omits that
1 V input hysteresis. The falling loaded-gate timing also differs by
162 ns. Input hysteresis, output sink behavior and the authored delay all
differ here; this comparison does not isolate their individual contributions.
These values are model-to-model measurements under one nominal load,
not datasheet worst-case limits.

Minimum faithful future repair: retain the model's separate nominal input
thresholds (2.2 V turn-on and 1.2 V turn-off),
then calibrate independent source/sink delay or output resistance against the
vendor loaded waveform. A single 2.1–2.3 V ramp and one 18.75 ns pole cannot
preserve both edges. Any such repair still needs the full-plant numerical
test; this probe only identifies the transfer behavior that the current finite
law omits.
