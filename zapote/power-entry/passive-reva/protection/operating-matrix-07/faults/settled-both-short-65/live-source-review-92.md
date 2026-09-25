# BOTH-SHORT live source review

The fresh `full-BOTH-SHORT` materialization is byte-identical to the prepared24 BOTH-SHORT closure for all eight reviewed regular files. The exact SHA-256 values are recorded in `live-source-review-92.json`; they match the materialized source identity and prepared closure.

The declared run contract is `kind=both-short`, with both runner and validator selecting `both-short`; `T_FAULT=expected_fault=0.6541666666667 s`, `TSTOP=0.662 s`, 2 ms event/observation windows, 2 us turnoff, 25 ns local gap, 1 us outer gap, 3600 s wall limit, 900 s export timeout, and `bypass=false`.

The deck holds F2 closed (`Vf2ctl f2ctl 0 5`) and asserts both modeled 1 mOhm branches: `Sswfail sw channel_source swfail_ctl 0 SWFAIL` and `Sdiodeshort sw d1_path dshort_ctl 0 SWDIODESHORT`. The fault marker is the maximum of the two controls. This verifies source identity and topology only; no solver outcome, electrical verdict, or acceptance is claimed.

No raw trace, FIFO, solver, or restart action was accessed.
