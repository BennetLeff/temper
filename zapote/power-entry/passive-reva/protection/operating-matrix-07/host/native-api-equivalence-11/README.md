# Current-host text versus native binary export

Parent-verified bounded 1 ms probe of the actual current diagnostic host.
The copied electrical source differs only in TSTOP (650 ms to 1 ms). The host
adds a native binary export after its existing text export; its callback,
first-invalid recording and watchdog code are unchanged. Both FIFO readers
and the host exited zero, retaining 5,905 rows with 31 fields.

The reviewed streaming adapter recovers every one of the 183,055 binary64
values identically to the current host's text output. No resampling, row
filtering or tolerance comparison was used. Source/deck/outputs are bound by
`parent-review.json`; the exact small host diff is `out/progress-diff.patch`.

Correction: the actual host calls `ngSpice_Command("wrdata ...")`. It does
not use `ngGet_Vec_Info` to export the plot. Earlier API_NGGET labels in this
probe's comments/report are incorrect; the parent receipt supersedes that
interpretation. The comparison does establish what is needed here: native
binary versus the actual current host's export, from the same plot. An
invented third export API is not an adoption requirement.

The original file name `out/api.tsv.gz` is retained for provenance but denotes
the current host's wrdata output. No full run or operating-point acceptance
is inferred from this transport probe. Production integration still must
select one canonical native output, record format/platform/byte order and
propagate decoder/compressor failures through the reviewed runner.
