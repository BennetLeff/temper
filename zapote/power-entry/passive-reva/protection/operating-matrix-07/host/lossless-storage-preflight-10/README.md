# Lossless storage preflight (bounded sample only)

This is a read-only storage experiment. It does not scan a full campaign
trace, run a campaign case, rewrite an existing artifact, delete anything, or
change the campaign host. The source sample is the existing
`host/compression-preflight/sample.tsv`, a fixed 30,000,000-byte prefix of the
normal trace. The existing compressor artifacts were reused and checked by
byte-for-byte decompression. A separate 1 ms, four-vector ngspice deck checks
the standard native binary raw format; it is not a campaign model.

The installed tools were already present; no package was installed:

```text
/usr/bin/gzip
/opt/homebrew/bin/pigz 2.8
/opt/homebrew/bin/zstd
/opt/homebrew/bin/xz
/opt/homebrew/bin/ngspice 45.2
```

## Text compressor measurement

The existing 30 MB sample contains 38,607 complete 31-field rows plus one
partial row that the earlier preflight deliberately excluded from its
projection. The sample itself is retained at
`host/compression-preflight/sample.tsv`; this task did not recreate it.

| representation | bytes | wall time | round-trip |
| --- | ---: | ---: | --- |
| source TSV | 30,000,000 | — | source |
| `gzip -c` | 5,855,432 | 0.48 s | exact bytes |
| `pigz -p 4 -c` | 5,857,651 | 0.12 s | exact bytes |
| `zstd -3 -q -c` | 6,195,765 | 0.29 s | exact bytes |
| `xz -3 -c` | 5,128,180 | 1.15 s | exact bytes |

The four exact checks are recorded in `text-roundtrip-receipt.txt`. The source
sample SHA-256 is
`29a45c8e87e39e58f3dd46446dee4d58ab03f71e3c18cdaebfdd036d9b5c9860`.
The existing preflight measured a 15-column normal projection at 3,885,885
gzip bytes. That projection is a different column set, so its number is not
added to any binary estimate below.

## Native ngspice binary raw probe

`native-probe.cir` is a bounded 1 ms RC transient with 1,091 accepted points
and four real vectors. It runs in less than five seconds and executes
`set filetype=binary`, `run`, and `write native-probe.raw all`. The output is
the standard ngspice raw format, not a new project format. The tiny probe was
run from this directory so its relative output remained local.

The native file has a 287-byte ASCII header followed by 34,912 bytes of
little-endian IEEE-754 doubles:

```text
No. Variables: 4
No. Points: 1091
0 time time
1 v(in) voltage
2 v(out) voltage
3 i(v1) current
```

That is exactly `1091 * 4 * 8` payload bytes. The parser receipt
(`native-parse-receipt.txt`) verifies the payload length, finite values,
header order, first rows, and hashes. Compressing and decompressing the native
file with gzip, zstd, and xz returned the **same raw bytes** (`cmp` passed):

| representation | bytes | wall time |
| --- | ---: | ---: |
| native binary raw | 35,199 | — |
| native raw + gzip | 25,258 | <0.01 s |
| native raw + zstd-3 | 24,191 | 0.25 s |
| native raw + xz-3 | 21,492 | 0.01 s |
| native ASCII raw (comparison) | 106,754 | — |

The binary and ASCII probes contain the same variable names and row count. The
default ASCII writer prints 15 significant decimal digits: only 3,161 of the
4,364 parsed values round back to identical binary64 values, and the largest
difference is three ULPs. That is a numeric-identity result, not a text-byte
result. The native binary payload retains the IEEE-754 values exactly; ordinary
TSV/gzip round-trip retains the original text bytes exactly. Both statements
are useful, but they are not interchangeable.

The probe does not prove that the campaign callback can write every host-added
fault column to a native raw plot, nor that the existing Rust TSV checker can
consume a native raw file. It also does not exercise a FIFO. Those are
integration changes that require a separate design and review; no campaign
host was modified here. The measured binary generation wall time was 0.04 s
versus 0.01 s for this tiny ASCII probe, too small to establish an export-speed
advantage.

## Numeric-payload sample benchmark

