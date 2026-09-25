# Export resource diagnosis (bounded, read-only)

Date: 2026-09-21  
Status: diagnosis only; no rerun, output mutation, or acceptance decision.

## Observations

The parent run reported two resource failures: F2-CREST (session 44256) reached
about 0.662 s and 32,237,324 callbacks before its export stopped at 3,458,089,930 bytes (about3.22GiB), while LL08 (session 50666) stopped near 0.383 s with an approximately
10-byte raw artifact. After the processes were gone, the host reported about
18 GiB free disk and `sysctl vm.swapusage` reported 18,432 MiB total swap with
16,761.94 MiB used. These are observations from the runs, not proof that one
particular resource limit caused either stop. In particular, the compressed
3.22-GiB prefix is not evidence of the expected final size.

## What the hosts retain

Both native hosts run `bg_run`, receive scalar callback values, and then issue
`set filetype=binary` followed by `write ...` after the solver stops:

* [`faults/native-capture-13/deck/progress.rs`](/private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/operating-matrix-07/faults/native-capture-13/deck/progress.rs:269)
  loads the run and writes the ordered normal-plus-fault signal union at
  lines 309--310. `fault_export_signals` validates a 31-entry normal inventory
  and an exact 21-entry fault inventory, then deduplicates them to 41 non-time
  vectors at lines 77--122. The native payload therefore contains the time
  vector plus those 41 vectors (42 real doubles per row).
* [`host/normal-native-host-12/deck/progress.rs`](/private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/operating-matrix-07/host/normal-native-host-12/deck/progress.rs:237)
  uses the same post-run `write` path at lines 277--278, with the 15-vector
  `NORMAL_SIGNALS` list at line 46. Its callbacks at lines 105--184 are scalar
  diagnostics; they are not a full-trace side channel.

The local ngspice 45.2 source confirms the memory behavior:

1. `OUTpD_memory` appends every accepted point to each plot vector
   ([`src/frontend/outitf.c`](/private/tmp/ngspice-45.2-src/src/frontend/outitf.c:558-610)).
   `AddRealValueToVector` grows a `double` array as needed
   ([`outitf.c`](/private/tmp/ngspice-45.2-src/src/frontend/outitf.c:1234-1255));
   `dvec_extend` uses `TREALLOC` ([`src/frontend/dvec.c`](/private/tmp/ngspice-45.2-src/src/frontend/dvec.c:137-157)).
   Thus the shared hosts already retain the complete selected vectors in
   simulator memory before export.
2. The `write` command shallow-copies the plot, then calls `vec_copy` for each
   selected vector and any required scale vectors before `raw_write`
   ([`src/frontend/postcoms.c`](/private/tmp/ngspice-45.2-src/src/frontend/postcoms.c:514-585)).
   The copied vectors are freed only after `raw_write` returns
   ([`postcoms.c`](/private/tmp/ngspice-45.2-src/src/frontend/postcoms.c:587-592)).
   Therefore export temporarily holds the simulator's full arrays and a second
   full copy, in addition to solver and allocator state.
3. The binary writer emits an ASCII header, a variable table, then point-major
   `double` values ([`src/frontend/rawfile.c`](/private/tmp/ngspice-45.2-src/src/frontend/rawfile.c:90-122),
   lines 150--160, and lines 223--230). The scale is moved to the first vector
   and current/vector names are normalized in the header at lines 162--189.
4. `ngGet_Vec_Info` does not make a copy. It returns aliases to
   `v_realdata`/`v_compdata` and the current length
   ([`src/sharedspice.c`](/private/tmp/ngspice-45.2-src/src/sharedspice.c:1184-1231)).
   Those pointers belong to ngspice and are only safe while the plot and its
   allocations remain alive. `sh_ExecutePerLoop` sends one latest scalar per
   vector to the callback ([`sharedspice.c`](/private/tmp/ngspice-45.2-src/src/sharedspice.c:2254-2288));
   it is not a zero-copy file stream.

## Defensible resource envelope

These are payload sizes computed from row counts and schema widths. They are
not upper bounds on process memory or measurements of peak RSS:

