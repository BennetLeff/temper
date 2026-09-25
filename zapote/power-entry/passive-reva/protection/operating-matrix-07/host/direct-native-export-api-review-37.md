# Direct native export API safety review (ngspice 45.2)

This is a read-only API audit for a possible borrowed-vector exporter. It does
not implement or enable an exporter, run ngspice, inspect a campaign trace, or
change a source/checker. The installed ABI was checked against the local
ngspice 45.2 source at `/private/tmp/ngspice-45.2-src` and the installed header
at `/opt/homebrew/Cellar/libngspice/45.2/include/ngspice/sharedspice.h`.

## What the API actually returns

The public header defines `vector_info` at `sharedspice.h:173-183`:

```c
char *v_name;
int v_type;
short v_flags;
double *v_realdata;
ngcomplex_t *v_compdata;
int v_length;
```

There are no ownership handles, capacity fields, scale pointers, dimensions,
or endian metadata in this structure. `NG_BOOL` is a C `_Bool` at the library
boundary (and `bool` when the external header is used), but no bool occurs in
`vector_info`; do not substitute the `vecvalues` layout, whose two bool fields
are a different ABI. On this aarch64 host the expected C layout is 40 bytes
with offsets 0, 8, 12, 16, 24, and 32; a direct Rust declaration must use
`#[repr(C)]`, `*mut c_char`, `c_int`, `c_short`, and pointers in exactly this
order. A compile-time layout test against the C header is required before
using a Rust FFI struct.

`ngGet_Vec_Info` is declared at `sharedspice.h:400-407`. The implementation at
`src/sharedspice.c:1184-1232` is more restrictive than the header suggests:

* it resolves the name with `vec_get`, returns null before initialization or
  when the vector is absent, and rejects `v_numdims > 1`;
* it copies only metadata and pointers into one process-global `static
  pvector_info myvec`; every call overwrites that same metadata object;
* `v_name`, `v_realdata`, and `v_compdata` remain aliases to ngspice's `dvec`,
  not caller-owned copies;
* with XSPICE enabled, the beginning of a later call frees the previously
  returned event-derived vector and its scale (`sharedspice.c:1198-1204`).

The exporter must copy the six scalar fields from each result immediately and
must never retain the returned `pvector_info` itself. It must read every data
pointer before `ngSpice_Reset`, plot destruction, another allocation, or a
later event-vector lookup. `ngSpice_LockRealloc` is documented in
`sharedspice.h:102-106`; its implementation locks only vector reallocations
(`sharedspice.c:1446-1458`). It does not make a reset, garbage collection, or
event-vector free safe. The production exporter should therefore run only
after `ngSpice_running()` is false and the stopped callback has been observed,
with exclusive ownership of all ngspice API calls. It must issue no mutating
command until the read is complete. A realloc lock can be additional protection,
but it cannot prevent reset or event-vector frees and is not the lifetime proof.

`vec_get` is case-insensitive through the plot lookup table
(`src/frontend/vectors.c:177-207`) and maps `i(node)`/`I(node)` to an internal
`node#branch` name (`vectors.c:522-555`). A caller must use exact, predeclared
names and validate the returned `v_name`/`v_type`; it must not infer the native
header name from the request string. A `v_link2` lookup can create and insert a
temporary copied vector (`vectors.c:220-223`, `vec_new` at `vectors.c:918-954`),
so wildcard names (`all`, `allv`, etc.) are forbidden. `ngSpice_AllVecs` is not
a substitute for ownership: if used only for a duplicate-name audit, copy its
null-terminated names immediately and treat the returned array as borrowed.

The source flags are in `src/include/ngspice/dvec.h:11-22`: `VF_REAL=1`,
`VF_COMPLEX=2`, and `VF_EVENT_NODE=256` (among other flags). The corresponding
simulation types are in `src/include/ngspice/sim.h:4-27`: `SV_TIME=1`,
`SV_VOLTAGE=3`, and `SV_CURRENT=4`. For this normal15/fault42 contract, every
selected vector must have exactly one of `VF_REAL` or `VF_COMPLEX`, must be
real, finite, one-dimensional, and have the expected type: `time` is
`SV_TIME`, `v(...)` is `SV_VOLTAGE`, and `i(...)` is `SV_CURRENT`. Reject
event-node vectors and complex data rather than reading the wrong union member.

## Why a direct writer is not automatically raw-file equivalent

The existing `write` path makes a second full copy. `postcoms.c:527-548` calls
`vec_copy` for each selected vector; if the default scale is absent it copies
that scale too (`postcoms.c:551-578`), then calls `raw_write` and frees those
copies only afterward (`postcoms.c:585-592`). This explains the resource
pressure, but bypassing this copy creates a byte-contract obligation.

`raw_write` first moves the plot scale to the first vector
(`src/frontend/rawfile.c:150-160`). It writes the current/vector names using
`v_type`, stripping `#branch` and emitting `i(name)` for currents or `v(name)`
for voltages (`rawfile.c:162-189`). It emits `Flags: real` or `complex`, and
optionally `unpadded`; binary values are point-major doubles in linked-vector
order (`rawfile.c:223-258`). Each `fwrite` writes the host representation
directly. The header has no endian marker, so the candidate must be compiled
and run only on little-endian targets, record the writer platform, and reject
other targets. `raw_padding` defaults on (`rawfile.c:43-59`); unequal vector
lengths silently acquire zero rows (`rawfile.c:247-255`). A strict direct
writer should instead reject any selected vector whose `v_length` differs from
the time length, because the campaign decoder requires a rectangular exact
schema and no hidden padding.

