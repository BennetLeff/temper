# Buffered C7 drive: experiment 02 result

Carry **IPW65R045C7 + UCC27624DR with a separate 12 V driver supply** into
the next circuit-design iteration. A 4.7 Ω gate resistor is a useful initial
test setting. This experiment supports that priority; it does not select a
production resistor, qualify a replacement or change the current board.

## Conditional comparison

At 120 Vrms, 15 A input RMS, 400 V bus, 129.107 kHz, 12 V driver bias and
4.7 Ω external gate resistance, the partial MOSFET-plus-gate losses are:

| Device | Assist active throughout transition | Assist absent | DC-max resistance substitution |
| --- | ---: | ---: | ---: |
| STW65N65DM2AG | 78.24 W | 93.18 W | 107.95 W |
| IPW65R045C7 | **37.78 W** | **45.50 W** | **53.47 W** |

All three columns are hypothetical dynamic-driver profiles. The 5 Ω and
8.5 Ω source resistances are PMOS-only DC test values; the approximate 1.04 Ω
parallel NMOS provides a brief assist with unspecified duration. None of the
columns is a guaranteed upper/lower bound or a measured operating point.

The previous 10 V / 10 Ω direct-drive controls reproduce exactly: ST
**139.51 W**, C7 **68.35 W**. The new circuit proposal changes the supply,
driver and gate resistance together. It must not attribute the entire gain to
the external driver alone. Keeping 10 Ω with the proposed buffer gives the C7
**62.90/70.63/78.60 W**, depending on profile, so adding a buffer by itself
does not ensure lower loss.

## Gate-resistor tradeoff

| C7 external gate resistor | Full assist | No assist | DC-max substitution |
| --- | ---: | ---: | ---: |
| 2.2 Ω | 25.92 W | 33.65 W | 41.62 W |
| 4.7 Ω | 37.78 W | 45.50 W | 53.47 W |
| 10 Ω | 62.90 W | 70.63 W | 78.60 W |

Lower resistance speeds the assumed transitions and lowers modeled overlap
loss. This model cannot choose the fastest setting: common-source inductance,
commutation, VDS/VGS overshoot, ringing, false turn-on and EMI remain open.
The 4.7 Ω starting point is a design judgment between the tested settings,
not an optimum or a demonstrated safe value.

At 4.7 Ω the C7's conditional turn-on interval is approximately 39/64/85 ns;
turn-off is approximately 46/46/49 ns. The modeled plateau currents are
about 0.47–1.03 A, below the driver's typical 5 A peak figure. Effective
impedance and assist duration matter more here than the headline peak rating.

## Supply and sequencing consequences

The candidate needs 11.4–12.6 V at the buffer pins **including transients**,
while the PFC controller keeps a separate proposed 15 V ±5% supply. Sharing
the 12 V band would not guarantee controller startup: 11.4 V is below its
12.1 V maximum turn-on threshold. Both supply producers remain unimplemented.

Using the C7's 10 V-source 93 nC charge at 12 V as an explicit approximation
gives **12.01 mA** charge current and **0.144 W** gate-network energy rate.
One effective µF would show **0.093 V** ideal Q/C droop per charge event;
the ideal minimum for 0.2 V is 0.465 µF. Those calculations exclude driver
overhead, bypass ESR/ESL and supply impedance; they do not establish a 12 V
charge upper bound or replace TI's 100 nF plus ≥1 µF local bypass guidance.

The buffer's EN inputs default enabled. A hardware mechanism must hold EN low
during invalid supplies, startup/shutdown and faults, and only release after
both rails are valid and a low PWM state has been observed. That circuit is
not present on the current PCB. See the [measurement contract](MEASUREMENT-CONTRACT.md).

## What was established

- All **2,916 cases** pass source/configuration, grid, finite-value and disjoint
  accounting checks. They cover both parts, three lines/supply voltages/gate
  resistors/driver profiles/Qgd factors/transfer charges and two Rds factors.
- The independent continuous-phase and asymmetric triangle audit agrees on
  every case, with maximum relative discrepancy below **1.035e-11**.
- The preceding experiment's entire 4,374-case JSON report is reproduced
  byte-for-byte through the updated shared solver.
- Physical applicability, supply/enable realization and qualification remain
  **INDETERMINATE**. The CLI exits 2, not a hardware acceptance code.

The power numbers are conditional partial losses, not measured temperatures,
whole-board loss or delivered output. The model's nominal input power is
1,796.31 W. Qg/Rds source points are at 10 V, source charge/current conditions
differ by device, Rds×2 is not a temperature model, and driver DC resistance
does not establish dynamic impedance. The broader sweeps are sensitivity
studies, not guaranteed statistical or physical bounds.

The next concrete design work is the buffered gate stage, separate supply
producer and hardware enable interlock in the authored circuit. The decisive
measurement is the actual source/sink current and assist behavior while the
C7 traverses its plateau, followed by commutation/overshoot checks. Choose
cooling from applicable losses and the installed assembly afterward.

Raw results and verification receipts are under [evidence/](evidence/VALIDATION.md).
