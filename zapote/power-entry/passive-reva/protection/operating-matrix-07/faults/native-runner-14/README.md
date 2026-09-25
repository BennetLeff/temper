# Native fault runner 14 (prepared diagnostic candidate)

This is a bounded single-case supervisor for the native fault42 capture. It
does not launch a campaign or make an acceptance decision. Stage 1 runs the
five-argument native host (`case.cir WALL TSTOP raw.fifo first-invalid.tsv`)
through `pigz -p 4` and retains only `raw.trace.raw.gz`. Before it waits for the
compressor, it requires fresh capture metadata with `schema=fault42`, both
65535 name masks, positive point count, `solver_stopped`, little-endian native
format, and `accepted=false`/`diagnostic_only=true`.

Stage 2 streams `pigz -dc` into the reviewed native fault42 decoder, the
event-aware adapter, and the event-aware validator. The checked17 stream and
supplement are FIFOs; only the compressed raw42 artifact and reports remain.
All children have bounded waits, disk-floor checks (10 GiB), and kill/reap
cleanup. Source include closure and all tool hashes are compared before and
after transport. `SPICE_SCRIPTS` must be explicitly set to the reviewed
ngspice scripts directory. Manifest timing, case identity, and each declared
`output_sha256` are checked with typed `jq` queries before launch.

The planned case mapping is explicit: `f2-start`, `f2-crest`, and `f2-zero`
use their exact adapter kind and validator `f2-open`; `bypass-neg` requires an
explicit `--bypass` and also maps to validator `f2-open`; switch, diode, and
both-short retain their names. No `f2-open` alias is silently promoted.

## Bounded verification

```sh
rustc --edition=2021 -D warnings --test supervisor.rs \
  -o /tmp/matrix07-fault-native-runner14-tests
/tmp/matrix07-fault-native-runner14-tests
rustc --edition=2021 -D warnings -O supervisor.rs \
  -o /tmp/matrix07-fault-native-runner14
rustc --edition=2021 -D warnings fixture/synthetic-native-host.rs \
  -o /tmp/matrix07-native-runner14-synthetic-host
```

The Rust TEST_ONLY fixture completes the real FIFO/native-decoder/adapter/
validator transport in under ten seconds and writes `COMPLETE_REVIEW_PENDING`
with `acceptance=false`. A `/usr/bin/true` host negative control rejects a
missing capture metadata file before waiting for the compressor and leaves no
FIFO. Neither command invokes ngspice.

No physical fault, protection, thermal, or product qualification claim follows
from this candidate; parent review remains required.
