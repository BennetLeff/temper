# Digital construction acceptance

Standalone voltage sensing is placed, routed and source-bound. Integration, fabrication approval and physical acceptance are separate unfinished milestones.

| Check | Result |
|---|---|
| Atopile 0.2.69 | Successful source-build-04, strict compiled export |
| Component / pin census | 17 components, 42 pins; 11 connected nets plus unused VBIAS singleton |
| Source → schematic oracle | PASS, all 42 pin assignments |
| KiCad 10.0.4 ERC | 0 findings in each of 3 final runs |
| DRC / unconnected / schematic parity | 0 / 0 / 0 in each of 3 final runs |
| Rust voltage checks | No fail findings; overall INDETERMINATE by design |
| Rust workspace | 135 tests pass, including 15 voltage and 4 common board CLI tests |
| Rust lint | Workspace strict Clippy passes |
| Existing Python transport tests | 5 pass |
| Native schematic and 3D visual review | Completed; J1 body model missing, no full mechanical interference qualification |
| Hardware | NOT RUN; nothing purchased, fabricated or energized |

The current source, candidate, validator code and reports are bound by `evidence/final-manifest.json`. Historical receipts describe their own bytes, not the final candidate. Earlier RTD/current-sense acceptance statements retain their original evidence scope; changing shared validator source does not retroactively recertify those physical units.

Review identified an ambiguous CLI acceptance contract. Resolved by documenting and command-testing strict nonzero exit for INDETERMINATE, while retaining the separate zero-hard-findings digital milestone. No physical gap was converted into PASS.

Remaining: qualify the 250 V envelope, receiver acquisition/load, comparator limits/internal hysteresis, power-off/brownout and surge/fault behavior; reconcile common return with the cooker architecture; verify real connector/mechanical assembly and insulation; validate end-to-end shutdown timing. These are recorded obligations for integration/physical work, not claims of completed tests.
