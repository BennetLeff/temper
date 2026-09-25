# BOTH-SHORT normal-prefix and phase candidate

**Status: parent review pending; accepted=false.** This candidate records only
the completed saved-archive normal-prefix and crest-phase diagnostics. It does
not accept the fault case, waive the validator result, or make a hardware
claim. Full analysis and the separate legacy strict-checker receipt remain
required.

The capture is bound to `faults/settled-both-short-65/full-BOTH-SHORT`:
32,036,953 fault42 rows ending at 0.662 s, 5,286,116,925 bytes, SHA-256
`52b33da8bbb29fd1038e575fd0d79c950ce086f4ad0b619903334164e66f7166`. The
source identity is BOTH-SHORT (`case.cir` SHA
`c35139cff49f8f43db43a4dca9cff13c06c0289150b09dab12ba5aff29ffcb51`, manifest
SHA `92345035c765b9132540e067b1ffe3ce06e4845095671328700386502dc0479b`).

The exact selector retained 30,109,591 original rows through
0.6499999876940904 s. The cutoff gap is 12.305909624643618 ns, within the
1-us bound. The recorded fault-control rising edge is
0.6541666661706754 s. The audit retained all selected rows: 47 equal-time
groups, 64 repeats, maximum group size 3, no missing right neighbor, logic
change, backward step, or boundary group. Its E3 spread is
`1.7009003384814868e-13 J`; E3 sum-absolute is
`2.6323037478888208e-12 J`.

The last-three-cycle metrics report 120.000000 V RMS, 7.318003 A RMS,
868.144984 W real input, 773.452906 W load, PF 0.988595, and bus mean
383.377214 V with 381.322638–385.378685 V extrema. Cycle means are
382.8587798497746, 383.38766725877025, and 383.8851947230978 V. Using the
frozen first-cycle denominator gives drift 0.0026809229077258616 (the report
prints 0.002681). Inductor peak 30.649183 A is report-only. VD, VDS, and
|VGS| peaks are 385.488063 V, 386.786740 V, and 14.982193 V; armed/on
fractions are both 1.0. The report has zero normal screens and remains
`REPORTED_NOT_ACCEPTED`.

The crest phase scan used `[0.65, 0.6583333333333] s`, tolerance 1%, and
reports one edge, initial low marker, strict neighbors, a positive peak, and
one peak-tie group. The endpoint error is approximately −1.11e−16 s. The
observed and bounded source-spread terms are 1.4210854715202004e−14 V and
1.4210854715202007e−14 V; representative criterion error is
1.7585035537258274e−14 and `sufficient_bound_pass=true`. This is phase-source
evidence only.

The authoritative small-report hashes and all source hashes are recorded in
`normal-phase-candidate-112.json`. No raw archive or FIFO was read while
preparing this candidate.