To compare representations without inventing a parser framework, the same
38,607 complete sample rows were parsed as finite doubles and packed in the
standard native raw payload order. This is a **synthetic payload benchmark**,
not a valid ngspice raw file and not proof that the decimal source has the
original simulator bits. The pack/unpack check was exact for all values after
the decimal-to-binary parse. The source header and column order are retained
in `sample-values.header.txt` for audit.

### All 31 fields

| representation | bytes | wall time | byte round-trip |
| --- | ---: | ---: | --- |
| little-endian f64 payload | 9,574,536 | — | source payload |
| payload + gzip | 4,007,982 | 0.15 s | exact |
| payload + pigz-4 | 4,010,251 | 0.04 s | exact |
| payload + zstd-3 | 3,894,313 | 0.02 s | exact |
| payload + xz-3 | 3,315,908 | 0.62 s | exact |

The binary gzip file is 31.6% smaller than the existing all-column text gzip
sample; binary xz is 43.4% smaller. Those are sample measurements, not a
full-trace forecast.

### The 15-field normal input set

The first 15 fields are the time plus the 14 normal vectors used by the
existing reduced normal export. The same finite-double packing gives:

| representation | bytes | wall time | byte round-trip |
| --- | ---: | ---: | --- |
| little-endian f64 payload | 4,632,840 | — | source payload |
| payload + gzip | 2,818,820 | 0.10 s | exact |
| payload + pigz-4 | 2,820,065 | 0.03 s | exact |
| payload + zstd-3 | 2,953,546 | 0.01 s | exact |
| payload + xz-3 | 2,356,544 | 0.43 s | exact |

For this same sample and same 15 fields, binary gzip is 27.5% smaller than the
existing 3,885,885-byte projected-text gzip. This is the cleanest measured
comparison for the planned normal grid. It is not added to the text estimate:
it is an alternative representation of the same rows.

All files, hashes, timings, and receipts for these bounded measurements are in
this directory. The binary sample hashes are deliberately separate from the
native probe hash because the sample payload is not an ngspice raw file.

## Capacity implication without double-counting

The current storage plan estimates approximately 29.10 GiB for nine reduced
15-column normal exports and 40.47 GiB for seven retained raw fault exports,
before staging and reserve. Those estimates use text gzip and are documented
in `host/storage-budget-09.md`. Native binary or a different compressor would
replace those numbers; it must not be summed with them.

For scale only, multiplying the small-sample ratios by the measured
22,759,008-row 500 ms trace and the existing 650/500 time factor gives the
following *unvalidated* alternatives:

| sample-based alternative | nine normal grid | six long + one startup fault (rough 42/31 column scaling) |
| --- | ---: | ---: |
| binary payload + gzip | 18.11 GiB | 23.76 GiB |
| binary payload + zstd-3 | 18.97 GiB | 23.09 GiB |
| binary payload + xz-3 | 15.14 GiB | 19.66 GiB |

These figures are intentionally not a capacity approval. The sample is an
early fixed-byte prefix, while the measured full 31-column gzip is 4,024,370,873
bytes; compression ratios can change substantially with time and switching
state. The 42-column column-count scaling is only a rough proxy, exactly as in
the existing storage note. A larger independently retained sample or one
completed campaign artifact must replace it before using a new capacity plan.

The current free-space snapshot is volatile and is recorded in
`capacity-snapshot.txt`; it measured 33,119,848 KiB (31.6 GiB) at
`2026-09-21T00:56:16Z`. This reinforces the existing stop-before-floor rule;
it is not a reason to delete or silently recompress evidence.

## Recommendation and limits

For the campaign as currently implemented, keep the reviewed FIFO-to-gzip
path and do not change the host or checker based on this preflight. If storage
remains the blocker, the standard lossless path worth prototyping is:

1. have ngspice write its native binary raw plot containing the complete
   simulator-owned vector set;
2. stream that file through a standard compressor (zstd for speed, xz for
   smaller archival output, or gzip where existing tooling is required); and
3. add a reviewed native-raw reader that proves header/order/vector coverage
   before replacing TSV export.

The tiny probe proves the native container and exact f64/compressor round-trip;
it does not prove campaign integration, fault marker coverage, FIFO behavior,
or checker compatibility. Until those are measured, adopting native raw is a
proposal only. The bounded sample does establish that compressor choice alone
cannot close the projected storage gap safely, while a native binary path could
provide a material alternative without dropping rows or precision.
