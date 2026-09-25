# Rev38 candidate acceptance ledger

**Status: engineering candidate, overall OPEN (2026-09-24).** This ledger is
the current digital evidence index for the selected HOT receiver and existing
cooker ESP command-source architecture. The source connector contract passed,
but there is no accepted Rev38 native section board or assembled SELV harness.
No numerical fault response, protected operation, or mains build is approved.

## Evidence identity

| Item | Frozen identity or current candidate byte hash |
| --- | --- |
| Earlier Git milestone | `6de13975a65a86ac7c711bf520f6c4b16faa3188` |
| Rev38 296-reference build receipt | `source-build-06` SHA-256 `a164f33463b42748eefd4474be5f225077e191eae2378448eccad69b932b3d36` (Atopile 0.2.69, compiled-and-exported) |
| Rev38 compiled netlist and resolved export | `source-build-06/build/default.net` SHA-256 `913a0bf51726cb756af2384aea3ac2c949c405f612b345aedbae7ef4c0d79796`; `source-build-06/resolved-components.json` SHA-256 `b75d376c9cf2eb5a14619d200f89600b6e93c72a963044cd0048f6a8ce1bf3c0` |
| Cooker mate 189-reference build receipt | `cooker-source-02` SHA-256 `21d303f769dccaaaf25049e87cd948d55de8ab19be478c9aab277f535d45baa4` |
| Two-source artifact lock | SHA-256 `e90f2c47e79bad7b92cf620653f4664b8600774647587d7f8db60915f6afab76` |
| Rust pin audit | `audit.rs` SHA-256 `48f207bf1295fc2314ad26d7b56f19567ac91e8f003587cef56522992a22bebc` |
| AVR64DA32 target and profiles | `receiver-firmware/avr64da32_target.c` SHA-256 `0e8e4240bb2398c5caa02fb6d7d66b3582edb104b39c25e885eafc4f1594f758`; `avr64da32.mk` SHA-256 `32e391a3871c95f97886d719e29975fdddebf9d3572b0ed8ba5e1f153b7603ef`; locked ELF `4e5f8cdc72b749e41dd348de25343a01dcb833825e81b3586eeb9f60da916596`; engineering ELF `f7b13f821114a661ef2a83b50cab1c896e63a8f46030022626fa13113e1925bf` (temporary local files, Microchip AVR toolchain 4.0.0.52) |
| Reference model and protocol tests | `model.rs` SHA-256 `86165afe2bd2c80cb353aa9fdb3993d89ed9597257fe6416d8ef48d80043a567`; `protocol-tests.rs` SHA-256 `6b4e8456092fe226e649ad37eddb2ed8e424acd7327a7b162e69b67de08db49a` |
| ESP source adapter | `firmware/main/power_entry_authorization.c` SHA-256 `9241602d8f193ae10a1f1fc4fc87369de6a08116b8804466910194f44d03bc50`; header SHA-256 `62e936dec957a3ae5e7bc55e1c6b9e48b06620cb26cf5d3adab8e57c0faab274` |
| RTD monitor input and cooker temperature | `firmware/components/sensors/rtd_service.c` SHA-256 `ee2b938d75566082798c474b7fb74baedaf11d86e5fe587a1072809142acaf32`; header SHA-256 `4b6fe77c182568587941027c9b821ff3c7f0086a11dd5fdabdf3cea49a5da109`; host test SHA-256 `cf1bd1191baf59aa69f58e580b2b5c65b1e9d66fa8340589f03ac9bfeba14cbf` |
| Cooker control progress and boot ordering | `firmware/main/main.c` SHA-256 `ca1c5433e979885337035bcd37c7ef0ef124f5e19c2b12d27bd252b5ed9afa41`; `state_machine.c` SHA-256 `6a1218edf6adee00cc38bf09739b501262993d6a19c068642d02d4798dd722d2`; `state_handlers.c` SHA-256 `7c71a9d0d0bd7dda4bb303815eb28d330863a78f995068ed3decebe77d99b55d`; `state_machine.h` SHA-256 `717eb58eeed8b9553eb98417ea08ad1966080df228d75afdf7effbe949f05b6a`; `firmware/test/test_state_machine.c` SHA-256 `ef84306cc2c1f619c917cc6d05ad1ecf9dc0ad80b9a0970d5965abe080e02ba4` |
| Cooker board-backed hooks (host only) | `firmware/main/cooker_board_io.c` SHA-256 `459e0fb3fe27cdfa2001a20d394fd035dd389a895ea389b0692ae824790931ec`; focused test SHA-256 `b7653bb4571747159570cb3a9965a54bdda70074f378fced087443c9d82f6a1b`; normal-image source registration `firmware/main/CMakeLists.txt` SHA-256 `243efabbb2b3c4231968c75ca5a094d282a2c49cc39e5f1bc306e1b406b096ab` |
| Diagnostic target link anchor | `firmware/main/diagnostic_lockout_idf.c` SHA-256 `931ebbc4d7a834ed2910791022fc36b680aaa4ee555dc4e1e1835c4d06b2d5e2`; refreshed target link PASS: ELF `8ddfbea149b14dcf6f232989be5b2aa561738e408646d5207339e1becfe52885`, bin `e2a4651d9f09e3ce47dcff7dae924beb535398d3dee901c37c353bf164af6382` |
| Rev38 source-task target entry | `firmware/main/rev38_source_test_idf.c` SHA-256 `5fb7af8681470ded15ce9ed9099028451bd41a2826e0910af3ae9080ff6231aa`; `firmware/main/CMakeLists.txt` SHA-256 `15f9eed25f55086d7616ed579b6134f810e8c50788986497aa72c4569bdd571e`; ESP-IDF target link PASS: first ELF `f6b5e305203cb5aa817254b5b4bf7f1cddeb4cc933b75ca7d7431904ab734613`, bin `635ebf3527ec84f7adfaad95728baee65452d780f518500c3067bfdef079279b`; fresh defaults-only ELF `a69de5cfd7ba6aa14a6155414b0cc8aff2fa174c362951c7c97ba4fdbf255c64`, bin `dea7ab8bbc0491b792c80c80ff6797f2be43da00e6264a2179b65661c60aca9a`; both generated `sdkconfig` SHA-256 `88adb4734e78f358e8cbd60dc71eab8bd0052a39700d9443edf43a4e2aaa4861` |
| Heatsink NTC host model | `firmware/components/safety/ntc_guard.c` SHA-256 `60fc13c60b9b0e00eebedb16f04a6d359dde3e73faa42ff72697c9e4e9a8496d`; header SHA-256 `90bda483eb56afe7ca091542a237b857177d20c0ed086c55eda6996ab7132855`; host tests SHA-256 `6ca2e1a709a1ec8749e91b6492955874df610133865e8cf66064f7c41dc69f62` and `968910cacfb8a81ff42e428c6399c044ae0ea29d2fd9f1b518bb02afce1de34d` |
| Native board, production runtime and physical capture | **No accepted artifact or hash**. `placement-review/03/` is an unrouted placement diagnostic with provisional stackup and exact source parity. |
| Stackup-aware native diagnostic | `stackup.json` SHA-256 `45bbfe06341177314ac3e9722ac2afcbf6eda05e8fc87cec052ade77aa98b488`; `tools/build_native.py` SHA-256 `0f188109cd150c28b1cb7d48688feaf41872bc15292d6058ad2156f14ebe8c3a`; `placement-review/03/poses.json` SHA-256 `c3bd07de25a8c53da0576a330256a138279704ae37d54e4cc8b476216f78c7a5`; board SHA-256 `c277e9cae08213557f8bed43253253966229c695a9e754474d229babcf786ff5`, manifest SHA-256 `46bd18598f2717da1891d0398639a60bebc798e13bfecb529ac60cbe05de4798`; native geometry export SHA-256 `3c539845b5e6e7b841d2450732d9ac6bc25b8b64d0abe9d24637ce9fd651b56e` |
| Native board/source identity gate | `zapote-board.rs` SHA-256 `1568149a6d3917bb865b7c92e9d14cfe1f1c2e4d2c80931ebc032d8dc1fdec4f`; `board_cli.rs` SHA-256 `63066a07a65fd6a6bce890861b2fdce2c15e9b1720fda9e1eaadf4896bc6013a`; `placement-review/03/native-diagnostic/identity-report.json` SHA-256 `7eac1a6503e9e38818c23497f1cbd82a7871ded7b8af3fdddde0519992c5e92b` |
| Native document/domain gate code | `zapote-drc/src/native_binding.rs` SHA-256 `c6cf4c7fbc50e649c2709117fde1f45e8a8a9b3720a796c99d8c4c4270ddbb2b`; `tests/native_multipad.rs` SHA-256 `55d3efc0edfffaa244d498c9288f528823cecd3ba77f6358e5a77463061e5ded`; `tests/rev38_native_domains.rs` SHA-256 `b31635c3685a846d0f7e14399ca5841ac164036604f5c48edaf78d62b3f23365` |
| Cooker native readiness diagnostic | `cooker-mate/evidence/native-readiness-02.json` SHA-256 `9d441e0ae16a4ed912ff7420beb38fc2b3a8c5eed39da8589c8814811565e5ef`; static probe only |
| Follow-on cooker power assembly | **Outside this plan's U7 gate**; `docs/superpowers/specs/2026-09-24-rev38-single-bank-cooker-design.md` explores a single-bank half bridge, and `POWER-ASSEMBLY-BOUNDARY.md` records the unjoined product source |

