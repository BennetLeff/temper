# Native fault runner 29 (anonymous capture transport candidate)

This is a bounded fork of `faults/native-runner-19`. It preserves the source
closure checks, case manifest and timing validation, fault42 parser/adapter/
validator pipeline, disk floor, timeout, semantic metadata checks, capture
stage-1 receipt, delayed-footer drain, raw byte/hash recording, and fail-closed
result policy.

The stage-1 capture handoff is the only transport change. `pigz -p 4 -c` is
spawned directly with `Stdio::piped()` and its owned `ChildStdin` descriptor is
passed to the native host as `/dev/fd/N`. A `pre_exec` hook clears
`FD_CLOEXEC` on that dynamically selected descriptor; fd 3 is never assumed.
The parent drops its writer immediately after host spawn, so host close/EOF is
the compressor's completion boundary. No shell or capture FIFO is used. The
adapter/validator FIFOs in stage 2 remain unchanged.

Parent reviewed the transport fork; see `parent-review.json`. All12 bounded
tests passed with none ignored in the approved execution environment. No
campaign or ngspice simulation was run through29; electrical acceptance remains
pending. The original worker manifest preserves its pre-review candidate status.
The inherited-fd host-open test is marked ignored in this sandbox because
`/dev/fd/N` returns the known `Operation not permitted` denial here. It asserts
success when run in the approved execution environment; a denial is not a
passing transport result, and the parent must repeat that tiny probe before
any real case.

## Bounded checks

```sh
rustc --edition=2021 -D warnings --test supervisor.rs \
  -o /tmp/native-runner29-tests
/tmp/native-runner29-tests
rustc --edition=2021 -D warnings -O supervisor.rs -o /tmp/native-runner29
```

The 12 tests include: direct anonymous stdin gzip EOF/readback; an ignored
dynamic-fd host export that requires success in the approved environment;
dynamic-fd host-start failure with compressor reaping; typed metadata and
row-count checks; timeout reaping; and runner-19's delayed-footer positive-
point drain regression. The local run is 11 passed, 1 ignored, 0 failed.
