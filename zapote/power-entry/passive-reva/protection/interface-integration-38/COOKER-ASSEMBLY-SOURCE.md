# Two-board Rev38 source contract

Status: **digital source and connector audit PASS; native boards and physical
harness NOT RUN**. These are separate PCB sources. The cable is a proposed
straight-through 16-contact assembly, with pad *n* on the existing cooker
board connected only to pad *n* on the Rev38 board. Neither Atopile netlist
contains a physical conductor between the boards.

| Frozen source | Entry | References | ESP32-S3 count | Receipt SHA-256 |
| --- | --- | ---: | ---: | --- |
| `source-build-03` | `PowerEntryIntegrated38` | 295 | 0 | `9433de53a1dd1c8dba86d2df6a47d96fc54e413702979518997c43f5591af911` |
| `cooker-source-01` | `CookerMate38` importing the tracked cooker `Top` | 189 | 1 | `3d597b1de0dd8884047ee441a21b0d55ceb2f6bd84847e7a576a6576181f4429` |

The cooker snapshot's [receipt](cooker-source-01/build-receipt.json) records
the exact canonical cooker and derivative source hashes, pinned Atopile build
result, netlist/BOM and resolved-export hashes. Its freezer copies tracked
`.ato` files only, so unrelated untracked worktree experiments cannot enter
this source identity. The Rev38 [receipt](source-build-03/build-receipt.json)
records its separate source identity. Both compiled netlists and BOMs are
retained with their source snapshots.

Run the receipt-bound, shared exact-pin check from this directory:

```sh
python3 tools/check_assembly_source.py
rustc --edition=2021 --test audit.rs -o /tmp/temper-rev38-audit-tests
/tmp/temper-rev38-audit-tests
```

The wrapper checks the locked receipt bytes, copied source bytes, build
adapters and exported artifacts before compiling and running the Rust audit.
The audit compares every numbered port contact, requires the intended power
and return groupings, checks the exact members of each Rev38 signal net and
the cooker-side producer/consumer, and rejects a second ESP, an extra STOP
driver, a wrong protocol part, a swapped UART contact and an open return in
tests. It checks the *design contract* for a
straight-through cable, not cable continuity, contact heating, isolation,
assembly keying or power-up behavior. The native cooker header, Rev38 native
board, rail budget and cable measurements remain open. The modeled cooker ESP
also has only one GND pad in its source component; physical WROOM-1 ground
pads 40/41 need package review before native acceptance.
