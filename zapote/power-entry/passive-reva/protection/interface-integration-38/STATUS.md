# Rev38 implementation status

This file tracks the approved plan without changing its requirements.
The branch is an engineering candidate. **U4-U7 and the Definition of Done
are not yet complete.** No protected-operation or mains-build claim follows
from the current host tests or partial netlist.

| Unit | Current evidence | Remaining gate |
| --- | --- | --- |
| U1 | `response-contract.md`, `fault-response.tsv`, and `timing-analysis.md` establish the bounded-reset candidate and per-fault missing-input ledger. | Independently support allowable and worst-case implementation bounds, margin, and applicability using the joined circuit and real power-stage envelope. Numerical acceptance OPEN. |
| U2 | `receiver-selection.md` selects AVR64DA32-E/PT and assigns physical pins; journal format and exhaustion behavior are host-tested. | Fuse image, device NVM/BOD/boot-pin verification, and selected-device build. |
| U3 | `model.rs` and `protocol-tests.rs` cover the logical session, fault, deadline, and reset controls. | Recheck model against the eventual joined source and native circuit; logic tests do not prove physical pulse capture. |
| U4 | `power_entry_integrated_38.ato` compiles source authority, receiver, HOT TPS3431 watchdog, two HOT TPS3890 undervoltage supervisors, and a partial UCC27624/STW gate path. It joins source PERMIT, health, STOP, physical HOT PERMIT feedback and retained HOT SESSION feedback across the assigned isolators. The driver has a hardware permission AND, AUX-biased ENA shunt, local low defaults, gate resistor and STW switch pins. HOT WDI/WDO and the wire-AND rail RESET outputs join the retained trip fan-in. `audit.rs` passes 59 standalone/joined pin and mutation tests, including rail producer disconnects, ENA floating, watchdog WDI/WDO disconnects, abort bypass, feedback swap, and isolation bridge. `gate-enable-corners.md`, `HOT-WATCHDOG.md`, and `HOT-RAILS.md` record open electrical/timing proofs. | Prove coincident trip/reset and setup/hold corners; join actual HOT F2 and AUX overvoltage/fast-dip producers, UCC28180 PWM, PFC/reservoir, and electrical corner analysis. Verify both TPS3890 thresholds over selected part tolerances and input bias, CT timing, power-up/down, and rail ordering. The LVC output during intermediate HOT rail collapse, PMBT3904 saturation across temperature, UCC EN internal pull-up maximum, and AUX transient range remain unresolved. Source reset-good, interlock, STOP, heartbeat and protocol/relay GPIO producers remain external. The joined file is still partial and does not pass U4. |
| U5 | Fixed wire codec, interrupted-write journal, and receiver session core pass host tests. Disarm now requires PA6 arm, PF1 sample edge, then fresh PC0 Q readback before prep reset. Revalidation checks physical clear on a separate fresh sample after abort release. | AVR NVMCTRL/USART/timer/GPIO adapter, boot/pulse/fuse receipt, selected MCU target build and pin-state review. `avr-gcc` is not installed in this checkout. |
| U6 | The interface and source behavior are specified in the approved design. | Actual ESP source driver, cooker integration, host tests, output/WDI ownership and ESP-IDF build. `idf.py` is not on this shell's PATH. |
| U7 | No Rev38 native candidate exists. | Native schematic and PCB, BOM and footprint review, source/native parity, ERC/DRC, stackup and unit gates, authoritative acceptance receipt. Physical captures remain NOT RUN. |

Immediate construction order: finish U4's actual HOT F2 and AUX fault,
PWM and source paths; bind those pins to U5's AVR adapter and U6's source driver;
then export and audit U7. Update U1 with every selected component and
measured path. Do not promote the partial `isolation` build to a joined
Atopile PASS.
