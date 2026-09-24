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
| U4 | The joined Atopile candidate now includes the ESP32-S3-WROOM-1-N8R8 pad fixture, TCA6408A-Q1 expander, active-low START switch, source authority, both isolators, AVR receiver, watchdog, rail and fault detectors, driver, PFC, and fused-board-terminal AC path. `source_mcu` and `integrated` compile; `audit.rs` passes 101 exact-pin and mutation tests, including an ESP UART pad swap. `PIN-INTERFACE-CONTRACT.md` is the common map. The IRM-20-15 direct path and IRM-20-24/LMR36015 regulated path, each with proposed LTC4368/TPS54202 downstream, are bench comparisons only. | The 3.3 V, protected AUX and HOT logic5 supply producers remain unjoined; source reset-good and interlock producers remain external. Resolve F1/inrush/thermal and AUX startup/window/OVP, expander retained-output and pulse timing, all electrical corners, then build native schematic/PCB. Physical captures are NOT RUN; U4 remains OPEN. |
| U5 | The receiver protocol, journal, core, runtime and host pin sequence tests pass. An AVR64DA32 fuse-readback guard now rejects the default image before runtime; the internal watchdog is serviced only after completed receiver ticks. A previous target image built with Microchip avr-gcc 15.1.0, but the changed adapter has not been target-built in this environment. | Select and program exact WDTCFG/BODCFG/SYSCFG0/OSCCFG bytes, verify UPDI readback, pin/reset/rail behavior, clock accuracy and watchdog period on device; derive nonzero timing windows. U5 remains OPEN. |
| U6 | Source core/runtime and new ESP32 adapter host tests pass. The adapter assigns direct STOP, heartbeat, permit set, safety sample, UART, START, and I²C pads, and orders expander latch/polarity/direction writes before sampling P3–P7. Runtime now reserves the configured sample-to-edge bound before timed control and WDI pulses; a near-deadline negative test fails against the previous runtime. A candidate ESP-IDF GPIO/I²C0/UART1 binding exists; neither IDF target build nor `app_main` integration has run. | Prove sole UART ownership and final bit completion, target-verified expander P1 and WDI pre-edge bounds, paired task epoch ownership, I²C read age, reset/boot/partial-power default states and physical reset-to-off; test on target. U6 remains OPEN. |
| U7 | No Rev38 native candidate exists. `bench-capture.md` now maps the joined candidate's supply, fault, reset and timing measurements to physical nodes; all captures are NOT RUN. | Native schematic and PCB, BOM and footprint review, source/native parity, ERC/DRC, stackup and unit gates, authoritative acceptance receipt. Physical captures remain NOT RUN. |

The source watchdog feed now uses the spare SN74LV221A-Q1 rising-trigger
channel. Its active-low output drives TPS3431 WDI, so an ESP heartbeat pad
fall caused by CPU reset cannot itself service the watchdog. The standalone
and joined Atopile builds pass, and `audit.rs` passes 101 pin/mutation tests.
The source host runtime requests a low-high-low trigger only after disarm;
its focused CMake test passes. A boot/other-core rising edge, one-shot rail
collapse, and the last possible post-reset WDI edge remain unmeasured, so
the reset-to-off time is still OPEN.

`ESP-PIN-INVENTORY.md` records the N8R8 module restrictions and the
firmware/electrical-source pin conflicts that the U4/U6 pin contract must
resolve. It assigns no candidate GPIOs.
`ESP-PIN-FIT.md` gives one unadopted pin-fit screen using a local I²C
expander. It preserves direct STOP, WDI-request and PERMIT-set pins, but
the expander's outputs can persist across an ESP CPU-only reset; the relay,
challenge and seen-reset consequences remain open.
The joined receiver now uses the spare second HCS21 gate to require both AVR
PA2 relay output and retained HOT RUN Q before the relay MOSFET gate can rise.
The audit rejects a direct PA2-to-relay bypass or a tied-high RUN gate input.
AVR firmware still holds PA2 low. Relay timing, precharge decision, driver
levels, contact behavior, and an expander-retained request remain open.
`F1-SCREEN.md` nominates Eaton `LP-CC-20` with `BCM603-1P` and `CVR-CCM`
for a proposed dedicated-20 A, 10 kA prospective-fault-current residential
review envelope. The compiled board now has a fused-L input, but the off-board
F1 assembly and inlet harness remain unbuilt. Whole-assembly fault, inrush,
thermal, F2/MOV coordination, and harness/access gates remain OPEN.
`AUX-WINDOW.md` now counts the joined relay and direct passive AUX branches;
about 41.50 mA of nominal-resistance paths at 15.75 V are identifiable before
the PFC controller, driver, logic5 converter and dynamic loads. The old
75 mA direct-AUX allowance cannot be inherited without a new load budget.
`AUX-OVP-WINDOW.md` also records that TPS26601's default UVLO can prevent
startup at a valid 14.625 V regulator output; the protected-AUX candidate
needs an externally qualified UVLO threshold as well as the OVP solution.
The 15.75/18.0 V screen permits at most 0.32663% independent variation per
OVP resistor before leakage; ordinary ±0.1%, ±25 ppm/K discrete parts can
exceed that at 125 °C before lifetime drift. No cutoff divider is selected.
The `AUX-OVP-WINDOW.md` TPS2663x alternative uses its wider guaranteed OVP
hysteresis and a screened ±0.02%, ±2 ppm/K TNPU divider. Even with the
manufacturer's 225,000 h drift and OVP-pin leakage bounds, its static margins
are only 36 mV for recovery and 42 mV for trip. Board leakage, fault input
waveform, output peak, top-resistor temperature, and current-limit behavior
are unqualified, so it is not yet a protected-AUX selection.
The LTC4368 controller is a second mathematical-only OVP screen. An
illustrative 339 kΩ/10 kΩ divider leaves 212 mV normal-high recovery and
167 mV provisional-limit trip headroom under stated resistor and pin-leakage
assumptions. External FET selection, dynamic output peak, load current, and
UV/startup behavior remain unproved; it is not a protected-AUX selection.

Immediate construction order: build and qualify U4's nominated off-board
Class CC F1/AC input and protected AUX source; bind those pins to U5's AVR
adapter and U6's source driver;
then export and audit U7. Update U1 with every selected component and
measured path. Do not promote the partial `isolation` build to a joined
Atopile PASS.
