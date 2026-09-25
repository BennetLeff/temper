# Native binary raw export probe (tiny integration only)

This is a bounded integration prototype. It copies the current hysteretic
650 ms source closure into `deck/`, changes exactly one token (`TSTOP=650m` to
`TSTOP=1m`), and runs that copy for 1 ms. It does not modify the live deck,
campaign host, checker, or any retained trace. The 1 ms result is a transport
and representation test, not an operating-point or fault result.

The copied closure is `cold.cir` plus the five include files needed by this
source: `protection.inc`, `standby.inc`, `clamp.inc`,
`ucc28180-pwm-latch.inc`, and `authored_logic_hysteretic.inc`. Their hashes are
in `deck/source-sha256.txt`; only the copied cold deck's TSTOP differs from the
current candidate. The unmodified tracked host source is copied as
`tracked-progress.rs` (SHA-256
`f063aad3972d184853d49d6240419221117f8eba4a69d811dbdd53b89caaf672`) and
compiles with `-D warnings` to `tracked-host`.

## What was changed for this probe

`native-progress.rs` is a local copy of that tracked host with one prototype
extension: after the existing `wrdata` export, it issues these as separate
ngspice commands:

```text
set filetype=binary
write <native-raw-path> all
```

The native path is an owned FIFO. A gzip reader is started before the host, so
the binary writer is tested through a sequential FIFO rather than by writing a
second uncompressed campaign file. The existing TSV `wrdata` path is a second
owned FIFO. Both readers and the host exited zero:

```text
host_rc=0 wrdata_reader_rc=0 raw_reader_rc=0
```

The run used a 10 s host wall limit and completed in 0.50 s. The outer tool
wait was bounded to 20 s. ngspice reported 5,905 rows, 31 saved vectors, and
the exact endpoint `1.00000000000000002e-03 s`. The host still uses the
tracked progress host's ordinary 120 s low-progress watchdog and callback
time counter; this local prototype does not add the hysteretic candidate's
first-invalid diagnostic mask. It is not production-ready and does not alter
the acceptance policy.

## Same-plot comparison

`out/wrdata.tsv.gz` is the existing ngspice `wrdata` text export from the
plot. `out/native.raw.gz` is the native binary `write ... all` export from that
same plot. `out/wrdata-native-comparison.txt` parses the text values as binary64
and maps the native variable table into the TSV order. The result is:

```text
wrdata_header_fields= 31
raw_variables= 31
wrdata_rows= 5905
raw_points= 5905
header_token_sets_equal= True
case_alias_i_Vac_to_i_vac= i(Vac) => i(vac)
wrdata_finite= True
raw_finite= True
wrdata_endpoint_s= 1.00000000000000002e-03
raw_endpoint_s= 1.00000000000000002e-03
row_order_and_count_equal= True
f64_comparisons= 183055
f64_bit_mismatches= 0
max_ulp_difference= 0
max_abs_difference= 0.0
WRDATA_PARSED_F64_BIT_IDENTICAL_TO_NATIVE= True
```

The native raw header sorts names differently from the `.save` line, so the
comparison uses a case-insensitive name map. This explicitly accounts for
ngspice's `i(Vac)`/`i(vac)` spelling. The adapter emits the canonical existing
TSV header/order. This is a comparison of two exports from one plot, not two
independently simulated runs.

The retained sizes are 962,447 bytes for compressed TSV, 668,014 bytes for
compressed native raw, and 1,465,347 bytes for the temporary uncompressed
native raw used by the tiny adapter. The native raw is 31 variables × 5,905
points × 8 bytes plus its ASCII header; gzip byte-roundtrip is checked by the
FIFO reader and adapter receipts.

## Minimal native-to-TSV adapter

`native_to_tsv.rs` is a small standalone Rust adapter for this probe. It is
not a general raw-file framework and currently loads the bounded input into
memory; that makes it unsuitable for campaign-scale files. It accepts only:

* one `Flags: real` header, one `No. Variables`, one `No. Points`, one
  `Variables` table, and one `Binary` marker;
* exactly the 31 expected real vectors, with unique names and supported
  `time`/`voltage`/`current` types;
* complete row-major little-endian f64 payload with finite values; and
* non-decreasing time. Backward time is rejected, while equal-time rows are
  preserved for the existing strict checker to judge.

It reorders ngspice's sorted names into the established TSV contract and does
not interpolate or deduplicate rows. `native_to_tsv_tests` has nine tests,
including a real reordered-name/value fixture, equal-time preservation,
backward/non-finite values, duplicate headers/vectors, malformed vector tables,
invalid units, complex flags, renamed/missing vectors, and truncated payloads.
All pass with `rustc --edition=2021 -D warnings`.

The actual binary was adapted to `out/native-adapted.tsv.gz`; its numeric
values match the `wrdata` export after parsing. The native adapter itself is a
prototype only and has not been wired into the campaign checker.

## Malformed-input evidence

`out/malformed-results.txt` records the expected non-zero failures:

```text
truncated_rc=1    truncated or trailing binary payload
renamed_rc=1      unexpected vector (missing/extra contract mismatch)
duplicate_rc=1    duplicate vector name
complex_rc=1      only Flags: real is supported
```

The source-level negative tests additionally reject duplicate header keys,
non-contiguous variable indices, unsupported vector units, non-finite values,
and backward time.

## Limits and decision boundary

The native writer's standard raw container and exact f64 payload are proven on
this 1 ms plot, including a binary FIFO write and standard gzip reader. The
probe does not prove that every future fault-added vector will be present in a
native plot, that a native raw stream can be consumed with bounded memory, or
that checker provenance/acceptance semantics are preserved in a replacement
runner. It also does not prove startup, normal operation, protection, or
hardware behavior. Adoption requires a reviewed streaming adapter, explicit
vector-coverage receipt for the fault schema, and a campaign-scale storage
measurement. Until then, retain the existing reviewed TSV/gzip path and treat
this native binary route as a proposal.

Parent update: `../native-api-equivalence-11/parent-review.json` proves the
actual current diagnostic host's wrdata output bit-identical to the native
writer on the tiny plot. That host has no ngGet_Vec_Info export, so a third
export API is not a prerequisite. Production runner integration remains.
