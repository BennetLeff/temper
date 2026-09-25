# F2-ZERO bounded post-capture packet

This is a reviewed command packet for the completed F2-ZERO archive only. It
does not launch ngspice, decode the archive while being prepared, or modify
the source case or raw gzip. `run.sh` is deliberately fail-closed: the parent
must provide a terminal capture receipt before any pipeline opens the gzip.

The packet owns only `faults/settled-postcapture-58/`. The fixed input is
`../settled-direct-capture-51/full-F2-ZERO`; the output directory is the fixed
`full-F2-ZERO` child below this directory and must not already exist.

## Parent-supplied completion gate

The current live session is not evidence of completion. The parent must wait
for the existing `runner.exit` and `monitor.exit` records beside the case,
then run this packet. `runner.exit` is recorded even for a completed capture
whose validator classified the waveform as a failure; that status is retained
and is not used as an acceptance waiver. The script requires a terminal
numeric runner status, monitor success, a nonempty raw gzip, and empty
`raw-gzip.stderr`; it hashes the raw before and after every pass. It also
checks source closure hashes from `source-identity.json`, the case SHA from
`manifest.json`, and all pinned tool hashes before opening the gzip. Missing
terminal records, a changing raw hash, or any source/tool mismatch aborts
without creating output.

## Bounded passes

The first pass is the full fault42 prefault scan. Its selector uses the real
last row at or before `.65`; `PREFIX_END` is read from
`prefault-scan.json`. The normal15 audit and event metrics both use that exact
selector endpoint; neither forces `.65` (the strict checker’s 1 ns endpoint
requirement is preserved by passing the selected literal).

The final pass is the phase43 successor with the unchanged 1% criterion and
the F2-ZERO zero-edge interval: `--end-s .682`, expected edge
`.6583333333333`, local interval `[.65,.6583333333333]`, `--kind zero`.
All pipeline child statuses are retained and checked with `pipefail`.

These are diagnostic reports. A zero exit or `PHASE_EVIDENCE_OK` is not case
acceptance; the parent must review endpoint, row-count, source, and electrical
contracts separately. No decoded stream is written to disk.
