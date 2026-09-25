# Driver hysteresis finite-slew candidate

This is a bounded numerical sensitivity candidate for the repeated timestamp
seen near 501.55 ms. It is not a full-plant repair, an accepted source, or a
hardware qualification. No electrical deck, native thresholds, checker limit,
or frozen source was changed.

`authored_logic_hysteretic_slew.inc` starts from the current authored
`AUTH_UCC27511A_H` interface and changes only the state-output path before
`Bdriver_req`: each normalized PWM, INM, and AUX state drives a 1 ohm / 5 nF
RC pole. TI's local `COMPHYS_BASIC_GEN` primitive has the same nominal values,
but its `R1 OUT 1 1` and `C1 1 0 5.0n` are connected to internal node `1`;
`EOUT` itself is a hard behavioral output. The candidate filters the authored
state instead, so it borrows a time constant while using a different topology.
The added pole is therefore approximately 5 ns, not an exact TI output-network
model. Native switch hysteresis remains unchanged: PWM/INM 2.2 V rising and
1.2 V falling; AUX 4.2 V rising and 3.9 V falling. The candidate still uses
the authored collapsed output and 18.75 nF driver-delay pole, and makes no
source/sink-stage equivalence claim.

## Bounded method

The copied slow, fast, sequence (RUN/AUX), AUX sweep, INM sweep, and late
fixtures use the candidate include. The unchanged TI vendor fixtures remain
the oracle; the prior authored fixture outputs in
`../driver-hysteresis-candidate` are the current-candidate comparison. Every
ngspice process was guarded with a 30 s alarm:

```sh
perl -e 'alarm 30; exec @ARGV' /opt/homebrew/bin/ngspice -b -o CASE.log CASE.cir
```

The strict checker was rebuilt with Rust and warnings denied:

```sh
rustc --edition=2021 -D warnings -O check_hysteretic.rs -o /tmp/matrix07-hysteresis-slew-check
/tmp/matrix07-hysteresis-slew-check .
rustc --edition=2021 -D warnings -O compare.rs -o /tmp/matrix07-hysteresis-slew-compare
/tmp/matrix07-hysteresis-slew-compare ../driver-hysteresis-candidate .
```

All nine bounded fixtures completed. `check_hysteretic` reported finite,
strictly increasing traces and PASS; the late fixture ended at 0.25702 s with
514,109 rows and no repeated timestamp. This late fixture is a reduced driver
screen, not a replay of the 650 ms full plant and not evidence that the
501.55 ms full-plant failure is fixed.

## Measured comparison

Gate 4 V edge timing is in nanoseconds; `state_*_input_v` is the normalized
native PWM state crossing. `current` is the existing authored candidate,
`slew` is this folder, and `TI` is the unchanged vendor fixture.

| fixture | current rise | slew rise | TI rise | current fall | slew fall | TI fall |
|---|---:|---:|---:|---:|---:|---:|
| slow PWM | 2502.621 | 2507.675 | 2490.995 | 5970.322 | 5975.410 | 5932.935 |
| 1 ns PWM | 3062.338 | 3067.392 | 3050.884 | 5211.195 | 5216.283 | 5173.673 |

The added state pole shifts both authored gate edges by about +5.054 ns on the
rise and +5.088 ns on the fall. It leaves the native state crossings at the
same nominal 2.2/1.2 V boundaries. Relative to TI, the current candidate's
slow gate residuals were +11.626/+37.387 ns (rise/fall); the finite-slew
candidate residuals are +16.680/+42.475 ns. The fast residuals change from
+11.454/+37.522 ns to +16.508/+42.610 ns. Thus this physically motivated pole
makes the reduced candidate slower and farther from the TI edge timing; it is
not a demonstrated fidelity improvement.

The 35 us RUN/AUX sequence gives the same conclusion:

| window | TI gate | current gate | slew gate |
|---|---:|---:|---:|
| PWM high minimum | 14.973332 V | 14.949873 V | 14.948867 V |
| PWM off max(abs) | 0.004691 V | 0.017616 V | 0.018243 V |
| RUN off max(abs) | 0.008722 V | 0.029435 V | 0.030506 V |
| AUX drop max(abs) | 0.001379 V | 0.017626 V | 0.017630 V |
| rearmed minimum | 14.984420 V | 14.981988 V | 14.981987 V |

Gate 4 V falling occurs at 12,249.301 ns (TI), 12,285.768 ns (current), and
12,290.856 ns (slew) after RUN; the AUX event is 20,091.158 ns, 20,210.782 ns,
and 20,210.816 ns respectively. The candidate does not improve the RUN edge
and is effectively unchanged on the AUX edge because the existing 18.75 nF
driver pole dominates there.

## Disposition

The finite-slew candidate is retained as a sensitivity result only. It
preserves native thresholds and gives a finite, bounded reduced fixture, but it
does not reproduce the TI edge more closely and does not recreate the coupled
bridge/boost/controller history at the 501.55 ms failure. Do not adopt this
include in the full deck or use its reduced pass to accept the 650 ms source.
The next useful evidence remains first-invalid instrumentation of the existing
full plant or a history-equivalent short replay.

Source hash for the candidate include:

```text
f775edfb2b187f820499df5c1ffbea8923df4fef0049b474ba1df0eb2a9c6a81  authored_logic_hysteretic_slew.inc
```
