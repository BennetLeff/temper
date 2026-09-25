# Native normal-trace host

The parent-reviewed host retains the current callback, first-invalid snapshot,
wall limit and stall guards. It writes one complete ngspice native binary plot
containing the 15 normal-observation columns. The circuit still saves the full
31-vector set for the diagnostic callback. No electrical model, timestep,
tolerance, row order or sample has been changed.

CLI: `HOST DECK WALL_SECONDS TARGET_SECONDS EXPORT_PATH SNAPSHOT_PATH`.
`EXPORT_PATH` may be an owned FIFO feeding pigz. The capture metadata records
format, schema, platform, byte order and callback counts; it does not grant
acceptance. A non-little-endian build fails rather than labeling its bytes
incorrectly.

Parent tests: six host unit tests, then independent 1ms FIFO transport with
5,905 rows/15 fields; producer, compressor and streaming decoder all exited0.
The output was461,341 compressed bytes; all diagnostic names were observed.
This tiny result does not predict full-case size or qualify circuit behavior.
Exact source, binary and test identities are in `parent-review.json`.

The runner must wait for producer and compressor, check format/source identity,
then run the normal metrics and the per-trace event/error audit. Case records
remain pending parent review until all those results are assessed.
