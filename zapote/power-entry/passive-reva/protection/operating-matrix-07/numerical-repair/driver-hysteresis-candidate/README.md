# Authored hysteretic-driver candidate

This directory is a bounded model-fidelity fixture. It does not qualify the
UCC27511A hardware, prove worst-case timing, or replace the unchanged TI
transient model in a full plant.

The authored interface is `AUTH_UCC27511A_H` in
`authored_logic_hysteretic.inc`. Its five pins are `INM` (active-high
disable), `INP` (PWM), `VDD` (auxiliary supply), `GND`, and one collapsed
`OUT`. A collapsed output is deliberate: the TI model exposes separate
`OUTH`/`OUTL` source and sink paths, while this candidate uses one finite
voltage-source approximation and one external 10 ohm gate resistor. The
vendor oracle keeps the original split 10 ohm resistors, so their waveforms
are compared without calling the interfaces equivalent.

Each input has one native ngspice `SW` state with explicit hysteresis. The
thresholds come from the unchanged TI model at
`../../../f2-shutdown-04/vendor/UCC27511A_TINA_TRANS/UCC27511A.lib`: its
logic sources are 2.2 V with a 1.0 V hysteresis source (2.2 V rising and
1.2 V falling), and its auxiliary validity source is 4.2 V with 0.3 V
hysteresis (4.2 V rising and 3.9 V falling). The candidate expresses those
same nominal boundaries as `Vt=1.7,Vh=0.5` for PWM/INM and
`Vt=4.05,Vh=0.15` for AUX. A fixed 1 V reference and 100 kΩ state
pulldowns create bounded 0/1 state levels. Continuous endpoint normalization
removes the known `Roff` leakage without adding another threshold element.
The candidate retains the prior finite output starting point (1 ohm,
18.75 nF pole, then 1 ohm output resistance) only as a declared approximation;
it does not claim the TI output stage's asymmetric source/sink impedance.
The TI input loading (200 kΩ `INM` to `VDD`, 230 kΩ `INP` to ground) is
also present so the input divider is not silently idealized.

The official primary references are the
[UCC27511A datasheet](https://www.ti.com/lit/ds/symlink/ucc27511a.pdf) and
TI's [SLVMCJ6 transient-model archive](https://www.ti.com/lit/zip/slvmcj6).
The local model is the unchanged extraction recorded by
`f2-shutdown-04/vendor/README.md`; `.spiceinit` selects PSpice compatibility
before ngspice parses that model.

## Bounded fixtures and measured deltas

`vendor-threshold.cir` and `authored-threshold-hysteretic.cir` use the same
slow 0-to-5 V/us PWM ramps, 15 V AUX, disable-low input, 10 kΩ gate pulldown,
and 12 nF gate load. `vendor-fast.cir` and `authored-fast.cir` repeat the
comparison with approximately 1 ns input edges. The strict Rust checker
rejects missing, duplicate, non-finite, non-increasing, incomplete, or
over-large time steps before reporting crossings.

```
ngspice -b -o vendor-threshold.log vendor-threshold.cir
ngspice -b -o authored-threshold-hysteretic.log authored-threshold-hysteretic.cir
ngspice -b -o vendor-fast.log vendor-fast.cir
ngspice -b -o authored-fast.log authored-fast.cir
ngspice -b -o vendor-sequence.log vendor-sequence.cir
ngspice -b -o authored-sequence.log authored-sequence.cir
ngspice -b -o authored-aux-sweep.log authored-aux-sweep.cir
ngspice -b -o authored-inm-sweep.log authored-inm-sweep.cir
ngspice -b -o authored-late.log authored-late.cir
rustc --edition=2021 -D warnings -O check_hysteretic.rs -o /tmp/check_hysteretic
/tmp/check_hysteretic .
```

The checked nominal traces are finite, strictly increasing, and end at their
declared times. Measured loaded-gate observations are:

| fixture | TI model | authored candidate | residual |
| --- | ---: | ---: | ---: |
| slow gate 4 V rising | 2.491 µs at 2.455 V input | 2.503 µs at 2.513 V | +11.6 ns / +58 mV |
| slow gate 4 V falling | 5.933 µs at 0.335 V input | 5.970 µs at 0.148 V | +37.4 ns / −187 mV |
| slow gate peak | 14.9869 V | 14.9820 V | −4.9 mV |
| 1 ns gate 4 V rising | 3.051 µs | 3.062 µs | +11.5 ns |
| 1 ns gate 4 V falling | 5.174 µs | 5.211 µs | +37.5 ns |

The input threshold state is the intended source-derived 2.2/1.2 V boundary;
the 2.719 V authored `OUTH=13.5 V` crossing on the slow ramp includes the
candidate's finite output pole, so it must not be mistaken for a changed
logic threshold.

`vendor-sequence.cir` and `authored-sequence.cir` retain the matrix-07
disable FET and PWM divider. They exercise independent PWM edges, an active
RUN disable, AUX collapse while the gate is high, RUN low while AUX is absent,
AUX return while disarmed, and a fresh re-arm. Authored versus TI gate
plateaus are:

| window | TI model | authored candidate |
| --- | ---: | ---: |
| PWM high | 14.9733 V | 14.9499 V |
| PWM off | 4.69 mV max(abs) | 17.62 mV |
| RUN disabled | 8.72 mV max(abs) | 29.43 mV |
| AUX drop | 1.38 mV max(abs) | 17.63 mV |
| AUX return while disarmed | 5.3 µV max(abs) | 0.444 mV |
| re-armed | 14.9844 V | 14.9820 V |

Gate 4 V falling occurs at 12.249 µs (TI) versus 12.286 µs (authored) after
the RUN event, and 20.091 µs versus 20.211 µs after the AUX event. These
residuals are expected from the collapsed finite source/sink approximation;
they are bounds for this fixture, not datasheet limits.

The dedicated partial-rail regressions exercise boundaries that a nominal
15 V sequence cannot distinguish. `authored-aux-sweep.cir` drives AUX from
0 V to 6 V and back while PWM is high and INM is low. The state crosses at
4.200000 V on the rise and 3.900000 V on the fall; the settled 6 V gate
plateau is 5.9922 V, while the invalid windows remain below 0.1 V. The
companion `authored-inm-sweep.cir` drives INM from 0 V to 3 V and back at
15 V AUX/PWM high; its state crosses at 2.2005 V rising and 1.2000 V
falling, with 14.9820/14.9644 V enabled plateaus and a disabled gate below
0.1 V. These checks are specifically intended to catch a 7--8 V substitute
qualification threshold; they do not add hardware claims.

`authored-late.cir` holds PWM high through a static prehistory, applies an
approximately 1 ns falling edge near 0.257 s, and runs with a 500 ns maximum
step. It produced 514,093 finite rows ending at exactly 0.25702 s: the gate
was 14.9820 V before the edge and below 2e-15 V in the post-edge window. This
only demonstrates that this reduced native-switch candidate survives the late
absolute-time screen; it does not reproduce or explain the full-plant vendor
stall.
