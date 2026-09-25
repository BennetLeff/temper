# Vendor-COMPHYS input-state hybrid candidate

This is a bounded fidelity experiment for the repeated timestamp near
501.55 ms. It is not a full-plant repair, an accepted source, or a hardware
qualification. No full cold run, electrical deck, native threshold, checker
criterion, or frozen source was changed.

`authored_logic_vendor_comphys.inc` replaces only the authored native-SW
input frontend with the local TI model's `COMPHYS_BASIC_GEN` primitive. The
primitive body is byte-identical after CRLF normalization to
`UCC27511A.lib` lines 135--142: its `EOUT` is a hard behavioral output, while
its 1 ohm/5 nF network is internal to node `1`. The candidate does not add a
filter after `COMPHYS OUT`.

The input connections follow the TI model's exact logic references in
`UCC27511A.lib` lines 79--95:

* PWM: `INP`, 2.2 V threshold, 1 V HYS (2.2 V rising / 1.2 V falling).
* INM: `INM`, 2.2 V threshold, 1 V HYS (active-high disable).
* AUX: `VDD`, 4.2 V threshold, 0.3 V HYS (4.2 V rising / 3.9 V falling).

The nominal input loads remain 200 kΩ from INM to VDD and 230 kΩ from GND to
INP. The instrumentation names `pwm_state`, `inm_state`, `aux_state`,
`driver_req`, and `drv_delay` are retained. The output is deliberately still
the authored surrogate: the state product feeds `Bdriver_req`, then the
18.75 nF delay pole and 1 ohm output resistance. This is therefore a
**hybrid input-vendor/output-surrogate**, with global `GND` mapped to ngspice
node 0; it is not the complete TI OUTH/OUTL stage.

## Bounded method

The copied slow, fast, sequence (RUN/AUX), AUX, INM, and late fixtures were
run with ngspice-45.2. Every process had an explicit 30 s alarm:

```sh
perl -e 'alarm 30; exec @ARGV' /opt/homebrew/bin/ngspice -b -o CASE.log CASE.cir
```

The strict Rust checker and comparison tool were rebuilt with warnings denied:

```sh
rustc --edition=2021 -D warnings -O check_hysteretic.rs -o /tmp/matrix07-vendor-comphys-check
/tmp/matrix07-vendor-comphys-check .
rustc --edition=2021 -D warnings -O compare.rs -o /tmp/matrix07-vendor-comphys-compare
/tmp/matrix07-vendor-comphys-compare ../driver-hysteresis-candidate .
```

All nine bounded fixtures completed. The checker reported finite,
strictly-increasing traces and PASS. The reduced late fixture ended at
0.25702 s with 514,094 rows and gate off; it is not a replay of the 650 ms
full-plant history and does not explain or fix the 501.55 ms stall.

## Results against current authored and TI fixtures

Gate 4 V timings are nanoseconds. `current` is the existing authored native-SW
candidate; `hybrid` is this folder; `TI` is the unchanged vendor fixture.

| fixture | current rise | hybrid rise | TI rise | current fall | hybrid fall | TI fall |
|---|---:|---:|---:|---:|---:|---:|
| slow PWM | 2502.621 | 2502.621 | 2490.995 | 5970.322 | 5970.322 | 5932.935 |
| 1 ns PWM | 3062.338 | 3062.318 | 3050.884 | 5211.195 | 5211.211 | 5173.673 |

The hybrid reproduces the current authored gate timing almost exactly while
using the vendor hysteresis primitive for the input states. Its slow native
state crossings remain 2.2/1.2 V. On the 1 ns fixture, interpolation through
the hard COMPHYS transition gives state-input readings 1.968928/1.100000 V;
those are event-sampling values, not changed threshold parameters. The TI
oracle remains faster by about 11.626 ns on slow rise and 37.387 ns on slow
fall, and by 11.434 ns/37.538 ns on the fast edge.

The 35 us RUN/AUX sequence is likewise close to the current surrogate:

| window | TI gate | current gate | hybrid gate |
|---|---:|---:|---:|
| PWM high minimum | 14.973332 V | 14.949873 V | 14.949844 V |
| PWM off max(abs) | 0.004691 V | 0.017616 V | 0.017721 V |
| RUN off max(abs) | 0.008722 V | 0.029435 V | 0.029632 V |
| AUX drop max(abs) | 0.001379 V | 0.017626 V | 0.017700 V |
| rearmed minimum | 14.984420 V | 14.981988 V | 14.981988 V |

Gate 4 V falling after RUN is 12,249.301 ns (TI), 12,285.768 ns (current),
and 12,286.022 ns (hybrid). After AUX it is 20,091.158 ns, 20,210.782 ns,
and 20,210.817 ns respectively. AUX and INM sweep fixtures measured the
intended 4.2/3.9 V and 2.2/1.2 V state boundaries with finite traces.

## Fidelity boundary and disposition

This hybrid answers a narrower question: replacing the authored frontend with
the vendor's actual COMPHYS hysteresis primitive does not materially change
the reduced gate or RUN/AUX waveforms. It does not test TI's real OUTH/OUTL
output current paths, the bridge/boost/controller coupling, or the absolute
time history at 501.55 ms. It therefore cannot repair or accept the full
source. Retain it as a source-bound comparison only; do not adopt it in the
full deck without parent review and a history-equivalent test.

Hashes:

```text
TI UCC27511A.lib       eb78c0ce0d9cf2dd5bbc5f937bbfc6cc38c95215e035feaeb3950672e8c05c6d
candidate include      9df45215d576dae8b29b3aab0e2289c7034b948091fa8b073b37628729159bc3
```
