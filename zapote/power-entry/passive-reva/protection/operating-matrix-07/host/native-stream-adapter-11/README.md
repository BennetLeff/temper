# Native raw streaming adapter candidate (bounded probe only)

This directory is a production-candidate design probe. It does not change the
campaign host, checker, retained traces, or live source, and it does not run a
full simulation. The adapter reads one ngspice 45.2 real binary raw plot from
stdin and emits the established canonical TSV contract on stdout while keeping
only a bounded header and one row in memory.

## Contract

The invocation is deliberately explicit:

```text
native_stream_adapter --schema normal15|diagnostic31 --byte-order little
```

`--byte-order little` is a required declaration. Native raw is a platform
format, so a campaign receipt must record the writer platform and this byte
order; the adapter does not assume that a future host's native endian format is
portable. If an input header contains `Endian:` or `Byte Order:`, only
`little` is accepted. No `--allow-extra` mode exists: `normal15` requires the
exact 15-vector schema and `diagnostic31` the exact 31-vector schema. A
diagnostic plot cannot be silently truncated into a normal plot.

The parser requires one real plot, unique `Flags`, counts, `Variables`, and
`Binary` sections, a contiguous vector table with unique canonical names,
name-derived `time`/`voltage`/`current` units, and complete row-major little-endian
binary64 payload. Header bytes and vector names are bounded. Payload values are
checked finite; backward timestamps fail, while equal timestamps are retained
in their original order for the existing checker. Exact payload length and
trailing-byte checks fail closed. Values are reordered to these schemas and
printed with `%.17e`:

```text
normal15:     time v(acsrc) v(acn) i(Vac) v(load) v(vb) i(Lboost) v(vd)
              v(sw) v(gate) v(q) v(en) v(fault) v(vcomp) v(icomp)
diagnostic31: normal15 plus v(xu.raw) v(xu.pwm_hold) v(pwm) v(pwm_input)
              v(xdriver.driver_req) v(xdriver.drv_delay) v(xu.phase)
              v(xu.blank) v(isense) v(xu.ov) v(xu.fault) v(xu.pcl_hold)
              v(xu.pcl_request) v(disable) v(xu.m1) v(xu.m2)
```

The implementation is a standalone candidate because the earlier tiny parser
is frozen experiment evidence. It is the maintained candidate for this
contract; no parser framework is introduced. The native writer and campaign
runner still need a reviewed streaming integration.

## Checks run

Both builds pass with warnings denied:

```text
rustc --edition=2021 -D warnings --test native_stream_adapter.rs
rustc --edition=2021 -D warnings native_stream_adapter.rs
8 tests passed
```

The tests cover actual reordered names and values, equal first/interior/last
timestamps with an interior peak preserved, normal15 rejection of diagnostic
extras, unsupported flags/byte order/arguments, truncation and trailing bytes,
duplicate headers/vector tables, non-finite and backward time, bounded
unterminated headers, bad name-derived units, malformed section order, checked
payload-size overflow, and marker splits across small and default-sized reader
chunks.

## Tiny diagnostic31 integration

The existing 1 ms binary raw output was streamed through this adapter and then
through the unchanged normalizer. The adapter and normalizer exited zero. The
unchanged checker intentionally rejected the 1 ms fixture because it covers
fewer than three integer AC cycles; this is a parser/transport result, never an
operating-point or acceptance result:

```text
adapter_rc=0 normalizer_rc=0 checker_rc=1
REJECTED: coverage shorter than 3 integer cycles
```

The adapter output has 5,905 rows plus its header and retains all 31 fields.
The exact output is in `out/diagnostic31.tsv`; `out/run-status.txt` records the
bounded command result.

## Tiny normal15 same-plot proof

`tiny15/` is a copied 1 ms source closure. Its only source change is the
explicit 15-vector `.save`/`wrdata` selection plus `set numdgt=17`; it is not
the live candidate. ngspice produced 5,905 rows and 15 native variables. The
adapter output and the same-plot `wrdata` values were compared as binary64
after accounting for ngspice's interleaved `(time,value)` wrdata columns:

```text
rows=5905 fields=88575 bit_mismatches=0
endpoint_api=1.00000000000000002e-03
endpoint_adapter=1.00000000000000002e-03
```

This is a same-plot `wrdata` comparison, not an independent simulation and not
an `ngGet_Vec_Info` callback proof. The raw writer and adapter are therefore
still a proposal for campaign use; direct callback equivalence and campaign
scale resource/watchdog behavior remain open.

## Files and hashes

```text
native_stream_adapter.rs  8befda55d234c3269dd36367473b54530c12589489eb13c873e689df429395a5
tiny15/cold.cir           7fd87a4c612484ca60889562d10350af0d55e4c6baf51b61d774277e4cbafeef
out/tiny15-comparison.txt d5b7e3e6ef8f2e599d2c7c3b3919e03a294ee274bb0769c1b31e24b40b42a251
```

No full fault case, normal acceptance, protection result, or hardware claim is
made here. Adoption remains gated on source-closure review, exact fault-schema
coverage for any 42-column fault run, direct provenance receipt, direct API
equivalence, host integration, and a campaign-scale bounded-storage test.

Parent update: `../native-api-equivalence-11/parent-review.json` proves the
actual current diagnostic host's wrdata output bit-identical to the native
writer on the tiny plot. That host has no ngGet_Vec_Info export, so a third
export API is not a prerequisite. Production runner integration remains.