The public `vector_info` does not expose `v_scale`, `v_numdims`, `v_dims`,
`v_alloc_length`, or the plot list. Thus it cannot reproduce raw-write's
additional non-default per-vector scale handling (`postcoms.c:560-578`) in the
general case. The candidate must either prove the target transient plot has
one shared time scale for every selected vector, or reject the plot. It must
not silently claim native equivalence from equal lengths alone.

The current host's 15-vector list is `time`, `v(acsrc)`, `v(acn)`, `i(Vac)`,
`v(load)`, `v(vb)`, `i(Lboost)`, `v(vd)`, `v(sw)`, `v(gate)`, `v(q)`, `v(en)`,
`v(fault)`, `v(vcomp)`, and `v(icomp)`. The differential value
`v(acsrc,acn)` is not in that list: it must be derived as the exact binary64
subtraction `v(acsrc)[row] - v(acn)[row]` from the same borrowed plot, or the
deck must explicitly save and expose an expression vector. A nominally named
`v(acsrc,acn)` lookup must not be assumed to exist. For fault42, the same rule
applies to any added differential column; prove the expression source and
column mapping rather than comparing against a separately simulated plot.

## Rejection and equivalence checks

These are review concerns for the candidate. Generic arbitrary-plot support is
not required: the host can be restricted to its frozen analog transient sources,
fixed signal inventory and sole API-owning thread. Unsupported event, complex,
modified-scale or wildcard paths must not enter that supported contract.
Concrete fixture and source proofs should cover the applicable boundaries:

1. `ngGet_Vec_Info` before `ngSpice_Init`, after reset, a missing exact name,
   and an unsupported wildcard returns null/error with no output artifact.
2. Each selected vector is checked for canonical returned name, expected
   `v_type`, exactly one real/complex flag, non-null `v_realdata`, null
   `v_compdata` for real data, finite values, positive `v_length`, equal length,
   one dimension, and no event-node flag. Include an intentionally complex
   vector, a multidimensional vector, a NaN/Inf, and a length mismatch.
3. Call the API for every vector and retain only copied scalar metadata; a test
   must demonstrate that a later call changes the shared `myvec` object while
   previously copied data pointers remain valid until the plot is torn down.
   An XSPICE event-vector lookup followed by another lookup must be rejected or
   completed before the next call; it must never read the first pointer after
   the second call.
4. Exercise `i(Vac)`, `I(Vac)`, internal `Vac#branch`, and the emitted canonical
   `i(Vac)` name. Reject duplicate canonical names from the plot inventory.
   Verify that direct output does not accidentally emit `Vac#branch` or merge
   a voltage and current with the same spelling.
5. Verify the host requires `ngSpice_running()==false` plus its stopped callback,
   and that its sole API-owning thread cannot call reset/teardown or a mutating
   command while borrowed arrays are read. Do not claim a realloc lock blocks
   reset. A watchdog or compressor error must leave a failed receipt, never a
   partially accepted native file.
6. Compare one complete tiny same-plot run against the existing native `write`
   output. Parse both headers and compare: variable count/order, normalized
   names, type/unit strings, real/complex flag, point count, endpoint, and every
   payload `f64::to_bits()` value in point-major order. Include `+0.0`, `-0.0`,
   subnormal finite values, duplicate timestamps, and a nonzero expression
   `v(acsrc)-v(acn)`; do not compare independently simulated plots. The direct
   writer's header may differ in title/date, but all schema and payload fields
   must match after that explicit normalization.
7. Verify that all vectors are equal length and use the shared transient scale;
   create a non-default-scale or shortened-vector fixture and require a clear
   rejection. Test a `nopadding`/padding mismatch so a future option cannot
   silently turn missing rows into zeros.
8. Run the tiny equivalence test on the same little-endian host with the exact
   libngspice 45.2 dylib and record the library path/hash, compiler, target
   endian, and source/deck hashes. A parser-only synthetic fixture is not an
   API equivalence result.

These tests establish safe borrowing and payload equivalence for a bounded
fixture. They do not establish that the simulator's retained vectors are
memory-bounded: `OUTpD_memory` appends every accepted point
(`src/frontend/outitf.c:558-610`), and direct export only removes the extra
post-run `vec_copy` allocation. The current campaign remains dependency-gated
on this real-payload proof and a resource-measured single retry.

## Parent verification

The installed-header C layout oracle (`vector-info-abi-oracle-37.c/.json`)
compiled and ran: size40, alignment8, offsets0/8/12/16/24/32. The actual prior
host links `/opt/homebrew/opt/libngspice/lib/libngspice.0.dylib`.
`src/maths/cmaths/cmath2.c:620–632` implements real differential subtraction
as `dd1[i] - dd2[i]`, supporting the proposed per-row derived column.
`outitf.c:1143` constructs ordinary retained vectors for this transient plot;
`OUTpD_memory` appends each regular output at the same accepted time. The final
implementation still requires same-plot payload comparison and source review.
