# Numerical summary

Baseline: **36/36 reproduced** selected native19-carryover rows (≤1% relative with1V floor). Required driver cases: **11/36 completed**; all others indeterminate. Optional stress: 9/11 completed attempted samples.

| Required case | Completed /12 | Off gate range V | Die VDS range V | 3V threshold deadtime ns | ZVS passes | Hot/VDS screen passes |
|---|---:|---|---|---|---:|---:|
| S1 | 6/12 | 0.529…0.938 | 197.278…204.095 | 135.616…229.192 | 6 | 6 |
| S2 | 5/12 | 1.623…1.720 | 327.382…337.427 | 109.411…206.285 | 5 | 5 |
| S4 | 0/12 | — | — | — | 0 | 0 |

Maximum absolute baseline discrepancies: VDS peak0.232732V; off-gate0.000885016V; incoming command-time VDS4.93576e-05V.

Full-tail audit to3.5µs: no higher peaks beyond3.193µs = **True**.

These ranges cover completed samples only and are not bounds. See CASES.md for every aborted combination. No circuit decision is changed on this evidence.
