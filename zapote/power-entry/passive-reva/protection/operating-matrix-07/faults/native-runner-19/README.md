# Native fault runner 19 (capture-drain reliability candidate)

This candidate is copied from `faults/native-runner-14` and changes only the
stage-1 capture handoff. A successful host is inspected for typed capture
metadata before the FIFO compressor is awaited. If metadata is missing or has
zero points, the blocked compressor is killed promptly. If the host produced a
positive-point trace but the semantic stop reason is not `solver_stopped` (for
example `wall_limit`), the supervisor drains the compressor to EOF under the
existing disk and timeout guards, records both child statuses plus raw byte
count/hash in `capture-stage1.json`, and then rejects the capture. This keeps a
readable partial gzip for diagnosis without promoting it. Receipt filesystem or
hash failures are returned as transport errors; the candidate never claims a
receipt was written when it was not.

The existing valid `solver_stopped` path still drains and returns both child
statuses. The live runner-14 source and binaries are untouched. No campaign or
ngspice simulation is launched here.

## Bounded checks

```sh
rustc --edition=2021 -D warnings --test supervisor.rs \
  -o /tmp/native-runner19-tests
/tmp/native-runner19-tests
rustc --edition=2021 -D warnings -O supervisor.rs -o /tmp/native-runner19
```

Nine tests pass, including a wall-limited positive-points synthetic host whose
consumer reads the FIFO to EOF and delays gzip footer creation for two seconds.
The test explicitly demonstrates that immediate compressor termination would
leave an empty or truncated output, while the candidate drains and reads back a
valid gzip. Missing/zero metadata cases use a single blocked `exec gzip` and
terminate it promptly.
The fixture source is retained for future TEST_ONLY transport checks; no
fixture binary or run artifact is included.
