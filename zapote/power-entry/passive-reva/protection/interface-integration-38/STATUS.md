# Rev38 implementation status

This file tracks the approved plan without changing its requirements.
The branch is an engineering candidate. **U4-U7 and the Definition of Done
are not yet complete.** No protected-operation or mains-build claim follows
from the current host tests or partial netlist.

| Unit | Current evidence | Remaining gate |
| --- | --- | --- |
| U1 | `response-contract.md`, `fault-response.tsv`, and `timing-analysis.md` establish the bounded-reset candidate and per-fault missing-input ledger. The event ledger identifies the Rev38 producers now joined and separates their connectivity from unproved capture. The timing companion maps every event to allowable/implementation input owners and evidence class; the AUX-source alternatives and startup-load decision gate are explicit. | Independently support allowable and worst-case implementation bounds, margin, and applicability using the joined circuit and real power-stage envelope. Numerical acceptance OPEN. |
| U2 | `receiver-selection.md` selects AVR64DA32-E/PT and assigns physical pins; journal format and exhaustion behavior are host-tested. The default locked target image builds with official avr-gcc. | Fuse image and device NVM/BOD/boot-pin verification; measured target timing and a nonzero-window programmed-device build. |
| U3 | `model.rs` and `protocol-tests.rs` cover the logical session, fault, deadline, and reset controls. | Recheck model against the eventual joined source and native circuit; logic tests do not prove physical pulse capture. |
| U4 | The joined Atopile candidate includes a 16-contact Rev38-side port for the existing cooker ESP, TCA6408A-Q1 expander, active-low START switch, source authority, both isolators, AVR receiver, watchdog, rail/fault detectors, driver, PFC, fused-board AC input, AUX branch loop, IRM-20-24 raw source, LMR36015BRNXT 15 V pre-cutoff converter, LTC4368/FDS3992 protected-AUX cutoff, and TPS54202 HOT logic5 converter. All three supply stage builds and `integrated` compile; `audit.rs` passes 136 exact-pin, BOM-identity and mutation tests. A separate `cooker-mate` derivative compiles the mating header joined to the existing cooker ESP and rail; its BOM has one ESP, and `build.sh` checks the exact pad map, power source/return chain, and supervised reset/interlock producer pins with the shared Rust audit. `SOURCE-RESET-INTERLOCK.md` records the new producer circuit and its unresolved GPIO14/open-drain and physical gates. `PIN-INTERFACE-CONTRACT.md` is the common map. The regulated 24 V route is the digital engineering candidate; direct IRM-20-15 remains a bench comparison. `SELV-SUPPLY-LOAD.md` inventories the added loads without crediting unproved cooker-rail headroom. | Create and check the native cooker mate/harness and qualify SELV 3.3 V capacity; implement GPIO14 open-drain ownership and qualify reset/interlock behavior at physical pins. Then close F1/inrush/thermal, AUX/logic5 load and startup, cutoff FET SOA and fast-fault peak, expander retained-output and pulse timing before building a native board. Physical captures are NOT RUN; U4 remains OPEN. |
| U5 | The receiver protocol, journal, core, runtime and host pin sequence tests pass. An AVR64DA32 fuse-readback guard rejects the default image before runtime; the internal watchdog is serviced only after completed receiver ticks. The adapter compiles and links with Microchip avr-gcc 15.1.0 for AVR64DA32; `receiver-firmware/README.md` records both the 16,050-byte locked-image build and a 16,594-byte offline nonzero-timing compiler exercise. | Select and program exact WDTCFG/BODCFG/SYSCFG0/OSCCFG bytes, verify UPDI readback, pin/reset/rail behavior, clock accuracy and watchdog period on device; derive accepted nonzero timing windows. U5 remains OPEN. |
| U6 | Source core/runtime and new ESP32 adapter host tests pass. The adapter assigns direct STOP, heartbeat, permit set, safety sample, UART, START, and I²C pads, and orders expander latch/polarity/direction writes before sampling P3–P7. Runtime reserves the configured sample-to-edge bound before timed control and WDI pulses; a near-deadline negative test fails against the previous runtime. The complete firmware host build and all 17 CTest entries pass. `rtd_service_sample_status()` now publishes a cross-task atomic healthy-conversion generation and readiness; the MAX31865 host tests cover repeated, stalled and faulted conversions after a valid sample. One `app_main` source task owns the candidate ESP-IDF GPIO/I²C0/UART1 binding and samples completed control-task epochs. A default-on **diagnostic lockout** ESP-IDF v5.3.6 image links the cooker core but holds STOP low, asserts the runaway cut and never starts cooker or Rev38 authorization tasks; `ESP-TARGET-COMPILE.md` records the exact evidence limits. Production mode still fails link on 32 unresolved cooker hooks. The source task remains locked out with zero target bounds and unqualified UART final-bit, reset feed-tail and independent monitor progress; no Rev38 WDI or START is enabled. | Supply real production implementations and source registration for the unresolved cooker hooks, then link and run the target image; define idle/heating monitor checks and sensor-age deadlines before crediting progress (`run_safety_check()` requires PLL lock even at idle), and prove sole UART ownership and final bit completion, target-verified expander P1 and WDI pre-edge bounds, I²C read age, reset/boot/partial-power default states and physical reset-to-off. U6 remains OPEN. |
| U7 | No Rev38 native candidate exists. The joined source separates off-board F2 `U226` from four-pin Phoenix terminal candidate `U227`; both retain unresolved footprint keys. `source-build-03` freezes the 295-reference Atopile source and resolved export, including the Rev38-side Molex header and no second ESP. The strict Rust bridge checks an exact assembly-only F2 declaration against that full source and keeps its identity in the receipt. Six focused tests pass. The native probe passes the off-board fuse projection and stops on the board terminal footprint placeholder, as recorded in `NATIVE-BUILD.md`. `F2-BOARD-INTERFACE.md` records the terminal pin grouping, drawing-derived pad centers, and a Phoenix-linked SamacSys archive comparison; the selected 1017526 drill/pin records still disagree, and the alternate 1017531 archive has an inconsistent body outline. No terminal footprint is assigned. The cooker mate now has its own frozen 189-reference `cooker-source-01` export, including the existing ESP/SELV rail and reset/interlock producers. The two-source 16-contact audit passes with swap/open mutations; `COOKER-ASSEMBLY-SOURCE.md` records the narrow digital evidence. Neither board nor physical harness exists, and cooker ESP ground-pad modeling remains open. `bench-capture.md` maps supply, fault, reset and timing measurements to physical nodes; all captures are NOT RUN. | Reconcile terminal drilling and fault-current/thermal application, create native cooker and Rev38 boards and qualify their pin/rail/harness interface, create reviewed poses and outline, then review source/native parity, ERC/DRC, stackup and unit gates. Physical captures remain NOT RUN. |

