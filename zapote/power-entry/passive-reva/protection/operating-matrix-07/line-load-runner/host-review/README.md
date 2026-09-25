# Host review of `line-load-runner`

Reviewed `runner.rs` and the runner README on 2026-09-20. The requested
`rustc -D warnings` build and existing `--self-test` pass. The findings below
are limited to concrete cleanup and source-token issues; no simulation was run.

## Findings

### 1. Pipeline spawn errors orphan already-started children

At [runner.rs:237-240](../runner.rs), `run_pipeline` starts `gzip`, then the
normalizer, then the checker. If the normalizer spawn fails, the checker-report
file creation fails, or the checker spawn fails, the function returns through
`map_err` without waiting for or killing the children already started. Rust's
`std::process::Child` destructor does not kill a running process. A missing or
non-executable normalizer/checker, or a report-path failure, can therefore
leave a gzip/normalizer process running after the runner has failed.

Minimal remedy: wrap the three children in a small guard whose `Drop` kills and
reaps every child, or explicitly kill/reap the already-started children on each
subsequent spawn/file-creation error. The existing `Running::Drop` guard does
not cover this function because these children are local variables.

### 2. `mkfifo` exit status is ignored

At [runner.rs:308-309](../runner.rs), the runner records only whether
`mkfifo` returned an I/O result and discards the command's exit status. It then
accepts any existing path with `fifo.exists()`, without checking that it is a
FIFO. A failed `mkfifo` can thus proceed when a path appears concurrently or
when a stale non-FIFO entry is present, allowing the gzip reader and tracked
producer to operate on the wrong file type and leaving a confusing partial
case. The output-root existence check reduces ordinary stale-path exposure but
does not remove this race.

Minimal remedy: require `status.success()` and inspect metadata with
`FileTypeExt::is_fifo()` before starting gzip; fail and clean the case directory
otherwise.

### 3. Parameter replacement is not token-bound

At [runner.rs:213-219](../runner.rs), `has_v`/`has_r` and `replace_param`
search for the raw substring `VAC_RMS=` or `RLOAD=`. They do not require a
parameter-token boundary. A malformed but otherwise accepted `.param` line
such as `XVAC_RMS=120` would be rewritten because it contains `VAC_RMS=`;
the generated deck would no longer represent the source parameter set while
the hash and one-token counters still describe the altered text. The same
issue applies to comments or other text on a `.param` line containing the
substring.

Minimal remedy: parse `.param` assignments and require the key to begin at
the start of a token (or whitespace after `.param`), then replace exactly that
assignment. Add a self-test for `XVAC_RMS`/`XRLOAD` and a comment containing
the look-alike text.

## Scope note

The baseline hash binding, exact endpoint check, direct-include hashing, FIFO
producer wait, checker exit propagation, and scheduler worker cap were traced
and did not produce an additional concrete acceptance or two-worker resource
bug in this review. The findings above are independent of whether the existing
normalizer/checker binaries are correct.