| case | rows observed | native columns | payload doubles | payload bytes (decimal) | payload GiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| F2-CREST observation | 32,237,324 | 42 | 1,353,967,608 | 10,831,740,864 | 10.09 |
| representative 15-column normal at 30.8M rows | 30,800,000 | 15 | 462,000,000 | 3,696,000,000 | 3.44 |

The first row's payload count is `32,237,324 × 42 × 8 = 10,831,740,864`
bytes. A 15-column run at 30.8M rows is about 3.70 GB (3.44 GiB). The normal LL08 observation stopped
before a complete endpoint, so its eventual size cannot be inferred from the
0.383-s/10-byte report.

The fault export alone copies approximately10.09GiB of selected row data,
in addition to the simulator's retained vectors. The retained inventory also
includes separate source nodes used to derive the differential source value.
Expression evaluation, allocated vector capacity, solver state and allocator
behavior add memory. Three times the payload is an unmeasured heuristic, not
a defensible upper bound, and must not be used as a launch guarantee.

The normal host retains its31-field saved inventory while exporting15fields.
At30.8million rows,31 retained plus15 export copies account for about
11.33GB decimal (10.56GiB) before capacity slack, expression temporaries and
solver state. Estimating normal memory as two or three15-field payloads
understates that retained inventory. The source's `vlength2delta` estimates
future allocation from elapsed simulation time or doubles early capacity;
allocated capacity can exceed used rows.

The immediate stop cause is established: both supervisors reported their
10GiB disk guard and terminated owned children. What consumed the transient
free space is not fully measured. Post-abort swap usage supports a resource
pressure hypothesis; swap grows dynamically, so its current total is not a
fixed capacity ceiling. Available disk recovered after processes exited.
No sampled pre/export RSS-and-swap timeline exists for a causal attribution.

A FIFO avoids an uncompressed output file but does not avoid these in-memory
copies or swap backing. Direct borrowed-vector export should remove the large
post-run copy; it will still retain simulator arrays. Before a full retry,
verify exact payload equivalence on a bounded real probe and record resource
use through solve and export. Run at most one full solver during that first
resource-measured retry. No circuit, timestep, checker or signal reduction is
needed to investigate this narrower remedy.

## Can `ngGet_Vec_Info` make this fixed-resource?

It can avoid the *second* `vec_copy` allocation, but it cannot make the
current hosts bounded: the simulator has already accumulated all vectors via
`OUTpD_memory`. A custom post-stop writer could obtain each borrowed vector,
write the exact header/variable order and point-major doubles, and then avoid
the duplicate plot copy. To preserve the current native42/normal15 bytes it
must reproduce the raw writer's scale-first ordering, current-name rules,
point count, padding, little-endian doubles, and header fields. It must read
the aliases before `ngSpice_Reset`/plot destruction and must not hold them
across any reallocation. This is a copy-avoidance change, not a streaming
capture.

The fixed-resource option is a true row stream: configure ngspice's batch
`run->writeOut` path (which allocates only a row buffer; see
[`outitf.c`](/private/tmp/ngspice-45.2-src/src/frontend/outitf.c:613-650) and
`fileInit_pass2`), or add a reviewed callback writer that emits one complete
row to a bounded FIFO/file while the callback receives it. A `.save none`
shared-module mode exists (`outitf.c` lines 234--243, 1191--1198, and
1234--1244) and keeps vector length at one, but using it would require an
explicit, tested native-row writer; it is not equivalent to the present
post-run `write` and must not be enabled by changing a deck silently. A fully streamed alternative would require the following additional work:

1. retain the exact signal inventory and native header contract;
2. choose batch/row streaming or a callback writer before starting the run;
3. enforce a disk reservation (at least the compressed-output budget plus a
   large reserve) and kill/reap the producer/exporter on breach;
4. measure the proposed export path before another full campaign retry;
   preserve the existing exporter as a short-probe equivalence reference.

This diagnosis does not change any circuit, host, checker, or receipt and does
not claim operating-matrix acceptance.