The previous `source-build-04` and `source-build-05` receipts remain historical;
their hashes are retained in `NATIVE-BUILD.md` and the earlier native
diagnostics. Each build receipt lists
every copied Atopile source hash and its resolved
export hash. The [two-board source record](COOKER-ASSEMBLY-SOURCE.md) links
the actual netlist/BOM bytes; `tools/check_assembly_source.py` verifies the
receipts, source copies, build manifests, adapters, exports and netlist/BOM lock before running
the Rust pin audit. Tool versions used for this local gate: Atopile **0.2.69**
(receipt build), `rustc 1.92.0`. `kicad-cli 10.0.4` also checked the saved
`placement-review/03/` diagnostic; its ERC, DRC, schematic parity and
footprint receipts are in `native-diagnostic/`. Earlier diagnostic history is
in `NATIVE-DIAGNOSTIC-05.md` through `NATIVE-DIAGNOSTIC-09.md`. Re-run the gates and update hashes if any listed input
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
| R12 | `fault-response.tsv`, `timing-analysis.md`, `bench-capture.md` identify producers, clear paths, missing hazard and implementation terms. The ledger now separates physical F2 opening from the first detectable threshold and records that UCC28180 cycle-by-cycle PCL is not a retained HOT overcurrent producer. | Independent numeric allowable/implementation bounds and measured margins OPEN; decide whether the current/energy envelope requires an added retained overcurrent trip. |
| R13 | Joined Rev38 source and frozen cooker source pass exact 16-contact connector audit with negative mutations; protocol and physical feedback are separate nets. The saved placement diagnostic has exact numeric-pad source/native parity. | Accepted routed-board parity, isolation layout and fault captures OPEN. |

