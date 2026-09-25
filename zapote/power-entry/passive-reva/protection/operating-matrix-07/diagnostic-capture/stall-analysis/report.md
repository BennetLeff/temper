# Before-stall trace analysis

Input: canonical `operating-matrix-07/diagnostic-capture/before-stall.tsv`
(538 MB, 45 columns). The Rust reader in this directory (`analyze.rs`) streams
rows once and supersedes the earlier analyzer/Python tooling.

Command and result:

```sh
rustc --edition=2021 -O analyze.rs -o /tmp/matrix07-stall-analysis
/tmp/matrix07-stall-analysis /path/to/before-stall.tsv > report.txt
```

The trace has 501,348 finite rows and 501,347 strictly increasing intervals,
from 0.3400000183936029 s through 0.3514900000000000 s. The minimum interval
is 5.5511151231257827e-17 s at 0.3431591509495921 s. This is an observed
floating-point time separation, not evidence that the solver's internal
accepted timestep was exactly that value.

## Counts

Threshold counts are cumulative (`dt <= threshold`):

| interval threshold | count | phase > 570 ns | negative post-hoc margin |
|---:|---:|---:|---:|
| 1e-15 s | 1,913 | 1,913 | 0 |
| 1e-14 s | 4,530 | 4,530 | 0 |
| 1e-12 s | 45,861 | 12,093 | 0 |
| 1e-10 s | 135,350 | 69,366 | 15 |

The phase margin is evaluated only as a supporting observation after reading
the trace: `0.72 + M2*1e6*(phase - 570 ns) - ICOMP`, for `phase > 570 ns`.
Its minimum is −3.819070022 at 0.3456441076635309 s. At the absolute
minimum-step interval, phase is 1.9247728549887100e−6, M2 is
1.3383692705941677, ICOMP is 2.5087525227192677, and the same margin is
0.024433835.

The first minimum-step interval is:

```text
3.43159150949592040e-1 -> 3.43159150949592096e-1 s
dt = 5.55111512312578270e-17 s
```

At that interval `xu.raw` remains 5 V, `xu.pwm_hold` changes by
2.7755576e−7 V, `xu.phase` changes by 5.5511e−17, `xu.m1`/`xu.m2` change by
1.7e−16/4.4e−16, `xu.blank` changes by 6.0652e−11 V,
`xu.icomp_reset`/`xu.pcl_hold` remain 0, `ICOMP` changes by 3.8325e−13 V,
and `PWM` remains 15 V. The tiny-step interval is therefore not itself a
large raw/PWM/phase edge.

Actual 2.5 V threshold crossings (a value changing from below 2.5 V to at
or above it, or vice versa) are separate from the broad delta indicators:

| interval population | `xu.raw` crossings | `xu.pwm_hold` crossings |
|---|---:|---:|
| `dt <= 1e-15 s` | 0 | 197 |
| `dt <= 1e-14 s` | 0 | 375 |
| `dt <= 1e-12 s` | 0 | 617 |
| `dt <= 1e-10 s` | 0 | 2,966 |
| `dt > 1e-10 s` | 2,966 | 0 |

The first tiny `pwm_hold` crossing occurs at 0.340004804421065954 s with
`dt = 3.791e-12 s` (2.510202743 -> 2.491245685 V). The first 20 crossing
examples and all parser-derived values are in `report.txt`; the table does
not infer a cause from the threshold coincidence.

For comparison, broad edge indicators on ordinary intervals (`dt > 1e-10 s`)
occurred 2,966 times on `xu.raw`, 12,036 on `xu.pwm_hold`, 122,167 on
`xu.phase`, 113,256 on `xu.blank`, and 15,023 on `ICOMP`; `xu.m1`, `xu.m2`,
`xu.icomp_reset`, `xu.pcl_hold`, and `PWM` had zero ordinary indicators under
the selected thresholds. At `dt <= 1e-15 s`, only 197 `PWM` changes exceeded
the broad indicator threshold; raw/phase/blank/ICOMP did not. At `dt <=
1e-12 s`, PWM-hold and blank indicators become common (30,922 and 20,969),
while phase itself remains unflagged under the 1e−8 threshold.

## Interpretation boundary

The minimum-step population overlaps small PWM-hold/blank transitions. Only
15 of those intervals also have a negative M2-weighted post-hoc margin, while
the competing ordinary-edge counts show that phase, blanking, and ICOMP also
change frequently at normal-sized intervals. The trace alone therefore does
not establish whether the stall is caused by the phase-floor expression,
ternary/ADC bridge event scheduling, DFF event rollback, blanking-cap
stiffness, or another analog path. No node is named as the root cause, and no
engineering limit is changed.

The next decisive observation is an interactive interruption at the actual
stalled PID followed by `where`, `status`, `rusage tranpoints traniter
rejected trancuriters trantime`, and XSPICE `edisplay`/`eprint` for event
nodes. Those commands can distinguish a nonconvergent device from repeated
analog/event rollback; minimum `dt` alone cannot.
