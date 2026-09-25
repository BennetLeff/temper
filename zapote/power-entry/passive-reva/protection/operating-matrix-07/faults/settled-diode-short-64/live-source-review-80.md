# DIODE-SHORT live source review

The fresh `full-DIODE-SHORT` materialization is byte-identical to the prepared24 DIODE-SHORT closure for all eight reviewed regular files: `case.cir`, `manifest.json`, and the six included source files. Their SHA-256 values are recorded in `live-source-review-80.json`; the case and manifest hashes match `source-tool-binding.json`.

The run contract is exact: `kind=diode-short`, runner and validator both `diode-short`, fault/expected time `0.6541666666667 s`, event and observation windows `0.002 s`, turnoff `2 us`, local gap `25 ns`, outer gap `1 us`, `TSTOP=0.662 s`, wall limit `3600 s`, export timeout `900 s`, and `bypass=false`.

The deck holds F2 closed with `Vf2ctl f2ctl 0 5` and inserts the declared one-leg short `Sdiodeshort sw d1_path dshort_ctl 0 SWDIODESHORT` with a 1 ns finite PWL command edge. This is a source identity review only; no electrical or acceptance result is claimed.

Only explicit regular source/metadata files were read. Live FIFOs, raw capture, solver execution, and restart actions were not touched.
