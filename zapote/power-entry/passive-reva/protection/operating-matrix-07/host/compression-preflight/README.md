# Lossless compression preflight (small prefix only)

This is a read-only storage estimate for the completed baseline trace
`normal-hysteretic-driver-candidate/trace.tsv.gz`.  The canonical
4,024,370,873 byte gzip file was not rewritten, deleted, or recompressed.  I
extracted only the first 30,000,000 uncompressed bytes into `sample.tsv`, then
compared the standard compressors already installed on this host:

| command | output bytes | wall | user | sys | versus default gzip |
|---|---:|---:|---:|---:|---:|
| `gzip -c sample.tsv` | 5,855,432 | 0.48 s | 0.46 s | 0.01 s | baseline |
| `zstd -3 -q -c sample.tsv` | 6,195,765 | 0.29 s | 0.13 s | 0.01 s | +5.8% |
| `xz -3 -c sample.tsv` | 5,128,180 | 1.15 s | 2.52 s | 0.03 s | -12.4% |
| `pigz -p 4 -c sample.tsv` | 5,857,651 | 0.12 s | 0.49 s | 0.01 s | +0.04% |

All decompressed outputs matched the sample byte-for-byte.  The sample SHA-256
is:

```text
29a45c8e87e39e58f3dd46446dee4d58ab03f71e3c18cdaebfdd036d9b5c9860
```

The source gzip SHA-256 is recorded in `source-gzip.sha256`:

```text
dd20b2bb827a0fc876fa95f83fcb023e66e3207fcab854c13982e5ab3469d032
```

## Exact commands

```sh
gzip -cd /private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/operating-matrix-07/normal-hysteretic-driver-candidate/trace.tsv.gz \
  | head -c 30000000 > sample.tsv
gzip -c sample.tsv > sample.default.gz
/Users/bennet/Miniforge3/bin/zstd -3 -q -c sample.tsv > sample.zstd3
/opt/homebrew/bin/xz -3 -c sample.tsv > sample.xz3
/opt/homebrew/bin/pigz -p 4 -c sample.tsv > sample.pigz-p4.gz

gzip -cd sample.default.gz | shasum -a 256
/Users/bennet/Miniforge3/bin/zstd -q -cd sample.zstd3 | shasum -a 256
/opt/homebrew/bin/xz -cd sample.xz3 | shasum -a 256
gzip -cd sample.pigz-p4.gz | shasum -a 256
```

The compressor binaries were already present (`gzip`, zstd, xz, and pigz
2.8); no installation or canonical-trace mutation was performed.  The pigz
binary SHA-256 is
`a05b6a8ff40a84f8c1fa4052e38a70a682e30f142f5fc7486356134572733a80`.
Each command ran well under the bounded 60-second per-compressor budget.
`gzip -cd sample.pigz-p4.gz | cmp - sample.tsv` passed, and the decompressed
SHA-256 matched the sample SHA-256
`29a45c8e87e39e58f3dd46446dee4d58ab03f71e3c18cdaebfdd036d9b5c9860`.

## Recommendation boundary

On this prefix, xz level 3 produced the smallest file and pigz with four
workers was the fastest; pigz's gzip-compatible output was 2,219 bytes (0.04%)
larger than default gzip.  The sample is not claimed representative of the
full 22.7-million-row trace, so no full-trace savings or nine-grid storage
forecast is inferred.  If export time is the bottleneck, pigz is a candidate
for a future export stage after a larger sample confirms the tradeoff; it does
not change the single-threaded SPICE/FIFO reader.  If disk pressure requires
an archival choice, benchmark a larger independently retained sample first,
then archive completed traces only with a compressor/decompressor hash check
against the original bytes.  Do not replace canonical gzip traces based on
this small-prefix result alone.

## Column-projection estimate (planning only)

The normal-tracked deck's `.save` contract is in `normal-tracked/cold.cir`:
`time` plus these 14 normal signals, in order:

```text
v(acsrc) v(acn) i(Vac) v(load) v(vb) i(Lboost) v(vd) v(sw) v(gate) v(q) v(en) v(fault) v(vcomp) v(icomp)
```

The normalizer (`checker/normalize.rs`) requires exactly one occurrence of its
13-field source subset (time plus the first 12 signals through `v(fault)`). It
derives the exact 12-field checker header
`time_s v_ac_v i_ac_a v_load_v i_load_a v_b_v i_l_a v_d_v v_ds_v v_gs_v armed on`.
The operating-point checker rejects any other header, nonfinite row, duplicate
or missing source column, non-increasing time, excessive gap, or switching-step
alias. Thus `vcomp` and `icomp` may be retained as normal diagnostics, but they
are not inputs to acceptance. The 16 controller-internal signals currently
added by the hysteretic candidate are likewise not needed on every grid row;
the first-invalid capture can retain one owned snapshot of them. This is only
safe after the callback/snapshot path has been verified; the `.save` expansion
must remain unchanged for that diagnostic experiment.

As a bounded byte-count estimate, `project_prefix.rs` projected the complete
rows in the retained 30,000,000-byte prefix from all 31 columns (time + 30
signals) to the 15-column normal set (time + the 14 signals above):

| representation | bytes | change from all-column prefix |
|---|---:|---:|
| raw source prefix | 30,000,000 | baseline |
| raw projected prefix | 14,055,126 | -53.1% |
| default-gzip source prefix | 5,855,432 | baseline |
| default-gzip projected prefix | 3,885,885 | -33.6% |

The projection retained 38,607 complete rows; the fixed-byte sample's final
partial row was deliberately dropped. The projected raw SHA-256 is
`f9c915b523a50f685b3edd06c60408b33aa81d2458ad63ac4d22480881988476`, and
`gzip -cd projected-normal.default.gz | cmp - projected-normal.tsv` passed.
This is a prefix estimate only, not a claim about the full 22.7-million-row
trace or the nine-grid forecast. It does show that preserving the normal
checker inputs while moving internal diagnostics to a first-invalid snapshot
could materially reduce storage; parent review is required before any runner
or deck changes.
