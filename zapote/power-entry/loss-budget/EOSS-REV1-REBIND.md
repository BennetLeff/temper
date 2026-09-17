# Stored-energy source correction — 2026-09-17

The earlier curve claimed DS11178 Rev 2 Figure 8 but retained only
DocID028164 Rev 1. That was not a reproducible source binding. The corrected
curve uses the retained **Rev 1, page 7, Figure 12**, whose PDF SHA-256 remains
`6ead5993ed475f54b262779c621e36ebfafc5d6a3b73ff58e7fa1074f7398322`.
No PDF bytes or historical receipts were replaced.

Figure 12 was inspected visually and its vector curve extracted with:

```
pdftocairo -f 7 -l 7 -svg sources/STW65N65DM2AG.pdf evidence/correction-02/st-rev1-page7.svg
```

In that retained SVG, the curve has transform
`matrix(0.0519644, 0, 0, 0.051946, 156.911892, 625.86976)`.
The calibrated page coordinates are x=156.911892 at 0 V, x=268.427589
at 600 V; y=625.86976 at 0 µJ, y=514.393719 at 36 µJ.
The right-hand grid edge is **700 V**, not 600 V. Use the labelled ticks;
inferring axis endpoints from the last curve point shifts the entire result.

Sampling the monotone cubic vector at 50 V intervals gives, in µJ:

| V | Vector read | Rounded model input |
|---:|---:|---:|
| 0 | 0 | 0 |
| 50 | 2.823 | 2.8 |
| 100 | 4.056 | 4.1 |
| 150 | 5.321 | 5.3 |
| 200 | 6.950 | 7.0 |
| 250 | 8.994 | 9.0 |
| 300 | 11.453 | 11.5 |
| 350 | 14.285 | 14.3 |
| 400 | 17.478 | 17.5 |
| 450 | 20.991 | 21.0 |
| 500 | 24.827 | 24.8 |
| 550 | 28.984 | 29.0 |
| 600 | 33.488 | 33.5 |

Linear interpolation of the rounded table at 389.615 V gives **16.835 µJ**,
or **2.174 W** at 129.107 kHz. Direct vector sampling near 389.7 V gives
16.801 µJ, a useful independent check of the interpolation. The ±0.6 µJ
allowance is a chosen extraction/interpolation allowance (±0.0775 W), not
manufacturer tolerance or a guaranteed operating bound. The old 18.565 µJ /
2.397 W value is superseded. `C_oss eq.` remains time-equivalent and is never
used as an energy-equivalent capacitance.

Rev 1 Table 6 also supplies typical Qg=120 nC, Qgs=27 nC, Qgd=58 nC and
Rg=3.3 Ω. Total Qgs includes charging before channel conduction; it is not
current-transfer charge. These data were taken at 520 V, 60 A, 10 V gate
bias, not the modeled phase-mean currents. They therefore remain sensitivity
inputs until validated at the operating point.
