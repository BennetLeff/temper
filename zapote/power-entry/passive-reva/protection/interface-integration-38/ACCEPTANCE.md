# Rev38 candidate acceptance ledger

**Status: engineering candidate, overall OPEN (2026-09-24).** This ledger is
the current digital evidence index for the selected HOT receiver and existing
cooker ESP command-source architecture. The source connector contract passed,
but there is no Rev38 native section board or assembled SELV harness.
No numerical fault response, protected operation, or mains build is approved.

## Evidence identity

| Item | Frozen identity or current candidate byte hash |
| --- | --- |
| Git milestone | `6de13975a65a86ac7c711bf520f6c4b16faa3188` |
| Rev38 295-reference build receipt | `source-build-04` SHA-256 `ecd434f9e896cae47cadd73f955235d1c254030c46d6887461b6986b423a68cf` |
| Cooker mate 189-reference build receipt | `cooker-source-02` SHA-256 `21d303f769dccaaaf25049e87cd948d55de8ab19be478c9aab277f535d45baa4` |
| Two-source artifact lock | SHA-256 `72c3d6252567b0a0ab1c3c8353c6e878a9dfc029f032529a934f9b4b754ade8c` |
| Rust pin audit | `audit.rs` SHA-256 `1e6b0ae3edc257f7a12fc82614be38a1e809cad6d1c9e359360932c8f60c5a8f` |
| AVR64DA32 target and profiles | `receiver-firmware/avr64da32_target.c` SHA-256 `0e8e4240bb2398c5caa02fb6d7d66b3582edb104b39c25e885eafc4f1594f758`; `avr64da32.mk` SHA-256 `32e391a3871c95f97886d719e29975fdddebf9d3572b0ed8ba5e1f153b7603ef`; locked ELF `4e5f8cdc72b749e41dd348de25343a01dcb833825e81b3586eeb9f60da916596`; engineering ELF `f7b13f821114a661ef2a83b50cab1c896e63a8f46030022626fa13113e1925bf` (temporary local files, Microchip AVR toolchain 4.0.0.52) |
| Reference model and protocol tests | `model.rs` SHA-256 `86165afe2bd2c80cb353aa9fdb3993d89ed9597257fe6416d8ef48d80043a567`; `protocol-tests.rs` SHA-256 `6b4e8456092fe226e649ad37eddb2ed8e424acd7327a7b162e69b67de08db49a` |
| ESP source adapter | `firmware/main/power_entry_authorization.c` SHA-256 `9241602d8f193ae10a1f1fc4fc87369de6a08116b8804466910194f44d03bc50`; header SHA-256 `62e936dec957a3ae5e7bc55e1c6b9e48b06620cb26cf5d3adab8e57c0faab274` |
| RTD monitor input and cooker temperature | `firmware/components/sensors/rtd_service.c` SHA-256 `ee2b938d75566082798c474b7fb74baedaf11d86e5fe587a1072809142acaf32`; header SHA-256 `4b6fe77c182568587941027c9b821ff3c7f0086a11dd5fdabdf3cea49a5da109`; host test SHA-256 `cf1bd1191baf59aa69f58e580b2b5c65b1e9d66fa8340589f03ac9bfeba14cbf` |
| Cooker control progress and boot ordering | `firmware/main/main.c` SHA-256 `ca1c5433e979885337035bcd37c7ef0ef124f5e19c2b12d27bd252b5ed9afa41`; `state_machine.c` SHA-256 `4692ffeac4decb32aa762b25f4aed440ab32262563d6fa22f338a7e807039288`; `state_handlers.c` SHA-256 `866f5bafd45152a53fd4c3fe83f4f20554154551e94160907af4d76f9666a98b`; `state_machine.h` SHA-256 `717eb58eeed8b9553eb98417ea08ad1966080df228d75afdf7effbe949f05b6a`; host test SHA-256 `233b80ae37e4b15a3d98f2d369164d96537c1c01700e36736f6a03858d9789ed` |
| Diagnostic target link anchor | `firmware/main/diagnostic_lockout_idf.c` SHA-256 `931ebbc4d7a834ed2910791022fc36b680aaa4ee555dc4e1e1835c4d06b2d5e2`; target rebuild still OPEN |
| Heatsink NTC host model | `firmware/components/safety/ntc_guard.c` SHA-256 `60fc13c60b9b0e00eebedb16f04a6d359dde3e73faa42ff72697c9e4e9a8496d`; header SHA-256 `90bda483eb56afe7ca091542a237b857177d20c0ed086c55eda6996ab7132855`; host tests SHA-256 `6ca2e1a709a1ec8749e91b6492955874df610133865e8cf66064f7c41dc69f62` and `968910cacfb8a81ff42e428c6399c044ae0ea29d2fd9f1b518bb02afce1de34d` |
| Native board, production runtime and physical capture | **No accepted artifact or hash** |
| Cooker native readiness diagnostic | `cooker-mate/evidence/native-readiness-02.json` SHA-256 `9d441e0ae16a4ed912ff7420beb38fc2b3a8c5eed39da8589c8814811565e5ef`; static probe only |
| Follow-on cooker power assembly | **Outside this plan's U7 gate**; `docs/superpowers/specs/2026-09-24-rev38-single-bank-cooker-design.md` explores a single-bank half bridge, and `POWER-ASSEMBLY-BOUNDARY.md` records the unjoined product source |

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
| Rust pin audit mutation suite | **PASS: 144/144** | Includes swapped UART contacts, open return, open ESP ground pad 41, extra STOP driver, weak heartbeat pull-down and wrong Rev38 protocol-isolator identity. |
| Import-boundary and derived-artifact checks | **PASS** | `scripts/import_linter_gate.py`: 5 kept, 0 broken; `scripts/regen_derived.py --check`: consistent. |
| RTD sample-age and cooker temperature input | **PASS: 22 focused host tests; 17/17 CTest** | Conversion age, wrap and invalidation; PT100 manufacturer-table values; INIT wait and preserved probe-fault diagnosis. The 100 ms control sample rejection is not an accepted monitor deadline. No monitor epoch or Rev38 authorization is credited. |
| Heatsink NTC host conversion | **PASS: 9 focused host tests; 17/17 CTest** | Matches the selected 100 kΩ/B4190 Vishay part and 10 kΩ top resistor at cold, 25 °C, and 85 °C points; rejects open, short, over-range and implausible rate. ESP ADC transfer/calibration, production read hook, board divider and target behavior remain OPEN. |
| Cooker control progress gate | **PASS: 61 focused state-machine tests; 17/17 CTest** | A completed nonfault handler permits a control epoch; deferred messages and fault ticks do not. The production call site is not target-tested; target timing and monitor freshness remain OPEN. |
| Receiver engineering target profiles | **PASS: two offline AVR64DA32 links** | The locked default and separately named nonzero-window engineering profile build with the official Microchip toolchain. `receiver-firmware/ENGINEERING-WINDOWS.md` states transport arithmetic and unmeasured processing hypotheses. This is target-code evidence, not numerical or device acceptance. |
| Receiver device qualification | **OPEN** | Target compilation does not prove programmed fuses, reset, clock, watchdog, pin levels or deadline behavior on silicon. The candidate windows and installed-device maximums are unaccepted. |
| ESP production integration | **OPEN** | Diagnostic lockout target image is not a production image; cooker hooks and target timing/pin captures remain unresolved. |
| F1/F2, AUX, SELV port and thermal/fault envelopes | **OPEN** | `SELV-PORT-CONTRACT.md` sets candidate board-input limits and a 100 mA Rev38 allocation, not an accepted load maximum or qualified cooker rail. See also `F1-SCREEN.md`, `F2-BOARD-INTERFACE.md`, `AUX-SOURCE-CANDIDATE.md`, `SELV-SUPPLY-LOAD.md`. The 10 kΩ GPIO21 pull-down reduces one typical boot pull-up risk but does not bound WDI feed tail. |
| Native schematic/PCB, ERC/DRC, stackup, source/native parity and maintained unit gate | **NOT RUN for Rev38** | No accepted Rev38 section-board bytes; canonical `pcb/temper.kicad_pcb` remains outside this candidate. `INSULATION-BASIS.md` identifies a 16.0 mm provisional Group IIIa board creepage screen and a separate 12.6 mm Group I package screen; selected ISO774x DW only specifies >8 mm external path. Product standard, voltage envelope and construction are unresolved. |
| Cooker source/footprint readiness | **Follow-on product work** | The frozen derivative proves a proposed controller interface. Its old F1/NTC footprints and product placement do not gate the Rev38 section board. The 3.3 V port supply, load, startup and fail-low contract do gate Rev38 interface acceptance. |
| Low-voltage assembled injection, fault-to-current cessation, mains safety and passive protection/cooling milestone | **NOT RUN / OPEN** | Require a joined physical design and separately accepted measurements. |

The next digital release gate is a reviewed native Rev38 section board with
exact parts, poses, outline, source/native parity, and a defined SELV
controller port. That port has a candidate 3.3 V supply/load/startup/fail-low
contract for the existing cooker ESP command source; qualification remains
open. The F2 terminal drill/pin record
remains open. Cooker inverter power joins and native cooker-board placement
belong to a later product-integration gate.