The diagnostic ESP-IDF link receipt predates the current RTD freshness-status
change. Its rebuild attempt stopped before IDF startup because Docker's local
daemon socket was absent; current changed RTD bytes have host-test evidence
only. U6 target compilation remains OPEN.

The source watchdog feed uses the spare SN74LV221A-Q1 rising-trigger channel
and the receiver relay gate requires both AVR PA2 and retained HOT RUN Q.
Those default-off joins pass digital audit. A boot/other-core rising WDI edge,
expander-retained relay request, one-shot rail collapse, and the last possible
post-reset WDI edge remain unmeasured. Their reset-to-off timing is OPEN.

The cooker-mate derivative now has digital reset/interlock producers on
pins 14/15. Their supervisor, LVC gates and existing NAND latch have no
power-ramp or transient-fault capture. The source adapter releases GPIO14
as an input during boot. Its new candidate operation sinks GPIO14 only in
open-drain mode for one pulse per deliberate restart, with a bounded fresh
disarm sample before the edge and healthy physical readback afterward. A slow
UART drain, stale sample, failed pulse or second request fails closed in host
tests. The current restart-disarm API also requires
`safety_ok`, which contains the interlock itself, so it cannot acknowledge
disarm while the cooker fault latch is set. The source core and runtime now
expose a separately sampled, host-tested latch-reset eligibility predicate
that requires physical local/HOT PERMIT and HOT session low with rail good.
The source task now accepts one queued deliberate restart request, waits for
physical disarm, uses the one-shot latch reset only when required, and calls
`esp_restart()` after healthy disarm. No UI/operator caller exists. The changed
ESP32-S3 object has no target build or pin capture, and the 1 ms candidate
pulse has no measured maximum. Physical reset behavior remains OPEN.

