# Rev38 implementation status

This file tracks the approved plan without changing its requirements.
The branch is an engineering candidate. **U4-U7 and the Definition of Done
are not yet complete.** No protected-operation or mains-build claim follows
from the current host tests or partial netlist.

| Unit | Current evidence | Remaining gate |
| --- | --- | --- |
| U1 | `response-contract.md`, `fault-response.tsv`, and `timing-analysis.md` establish the bounded-reset candidate and per-fault missing-input ledger. The event ledger identifies the Rev38 producers now joined and separates their connectivity from unproved capture. The timing companion maps every event to allowable/implementation input owners and evidence class; the AUX-source alternatives and startup-load decision gate are explicit. | Independently support allowable and worst-case implementation bounds, margin, and applicability using the joined circuit and real power-stage envelope. Numerical acceptance OPEN. |
| U2 | `receiver-selection.md` selects AVR64DA32-E/PT and assigns physical pins; journal format and exhaustion behavior are host-tested. | Fuse image, device NVM/BOD/boot-pin verification, and selected-device build. |
| U3 | `model.rs` and `protocol-tests.rs` cover the logical session, fault, deadline, and reset controls. | Recheck model against the eventual joined source and native circuit; logic tests do not prove physical pulse capture. |
| U4 | `power_entry_integrated_38.ato` compiles source authority, receiver, HOT TPS3431 watchdog, two HOT TPS3890 undervoltage supervisors, four-channel VD/VB detector, dual-channel AUX window, UCC28180 PWM/VSENSE inhibit, a boost/F2/local-reservoir/bank power path, an F1-holder/CMC/NTC/precharge-relay AC-entry candidate, and a partial UCC27624/STW gate path. It joins source PERMIT, health, STOP, physical HOT PERMIT feedback and retained HOT SESSION feedback across the assigned isolators. The driver has a hardware permission AND, AUX-biased ENA shunt, local low defaults, gate resistor and STW switch pins. HOT WDI/WDO, wire-AND rail RESET, and the VD/VB plus AUX summary join the retained trip fan-in. The spare source HCS21 gate now makes a WDO-independent pre-watchdog sample of reset-good, interlock, and rail-good. `audit.rs` passes 97 standalone/joined pin and mutation tests, including a deliberate short of that sample to WDO, F2 divider and trip disconnects, rail producer disconnects, ENA floating, watchdog WDI/WDO disconnects, abort bypass, feedback swap, and isolation bridge. `gate-enable-corners.md`, `HOT-WATCHDOG.md`, `HOT-RAILS.md`, `F2-DETECTOR.md`, `AUX-WINDOW.md`, `PFC-CONTROL.md`, `PFC-POWER.md`, and `AC-INPUT.md` record open electrical/timing proofs. `AUX-OVP-WINDOW.md` proves the proposed TPS26601 ±1% static cutoff window impossible under the current 15.75/18.0 V screens; a ±0.1% example remains dynamically unqualified. | Prove coincident trip/reset and setup/hold corners; select the actual F1 cartridge and qualify the now-joined AC input, then select and join a protected AUX source and complete electrical corner analysis. Verify VD/VB and AUX thresholds, response and input injection, plus both TPS3890 thresholds/CT/rail ordering. The LVC output during intermediate HOT rail collapse, PMBT3904 saturation across temperature, UCC EN internal pull-up maximum, and AUX transient range remain unresolved. Source reset-good, interlock, STOP, heartbeat and protocol/relay GPIO producers remain external. The joined file is still partial and does not pass U4. |
| U5 | Fixed wire codec, interrupted-write journal, receiver session core, and host pin-sequencing runtime pass focused tests. The runtime drives boot outputs low, orders preparation edges across fresh physical samples, rejects invalidating stream errors, and is the sole synchronous RUN-set pulse owner. It checks the START deadline again after the last output callback; a host fixture delays that callback through expiry. A provisional AVR64DA32 register adapter maps the selected GPIOs, TCB0, USART0 and mapped EEPROM. The default zero-window target image builds with official Microchip avr-gcc 15.1.0 and remains locked out; an offline nonzero-window compiler exercise also builds. | Qualify actual timing values, measured sample-to-pin and pulse widths, clock/USART and NVM behavior, relay policy, boot/reset pin states, BOD/fuse programmed-image receipt and saved netlist pin review. The target build is compiler evidence, not a programmed-device PASS. |
| U6 | `firmware/main/power_entry_authorization.c` and `power_entry_source_runtime.c` are listed in the main component and pass focused host CMake targets; the ESP-IDF component build has not run. The core enforces boot lockout, physical disarm/history-reset ordering, release-then-press START, fixed ACK deadline, ACK-armed START with a fresh bounded transmit commit, invalidating decoder abort, and stopped deliberate restart. The runtime orders STOP/UART cancellation, challenge, reset pulse, readback, permit set, WDI and synchronous frame writes. Host tests reject delayed commit, delayed permit/WDI writes, failed UART, lost HOT readback, and stale queued TX on serial error or restart. Boot now leaves WDI untouched and the host fixture rejects a boot-time feed edge. `ESP-PIN-FIT.md` screens a pin/expander allocation that preserves USB and UART0, with retained-output hazards explicit. | Select and join an actual ESP pin contract, including expander defaults if used; implement GPIO/UART/timer ownership and boot disarm, wire the runtime into the cooker state machine, prove sample-to-pin, pulse, UART completion and post-reset feed-tail bounds, test two-core progress on target, and run an ESP-IDF build. ESP reset-time pad behavior and other owners may still create a WDI edge; this is not yet captured. `idf.py` is not on this shell's PATH. |
| U7 | No Rev38 native candidate exists. | Native schematic and PCB, BOM and footprint review, source/native parity, ERC/DRC, stackup and unit gates, authoritative acceptance receipt. Physical captures remain NOT RUN. |

The source watchdog feed now uses the spare SN74LV221A-Q1 rising-trigger
channel. Its active-low output drives TPS3431 WDI, so an ESP heartbeat pad
fall caused by CPU reset cannot itself service the watchdog. The standalone
and joined Atopile builds pass, and `audit.rs` passes 97 pin/mutation tests.
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
`F1-SCREEN.md` compares exact holder/cartridge variants and records why
prospective fault current, inrush, and thermal inputs are required before
the provisional holder path can become an F1 selection.
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

Immediate construction order: select and qualify U4's actual F1 cartridge/AC input and protected AUX source; bind those pins to U5's AVR adapter and U6's source driver;
then export and audit U7. Update U1 with every selected component and
measured path. Do not promote the partial `isolation` build to a joined
Atopile PASS.
