# First modeled normal baseline

The complete 120 VAC / 190 ohm cold run meets the original normal-operation
screens through 650 ms under `event-aware-normal-v1`. Its last three cycle
means are 382.85, 383.39 and 383.89 V (0.2731% drift, below 0.5%). Input is
7.32 A RMS; modeled input/load power is 868.63/773.45 W. All original
electrical screens pass. This permits the next operating-matrix simulations.

The original checker still rejects the trace because it requires strictly
increasing time. That result is preserved. The exact ngspice source audit
shows accepted output callbacks can carry repeated binary64 time; the full
trace contains 66 such intervals in 45 groups, with continued progress, no
backwards or nonfinite values, and no saved logic changes inside the groups.
Every original row remains retained and included in stress extrema. The
conservative neighboring-state analysis places the choice-of-row effect far
below reported current, power and voltage precision; no group coincides with
a measurement boundary. The selected storage changes are separately reported.
No timestamp was nudged, interpolated away or deduplicated.

This is a versioned numerical-method decision for the recorded model, not a
waiver for future duplicate timestamps. Every new case needs its own complete
source-bound trace and the same observable checks. Parent review corrected
cycle ordering, exact boundary handling, and overflow checks; eight metric
tests, six bound tests and independent strict/same-time/700 V peak/boundary
fixtures support the instruments. See `acceptance.json` for exact hashes.

The source remains an authored functional controller/driver and generic
power-device model with a material ISENSE-clamp model limitation. The
68.13 W positive residual is modeled loss/accounting, not measured heat or
proof of total energy closure. Hardware, thermal and fuse interruption
qualification remain outside this result. Frozen 04/05/06 evidence is unchanged.

Only the six small electrical source files are copied here. The 5.36 GB
compressed raw evidence remains at the referenced original path.
