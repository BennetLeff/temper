# Fault native capture 13 (bounded transport probe)

This directory prepares a native binary raw capture path for the existing
fault-specific 42-vector host. It does not alter `faults/tracked-host-09`, the
strict fault checker, the supervisor, or any live source. The 20 us run here is
an actual transport fixture from the already prepared F2-CREST source smoke;
it is not a fault acceptance result, normal qualification, or component-safety
claim.

## Capture host

`deck/progress.rs` is copied from `faults/tracked-host-09/progress.rs`. Its
five-argument CLI, first-invalid snapshot, progress wall limit, and two-save
schema validation remain. The callback now records duplicate timestamps and
continues after the first equal-time snapshot; it records a backward or
non-finite time as a fatal transport condition. The main loop stops only for
non-finite/backward time, solver completion, the existing stall guard, or the
wall limit. This transport policy change is confined to this candidate; the
tracked host is untouched. The remaining host changes are in
`out/progress-diff.patch`:

* metadata declares `ngspice-real-native`, little endian, writer platform,
  `fault42`, 17 checked columns plus four branch/marker extras, and the
  `fault-transport-only-v1` policy; and
* after the existing completion/receipt work, export uses only
  `set filetype=binary` and `write PATH time <validated 41-signal union>`.

The two `.save` lines still provide 31 normal vectors and the exact fault
interface. The ordered union is 42 fields including time; no row slicing,
interpolation, or timestamp editing occurs.

## Native fault42 decoder

`fault_native_adapter.rs` is a local schema extension of the reviewed
`host/native-stream-adapter-11` parser (the frozen source remains unchanged).
It adds the exact 42-name union and accepts `--schema fault42
--byte-order little`. It preserves native row order, maps ngspice's sorted
vector table into the fault host's union order, checks unique names/counts,
finite binary64 values, exact payload/trailing bytes, nondecreasing time, and
bounded headers. The native raw header labels `v(acsrc,acn)` as `notype`; this
one explicitly named differential voltage is accepted as a voltage vector,
while other units remain strict. Equal timestamps are retained for the fault
checker to classify.

## Actual tiny transport run

The copied F2-CREST case (`TSTOP=20 us`, `T_FAULT=10 us`) was run once with the
required ngspice model setup:

```text
SPICE_SCRIPTS=/opt/homebrew/Cellar/ngspice/45.2/share/ngspice/scripts
```

The native host wrote through a FIFO consumed by pigz. The host and reader both
exited zero, reached the exact endpoint, and emitted a 42-variable native raw
plot:

```text
host_rc=0 pigz_rc=0
points=2253 endpoint_s=1.99999999999999982e-05
adapter_rc=0
```

The output is diagnostic transport evidence only. Metadata records
`accepted=false`, `diagnostic_only=true`, `schema=fault42`, the explicit
source/branch schema counts, and the duplicate/backward/non-finite counters.
This tiny case had no invalid timestamps (`duplicate_count=0`,
`backwards_count=0`, `nonfinite_time=false`); the unit fixture separately
proves that an equal timestamp is retained and a backward timestamp is
counted for main-loop stop. It does not assert the fault response is safe or
that the source is an accepted operating point.

## Same-plot text/binary check

A test-only copy of the host (`testonly-progress.rs`) emitted both the native
FIFO and ASCII `wrdata` from the same completed ngspice plot. It is not the
production host and is retained only to verify representation. The reviewed
fault42 decoder output and the ASCII table have:

```text
api_rows=2253 native_rows=2253
api_fields=42 compared_fields=94626
bit_mismatches=0 max_abs_difference=0.0e+00
api_endpoint_s=1.99999999999999982e-05
native_endpoint_s=1.99999999999999982e-05
```

The receipt is `out/test-api-native-comparison.txt`. This proves one tiny plot's
native writer/decoder transport equivalence; it does not prove campaign-scale
storage, startup event selection, protection semantics, or hardware behavior.

## Builds and hashes

```text
rustc --edition=2021 -D warnings --test deck/progress.rs ...  # 5 tests passed
rustc --edition=2021 -D warnings -O deck/progress.rs ...
rustc --edition=2021 -D warnings --test fault_native_adapter.rs ...  # 10 tests passed
rustc --edition=2021 -D warnings -O fault_native_adapter.rs ...
```

The host source SHA is `fd880b8773275a31dbb6b2b050583100192f8b845817e9352ce42f477d2fda1e`;
the fault decoder source SHA is
`57aaea85a978b82395088b3e81434e937e952070bd3d4fab8a251b3c26938bad`; the
same-plot receipt SHA is
`29370bc52549f4160597ea311f5936a2c8b5492685e4ed43a2bbd936736b91ba`.
The copied deck/include hashes and command receipts are recorded under `out/`.

Before adoption, parent review must bind the accepted source closure and fault
case identity, decide the numerical fault-time policy, and retain the full raw
42-column evidence. No strict fault checker or automatic acceptance path is
invoked here.
