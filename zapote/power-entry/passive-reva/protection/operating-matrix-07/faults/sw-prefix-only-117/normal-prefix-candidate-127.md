# SW-SHORT normal-prefix candidate

**Status: parent review pending; accepted=false.** This artifact covers only
the cold-start prefix through 650 ms. The SW-SHORT full trace stops at
0.6544026486296868 s instead of the declared 0.662 s endpoint, so the overall
case remains **INDETERMINATE**. No phase evidence, full-fault verdict, or
hardware claim is inferred.

The prefix selector consumed 30,686,230 complete partial-trace rows and
retained 30,112,476 original rows through
0.6499999879903595 s. The cutoff gap is 12.00964050429576 ns, within the
1-us selector bound. The recorded fault marker edge is
0.6541666661706754 s, after the selected prefix.

The event-aware normal audit retained every selected row: 42 equal-time
groups, 66 repeated rows, maximum group size 3, no missing right neighbor,
logic change, backward step, or cycle-boundary group. E3 spread is
`1.7834979248562619e-13 J`; E3 sum-absolute is
`2.6436687128546568e-12 J`.

The last-three-cycle metrics report 120.000000 V RMS, 7.317915 A RMS,
868.156800 W real input, 773.407641 W load, PF 0.988620, and bus mean
383.365993 V with 381.307046–385.364828 V extrema. Cycle means are
382.8415289859337, 383.38277578251075, and 383.8736752876638 V. Using the
frozen first-cycle denominator gives drift 0.002696014469652877 (reported as
0.002696). Report-only inductor peak is 30.628569 A. VD, VDS, and |VGS|
peaks are 385.474781 V, 386.771411 V, and 14.982193 V; armed/on fractions are
both 1.0. The normal report has zero screens but remains
`REPORTED_NOT_ACCEPTED`.

The legacy strict-checker receipt was still pending when this candidate was
prepared. Source identities, raw identity, and all small-report hashes are
bound in `normal-prefix-candidate-127.json`. The partial endpoint and original
rejection remain preserved; this candidate does not upgrade the case.
