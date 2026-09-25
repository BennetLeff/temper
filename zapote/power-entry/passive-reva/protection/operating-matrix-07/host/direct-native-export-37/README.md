# Direct native export candidate 37

This is a bounded copy-avoidance candidate. It forks the reviewed normal12
and fault13 hosts and changes only the post-stop export. The callback, solver,
stop guards, `.save` inventories, CLI shape, and circuit files remain intact.

`native_export.rs` calls `ngGet_Vec_Info` only after the unchanged host has
observed ngspice stopped. It copies pointer/length/type metadata immediately,
checks the external 40-byte `vector_info` ABI oracle, requires real finite
vectors with equal lengths, and then performs one read-only point-major pass
through a 64 KiB `BufWriter`. No ngspice API is called while borrowed pointers
are live. `v(acsrc,acn)` is emitted as the exact per-row subtraction of the two
saved source vectors; the fixed fault inventory is compared to the canonical
42-column order before loading the circuit. Existing regular outputs are never
truncated; an inherited FIFO (including a `/dev/fd/N` symlink to a FIFO) is
opened without truncation and checked after opening.

This remains a copy-avoidance experiment: ngspice still retains its full plot
vectors during simulation. It does not claim fixed-resource simulation or
operating acceptance. The production candidate writes a separate
`native-export-receipt.json` only after the bounded writer flushes successfully;
partial artifacts and write errors are preserved as failures.

## Verification

Warning-clean unit builds and tests:

```text
rustc --edition=2021 -D warnings --test normal.rs ...  # 11 passed
rustc --edition=2021 -D warnings --test fault.rs ...   # 10 passed
```

The tests cover schema widths/units, null/negative/unequal/non-real/event-node
metadata, returned alias checks, ABI offsets, regular-file refusal without
truncation, and the unchanged callback guards. Binaries were built with the
installed ngspice 45.2 dylib:

```text
rustc --edition=2021 -D warnings -O normal.rs -L /opt/homebrew/opt/libngspice/lib -l dylib=ngspice -o direct-normal-worker
rustc --edition=2021 -D warnings -O fault.rs  -L /opt/homebrew/opt/libngspice/lib -l dylib=ngspice -o direct-fault-worker
```

The retained hashes are in `hashes.txt` and `candidate-receipt.json`.

Bounded 20-µs regular-file probes used `SPICE_SCRIPTS=/opt/homebrew/Cellar/ngspice/45.2/share/ngspice/scripts` and produced 316 normal rows / 2,253 fault rows. In separate, independently run processes (not a same-plot proof), the direct and original writers produced identical binary payload bytes after their differing headers:

```text
normal-sameplot/direct.raw   payload 37,920 bytes
normal-sameplot/original.raw payload 37,920 bytes  payload_identical=true
fault-sameplot/direct.raw    payload 757,008 bytes
fault-sameplot/original.raw  payload 757,008 bytes  payload_identical=true
```

The parent owns the required same-process test that runs direct export and the
old writer sequentially from one retained plot; these separate runs are only a
transport/value sanity check and are not acceptance evidence.