The five acceptance examples AE1–AE5 have logical scenarios in the Rust
model/protocol and firmware host suites, and corresponding future physical
nodes in `bench-capture.md`. Their **assembled fault-injection evidence is
NOT RUN**. In particular, AE5's first-START reset allowance is only a bounded
behavioral candidate; it is not a second watchdog deadline or a measured
current-cessation result.

## Gate results and remaining work

| Gate | Current result | Scope |
| --- | --- | --- |
| Frozen two-source build and assembly audit | **PASS** | 296 Rev38 refs, 189 cooker refs, one ESP on cooker source, none on Rev38; receipt hashes and straight-through 16 contacts checked. |
| Rust pin audit mutation suite | **PASS: 147/147** | Includes swapped UART contacts, open return, open ESP ground pad 41, extra STOP driver, weak heartbeat pull-down and wrong Rev38 protocol-isolator identity. |
| Import-boundary and derived-artifact checks | **PASS** | `scripts/import_linter_gate.py`: 5 kept, 0 broken; `scripts/regen_derived.py --check`: consistent. |
| Maintained Zapote unit suite | **FAIL, separate baseline** | Seven units checked: six indeterminate and existing `power-entry` fails `ERC.PFC.SHUNT_PART` for the unsupported shunt identity. See `UNIT-GATE-DIAGNOSTIC.md`. This is not a Rev38 U7 finding or waiver. |
| RTD sample-age and cooker temperature input | **PASS: 22 focused host tests; 18/18 CTest** | Conversion age, wrap and invalidation; PT100 manufacturer-table values; INIT wait and preserved probe-fault diagnosis. The 100 ms control sample rejection is not an accepted monitor deadline. No monitor epoch or Rev38 authorization is credited. |
| Heatsink NTC host conversion | **PASS: 9 focused guard tests; 18/18 CTest** | The guard matches the selected 100 kΩ/B4190 Vishay part and 10 kΩ top resistor at cold, 25 °C, and 85 °C points; the new board I/O hook uses a nominal 3.3 V conversion and fails closed for invalid or out-of-range results. Target ADC transfer, actual divider rail, calibration, independent analog trip and physical behavior remain OPEN. |
| Cooker control progress gate | **PASS: 62 focused state-machine tests; 18/18 CTest** | A completed nonfault handler permits a control epoch; deferred messages and fault ticks do not. The production call site is not target-tested; target timing and monitor freshness remain OPEN. |
| Receiver engineering target profiles | **PASS: two offline AVR64DA32 links** | The locked default and separately named nonzero-window engineering profile build with the official Microchip toolchain. `receiver-firmware/ENGINEERING-WINDOWS.md` states transport arithmetic and unmeasured processing hypotheses. This is target-code evidence, not numerical or device acceptance. |
| Receiver device qualification | **OPEN** | Target compilation does not prove programmed fuses, reset, clock, watchdog, pin levels or deadline behavior on silicon. The candidate windows and installed-device maximums are unaccepted. |
| ESP target integration | **Rev38 test-image link PASS; normal cooker source compile PASS, final link FAIL** | The earlier ESP-IDF v5.3 `TEMPER_REV38_TEST_IMAGE=ON` image linked with the actual source task and retains zero timing lockout. New board-backed ADC/NTC/RTD hooks and fail-closed invalid-temperature handling pass **18/18 host CTest**. After the user approved the Docker worktree mount, the normal cooker image compiled `cooker_board_io.c` and reached the ELF link, which still failed on 26 distinct missing cooker interfaces; see `ESP-TARGET-COMPILE.md`. Target pin/reset captures remain NOT RUN. |
| F1/F2, AUX, SELV port and thermal/fault envelopes | **OPEN** | `SELV-PORT-CONTRACT.md` sets candidate board-input limits and a 100 mA Rev38 allocation, not an accepted load maximum or qualified cooker rail. `F1-SCREEN.md` keeps the inlet fuse/NTC thermal and slow-overload gates open. Current `source-build-06` joins separate `74651173R` VD/VB studs with review-only footprints; their lug, PTH, copper, fault-current, DC and thermal application remains unqualified. The Phoenix studies are historical. AUX normal voltage-window and fast-fault peaks remain OPEN. The 10 kΩ GPIO21 pull-down does not bound WDI feed tail. |
| Native schematic/PCB, ERC/DRC, stackup, source/native parity and maintained unit gate | **DIAGNOSTIC ONLY; U7 OPEN** | `placement-review/03/` saves a 295-footprint functional-region diagnostic from `source-build-06`: 275 changed poses, 246 nets and 1,052 mapped numeric edges after off-board F2 exclusion. ERC, schematic parity and non-routing DRC findings are zero; 295 footprints match their vendored libraries. The provisional six-layer 1.8 mm CAD stackup passes the Rust consistency gate and is hashed into the source manifest. The board has no routes or zones and KiCad caps its unconnected report at 499. Physical placement and native acceptance remain open. `NATIVE-DIAGNOSTIC-09.md` preserves the prior seven-finding shelf result. The review-only TPS3431/LTC4368 variants need thermal and assembly qualification. Canonical `pcb/temper.kicad_pcb` is outside this candidate. `INSULATION-BASIS.md` has provisional 16.0 mm Group IIIa board and 12.6 mm Group I package creepage screens. The joined DWW pair specifies >14.5 mm external package path, but PD3 component certification, opposed copper, product standard, voltage envelope and construction are unresolved. |
| Saved board/source identity | **PASS on diagnostic bytes only** | The Rust board checker matches the PCB digest and all six declared source input digests to the saved manifest. Stale PCB and netlist mutations fail the focused 7/7 CLI suite. The manifest SHA-256 is pinned above. This does not detect HOT/SELV copper bridging or close U7. |
| Native pad/copper extraction and strict binding | **PASS as transport only** | The regenerated board exposes manifest-checked source instance and MPN fields on 295 footprints and stable UUIDs on 1,089 KiCad pad objects, including 16 mask/paste-only objects and three non-plated holes. KiCad 10.0.4 extraction saves 1,070 assigned pad connections and 1,052 connectivity clusters with zero routed copper. Rust document binding passes; it is not a spacing verdict. |
| HOT/SELV native spacing and crossing mutation | **FAIL; voltage/rule coverage OPEN** | `NATIVE-DOMAIN-SCREEN.md` records the four-net anchor and a broader pad-owner check: 62 SELV, 183 live and one PE named nets. The 19 unassigned KiCad pad objects comprise 16 paste/mask-only objects and three non-plated holes, not unassigned copper lands. The provisional 16.0 mm projected copper-distance screen covers all 245 assigned SELV/live nets on the saved /03 candidate but still fails at the unchanged 15.2 mm DWW opposed pads. Isolator-side and PE miswire mutations fail; a synthetic SELV-to-HOT trace fails the domain rule and cannot masquerade as the saved board. PE, installed hardware, actual voltage/air/creepage requirements, placement and routing remain open. |
| Cooker source/footprint readiness | **Follow-on product work** | The frozen derivative proves a proposed controller interface. Its old F1/NTC footprints and product placement do not gate the Rev38 section board. The 3.3 V port supply, load, startup and fail-low contract do gate Rev38 interface acceptance. |
| Low-voltage assembled injection, fault-to-current cessation, mains safety and passive protection/cooling milestone | **NOT RUN / OPEN** | Require a joined physical design and separately accepted measurements. |

The next digital release gate is a reviewed native Rev38 section board with
exact parts, poses, outline, source/native parity, and a defined SELV
controller port. That port has a candidate 3.3 V supply/load/startup/fail-low
contract for the existing cooker ESP command source; qualification remains
open. The current F2 stud land pattern, installed fault and thermal envelope,
and exposed-metal spacing remain open. Cooker inverter power joins and native cooker-board placement
belong to a later product-integration gate.
