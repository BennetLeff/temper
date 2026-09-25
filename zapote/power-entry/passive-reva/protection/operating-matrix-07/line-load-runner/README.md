# Bounded line/load runner

`runner.rs` is the execution harness for the nine-point matrix prepared in
`../line-load-prep/manifest.json`. That preparation manifest intentionally
remains `planned_unexecuted`/`PENDING`; execution is authorized only by a
separate accepted-baseline receipt whose bytes name the exact accepted deck hash,
include-closure hash, and endpoint.

The runner uses `jq` for strict JSON parsing and schema checks. The required
baseline receipt shape is:

```json
{
  "status": "accepted",
  "accepted": true,
  "endpoint_s": 0.5,
  "deck_sha256": "<sha256 of accepted cold.cir>",
  "includes_sha256": "<sha256 of sorted include-name/hash lines>"
}
```

The parent workflow should create that receipt only after the maintained
normalizer and `operating_point_checker` accept a complete cold trace. A
simulator exit code, a progress callback, or a partial trace cannot create
the receipt. The runner also checks that the requested `--end-s` exactly
matches the receipt endpoint.

For every point, the runner copies `cold.cir` and its recursive local include closure
into an isolated directory and changes only the `VAC_RMS=` and `RLOAD=` tokens
on their respective `.param` lines. It records the source hashes and generated deck values
in `case.json`; it refuses malformed or duplicate parameter tokens. The
closure resolver canonicalizes each path, rejects traversal/symlink escapes,
detects cycles, recognizes case-insensitive `.include`, rejects unsupported
`.inc`/`.lib` directives, and preserves non-UTF8 vendor libraries byte-for-byte
while still discovering nested ASCII directives in them.
normalizer and checker are then connected as a real `gzip -cd | normalize |
checker` pipeline, with each exit status checked independently. `result.json`
records `accepted`, `rejected`, or a runner failure. A rejected point remains
rejected; no aggregate summary can turn it green.

The scheduler defaults to two independent workers and refuses more than four.
Each tracked host receives the existing wall limit and endpoint, writes its
own `progress.tsv`, and uses a FIFO reader owned by a tracked compressor
process.
Gzip remains the default compressor.  An optional `--pigz PATH` selects a
canonical pigz executable and invokes it as `PATH -p 4 -c`; this option is
currently restricted to `--workers 2` so the scheduler uses at most eight
compression threads.  The output remains a gzip stream and is still consumed
with `gzip -cd`.  `source-identity.json` records the canonical compressor path,
binary SHA-256, format, and thread count for replay provenance.
The default tracked-host protocol is four arguments (`cold.cir WALL END
trace.fifo`). Pass `--first-invalid-snapshot` for hosts using the diagnostic
five-argument protocol; the runner then appends the case-local
`first-invalid.tsv` path and records that choice in `source-identity.json`.
The scheduler periodically copies the latest progress row into
`runner-progress.tsv`; it kills/reaps the FIFO reader when a producer fails or
the bounded scheduler timeout expires. All outputs live under the requested
new output directory, which must not already exist.

Build and run the cheap checks before any long run:

```sh
rustc --edition=2021 -O runner.rs -o /tmp/matrix07-line-load-runner
/tmp/matrix07-line-load-runner --self-test
```

After the normal source has an accepted hash-bound receipt, build the existing
Rust hosts and run the grid (two workers first):

```sh
rustc --edition=2021 -O ../checker/normalize.rs -o /tmp/matrix07-normalize
rustc --edition=2021 -O ../checker/operating_point_checker.rs -o /tmp/matrix07-checker
rustc --edition=2021 -O runner.rs -o /tmp/matrix07-line-load-runner
/tmp/matrix07-line-load-runner \
  --source ../normal-tracked \
  --baseline /path/to/accepted-normal-receipt.json \
  --manifest ../line-load-prep/manifest.json \
  --output ../line-load-runs/<accepted-source-id> \
  --tracked /private/tmp/matrix07-accepted-source-host \
  --normalize /tmp/matrix07-normalize \
  --checker /tmp/matrix07-checker \
  --spice-scripts /opt/homebrew/Cellar/ngspice/45.2/share/ngspice/scripts \
  --workers 2 --wall-limit 1800 --end-s 0.5
```

If export CPU time is the bottleneck, use the verified pigz binary while
keeping two tracked workers:

```sh
... --workers 2 --pigz /opt/homebrew/bin/pigz
```

`--pigz` is an export-stage choice only; it does not change the live FIFO
reader, tracker five-argument flag, decompression command, solver, or checker.
The self-test constructs both compressor command forms and performs a bounded
FIFO pigz roundtrip through `gzip -cd`.

The diagnostic host with a first-invalid snapshot uses the same command plus
`--first-invalid-snapshot`; use a unique host binary compiled from the exact
accepted source closure. This preparation directory does not create an
accepted receipt and does not launch the matrix.

The runner does not launch the sweep while the baseline is still pending.
The initial implementation is intentionally limited to one declared endpoint
and the nine existing manifest rows; it does not invent loads, alter solver
tolerances, or replace the maintained checker.
