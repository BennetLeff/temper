# F2-ZERO post-capture analysis

Parent-reviewed fixed commands; prepared but not executed on the campaign raw.
No solver is launched and no diagnostic result is promoted to acceptance.
The worker draft is retained in run-worker.sh and README-worker.md.

run.sh consumes only completed settled-direct-capture-51/full-F2-ZERO/raw.trace.raw.gz.
It requires wrapper runner.exit and monitor.exit at the launch root, successful
stage1 host/compressor records, complete42-column export and matching row count,
exact prepared manifest/closure and recorded input hashes, exact analysis tools,
and the compressed raw hash/size from capture-stage1.json. A nonzero final
validator/runner verdict is retained; complete raw can still be diagnosed.
The script refuses the live run before creating outputs. Missing or inconsistent
capture records require parent investigation rather than fabricated defaults.

After fresh no-clobber output creation, gzip integrity is checked. Four streaming
passes run the existing frozen tools: complete prefault scan; selected normal15
event audit; selected normal12 metrics via the existing normalizer; phase43 zero
check. All child exits are recorded. Prefix endpoint is the actual last sample
at or before650ms, and all three selector reports must agree. Full-row count and
682ms endpoint are checked. No decoded archive is written. Tool implementations
and numerical/electrical limits remain unchanged.

The zero-phase interval is declared BEFORE reading the result as fault time
plus/minus10ms: [0.6483333333333,0.6683333333333]s. It contains strict neighbors
around the edge and local mains crests; the existing all-choice1% criterion is
unchanged. This replaces the worker's copied crest interval, not any observed
failed result. The phase tool itself supplies the bracket/marker/ambiguity checks.

The raw hash is checked again after all successful passes. Every pipeline must
exit0 to produce analysis-receipt.json, whose accepted field is alwaysfalse.
Electrical failure or ambiguous data remains a rejection for parent review.
A10GiB capacity check runs before each pass; execution must be supervised via
its actual process handle. Parent checks still include full acceptance/evidence
binding, legacy strict result, source phase, physical scope and branch currents.

Parent fixed completion paths, output creation order, Bash3 compatibility,
source/capture binding, phase interval, metadata row checks and terminal receipt
handling. Bash syntax and shellcheck passed. A live-run refusal check exited
before output creation or raw reads. No full analysis was run during preparation.
