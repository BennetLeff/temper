# F2-ZERO legacy strict-check record

`legacy-strict.sh` is a prepared, bounded command recording for the frozen
legacy normal-checker. It is intentionally separate from `run.sh`: the parent
postcapture scan must already have completed and produced
`full-F2-ZERO/prefault-scan.json` and `preflight.json`. The script refuses to
overwrite an existing `full-F2-ZERO/legacy-strict/` directory, verifies the
terminal capture records under `settled-direct-capture-51`, checks the raw hash
and source identity, and reuses the approved tool pins.

The exact historical pipeline is retained: pigz, fault42 decoder, selector
with cutoff `.65` and maximum cutoff gap `1e-6`, normalizer `190`, then
`/private/tmp/matrix07-checker --end-s` with the actual
`last_selected_time_s` from `prefault-scan.json`. The checker endpoint is
therefore the same selected prefix endpoint used by the completed scan, rather
than a copied literal.

Execution records all five `PIPESTATUS` values, stderr files, before/after raw
hashes, and `receipt.json`. A repeated timestamp is classified only when the
checker exits `1` and emits the anchored line
`REJECTED: line [0-9]+: time not strictly increasing`; upstream `141`/`EPIPE`
statuses are retained as transport fallout. An all-zero pipeline is recorded
as complete; every other status or checker text is `PIPELINE_REVIEW_PENDING`,
never an automatic diagnostic completion. `accepted` is always `false`, and no
result is declared during preparation. The script also requires the parent
analysis exit/receipt and verifies every source-identity and manifest output
hash before opening the archive, with a 10 GiB free-space guard.

This file and the script were prepared without opening or decoding the full
trace and without running a solver. Run only after the parent has reviewed and
executed the completed postcapture packet.
