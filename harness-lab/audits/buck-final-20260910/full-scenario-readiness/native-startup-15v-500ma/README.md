# Native startup readiness capture

Development instrument capture for the unchanged LMR51430XDDCR datasheet
model (`62d3bda599e7f7a301b9cc7115e305d33e48edb07957e7f5602c19b92956e096`),
run with ngspice 45.2 (`/opt/homebrew/bin/ngspice -n -b`). The deck uses an
isolated ideal VIN source (0 to 15 V in 1 ms), EN tied directly to VIN, and a
voltage-compliant 0.5 A load `0.5*clamp(VOUT/0.1,0,1)`. It captures 21 ms,
which exceeds 20 ms after the 13.5 V ramp crossing.

The binary rawfile contains exactly five native variables: `time`, `v(out)`
(voltage), `v(in)` (voltage), `i(vin)` (current), and `i(load)` (current).
No raw header was edited after collection. Header reports 4,014,153 points.
The run exited successfully with no simulator error. Native measurements are
0.500000 A final load average (20–21 ms), 3.314904 V final output average,
and 15.000000 V maximum VIN during the 0–1 ms ramp. Exact model, deck,
provenance ledger, simulator log/version, rawfile, and SHA-256 manifest are
retained beside this report.

This capture is development evidence for exercising the binary decoder. It is
not a qualification receipt, hardware result, or claim about transient
performance.
