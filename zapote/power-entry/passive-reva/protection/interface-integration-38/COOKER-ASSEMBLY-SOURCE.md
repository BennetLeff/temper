# Two-board Rev38 source contract

Status: **digital source and connector audit PASS; native boards and physical
harness NOT RUN**. These are separate PCB sources. The cable is a proposed
straight-through 16-contact assembly, with pad *n* on the existing cooker
board connected only to pad *n* on the Rev38 board. Neither Atopile netlist
contains a physical conductor between the boards.

| Frozen source | Entry | References | ESP32-S3 count | Receipt SHA-256 |
| --- | --- | ---: | ---: | --- |
| `source-build-05` | `PowerEntryIntegrated38` | 296 | 0 | `4f07f1177fbe39eef940e665892c40285e77925ce4f4622ddbf21cd38672a7f5` |
| `cooker-source-02` | `CookerMate38` importing a frozen derivative of the tracked cooker `Top` | 189 | 1 | `21d303f769dccaaaf25049e87cd948d55de8ab19be478c9aab277f535d45baa4` |

The cooker snapshot's [receipt](cooker-source-02/build-receipt.json) records
the exact staged cooker and derivative source hashes, pinned Atopile build
result, netlist/BOM and resolved-export hashes. Its freezer copies tracked
`.ato` files only, so unrelated untracked worktree experiments cannot enter
this source identity. It then applies a fail-closed derivative override to
connect ESP module GND contacts 40/41 and assign KiCad's stock 41-contact
WROOM-1 footprint; the canonical cooker source and board are untouched.
The previous `cooker-source-01` and Rev38 `source-build-04` snapshots remain
historical. The current Rev38 [receipt](source-build-05/build-receipt.json)
records its separate source identity, including the two F2 board studs and
DWW isolator pair. Both compiled netlists and BOMs are
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
driver, a wrong protocol part, a swapped UART contact, an open return and an
open ESP ground contact in
tests. It checks the *design contract* for a
straight-through cable, not cable continuity, contact heating, isolation,
assembly keying or power-up behavior. The native cooker header, Rev38 native
board, rail budget and cable measurements remain open. The cooker derivative
now models all three WROOM-1 ground contacts; physical solder, thermal pad
and antenna-keepout review remain part of native acceptance.
