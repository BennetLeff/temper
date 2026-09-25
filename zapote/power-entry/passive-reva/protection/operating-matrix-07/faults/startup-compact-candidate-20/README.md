# Startup compact-pacer candidate 20

This is an unexecuted, source-bound diagnostic candidate cloned from
`faults/startup-klu-candidate-17`. It keeps KLU, the 89 ms endpoint, the 75 ms
fault time, all electrical values, tolerances, `.save` lists, initialization,
the 1 Gohm `Rschedule_probe`, and the six-file source closure unchanged.

The only case change is replacement of the 960,002-point finite `Vschedule`
PWL block with the three-point repeating form:

```spice
Vschedule schedule_probe 0 PWL(0 0 25n 1 50n 0) r=0 td=64.999975m
```

This is the same 25 ns rise/fall triangle over the modeled interval, expressed
with a 50 ns repeat and a delay. It is intended to remove the million-point
PWL lookup cost while retaining simulator breakpoints at the three-point
waveform corners. The compact source continues after 89 ms; that behavior is
outside this candidate's `.tran` endpoint and must still be checked at the
endpoint before any adoption.

The replacement is exactly reversible: restoring the original PWL block from
candidate 17 reproduces its `case.cir` SHA-256
`e8ddff3bec89f42568dd85e2e7a33e12e538fb9d3cccef915c036240388cb01c` byte for
byte. The compact case SHA-256 is
`bb589229f13e337430e91dd430c78f25a7943ef3055685ccd57b066567283060`.

No simulation, raw output, or acceptance claim is present here. Parent review
must compare waveform corners, endpoint value, finite monotone trace, and the
25 ns maximum-gap contract before execution.