The 2026-09-24 `make -C zapote check-units` rerun used KiCad 10.0.4's
`pcbnew` interpreter and reported six units INDETERMINATE and the maintained
`power-entry` unit FAIL. The runner now classifies the current `GBU2510A`
bridge's GBJ-bound loss/candidate obligations as INDETERMINATE while retaining
their required rule IDs; an unknown bridge identity still fails closed. The
remaining maintained power-entry FAIL is substantive: `WSL2726R0100FEA` is
an unsupported 10 mΩ/two-pad shunt identity, and four branch-copper findings
screen 15.0000 A nominal RMS against 10.4205 A at the saved 2.5 mm/70 µm
geometry and assumed 20 °C rise. These are findings on the separate
maintained GBU board, not a Rev38 native-board result. The plan preserves
the passive reference and does not authorize changing that board to make the
gate green. U7 digital acceptance remains OPEN.

`ESP-MONITOR-CONTRACT.md` records why an idle cooker cannot credit the
existing unconditional `run_safety_check()` and why fault-state control
ticks and cached RTD values need separate freshness gates before either
progress epoch can be used for Rev38 authorization.
`SELV-CONTROLLER-CONNECTOR.md` screens one 16-contact harness and pinout for
the selected shared cooker ESP. It is not a joined conductor or a measured
rail-budget claim.

`F1-SCREEN.md` nominates Eaton `LP-CC-20` with `BCM603-1P` and `CVR-CCM`
for a proposed dedicated-20 A, 10 kA prospective-fault-current residential
review envelope. The compiled board has a fused-L input and a separate AUX
branch loop, but neither off-board fuse assembly nor harness is built.
The 20 A fuse remains intact for at least 12 seconds at 40 A, while the
selected CMC, bypass contact and NTC have 15–16 A continuous ratings. Their
transient withstand or an independent clearing path is unproved.
Whole-assembly fault, inrush, thermal, F2/MOV coordination and access remain
OPEN; the F1 matrix's physical rows are NOT RUN.

`AUX-CUTOFF-CANDIDATE.md` records the joined LTC4368-2/FDS3992/50 mΩ
selection. Its independent-resistor static screen gives OV recovery no lower
than 15.95075 V and rising trip no higher than 17.84409 V under the stated
assumptions. This does not bound a fast-fault output peak. The protected rail
has 30.6 µF nominal direct capacitance; valid-start current, effective MLCC
values, FET linear SOA and latch reset are OPEN. `HOT-LOGIC5-CONVERTER.md`
records the joined TPS54202 output network and its 46.5 µF nominal 5 V bank.
`AUX-WINDOW.md` identifies about 41.50 mA of nominal-resistance direct AUX
paths before active switching loads, not a maximum. The old 75 mA allowances
cannot be inherited. With nominal direct-bank inrush, the cutoff's
lowest screened startup trip threshold leaves only 0.410 A for overlapping
active startup loads. This conditional subtraction is not a proven margin;
the joined-load and FET-stress worksheet remains NOT RUN.

The selected supply parts and pin/interface contract now need native
schematic/PCB realization, source/native parity, ERC/DRC, and physical tests.
U1's per-fault timing ledger must use those measured paths. Do not promote
Atopile connectivity or host tests into U4–U7 physical acceptance.
