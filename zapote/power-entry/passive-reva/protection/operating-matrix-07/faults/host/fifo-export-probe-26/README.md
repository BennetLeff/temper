# FIFO to pigz export transport probe (synthetic)

This probe isolates the exact runner-12 raw-export handoff:

```sh
exec pigz -p 4 -c < FIFO > OUT
```

It does not invoke ngspice, a tracked host, or any campaign case. A Rust
producer streams 4,404,086,473 decompressed bytes through an owned FIFO: a
unique four-line title is followed by 4,200 blocks of 1 MiB, each with a
little-endian block index and a deterministic repeated payload byte. A Rust
verifier reads `pigz -dc` as a stream and checks the title, every index and
payload byte, exact block count, and EOF, so missing, reordered, or truncated
data cannot pass by counting alone.

## Reproduction

The bounded command below retains only compressed output and small logs. It
checks a 10 GiB free-space floor, rejects compressed output over 100 MiB, and
reaps both children on an error or 120-second deadline:

```sh
rustc --edition=2021 -D warnings -O probe.rs \
  -o /private/tmp/matrix07-fifo-export-probe26
rm -rf out && mkdir out
/private/tmp/matrix07-fifo-export-probe26 out /opt/homebrew/bin/pigz
```

The retained result is `out/receipt.json` and `out/stream.raw.gz`. The run on
2026-09-20 completed in 7.764 s with producer and pigz exit 0, a 4,872,093-byte
gzip, SHA-256
`bd4ac61e8b126c81ab7a80377aed3f38584fd2300763c1e99dfb8bb629949cda`, and a
successful streaming verifier/decompressor pair. The output is 4.6 MiB on
disk; no uncompressed 4.4 GiB file was created.

This PASS bounds the synthetic FIFO/pigz path on this host only. It does not
explain the LL05 partial export, prove ngspice producer behavior, or make any
campaign evidence recoverable. A failing or successful synthetic probe must
not be promoted to electrical or fault acceptance.
