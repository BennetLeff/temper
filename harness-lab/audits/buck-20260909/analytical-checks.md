# Independent analytical checks

These calculations precede acceptance of the behavioral model. They are
ideal-circuit sanity checks, not simulation output or hardware measurements.
Sources are the retained TI SLUSEF4A electrical table and application page 20,
and the Temper component declarations cited in `requirements-components.md`.

The feedback divider independently gives:

- Nominal: 0.600 × (1 + 100/22.1) = **3.314932 V**.
- Low corner: 0.591 × (1 + 99/22.321) = **3.212254 V**.
- High corner: 0.609 × (1 + 101/21.879) = **3.420326 V**.

For an ideal buck in continuous conduction, D = Vout/Vin and
ΔIL = Vout × (1−D)/(L × f). At 15 V, 3.314932 V, 5.6 µH,
500 kHz and 0.5 A, this predicts **D = 0.220995**, **442 ns on-time**,
**0.92227 A peak-to-peak ripple**, **0.96113 A peak**, and
**0.03887 A valley**. The nominal design is close to the boundary between
continuous and discontinuous conduction at this load.

At 16.5 V, minimum nominal-tolerance inductance 4.48 µH, and minimum
oscillator frequency 450 kHz, the same continuous-conduction equation gives
1.31396 A peak-to-peak and a negative valley at 0.5 A. That is a warning
that the continuous-conduction assumption fails for the PFM part; it is not
permission to claim negative-current synchronous operation. The switching
model must change behavior near zero current. Inductor tolerance, bias and
temperature are separate from this nominal-tolerance calculation.

The datasheet's distinct application bench is **12 V → 5 V, 6.8 µH,
44 µF, 500 kHz at 25 °C** (not 8.2 µH). At its full 3 A load, ideal
D = 0.416667 and ΔIL = **0.85784 A peak-to-peak**. Figure 9-3 should
therefore show a roughly 2 µs switching period and triangular ripple near
0.86 A. The retained PDF visually agrees at the resolution of its plot;
this is a qualitative cross-check, not a digitized measurement.

Figure 9-4's output rise is roughly 4 ms after input application, consistent
with the specified typical soft-start reference ramp. Output 10–90% rise,
reference ramp time, and settling time are different observables. Figure
9-2 depicts sparse switching at no load, so a model that switches at 500 kHz
regardless of load has not reproduced the X/PFM variant.

No fitted compensation, arbitrary ripple limit, or output forcing is used
in these calculations. Full losses, transients, layout parasitics and thermal
behavior require separate evidence.
