# Rev38 candidate acceptance ledger

**Status: engineering candidate, overall OPEN (2026-09-24).** This ledger is
the current digital evidence index for the selected HOT receiver and existing
cooker ESP architecture. The source connector contract passed, but there is
no Rev38 native board, no native cooker mate board, and no assembled harness.
No numerical fault response, protected operation, or mains build is approved.

## Evidence identity

| Item | Frozen identity or current candidate byte hash |
| --- | --- |
| Git milestone | `6de13975a65a86ac7c711bf520f6c4b16faa3188` |
| Rev38 295-reference build receipt | SHA-256 `9433de53a1dd1c8dba86d2df6a47d96fc54e413702979518997c43f5591af911` |
| Cooker mate 189-reference build receipt | SHA-256 `3d597b1de0dd8884047ee441a21b0d55ceb2f6bd84847e7a576a6576181f4429` |
| Two-source artifact lock | SHA-256 `9a1baeba595e2fb7fa18b88e4af1436567d7ca350263ac6fe8ed0c01ea987f03` |
| Rust pin audit | `audit.rs` SHA-256 `d7768d6c75ccd4741c6d3c62cc4c084810107d591bdf06c9ad192d2feb7b684a` |
| Reference model and protocol tests | `model.rs` SHA-256 `86165afe2bd2c80cb353aa9fdb3993d89ed9597257fe6416d8ef48d80043a567`; `protocol-tests.rs` SHA-256 `6b4e8456092fe226e649ad37eddb2ed8e424acd7327a7b162e69b67de08db49a` |
| ESP source adapter | `firmware/main/power_entry_authorization.c` SHA-256 `9241602d8f193ae10a1f1fc4fc87369de6a08116b8804466910194f44d03bc50`; header SHA-256 `62e936dec957a3ae5e7bc55e1c6b9e48b06620cb26cf5d3adab8e57c0faab274` |
| Native board, production runtime and physical capture | **No accepted artifact or hash** |
| Cooker native readiness diagnostic | `cooker-mate/evidence/native-readiness-01.json` SHA-256 `65d1c05a769cbd413216b0aa32c8c2f9600a4028824edc71dfcb2917eac72cef`; static probe only |

Each build receipt lists every copied Atopile source hash and its resolved
export hash. The [two-board source record](COOKER-ASSEMBLY-SOURCE.md) links
the actual netlist/BOM bytes; `tools/check_assembly_source.py` verifies the
receipts, source copies, adapters, exports and netlist/BOM lock before running
the Rust pin audit. Tool versions used for this local gate: Atopile **0.2.69**
(receipt build), `rustc 1.92.0`. `kicad-cli 10.0.4` is available but has no
Rev38 board to check. Re-run the gates and update hashes if any listed input
changes; the Git milestone is provenance, not a claim that every later file
shares its commit.

## Requirement trace

| Requirement | Implemented candidate and current digital evidence | Acceptance gap |
| --- | --- | --- |
| R1–R3 | `power_entry_integrated_38.ato`, `audit.rs`, `model.rs`, `protocol-tests.rs`: retained HOT session/RUN clears, physical abort and PERMIT handling. | Physical clear polarity, capture and response time OPEN. |
| R4 | Separate source physical PERMIT readback and seen memory in source authority, Rust model and source adapter. | Cooker pin and reset behavior OPEN. |
| R5 | Local UCC27624 enable inhibit and HOT rail interlocks in joined source and audit. | Partial-power corner and native copper/voltage checks OPEN. |
| R6–R9 | AVR64DA32 receiver parser, durable counter, fixed deadlines, preparation cancellation and one-use START in receiver firmware and model tests. | Programmed fuse/readback, target clock, pin timing and physical latch action OPEN. |
| R10–R11 | Selected bounded-reset behavior in `response-contract.md`, source/receiver host tests and watchdog/START timing ledger. | Production ESP target image, watchdog physical period and reset-to-off inequality OPEN. |
| R12 | `fault-response.tsv`, `timing-analysis.md`, `bench-capture.md` identify producers, clear paths, missing hazard and implementation terms. | Independent numeric allowable/implementation bounds and measured margins OPEN. |
| R13 | Joined Rev38 source and frozen cooker source pass exact 16-contact connector audit with negative mutations; protocol and physical feedback are separate nets. | Native source/board parity, isolation layout and fault captures OPEN. |

The five acceptance examples AE1–AE5 have logical scenarios in the Rust
model/protocol and firmware host suites, and corresponding future physical
nodes in `bench-capture.md`. Their **assembled fault-injection evidence is
NOT RUN**. In particular, AE5's first-START reset allowance is only a bounded
behavioral candidate; it is not a second watchdog deadline or a measured
current-cessation result.

## Gate results and remaining work

| Gate | Current result | Scope |
| --- | --- | --- |
| Frozen two-source build and assembly audit | **PASS** | 295 Rev38 refs, 189 cooker refs, one ESP on cooker source, none on Rev38; receipt hashes and straight-through 16 contacts checked. |
| Rust pin audit mutation suite | **PASS: 142/142** | Includes swapped UART contacts, open return, extra STOP driver and wrong Rev38 protocol-isolator identity. |
| Import-boundary and derived-artifact checks | **PASS** | `scripts/import_linter_gate.py`: 5 kept, 0 broken; `scripts/regen_derived.py --check`: consistent. |
| Receiver device qualification | **OPEN** | Host and target compilation do not prove programmed fuses, reset, clock or watchdog on silicon. |
| ESP production integration | **OPEN** | Diagnostic lockout target image is not a production image; cooker hooks and target timing/pin captures remain unresolved. |
| F1/F2, AUX, cooker SELV rail and thermal/fault envelopes | **OPEN** | See `F1-SCREEN.md`, `F2-BOARD-INTERFACE.md`, `AUX-SOURCE-CANDIDATE.md`, `SELV-SUPPLY-LOAD.md`. |
| Native schematic/PCB, ERC/DRC, stackup, source/native parity and maintained unit gate | **NOT RUN for Rev38** | No accepted native board bytes; canonical `pcb/temper.kicad_pcb` remains outside this candidate. |
| Cooker source/footprint readiness | **OPEN** | Static probe finds two unresolved canonical F1/NTC footprints, missing ESP ground pads 40/41 in the source/land pattern, no reviewed poses/outline, and a stale strict-bridge extension. |
| Low-voltage assembled injection, fault-to-current cessation, mains safety and passive protection/cooling milestone | **NOT RUN / OPEN** | Require a joined physical design and separately accepted measurements. |

The next digital release gate is a reviewed native Rev38 board plus cooker
mate and cable contract with exact parts, poses, outline, and source/native
parity. The F2 terminal drill/pin record and the cooker ESP package ground
pin mapping currently prevent treating a generated layout as accepted.
