# Compression probe 21

This bounded benchmark samples only the first 32 MiB (33,554,432 bytes) of
the retained decompressed trace from
`faults/startup-klu-candidate-17/raw.trace.raw.gz`. The canonical trace was
not modified, recompressed in place, or deleted. The source archive SHA-256 is
`88c6f8a495c0e36be83650bb96014f5bb8d4f8199ebf1dd55f26f875f4432ef2`.

The sampled prefix SHA-256 is
`0f85b67b09c9c90e599f1fa0d74cedc41ae13d84e69b3b517157d5fb1f7e8e04` and its
size is exactly 33,554,432 bytes. All four compressed outputs were decompressed
back to that prefix and compared byte-for-byte; the four round trips passed.

Results on this host:

| codec and command | compressed bytes | compress wall | decompress wall | round trip |
|---|---:|---:|---:|---|
| pigz 2.8, `-p 2` | 14,771,463 | 0.31 s | 0.05 s | PASS |
| gzip 479, `-6` | 14,761,714 | 0.62 s | 0.05 s | PASS |
| zstd 1.5.7, `-3` | 14,440,301 | 0.04 s | 0.03 s | PASS |
| xz 5.8.3, `-T2 -6` | 11,736,868 | 7.86 s | 0.36 s | PASS |

The compression and decompression commands were each bounded by a 30-second
alarm. RSS was not readable: macOS `/usr/bin/time -l` could not query
`kern.clockrate` in the sandbox, so no memory number is reported. Tool versions,
exact commands, timing files, compressed outputs, round trips, and the prefix
hash record are retained in this directory.

This is a storage signal for an early startup prefix, not a claim about the
full 556 MiB compressed trace or future 42-field fault traces. The prefix may
have different entropy from the settled/fault region. If storage remains a
concern after this result, sample bounded mid and late windows in separate new
directories before choosing a campaign codec. No format should be adopted
solely from this prefix.
