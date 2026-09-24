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
| Cooker mate 189-reference build receipt | `cooker-source-02` SHA-256 `21d303f769dccaaaf25049e87cd948d55de8ab19be478c9aab277f535d45baa4` |
| Two-source artifact lock | SHA-256 `0cfcba30db822912aa278214c631ba7eab12d69a80427d9246d7ace227d95512` |
| Rust pin audit | `audit.rs` SHA-256 `bafb1112ee4d6f13a618a7b01c39ebc8f34997e9df078825489b8a7d99ff6ead` |
| Reference model and protocol tests | `model.rs` SHA-256 `86165afe2bd2c80cb353aa9fdb3993d89ed9597257fe6416d8ef48d80043a567`; `protocol-tests.rs` SHA-256 `6b4e8456092fe226e649ad37eddb2ed8e424acd7327a7b162e69b67de08db49a` |
| ESP source adapter | `firmware/main/power_entry_authorization.c` SHA-256 `9241602d8f193ae10a1f1fc4fc87369de6a08116b8804466910194f44d03bc50`; header SHA-256 `62e936dec957a3ae5e7bc55e1c6b9e48b06620cb26cf5d3adab8e57c0faab274` |
| RTD monitor input and cooker temperature | `firmware/components/sensors/rtd_service.c` SHA-256 `ee2b938d75566082798c474b7fb74baedaf11d86e5fe587a1072809142acaf32`; header SHA-256 `4b6fe77c182568587941027c9b821ff3c7f0086a11dd5fdabdf3cea49a5da109`; host test SHA-256 `cf1bd1191baf59aa69f58e580b2b5c65b1e9d66fa8340589f03ac9bfeba14cbf` |
| Cooker control progress and boot ordering | `firmware/main/main.c` SHA-256 `ca1c5433e979885337035bcd37c7ef0ef124f5e19c2b12d27bd252b5ed9afa41`; `state_machine.c` SHA-256 `4692ffeac4decb32aa762b25f4aed440ab32262563d6fa22f338a7e807039288`; `state_handlers.c` SHA-256 `866f5bafd45152a53fd4c3fe83f4f20554154551e94160907af4d76f9666a98b`; `state_machine.h` SHA-256 `717eb58eeed8b9553eb98417ea08ad1966080df228d75afdf7effbe949f05b6a`; host test SHA-256 `233b80ae37e4b15a3d98f2d369164d96537c1c01700e36736f6a03858d9789ed` |
| Diagnostic target link anchor | `firmware/main/diagnostic_lockout_idf.c` SHA-256 `931ebbc4d7a834ed2910791022fc36b680aaa4ee555dc4e1e1835c4d06b2d5e2`; target rebuild still OPEN |
| Native board, production runtime and physical capture | **No accepted artifact or hash** |
| Cooker native readiness diagnostic | `cooker-mate/evidence/native-readiness-02.json` SHA-256 `9d441e0ae16a4ed912ff7420beb38fc2b3a8c5eed39da8589c8814811565e5ef`; static probe only |
| Product power assembly | **OPEN**; `POWER-ASSEMBLY-BOUNDARY.md` records two unjoined front ends and no bank/inverter power contract |

Each build receipt lists every copied Atopile source hash and its resolved
export hash. The [two-board source record](COOKER-ASSEMBLY-SOURCE.md) links
the actual netlist/BOM bytes; `tools/check_assembly_source.py` verifies the
receipts, source copies, build manifests, adapters, exports and netlist/BOM lock before running
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
| Rust pin audit mutation suite | **PASS: 143/143** | Includes swapped UART contacts, open return, open ESP ground pad 41, extra STOP driver and wrong Rev38 protocol-isolator identity. |
| Import-boundary and derived-artifact checks | **PASS** | `scripts/import_linter_gate.py`: 5 kept, 0 broken; `scripts/regen_derived.py --check`: consistent. |
| RTD sample-age and cooker temperature input | **PASS: 22 focused host tests; 17/17 CTest** | Conversion age, wrap and invalidation; PT100 manufacturer-table values; INIT wait and preserved probe-fault diagnosis. The 100 ms control sample rejection is not an accepted monitor deadline. No monitor epoch or Rev38 authorization is credited. |
| Cooker control progress gate | **PASS: 61 focused state-machine tests; 17/17 CTest** | A completed nonfault handler permits a control epoch; deferred messages and fault ticks do not. The production call site is not target-tested; target timing and monitor freshness remain OPEN. |
| Receiver device qualification | **OPEN** | Host and target compilation do not prove programmed fuses, reset, clock or watchdog on silicon. |
| ESP production integration | **OPEN** | Diagnostic lockout target image is not a production image; cooker hooks and target timing/pin captures remain unresolved. |
| F1/F2, AUX, cooker SELV rail and thermal/fault envelopes | **OPEN** | See `F1-SCREEN.md`, `F2-BOARD-INTERFACE.md`, `AUX-SOURCE-CANDIDATE.md`, `SELV-SUPPLY-LOAD.md`. |
| Native schematic/PCB, ERC/DRC, stackup, source/native parity and maintained unit gate | **NOT RUN for Rev38** | No accepted native board bytes or single joined power path; canonical `pcb/temper.kicad_pcb` remains outside this candidate. |
| Cooker source/footprint readiness | **OPEN** | The frozen derivative now joins ESP pads 1/40/41 to SELV return and uses the stock 41-contact footprint. Static probe still finds unresolved canonical F1/NTC footprints, no reviewed poses/outline, and a stale strict-bridge extension. |
| Low-voltage assembled injection, fault-to-current cessation, mains safety and passive protection/cooling milestone | **NOT RUN / OPEN** | Require a joined physical design and separately accepted measurements. |

The next digital release gate is a reviewed native Rev38 board plus cooker
mate and cable contract with exact parts, poses, outline, and source/native
parity. First the two-source assembly must have one evaluated inlet and
explicit SELV rail and inverter power joins. The F2 terminal drill/pin record
and the cooker native package/placement work remain open after that decision.
