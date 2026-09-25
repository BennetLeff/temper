# Pacer cost review 18

This is a read-only diagnosis of the live `startup-klu-candidate-17` run. It
does not alter that deck, stop the run, or claim a solver result. The candidate
contains one isolated voltage source with 960,002 PWL points:

```spice
Vschedule schedule_probe 0 PWL(
  6.499997500000e-2 0
  ... alternating values every 25 ns ...
  8.900000000000e-2 1
)
Rschedule_probe schedule_probe 0 1G
```

The points span 64.999975 ms through 89 ms, so there are 960,001 intervals.
The source is a 25 ns rise / 25 ns fall triangle repeated only by explicit
text, and the final endpoint is high. The 1 Gohm resistor makes this source
part of the electrical matrix even though it is intended as an instrumentation
load.

## Evidence from the exact ngspice 45.2 source

The host has the unpacked 45.2 source at
`/private/tmp/ngspice-45.2-src`. The retained, numbered excerpt is
`ngspice-45.2-vsrc-excerpt.txt` (SHA-256
`e9c2ef99e06c47494085a91881150d22ae26d5cb4a2338634ac1decf884fc508`). The
original source-file hashes are:

| file | lines used | SHA-256 |
|---|---:|---|
| `src/spicelib/devices/vsrc/vsrcload.c` | 318–362 | `6f4baccc6bd523a8ac979593b762e90900787840bd7611cb19fdd81671828ff7` |
| `src/spicelib/devices/vsrc/vsrcacct.c` | 48–145, 170–218 | `36927a98f13fcff1678ca4531c4f55305b72e61f7a702b1600bd444da7516a7c` |
| `src/spicelib/devices/vsrc/vsrcpar.c` | 103–159 | `107953459a693221e86cb69db206a3b1369647fc0b2b48918300611aeb361959` |

In `vsrcload.c` the PWL evaluator starts at `i = 2` on every source-load
call and advances by two until it finds the containing breakpoint. With no
repeat and 960,002 points, the work grows with elapsed time through the dense
window. In `vsrcacct.c`, breakpoint scheduling also scans the entire PWL point
array to find the next corner. This is a concrete O(number-of-points) cost in
two per-step paths, not a conjecture based only on the netlist size.

The same source shows that a PWL with `r=0` is supported as a repeating source:
the repeat phase is reduced with `floor()` and then the short point list is
scanned. Its breakpoint scheduler still calls `CKTsetBreak`, so a compact
three-point repeat retains the 25 ns corners while avoiding the million-point
scan.

## What the live progress supports

The observed run remains numerically advancing; it has not shown a repeated
timestamp stall. Parent progress samples show simulated time and wall time:

| wall seconds | simulated time | rows |
|---:|---:|---:|
| 30.24 | 32.829 ms | 645,610 |
| 60.52 | 58.401 ms | 1,197,830 |
| 100.86 | 66.644 ms | 1,740,146 |
| 171.36 | 69.049 ms | 2,255,164 |
| 282.20 | 72.013 ms | 2,805,007 |
| 443 (parent update) | 74.518 ms | live |

The falling simulated-time rate while the dense PWL window advances is
consistent with the source-level O(N) diagnosis. It does not prove that the
pacer is the only cost: KLU factorization, nonlinear iterations, callback
export, and the 1 Gohm branch may contribute as well. The current evidence is
strong enough to prioritize a compact-source benchmark, not to rewrite the
live source.

## Candidate compact source and its limits

The standard constant-size PWL form to benchmark is:

```spice
Vschedule schedule_probe 0 PWL(0 0 25n 1 50n 0) r=0 td=64.999975m
Rschedule_probe schedule_probe 0 1G
```

This preserves the initial zero before the delay, the 25 ns rise and fall
corners, the alternating triangle, and the value 1 at 89 ms. It uses only
three points; `r=0` makes the period 50 ns and `td` delays the first corner.
The compact source continues after 89 ms, unlike the finite original, but the
candidate endpoint is 89 ms, so that continuation is outside the modeled
interval.

Do not use `PULSE(... PW=0 ...)` as the first replacement. In ngspice 45.2,
the PULSE loader treats an explicitly zero pulse width as the default final
time, not as a zero-width triangle (`vsrcacct.c` lines 67–72 and
`vsrcload.c`'s corresponding PULSE code). A PULSE with a tiny positive width
would introduce a finite high plateau and needs a separate waveform-equivalence
check.

The compact PWL is still a candidate, not an accepted electrical change. Its
floating-point behavior at the delay, every 25 ns corner, and the 89 ms
endpoint must be compared against the finite source before adoption.

## Minimum later benchmark

After the live run is preserved, make a new case directory and change only the
`Vschedule` definition to the compact three-point form. Keep KLU, all model
files, tolerances, `.save` lists, `Rschedule_probe`, and endpoint unchanged.
Run both decks to a short endpoint just beyond the pacing start (for example
70 ms) under the same ngspice binary and environment. Record wall time,
accepted-row count, endpoint, and the schedule-source values at:

* just before the delay;
* the delay;
* delay + 25 ns;
* delay + 50 ns; and
* the final endpoint.

Require finite, monotone timestamps and maximum trace gap no greater than 25 ns
over the paced interval. If the compact run is materially faster while these
corner and trace checks agree, the million-point PWL lookup is confirmed as a
dominant cost. If not, retain the source-cost finding but investigate solver
iterations, matrix factorization, and the 1 Gohm branch separately.

No benchmark or source mutation was performed in this review.
