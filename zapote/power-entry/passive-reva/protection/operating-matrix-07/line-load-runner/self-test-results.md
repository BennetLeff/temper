# Runner self-test receipt

Command:

```sh
rustc --edition=2021 -D warnings -O runner.rs -o /tmp/matrix07-line-load-runner
/tmp/matrix07-line-load-runner --self-test
```

Observed result on the host:

```text
self-test: materialization/hash/change-constraint/pipeline/process-fail-closed checks PASS
```

The bounded test covers the real production deck's separate `VAC_RMS` and
`RLOAD` parameter lines, inverse replacement of every other deck byte,
immutable include hashing, delayed FIFO EOF/footer drain, compressor failure,
producer exit before opening its FIFO, missing executable rejection, and the
duplicate-key and malformed-JSON receipt negatives, and the normalizer/checker
pipeline's synthetic checker-failure and missing-checker spawn negative
controls, including cleanup of already-spawned gzip/adapter children. It also
checks case-insensitive nested includes in a non-UTF8 file, rejects missing,
traversal, symlink-alias and unsupported `.lib` directives, and confirms
vendor-byte mutation changes the closure digest. It
also verifies both tracked-host argument modes: the default four-argument
protocol and the optional case-local `first-invalid.tsv` fifth argument.
does not execute the nine-point matrix or create an accepted baseline receipt.
